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


def test_anyone_sees_every_recipe(client, stored) -> None:
    """A family cookbook: even a recipe its source marked private is open to read."""
    page = client.get("/").content.decode()
    assert "Geteilt" in page and "Geheim" in page
    assert "/add/" not in page, "no way in to adding for someone not signed in"
    assert "/accounts/login/" in page


def test_anyone_reads_a_recipe_and_its_chart_but_never_edits_it(client, stored) -> None:
    for row in stored.values():
        assert client.get(f"/r/{row.slug}/").status_code == 200
        assert client.get(f"/r/{row.slug}/chart/").status_code == 200
        assert client.get(f"/r/{row.slug}/edit/").status_code == 302, "to the sign-in page"
    assert client.get("/r/no-such-recipe/").status_code == 404


def test_reading_in_another_language_spends_nothing(client, stored) -> None:
    page = client.get(f"/r/{stored['public'].slug}/?lang=en").content.decode()
    assert not TranslationJob.objects.exists()
    assert "Translating" not in page


def test_the_title_says_who_added_it_and_every_ingredient_can_be_ticked(client, stored) -> None:
    page = client.get(f"/r/{stored['public'].slug}/?lang=de").content.decode()
    assert "by NX" in page, "the owner by their initials, never their address"
    assert "n@example.com" not in page
    assert page.count('type="checkbox" data-ingredient=') == 1


def _shared(settings, tmp_path, django_user_model, text: str):
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    owner = django_user_model.objects.create_user(username="nonna", email="n@example.com")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(f"---\ntitle: Schnecken\nlang: de\nvisibility: public\n---\n{text}")
    store.commit(recipe, author="nonna", created_at="2026-11-21T10:00:00")
    return project_recipe(store, recipe.id, owner)


def test_a_recipe_in_parts_lists_them_under_the_sources_headings(
    client, settings, tmp_path, django_user_model
) -> None:
    row = _shared(
        settings,
        tmp_path,
        django_user_model,
        "= Teig\n\n@Mehl{500%g} kneten. => Teig\n\n"
        "= Guss\n\n@Puderzucker{80%g} rühren. => Guss\n\n"
        "=\n\nDen @&{Teig} backen und mit dem @&{Guss} bestreichen.\n",
    )
    page = client.get(f"/r/{row.slug}/?lang=de").content.decode()
    teig, guss = page.index(">Teig</h3>"), page.index(">Guss</h3>")
    assert teig < page.index("Mehl") < guss < page.index("Puderzucker")
    assert page.count(">Teig</h3>") == 2, "over its ingredients and over its step"
    assert 'data-ingredient="iuse_1_1"' in page, "a tick is keyed by its ingredient"


def test_a_steps_time_is_a_button_that_counts_it_down(
    client, settings, tmp_path, django_user_model
) -> None:
    row = _shared(settings, tmp_path, django_user_model, "@Mehl{500%g} ~{1%h} ruhen lassen.\n")
    page = client.get(f"/r/{row.slug}/?lang=de", HTTP_ACCEPT_LANGUAGE="de").content.decode()
    assert 'data-timer="act_1:0" data-seconds="3600" data-display="1 h"' in page
    assert 'aria-label="Timer für 1 h starten"' in page


def test_a_save_time_tip_stands_in_the_step_it_starts_at(
    client, settings, tmp_path, django_user_model
) -> None:
    row = _shared(
        settings,
        tmp_path,
        django_user_model,
        "@Zwiebel{1} schneiden. => Zwiebeln\n\n@Tomaten{4} würfeln. => Tomaten\n\n"
        "Die @&{Zwiebeln} mit den @&{Tomaten} kochen.\n",
    )
    page = client.get(f"/r/{row.slug}/?lang=de").content.decode()
    tip = page.index("Steps 1 and 2 don’t depend on each other")
    assert page.index("schneiden.") < tip < page.index("würfeln."), "inside step 1, not above"
    assert page.count("don’t depend on each other") == 1
