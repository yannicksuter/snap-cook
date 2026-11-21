# SPDX-License-Identifier: AGPL-3.0-or-later
"""snap-cook's admin pages: people, recipes, and recipes whose owner is gone.

Only for the addresses in ``SNAPCOOK_ADMIN_EMAILS`` (``AccessMiddleware``; others
get a 404, not a hint). Deliberately small: what running a family recipe site
needs, in the site's own look, instead of Django's generic admin.

People appear by their initials and a masked address (``accounts.identity``);
no page shows an address in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from accounts.identity import ARCHIVE_HANDLE, admin_emails, mask, normalize
from accounts.models import Profile
from catalog.models import Recipe as CatalogRecipe
from catalog.projection import project_recipe
from imports import sources
from imports.models import ImportJob
from snapcook_core.store import FilesystemStore


@dataclass(frozen=True)
class Person:
    pk: int
    initials: str
    email: str
    verified: bool
    google: bool
    admin: bool
    can_cook: bool
    recipes: int
    last_login: datetime | None
    joined: datetime
    is_you: bool


def people(request: HttpRequest) -> HttpResponse:
    """Everyone with an account: who, since when, last seen, and the cook switch."""
    admins = admin_emails()
    rows = (
        get_user_model()
        .objects.exclude(profile=None)
        .select_related("profile")
        .prefetch_related("emailaddress_set", "socialaccount_set")
        .order_by("-last_login", "-date_joined")
    )
    everyone = []
    for user in rows:
        addresses = list(user.emailaddress_set.all())
        verified = {normalize(address.email) for address in addresses if address.verified}
        if not addresses:
            continue  # made by a command, like the corpus curator: not a person
        everyone.append(
            Person(
                pk=user.pk,
                initials=user.profile.initials,
                email=mask(user.email or (addresses[0].email if addresses else "")),
                verified=bool(verified),
                google=any(a.provider == "google" for a in user.socialaccount_set.all()),
                admin=bool(verified & admins),
                can_cook=user.profile.can_cook,
                recipes=CatalogRecipe.objects.filter(owner=user).count(),
                last_login=user.last_login,
                joined=user.date_joined,
                is_you=user.pk == request.user.pk,
            )
        )
    return render(request, "backoffice/people.html", {"people": everyone, "section": "people"})


@require_POST
def set_cook(request: HttpRequest, pk: int) -> HttpResponse:
    """Switch on or off whether someone may add, change and translate recipes."""
    profile = Profile.objects.filter(user_id=pk).first()
    if profile is None:
        raise Http404
    profile.can_cook = request.POST.get("can_cook") == "1"
    profile.save(update_fields=["can_cook"])
    return redirect("backoffice:people")


@require_POST
def delete_person(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an account; their recipes go to the archive, owned by no one.

    Each recipe gets a version authored by ``archive`` (``RecipeStore.reassign``),
    so the store itself says it has no owner and a reindex keeps it out of the
    catalog, and so the person signing up again does not get it back by
    themselves. Their unsaved drafts go, with what they uploaded for them.
    """
    person = get_user_model().objects.filter(pk=pk).first()
    if person is None:
        raise Http404
    if person.pk == request.user.pk:
        messages.warning(request, _("You cannot delete yourself."))
        return redirect("backoffice:people")
    initials = getattr(getattr(person, "profile", None), "initials", "")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    now = _now()
    with transaction.atomic():
        for row in CatalogRecipe.objects.select_for_update().filter(owner=person):
            store.reassign(
                row.recipe_id, author=ARCHIVE_HANDLE, created_at=now, message="owner deleted"
            )
        for job in ImportJob.objects.filter(owner=person).exclude(status=ImportJob.Status.SAVED):
            job.delete_sources()
        person.delete()
    messages.success(request, _("%(initials)s was deleted.") % {"initials": initials})
    return redirect("backoffice:people")


@dataclass(frozen=True)
class Listed:
    recipe_id: str
    title: str
    slug: str
    owner: str
    public: bool
    original: str | None
    updated: datetime | str


def recipes(request: HttpRequest) -> HttpResponse:
    """Every recipe, and what it was read from, to read one again."""
    rows = CatalogRecipe.objects.select_related("owner__profile").order_by("-updated_at")
    listed = [
        Listed(
            recipe_id=row.recipe_id,
            title=row.title,
            slug=row.slug,
            owner=getattr(getattr(row.owner, "profile", None), "initials", ""),
            public=row.visibility == "public",
            original=_original(row.recipe_id, row.source_url),
            updated=row.updated_at,
        )
        for row in rows
    ]
    return render(request, "backoffice/recipes.html", {"recipes": listed, "section": "recipes"})


@require_POST
def read_again(request: HttpRequest, recipe_id: str) -> HttpResponse:
    """Read a recipe again from its kept original, into a draft to check and save.

    The draft is the admin's; saving it makes a new version of the recipe in its
    owner's name (``imports.views._save_again``). Reading spends API credit, so
    it is one recipe at a time, on purpose.
    """
    row = CatalogRecipe.objects.filter(recipe_id=recipe_id).first()
    if row is None:
        raise Http404
    kept = ImportJob.objects.filter(recipe_id=recipe_id).order_by("-created_at").first()
    url = (kept.source_url if kept else "") or row.source_url
    kind = sources.original_kind(sources.root() / recipe_id)
    if kind is None and not url:
        messages.warning(request, _("Nothing of this recipe’s original was kept."))
        return redirect("backoffice:recipes")
    job = ImportJob.objects.create(
        owner=request.user,
        kind={"files": ImportJob.Kind.FILES, "text": ImportJob.Kind.TEXT}.get(
            kind or "", ImportJob.Kind.PAGE
        ),
        source_url=url,
        replaces=recipe_id,
    )
    transaction.on_commit(lambda: async_task("imports.tasks.read_recipe", str(job.pk)))
    return redirect("imports:status", job.pk)


@dataclass(frozen=True)
class Archived:
    recipe_id: str
    title: str
    since: str
    original: str | None


def archive(request: HttpRequest) -> HttpResponse:
    """Recipes in the store that no account owns, to give to someone."""
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    owned = set(CatalogRecipe.objects.values_list("recipe_id", flat=True))
    archived = []
    for recipe_id in store.list_recipe_ids():
        if recipe_id in owned:
            continue
        head = store.head(recipe_id)
        if head is None:
            continue
        title, _lang = head.recipe.title.resolve(head.recipe.source_lang)
        archived.append(
            Archived(
                recipe_id=recipe_id,
                title=title,
                since=head.created_at[:10],
                original=_original(recipe_id, ""),
            )
        )
    cooks = (
        get_user_model()
        .objects.filter(emailaddress__verified=True)
        .select_related("profile")
        .distinct()
        .order_by("profile__initials")
    )
    context = {"archived": archived, "people": cooks, "section": "archive"}
    return render(request, "backoffice/archive.html", context)


@require_POST
def assign(request: HttpRequest, recipe_id: str) -> HttpResponse:
    """Give an archived recipe to someone: it is theirs, and in the catalog, again."""
    person = (
        get_user_model()
        .objects.filter(pk=request.POST.get("person"), emailaddress__verified=True)
        .select_related("profile")
        .first()
    )
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    if person is None or store.head(recipe_id) is None:
        raise Http404
    if CatalogRecipe.objects.filter(recipe_id=recipe_id).exists():
        return redirect("backoffice:archive")  # someone was quicker
    store.reassign(recipe_id, author=person.get_username(), created_at=_now(), message="assigned")
    row = project_recipe(store, recipe_id, person)
    messages.success(
        request,
        _("“%(title)s” belongs to %(initials)s now.")
        % {"title": row.title, "initials": person.profile.initials},
    )
    return redirect("backoffice:archive")


def _original(recipe_id: str, url: str) -> str | None:
    """What reading again would use: a kept original, else the link, else nothing."""
    kind = sources.original_kind(Path(sources.root()) / recipe_id)
    if kind is not None:
        return kind
    return "link" if url else None


def _now() -> str:
    return timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
