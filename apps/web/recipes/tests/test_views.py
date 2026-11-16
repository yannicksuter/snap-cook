# SPDX-License-Identifier: AGPL-3.0-or-later
"""The recipe list and the recipe page, as a reader uses them.

Covers what the redesign promises: amounts follow the servings stepper, the
step structure is put into words, and the interface and the recipe follow the
reader's language, from their settings or else from their browser.
"""

from __future__ import annotations

import pytest

from accounts.models import UserPreferences
from catalog.projection import project_store
from snapcook_core.store import FilesystemStore
from snapcook_core.testing import corpus_recipes

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(tmp_path, settings, django_user_model):
    """The corpus, committed to a scratch store and projected into the catalog."""
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    curator = django_user_model.objects.create_user(
        username="curator", email="curator@snap-cook.local"
    )
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    for recipe in corpus_recipes():
        store.commit(recipe, author="curator", created_at="2026-07-20T12:00:00", message="seed")
    project_store(store, lambda author: curator if author == "curator" else None)


@pytest.fixture
def cook(client, django_user_model):
    user = django_user_model.objects.create_user(username="cook", email="cook@example.com")
    client.force_login(user)
    return user


def _page(client, url: str, **headers) -> str:
    response = client.get(url, **headers)
    assert response.status_code == 200
    return response.content.decode()


# -- the list -------------------------------------------------------------------


def test_the_list_shows_every_visible_recipe(seeded, cook, client) -> None:
    page = _page(client, "/")
    assert "6 recipes" in page
    for title in ("Tomato sauce", "Pancakes", "Rösti"):
        assert title in page


def test_search_narrows_the_list(seeded, cook, client) -> None:
    page = _page(client, "/?q=tomato")
    assert "Tomato sauce" in page
    assert "Pancakes" not in page
    assert "1 recipe" in page


def test_a_search_without_matches_says_so(seeded, cook, client) -> None:
    page = _page(client, "/?q=lasagne")
    assert "No recipe matches “lasagne”." in page
    assert "Show all recipes" in page


# -- the recipe page --------------------------------------------------------------


def test_a_recipe_opens_at_the_servings_it_was_written_for(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/")
    assert "for 4 servings" in page
    assert "30 ml" in page


def test_servings_scale_every_amount(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/?servings=8")
    assert "for 8 servings" in page
    assert "60 ml" in page
    assert "Warm 60 ml olive oil" in page, "amounts inside the steps scale too"


@pytest.mark.parametrize(("asked", "shown"), [("0", "for 1 serving"), ("lots", "for 4 servings")])
def test_unusable_servings_fall_back(seeded, cook, client, asked: str, shown: str) -> None:
    assert shown in _page(client, f"/r/tomato-sauce/?servings={asked}")


def test_the_stepper_links_to_one_more_and_one_fewer(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/")
    assert "servings=3" in page
    assert "servings=5" in page


def test_the_structure_is_put_into_words(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/")
    assert "Steps 1 and 2 don’t depend on each other" in page
    assert "Uses what you made in steps 1 and 2." in page


def test_a_linear_recipe_gets_no_structure_hints(seeded, cook, client) -> None:
    page = _page(client, "/r/pancakes/")
    assert "don’t depend on each other" not in page
    assert "Uses what you made" not in page


def test_htmx_gets_only_the_fragment(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/?servings=2", HTTP_HX_REQUEST="true")
    assert "<html" not in page
    assert "for 2 servings" in page


# -- languages and units ------------------------------------------------------------


def test_the_saved_language_sets_the_interface(seeded, cook, client) -> None:
    UserPreferences.objects.create(user=cook, language="de")
    page = _page(client, "/")
    assert '<html lang="de"' in page
    assert "Rezepte" in page
    assert "6 Rezepte" in page


def test_without_saved_settings_the_browser_decides(seeded, cook, client) -> None:
    page = _page(client, "/", HTTP_ACCEPT_LANGUAGE="de-CH,de;q=0.9,en;q=0.5")
    assert '<html lang="de"' in page


def test_the_saved_language_outranks_the_browser(seeded, cook, client) -> None:
    UserPreferences.objects.create(user=cook, language="en")
    page = _page(client, "/", HTTP_ACCEPT_LANGUAGE="de")
    assert '<html lang="en"' in page


def test_recipes_open_in_the_reader_language(seeded, cook, client) -> None:
    UserPreferences.objects.create(user=cook, language="de")
    page = _page(client, "/r/rosti/")
    assert "Zutaten" in page
    assert "Reiben Sie" in page


def test_one_recipe_can_be_read_in_another_language(seeded, cook, client) -> None:
    """The link changes the recipe's language for this view, not the interface's."""
    page = _page(client, "/r/rosti/?lang=de")
    assert "Reiben Sie" in page
    assert "Ingredients" in page
    assert "Show in English" in page


def test_units_follow_the_saved_settings(seeded, cook, client) -> None:
    UserPreferences.objects.create(user=cook, unit_system="us")
    page = _page(client, "/r/tomato-sauce/")
    assert "Show in grams and millilitres" in page
    assert "30 ml" not in page
