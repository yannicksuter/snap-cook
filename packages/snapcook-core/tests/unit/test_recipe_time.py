# SPDX-License-Identifier: Apache-2.0
"""How long a recipe takes: as its source states it, or at least as its timers add up."""

from __future__ import annotations

import pytest

from snapcook_core.canonical.encode import to_canonical_doc
from snapcook_core.cooklang import parse_cook, print_cook
from snapcook_core.durations import minutes_text, parse_minutes
from snapcook_core.importing import read_draft
from snapcook_core.render import RenderOptions, build_render_model


@pytest.mark.parametrize(
    ("written", "minutes"),
    [
        ("25 Min", 25),
        ("2 Std. 10", 130),
        ("1 h 30 min", 90),
        ("1.5 h", 90),
        ("1,5 Stunden", 90),
        ("90", 90),
        (45, 45),
        ("30-40 min", 40),
        ("", None),
        (None, None),
        ("eine Weile", None),
    ],
)
def test_times_are_read_as_people_write_them(written, minutes) -> None:
    assert parse_minutes(written) == minutes


@pytest.mark.parametrize(("minutes", "text"), [(25, "25 min"), (120, "2 h"), (130, "2 h 10 min")])
def test_times_are_written_one_way(minutes, text) -> None:
    assert minutes_text(minutes) == text


_STATED = """---
title: Käsekuchen
prep time: 25 Min
total time: 2 Std. 10
lang: de
---
Bei ^conventional{175%C} ~{55%min} backen.
"""


def test_stated_times_survive_printing_and_reading_again() -> None:
    recipe = parse_cook(_STATED)
    assert (recipe.time.prep, recipe.time.total, recipe.time.cook) == (25, 130, None)
    printed = print_cook(recipe)
    assert "prep time: 25 min\ntotal time: 2 h 10 min\n" in printed
    assert print_cook(parse_cook(printed)) == printed


def test_a_stated_total_is_shown_as_stated() -> None:
    time = build_render_model(parse_cook(_STATED), RenderOptions(lang="de")).time
    assert (time.total, time.at_least, time.prep) == ("2 h 10 min", False, "25 min")


def test_without_a_stated_total_the_longest_chain_of_timers_is_a_lower_bound() -> None:
    # A base that chills 30 min while a filling rests 10, then 55 min in the oven:
    # the two run side by side, so the chain is 30 + 55, not 30 + 10 + 55.
    recipe = parse_cook(
        "---\ntitle: T\nlang: de\n---\n"
        "@Mehl{100%g} kneten und ~{30%min} kühlen. => Boden\n\n"
        "@Quark{500%g} rühren und ~{10%min} ruhen lassen. => Masse\n\n"
        "Die @&{Masse} auf den @&{Boden} geben und ~{55%min} backen.\n"
    )
    time = build_render_model(recipe, RenderOptions(lang="de")).time
    assert (time.total, time.at_least) == ("1 h 25 min", True)


def test_a_recipe_without_times_or_timers_says_nothing() -> None:
    recipe = parse_cook("---\ntitle: T\nlang: de\n---\n@Salz{1%g} streuen.\n")
    assert build_render_model(recipe, RenderOptions(lang="de")).time is None
    assert "time" not in to_canonical_doc(recipe)


def test_an_import_keeps_the_times_the_source_states() -> None:
    draft = read_draft(_STATED)
    assert draft.recipe is not None
    assert (draft.recipe.time.prep, draft.recipe.time.total) == (25, 130)


def test_the_oven_settings_are_listed_once_each() -> None:
    recipe = parse_cook(
        "---\ntitle: T\nlang: de\n---\n"
        "Bei ^conventional{175%C} (^fan{155%C}) ~{20%min} vorbacken.\n\n"
        "Bei ^conventional{175%C} ~{30%min} fertig backen.\n"
    )
    oven = build_render_model(recipe, RenderOptions(lang="de")).oven
    assert [(t.display, t.mode) for t in oven] == [
        ("175 °C Ober-/Unterhitze", "conventional"),
        ("155 °C Umluft", "fan"),
    ]
