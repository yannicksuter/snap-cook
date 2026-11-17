# SPDX-License-Identifier: AGPL-3.0-or-later
"""The owner changes a saved recipe: a new version of the same recipe.

The real path end to end: the page, the form, ``revise``, the commit to a
scratch store and the projection. Only the owner may edit, even where others
may read.
"""

from __future__ import annotations

import pytest

from catalog.projection import project_recipe
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore
from snapcook_core.translating import pending_pieces
from translations.models import TranslationJob
from translations.tasks import translate_recipe

pytestmark = pytest.mark.django_db

_KAESEKUCHEN = """---
title: Käsekuchen
servings: 12
visibility: public
lang: de
---
@Magerquark{1%kg} und @Zucker{75%g} glatt rühren.

Bei ^conventional{175%C} (^fan{155%C}) ~{55%min} backen.
"""


@pytest.fixture
def owner(client, django_user_model):
    user = django_user_model.objects.create_user(username="nonna", email="nonna@example.com")
    client.force_login(user)
    return user


@pytest.fixture
def stored(settings, tmp_path, owner):
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_KAESEKUCHEN)
    store.commit(recipe, author="nonna", created_at="2026-11-17T20:00:00", origin="imported")
    return store, project_recipe(store, recipe.id, owner)


def _save(client, row, **changes):
    page = client.get(f"/r/{row.slug}/edit/").content.decode()
    assert "@Zucker{75%g}" in page
    data = {
        "title": "Käsekuchen",
        "description": "",
        "servings": "12",
        "cooklang": _KAESEKUCHEN.replace("visibility: public\n", ""),
        "action": "save",
    }
    data.update(changes)
    return client.post(f"/r/{row.slug}/edit/", data)


def test_only_the_owner_is_offered_edit(stored, owner, client, django_user_model) -> None:
    _store, row = stored
    assert f'href="/r/{row.slug}/edit/"' in client.get(f"/r/{row.slug}/").content.decode()

    other = django_user_model.objects.create_user(username="cook", email="cook@example.com")
    client.force_login(other)
    page = client.get(f"/r/{row.slug}/").content.decode()
    assert "Käsekuchen" in page
    assert f'href="/r/{row.slug}/edit/"' not in page
    assert client.get(f"/r/{row.slug}/edit/").status_code == 404


def test_saving_makes_a_new_version_of_the_same_recipe(stored, owner, client) -> None:
    store, row = stored
    text = _KAESEKUCHEN.replace("visibility: public\n", "").replace("75%g", "80%g")
    response = _save(client, row, cooklang=text)
    assert response["Location"] == f"/r/{row.slug}/"

    head = store.head(row.recipe_id)
    assert len(store.history(row.recipe_id)) == 2
    assert (head.author, head.origin, head.message) == ("nonna", "authored", "edit")
    assert (head.recipe.id, head.recipe.visibility) == (row.recipe_id, "public")
    page = client.get(response["Location"]).content.decode()
    assert "Saved." in page
    assert "80 g" in page


def test_text_that_cannot_be_read_is_not_saved(stored, owner, client) -> None:
    store, row = stored
    # Without a single step there is no recipe; the fields cannot make one up.
    page = _save(client, row, cooklang="---\ntitle: Käsekuchen\n---\n").content.decode()
    assert "This text cannot be read" in page
    assert len(store.history(row.recipe_id)) == 1


def test_an_edit_keeps_the_translations_of_what_did_not_change(
    stored, owner, client, settings
) -> None:
    store, row = stored
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    job = TranslationJob.objects.create(
        recipe_id=row.recipe_id, lang="en", from_version=store.head(row.recipe_id).version_id
    )
    translate_recipe(str(job.pk))
    assert pending_pieces(store.head(row.recipe_id).recipe, "en") == []

    text = _KAESEKUCHEN.replace("visibility: public\n", "").replace("glatt", "cremig")
    _save(client, row, cooklang=text)
    pending = pending_pieces(store.head(row.recipe_id).recipe, "en")
    assert [piece.text for piece in pending] == ["⟦1⟧ und ⟦2⟧ cremig rühren."]
