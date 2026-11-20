# SPDX-License-Identifier: AGPL-3.0-or-later
"""The owner deletes a recipe: gone from the catalog, moved aside in the store.

Only the owner may, and only by a POST. A full reindex must not bring it back,
because the store is what the catalog is rebuilt from. What it was imported
from goes too, as when a draft is deleted.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from catalog.models import Recipe
from catalog.projection import project_recipe
from imports.models import ImportJob
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore
from translations import tasks
from translations.models import TranslationJob

pytestmark = pytest.mark.django_db

_RECIPE = """---
title: Käsekuchen
servings: 12
visibility: public
lang: de
---
@Magerquark{1%kg} und @Zucker{75%g} glatt rühren.
"""


@pytest.fixture
def owner(client, django_user_model):
    user = django_user_model.objects.create_user(username="nonna", email="nonna@example.com")
    client.force_login(user)
    return user


@pytest.fixture
def stored(settings, tmp_path, owner):
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "sources"
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_RECIPE)
    store.commit(recipe, author="nonna", created_at="2026-11-20T20:00:00", origin="imported")
    return store, project_recipe(store, recipe.id, owner)


def test_the_owner_finds_delete_at_the_end_of_edit(stored, client) -> None:
    _store, row = stored
    page = client.get(f"/r/{row.slug}/edit/").content.decode()
    assert f'action="/r/{row.slug}/delete/"' in page
    assert "/delete/" not in client.get(f"/r/{row.slug}/").content.decode(), "no menu on the recipe"


def test_deleting_takes_it_out_of_the_catalog_and_the_store(stored, client) -> None:
    store, row = stored
    response = client.post(f"/r/{row.slug}/delete/")
    assert response["Location"] == "/"
    assert not Recipe.objects.filter(recipe_id=row.recipe_id).exists()
    assert store.list_recipe_ids() == []
    assert client.get(f"/r/{row.slug}/").status_code == 404
    assert "“Käsekuchen” was deleted." in client.get("/").content.decode()

    call_command("reindex", "--full", "--yes")
    assert not Recipe.objects.exists(), "a rebuild from the store must not bring it back"


def test_what_it_was_imported_from_goes_with_it(stored, owner, client) -> None:
    _store, row = stored
    job = ImportJob.objects.create(
        owner=owner, kind="files", status="saved", recipe_slug=row.slug, recipe_id=row.recipe_id
    )
    job.source_dir().mkdir(parents=True)
    (job.source_dir() / "1.jpg").write_bytes(b"photo")
    other = ImportJob.objects.create(owner=owner, kind="text", source_text="another recipe")

    client.post(f"/r/{row.slug}/delete/")
    assert not ImportJob.objects.filter(pk=job.pk).exists()
    assert not job.source_dir().exists()
    assert ImportJob.objects.filter(pk=other.pk).exists()


def test_only_the_owner_may_delete(stored, client, django_user_model) -> None:
    store, row = stored
    reader = django_user_model.objects.create_user(username="cook", email="cook@example.com")
    client.force_login(reader)
    assert "Käsekuchen" in client.get(f"/r/{row.slug}/").content.decode()
    assert client.post(f"/r/{row.slug}/delete/").status_code == 404
    assert store.list_recipe_ids() == [row.recipe_id]
    assert Recipe.objects.filter(pk=row.pk).exists()


def test_a_link_alone_deletes_nothing(stored, client) -> None:
    store, row = stored
    assert client.get(f"/r/{row.slug}/delete/").status_code == 405
    assert store.list_recipe_ids() == [row.recipe_id]


def test_a_translation_answered_after_the_delete_does_not_bring_it_back(
    stored, client, monkeypatch, settings
) -> None:
    """The model answers after the owner deleted: committing would recreate the recipe."""
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    store, row = stored
    job = TranslationJob.objects.create(recipe_id=row.recipe_id, lang="en")
    model = tasks.translator()

    class DeletedMeanwhile:
        def translate(self, request):
            client.post(f"/r/{row.slug}/delete/")
            return model.translate(request)

    monkeypatch.setattr(tasks, "translator", DeletedMeanwhile)
    tasks.translate_recipe(str(job.pk))
    job.refresh_from_db()
    assert (job.status, job.problem) == ("failed", "gone")
    assert store.list_recipe_ids() == []
