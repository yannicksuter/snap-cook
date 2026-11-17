# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-rendered recipe views.

Presentation only. These views hold no domain logic: they call
``snapcook_core`` for rendering and ``catalog.access`` for visibility, then
build a context dict. If domain logic appears here, it is a bug -- move it into
the core package where a Flutter client and the API can reach it too.

The detail view is the thesis made interactive: one stored recipe, re-rendered
on the fly for the reader's language, unit system and number of servings, with
the method drawn as a chart beside it. The servings stepper is plain links that
HTMX turns into fragment swaps, so the page still works without JavaScript.

Language and units come from the reader's settings (``request.LANGUAGE_CODE``
already holds the saved language; see ``accounts.middleware``); a recipe in
another language is translated for them (``translations``). The query string
still overrides both for one view -- a shared link, the chart's print page --
without changing anything stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from ruamel.yaml import YAMLError

from catalog.access import get_recipe_or_404, visible_recipes
from catalog.models import Recipe as CatalogRecipe
from catalog.projection import project_recipe
from imports.forms import DetailsForm
from imports.models import ImportJob
from snapcook_core.cooklang.frontmatter import parse_document
from snapcook_core.editing import revise, text_for_editing
from snapcook_core.errors import CODE_NO_DENSITY, CODE_SCALING_MANUAL, CODE_UNIT_UNRESOLVED
from snapcook_core.importing import with_details
from snapcook_core.render import RenderOptions, build_render_model, render_mermaid
from snapcook_core.store import FilesystemStore
from translations.jobs import progress_for

_SYSTEMS = ("metric", "us")
_MAX_SERVINGS = 100
_MAX_SCALE = Decimal(100)
# For a recipe that does not say how many it serves, the stepper walks these.
_SCALE_STEPS = (Decimal("0.5"), Decimal(1), Decimal("1.5"), Decimal(2), Decimal(3), Decimal(4))


@dataclass(frozen=True)
class _View:
    """What this reader asked for, and the links that change one thing of it."""

    lang: str
    system: str
    scale: Decimal
    servings: int | None
    amount: str
    fewer: str
    more: str
    here: str
    """This recipe page, for this same view."""
    print_chart: str
    """The chart alone, for this same view, printing itself once drawn."""


def index(request: HttpRequest) -> HttpResponse:
    """Recipe list, optionally filtered by a search in the title, description or ingredients.

    Starts from ``visible_recipes`` rather than ``Recipe.objects`` -- see the
    warning in catalog/access.py.
    """
    query = request.GET.get("q", "").strip()
    recipes = visible_recipes(request.user).select_related("owner")
    if query:
        recipes = recipes.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(search_terms__icontains=query)
        )
    # The reader's own unsaved imports: where a draft waits after they left the
    # page that was reading it.
    drafts = ImportJob.objects.filter(owner=request.user).exclude(status=ImportJob.Status.SAVED)
    context = {"recipes": recipes[:50], "query": query, "drafts": drafts[:10]}
    return render(request, "recipes/index.html", context)


def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One recipe, rendered for the reader's language, units and servings."""
    catalog_recipe, head, view, model = _rendered(request, slug)
    recipe = head.recipe
    context = {
        "recipe": catalog_recipe,
        "model": model,
        "view": view,
        "mermaid": render_mermaid(model),
        "notes": _notes(model, view),
        # Shown in another language, a recipe is translated once, in the worker.
        "translation": progress_for(
            request.user, catalog_recipe.recipe_id, recipe, head.version_id, view.lang
        ),
    }
    is_htmx = request.headers.get("HX-Request")
    template = "recipes/_render.html" if is_htmx else "recipes/detail.html"
    return render(request, template, context)


def _notes(model, view: _View) -> list[str]:
    """What the core's diagnostics mean for a cook: a sentence each, at most once.

    The core records every value it would not scale or could not convert, in
    English, for whoever maintains the recipe. A cook needs to hear only about
    what they just did -- changed the amount, or chose cups and ounces -- once,
    in their own language. Everything else stays out of the page.
    """
    codes = {issue.code for issue in model.warnings}
    notes = []
    if CODE_SCALING_MANUAL in codes:
        notes.append(
            _(
                "Times and oven temperatures stay as in the recipe. "
                "Check them when you cook more or less."
            )
        )
    if view.system == "us" and codes & {CODE_UNIT_UNRESOLVED, CODE_NO_DENSITY}:
        notes.append(
            _("Some amounts cannot be shown in cups and ounces, so they stay as in the recipe.")
        )
    return notes


def chart(request: HttpRequest, slug: str) -> HttpResponse:
    """The chart alone, to print: the same language, units and servings as the page."""
    catalog_recipe, _head, view, model = _rendered(request, slug)
    context = {
        "recipe": catalog_recipe,
        "model": model,
        "view": view,
        "mermaid": render_mermaid(model),
        "print_now": request.GET.get("print") == "1",
    }
    return render(request, "recipes/chart.html", context)


@require_http_methods(["GET", "POST"])
def edit(request: HttpRequest, slug: str) -> HttpResponse:
    """The owner changes the recipe as text; saving makes a new version of it.

    The text is the recipe in its own language. ``revise`` keeps what text
    cannot hold -- the id, who may see it, its source, and the translations of
    every string that did not change -- and the commit is in the owner's name,
    as every version must be: ``reindex`` takes the owner from the latest one.
    """
    row = get_recipe_or_404(request.user, slug)
    if row.owner_id != request.user.pk:
        raise Http404  # someone else's recipe, shared with this reader: not theirs to change
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    head = store.head(row.recipe_id)
    if head is None:
        raise Http404

    if request.method == "POST":
        form = DetailsForm(request.POST)
        text = ""
        if form.is_valid():
            data = form.cleaned_data
            text = with_details(
                data["cooklang"],
                title=data["title"],
                description=data["description"],
                servings=data["servings"],
            )
    else:
        text = text_for_editing(head.recipe)
        form = DetailsForm(initial=_edit_fields(text))

    revision = revise(head.recipe, text) if text else None
    if request.method == "POST" and request.POST.get("action") == "save" and revision:
        if revision.recipe is not None:
            with transaction.atomic():
                # One commit at a time per recipe, against what HEAD is now: a
                # translation may have landed while this page was open.
                owner = CatalogRecipe.objects.select_for_update().get(pk=row.pk).owner
                head = store.head(row.recipe_id)
                revision = revise(head.recipe, text)
                if revision.recipe is not None:
                    store.commit(
                        revision.recipe,
                        author=head.author,
                        created_at=timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
                        message="edit",
                        origin="authored",
                    )
                    row = project_recipe(store, row.recipe_id, owner)
            if revision.recipe is not None:
                messages.success(request, _("Saved."))
                return redirect("recipes:detail", row.slug)

    model = None
    if revision is not None and revision.recipe is not None:
        saved = getattr(getattr(request.user, "preferences", None), "unit_system", "metric")
        options = RenderOptions(
            lang=revision.recipe.source_lang, system=saved if saved in _SYSTEMS else "metric"
        )
        model = build_render_model(revision.recipe, options)
    problem = ""
    if revision is not None and revision.recipe is None:
        problem = _("This text cannot be read: %(detail)s") % {"detail": revision.detail}
    context = {"recipe": row, "form": form, "model": model, "problem": problem}
    return render(request, "recipes/edit.html", context)


def _edit_fields(text: str) -> dict:
    try:
        front, _body = parse_document(text)
    except YAMLError:
        front = {}
    return {
        "title": front.get("title", ""),
        "description": front.get("description", ""),
        "servings": front.get("servings"),
        "cooklang": text,
    }


def _rendered(request: HttpRequest, slug: str):
    """The visible recipe, its HEAD, the reader's view of it, and that view rendered."""
    catalog_recipe = get_recipe_or_404(request.user, slug)
    head = FilesystemStore(settings.SNAPCOOK_STORE_DIR).head(catalog_recipe.recipe_id)
    if head is None:
        raise Http404
    view = _view_from_request(request, slug, head.recipe.servings)
    model = build_render_model(
        head.recipe, RenderOptions(lang=view.lang, system=view.system, scale=view.scale)
    )
    return catalog_recipe, head, view, model


def _view_from_request(request: HttpRequest, slug: str, base_servings: int | None) -> _View:
    languages = dict(settings.LANGUAGES)
    lang = request.GET.get("lang", "")
    if lang not in languages:
        lang = request.LANGUAGE_CODE if request.LANGUAGE_CODE in languages else "en"

    system = request.GET.get("system", "")
    if system not in _SYSTEMS:
        saved = getattr(getattr(request.user, "preferences", None), "unit_system", "metric")
        system = saved if saved in _SYSTEMS else "metric"

    def url(route: str = "recipes:detail", **changes: object) -> str:
        params: dict[str, object] = {"lang": lang, "system": system}
        if base_servings:
            params["servings"] = servings
        else:
            params["scale"] = _scale_str(scale)
        params.update(changes)
        return f"{reverse(route, args=[slug])}?{urlencode(params)}"

    if base_servings:
        servings = _parse_servings(request.GET.get("servings"), base_servings)
        scale = Decimal(servings) / Decimal(base_servings)
        amount = str(servings)
        fewer = url(servings=servings - 1) if servings > 1 else ""
        more = url(servings=servings + 1) if servings < _MAX_SERVINGS else ""
    else:
        servings = None
        scale = _parse_scale(request.GET.get("scale"))
        amount = f"{_scale_str(scale)}×"
        smaller = [step for step in _SCALE_STEPS if step < scale]
        larger = [step for step in _SCALE_STEPS if step > scale]
        fewer = url(scale=_scale_str(smaller[-1])) if smaller else ""
        more = url(scale=_scale_str(larger[0])) if larger else ""

    return _View(
        lang=lang,
        system=system,
        scale=scale,
        servings=servings,
        amount=amount,
        fewer=fewer,
        more=more,
        here=url(),
        print_chart=url("recipes:chart", print=1),
    )


def _parse_servings(raw: str | None, base: int) -> int:
    try:
        value = int(raw) if raw else base
    except ValueError:
        return base
    return min(max(value, 1), _MAX_SERVINGS)


def _parse_scale(raw: str | None) -> Decimal:
    if not raw:
        return Decimal(1)
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(1)
    if not value.is_finite() or value <= 0:
        return Decimal(1)
    return min(value, _MAX_SCALE)


def _scale_str(scale: Decimal) -> str:
    if scale == scale.to_integral_value():
        return str(int(scale))
    return format(scale.normalize(), "f")
