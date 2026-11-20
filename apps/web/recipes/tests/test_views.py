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


def test_a_search_finds_a_recipe_by_its_ingredients_in_any_language(seeded, cook, client) -> None:
    # Rösti is written in English with German translations; the potato is in the
    # registry with its name in both.
    for word in ("potato", "Kartoffel", "butter"):
        page = _page(client, f"/?q={word}")
        assert "/r/rosti/" in page, word
    assert "/r/rosti/" not in _page(client, "/?q=tomato")


def test_a_search_without_matches_says_so(seeded, cook, client) -> None:
    page = _page(client, "/?q=lasagne")
    assert "No recipe matches “lasagne”." in page
    assert "Show all recipes" in page


# -- the recipe page --------------------------------------------------------------


def test_a_recipe_opens_at_the_servings_it_was_written_for(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/")
    assert "for 4 servings" in page
    assert "2 tbsp" in page  # as the recipe says it, not 30 ml


def test_servings_scale_every_amount(seeded, cook, client) -> None:
    page = _page(client, "/r/tomato-sauce/?servings=8")
    assert "for 8 servings" in page
    assert "4 tbsp" in page
    assert "Warm 4 tbsp olive oil" in page, "amounts inside the steps scale too"


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
    """A shared link changes the recipe's language for this view, not the interface's."""
    page = _page(client, "/r/rosti/?lang=de")
    assert "Reiben Sie" in page
    assert "Ingredients" in page


def test_units_follow_the_saved_settings(seeded, cook, client) -> None:
    UserPreferences.objects.create(user=cook, unit_system="us")
    page = _page(client, "/r/rosti/")
    assert "800 g" not in page
    assert " lb" in page or " oz" in page


# -- the chart --------------------------------------------------------------------


def test_the_recipe_ends_with_its_chart_not_a_list_of_options(seeded, cook, client) -> None:
    page = _page(client, "/r/rosti/")
    assert "At a glance" in page
    assert '<pre class="mermaid">' in page
    assert 'id="more"' not in page
    assert "Show as plain text" not in page
    assert "/r/rosti/chart/?lang=en&amp;system=metric&amp;servings=2&amp;print=1" in page


def test_the_chart_prints_on_a_page_of_its_own(seeded, cook, client) -> None:
    page = _page(client, "/r/rosti/chart/?lang=de&servings=4&print=1")
    assert "<h1" in page and "Rösti" in page
    assert "for 4 servings" in page
    # Escaped in the page; Mermaid reads the <pre>'s text, markup and all.
    assert "&lt;span class=qty&gt;1.5 kg&lt;/span&gt; Kartoffel" in page
    assert "chart:drawn" in page and "window.print()" in page
    assert 'href="/r/rosti/?lang=de&amp;system=metric&amp;servings=4"' in page
    assert "chart:drawn', () => window.print()" not in _page(client, "/r/rosti/chart/")


# -- notes ------------------------------------------------------------------------------


def test_changing_the_amount_says_once_that_times_stay(seeded, cook, client) -> None:
    assert "Times and oven temperatures stay" not in _page(client, "/r/rosti/")
    page = _page(client, "/r/rosti/?servings=3")
    assert page.count("Times and oven temperatures stay as in the recipe.") == 1
    assert "not scaled automatically" not in page
