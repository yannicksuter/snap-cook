# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project the authoritative file store into the Postgres catalog.

This is the one direction data flows: validate -> write file -> **project**. The
catalog is a cache, and every field it holds is derived here from a store version
record. If a field cannot be derived in this function, it does not belong in
`catalog` -- it belongs in `accounts` or `social`. That rule is what makes
`reindex --full` an executable proof rather than a hope.

Ownership is the one field that needs a second input: the store records an
`author` handle, and this maps it to a local `User`. The mapping is stable, so a
rebuild reproduces the same `owner_id`; a recipe whose author has no user row is
**skipped**, not guessed at, because inventing an owner would be a silent
authorization decision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from catalog.models import Recipe as CatalogRecipe
from catalog.models import RecipeVersion
from snapcook_core.schema.recipe import Recipe as CoreRecipe
from snapcook_core.store.base import RecipeStore, VersionRecord

__all__ = ["OwnerResolver", "project_recipe", "project_store"]

OwnerResolver = Callable[[str], object | None]


def _parse_dt(value: str) -> datetime:
    """Parse a store ISO timestamp into an aware UTC datetime.

    All stored times are UTC (a repo-wide rule), so a naive string is stamped
    UTC rather than guessed at from the server's local zone.
    """
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _unique_slug(recipe: CoreRecipe, title: str) -> str:
    """A stable, unique slug. Deterministic so a rebuild reproduces it.

    Falls back to the recipe id, never a random suffix or a counter, because a
    counter depends on projection order and would not survive a rebuild
    byte-identically.
    """
    base = slugify(title) or "recipe"
    clash = CatalogRecipe.objects.filter(slug=base).exclude(recipe_id=recipe.id).exists()
    if not clash:
        return base
    suffix = recipe.id.rsplit("_", 1)[-1][:8].lower()
    return f"{base}-{suffix}"


def project_recipe(store: RecipeStore, recipe_id: str, owner: object) -> CatalogRecipe:
    """Upsert one recipe and its full version history into the catalog."""
    history = store.history(recipe_id)
    head = history[0]
    recipe = head.recipe

    title, _ = recipe.title.resolve(recipe.source_lang)
    description = ""
    if recipe.description is not None:
        description, _ = recipe.description.resolve(recipe.source_lang)

    provenance = recipe.provenance

    row, _ = CatalogRecipe.objects.update_or_create(
        recipe_id=recipe.id,
        defaults={
            "slug": _unique_slug(recipe, title),
            "owner": owner,
            "title": title,
            "description": description,
            "lang": recipe.source_lang,
            "visibility": recipe.visibility,
            "license_spdx": provenance.license_spdx or "",
            "source_url": provenance.source_url or "",
            "tags": list(recipe.tags),
            "head_version_id": head.version_id,
            "head_content_hash": head.content_hash,
            "created_at": _parse_dt(history[-1].created_at),
            "updated_at": _parse_dt(head.created_at),
        },
    )

    _project_versions(row, history)
    return row


def _project_versions(row: CatalogRecipe, history: list[VersionRecord]) -> None:
    row.versions.all().delete()
    RecipeVersion.objects.bulk_create(
        RecipeVersion(
            recipe=row,
            version_id=version.version_id,
            content_hash=version.content_hash,
            parents=list(version.parents),
            origin=version.origin,
            author_key=version.author,
            message=version.message,
            created_at=_parse_dt(version.created_at),
        )
        for version in history
    )


def project_store(store: RecipeStore, owner_for: OwnerResolver) -> tuple[int, list[str]]:
    """Project every recipe in the store. Returns (projected count, skipped ids).

    A recipe whose author maps to no local user is skipped and reported, never
    projected with a fabricated owner.
    """
    projected = 0
    skipped: list[str] = []
    for recipe_id in store.list_recipe_ids():
        head = store.head(recipe_id)
        if head is None:
            continue
        owner = owner_for(head.author)
        if owner is None:
            skipped.append(recipe_id)
            continue
        project_recipe(store, recipe_id, owner)
        projected += 1
    return projected, skipped


def owner_resolver_from_db() -> OwnerResolver:
    """Resolve a store author handle to a local user, by username or email.

    Built once as a dict so projecting a whole store is not a query per recipe.
    """
    users = get_user_model().objects.all()
    by_key: dict[str, object] = {}
    for user in users:
        by_key[user.get_username()] = user
        if getattr(user, "email", ""):
            by_key.setdefault(user.email, user)
    return lambda author: by_key.get(author)
