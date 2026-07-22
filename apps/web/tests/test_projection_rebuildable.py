# SPDX-License-Identifier: AGPL-3.0-or-later
"""The projection is a cache: rebuilding it from files loses nothing.

This is the executable proof of the architecture's central claim. If
``reindex --full`` cannot reproduce the catalog byte-for-byte, then some field in
`catalog` is not derivable from the store, and "Postgres is a cache" has quietly
become false.

The test seeds the store, projects it, snapshots the meaningful columns, then
truncates and rebuilds and snapshots again. The two snapshots must be identical.
``indexed_at`` (an ``auto_now`` bookkeeping stamp) and the surrogate primary keys
are excluded, because they describe *when we rebuilt*, not *what the recipe is* --
including them would assert the clock is deterministic, which is not the claim.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from catalog.models import Recipe, RecipeVersion
from catalog.projection import project_store
from snapcook_core.store import FilesystemStore
from snapcook_core.testing import corpus_recipes

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _snapshot() -> tuple:
    recipes = [
        {
            "recipe_id": r.recipe_id,
            "slug": r.slug,
            "owner": r.owner_id,
            "title": r.title,
            "description": r.description,
            "lang": r.lang,
            "visibility": r.visibility,
            "license_spdx": r.license_spdx,
            "source_url": r.source_url,
            "tags": r.tags,
            "head_version_id": r.head_version_id,
            "head_content_hash": r.head_content_hash,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in Recipe.objects.order_by("recipe_id")
    ]
    versions = [
        {
            "recipe_id": v.recipe.recipe_id,
            "version_id": v.version_id,
            "content_hash": v.content_hash,
            "parents": v.parents,
            "origin": v.origin,
            "author_key": v.author_key,
            "message": v.message,
            "created_at": v.created_at.isoformat(),
        }
        for v in RecipeVersion.objects.order_by("recipe__recipe_id", "version_id")
    ]
    return (recipes, versions)


@pytest.fixture
def seeded_store(tmp_path, settings, django_user_model):
    """A store seeded with the whole corpus, projected once into the catalog."""
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    curator = django_user_model.objects.create_user(
        username="curator", email="curator@snap-cook.local"
    )
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    for recipe in corpus_recipes():
        store.commit(recipe, author="curator", created_at="2026-07-20T12:00:00", message="seed")
    project_store(store, lambda author: curator if author == "curator" else None)
    return store, curator


def test_all_corpus_recipes_are_projected(seeded_store) -> None:
    assert Recipe.objects.count() == len(corpus_recipes())
    assert RecipeVersion.objects.count() == len(corpus_recipes())


def test_rebuild_is_byte_identical(seeded_store) -> None:
    before = _snapshot()
    call_command("reindex", "--full", "--yes")
    after = _snapshot()
    assert before == after


def test_second_rebuild_is_also_identical(seeded_store) -> None:
    """Idempotent: truncate-and-rebuild twice lands in the same place."""
    call_command("reindex", "--full", "--yes")
    once = _snapshot()
    call_command("reindex", "--full", "--yes")
    assert _snapshot() == once


def test_reindex_only_touches_catalog(seeded_store, django_user_model) -> None:
    """Accounts survive a full reindex untouched -- the app boundary holds."""
    call_command("reindex", "--full", "--yes")
    assert django_user_model.objects.filter(username="curator").exists()


def test_head_matches_the_store(seeded_store) -> None:
    store, _ = seeded_store
    for recipe in corpus_recipes():
        row = Recipe.objects.get(recipe_id=recipe.id)
        assert row.head_content_hash == store.head(recipe.id).content_hash


def test_editing_a_recipe_then_reindexing_tracks_the_new_head(seeded_store, settings) -> None:
    store, curator = seeded_store
    recipe = corpus_recipes()[0]
    edited = recipe.model_copy(update={"servings": 8})
    store.commit(edited, author="curator", created_at="2026-07-21T09:00:00", message="bigger")

    call_command("reindex", "--full", "--yes")

    row = Recipe.objects.get(recipe_id=recipe.id)
    assert row.head_content_hash == store.head(recipe.id).content_hash
    assert row.versions.count() == 2
