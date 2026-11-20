# SPDX-License-Identifier: AGPL-3.0-or-later
"""The top of a recipe: how long it takes and how the oven is set, with its symbols."""

from __future__ import annotations

import pytest

from catalog.projection import project_recipe
from recipes.oven import oven_mask_css, oven_svg
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore

pytestmark = pytest.mark.django_db

_STATED = """---
title: Käsekuchen
prep time: 25 min
total time: 2 h 10 min
visibility: public
lang: de
---
Bei ^conventional{175%C} (^fan{155%C}) ~{55%min} backen.
"""


@pytest.fixture
def cook(client, django_user_model):
    user = django_user_model.objects.create_user(username="nonna", email="nonna@example.com")
    client.force_login(user)
    return user


def _page(settings, tmp_path, cook, client, text: str, path: str = "") -> str:
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(text)
    store.commit(recipe, author="nonna", created_at="2026-11-19T10:00:00")
    row = project_recipe(store, recipe.id, cook)
    return client.get(f"/r/{row.slug}/{path}?lang=de").content.decode()


def test_the_stated_times_and_oven_settings_come_first(settings, tmp_path, cook, client) -> None:
    page = _page(settings, tmp_path, cook, client, _STATED)
    assert "Ready in" in page and "2 h 10 min" in page
    assert "Hands-on" in page and "25 min" in page
    assert "Takes at least" not in page
    assert page.count('<rect x="3" y="3" width="18" height="18" rx="3.5"/>') >= 4  # facts + chips
    assert "175 °C Ober-/Unterhitze" in page and "155 °C Umluft" in page


def test_without_a_stated_total_the_timers_give_a_lower_bound(
    settings, tmp_path, cook, client
) -> None:
    text = _STATED.replace("prep time: 25 min\ntotal time: 2 h 10 min\n", "")
    page = _page(settings, tmp_path, cook, client, text)
    assert "Takes at least" in page and "55 min" in page
    assert "Ready in" not in page


def test_the_printed_chart_carries_the_facts_too(settings, tmp_path, cook, client) -> None:
    page = _page(settings, tmp_path, cook, client, _STATED, path="chart/")
    assert "Ready in" in page and "2 h 10 min" in page


@pytest.mark.parametrize(
    "mode",
    [
        "conventional",
        "top",
        "bottom",
        "fan",
        "hot_air",
        "fan_bottom",
        "fan_conventional",
        "grill",
        "fan_grill",
    ],
)
def test_every_oven_setting_has_a_symbol_on_the_page_and_in_the_chart(mode) -> None:
    assert oven_svg(mode).startswith("<svg ")
    assert f".nodeLabel .temp.m-{mode} {{ --icon: url(" in oven_mask_css()


def test_no_setting_no_symbol() -> None:
    assert oven_svg(None) == oven_svg("broil") == ""
