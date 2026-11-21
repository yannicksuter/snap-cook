# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading without an account: shared recipes, nothing private, nothing that costs."""

from __future__ import annotations

import pytest

from catalog.projection import project_recipe
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore
from translations.models import TranslationJob

pytestmark = pytest.mark.django_db


def _recipe(title: str, visibility: str) -> str:
    return f"""---
title: {title}
servings: 4
visibility: {visibility}
lang: de
---
@Quark{{500%g}} rühren.
"""


@pytest.fixture
def stored(settings, tmp_path, django_user_model):
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    owner = django_user_model.objects.create_user(username="nonna", email="n@example.com")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    rows = {}
    for title, visibility in (("Geteilt", "public"), ("Geheim", "private")):
        recipe = parse_cook(_recipe(title, visibility))
        store.commit(recipe, author="nonna", created_at="2026-11-21T10:00:00")
        rows[visibility] = project_recipe(store, recipe.id, owner)
    return rows


def test_anyone_sees_the_shared_recipes(client, stored) -> None:
    page = client.get("/").content.decode()
    assert "Geteilt" in page and "Geheim" not in page
    assert "/add/" not in page, "no way in to adding for someone not signed in"
    assert "/accounts/login/" in page


def test_anyone_reads_a_shared_recipe_and_its_chart(client, stored) -> None:
    slug = stored["public"].slug
    assert client.get(f"/r/{slug}/").status_code == 200
    assert client.get(f"/r/{slug}/chart/").status_code == 200
    assert client.get(f"/r/{stored['private'].slug}/").status_code == 404


def test_reading_in_another_language_spends_nothing(client, stored) -> None:
    page = client.get(f"/r/{stored['public'].slug}/?lang=en").content.decode()
    assert not TranslationJob.objects.exists()
    assert "Translating" not in page


def test_the_title_says_who_added_it_and_every_ingredient_can_be_ticked(client, stored) -> None:
    page = client.get(f"/r/{stored['public'].slug}/?lang=de").content.decode()
    assert "by NX" in page, "the owner by their initials, never their address"
    assert "n@example.com" not in page
    assert page.count('type="checkbox" data-ingredient=') == 1


def test_a_recipe_in_parts_lists_them_under_the_sources_headings(
    client, settings, tmp_path, django_user_model
) -> None:
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    owner = django_user_model.objects.create_user(username="nonna", email="n@example.com")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(
        "---\ntitle: Schnecken\nlang: de\nvisibility: public\n---\n"
        "= Teig\n\n@Mehl{500%g} kneten. => Teig\n\n"
        "= Guss\n\n@Puderzucker{80%g} rühren. => Guss\n\n"
        "=\n\nDen @&{Teig} backen und mit dem @&{Guss} bestreichen.\n"
    )
    store.commit(recipe, author="nonna", created_at="2026-11-21T10:00:00")
    row = project_recipe(store, recipe.id, owner)
    page = client.get(f"/r/{row.slug}/?lang=de").content.decode()
    teig, guss = page.index(">Teig</h3>"), page.index(">Guss</h3>")
    assert teig < page.index("Mehl") < guss < page.index("Puderzucker")
    assert page.count(">Teig</h3>") == 2, "over its ingredients and over its step"
    assert 'data-ingredient="iuse_1_1"' in page, "a tick is keyed by its ingredient"
