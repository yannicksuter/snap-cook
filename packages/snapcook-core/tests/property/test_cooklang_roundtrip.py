# SPDX-License-Identifier: Apache-2.0
"""Cooklang round-trip idempotence -- the authoring-format gate.

The printer and parser are only trustworthy as a pair if they are inverses. Two
properties pin that:

**Text idempotence.** ``print(parse(print(r))) == print(r)``. Once a recipe is in
canonical text form, parsing and reprinting must reproduce it exactly. This is
the primary gate: a drift here means the two halves disagree about the dialect.

**Semantic fidelity.** A parsed recipe renders the same step text as the
original in its source language. Ids and translations are not preserved by a
single-language projection, but what the reader *sees* must be.
"""

from __future__ import annotations

import pytest

from snapcook_core.cooklang import parse_cook, print_cook
from snapcook_core.render import RenderOptions, build_render_model
from snapcook_core.testing import corpus_recipes

pytestmark = pytest.mark.property


@pytest.mark.parametrize("recipe", corpus_recipes(), ids=lambda r: r.id)
def test_print_parse_print_is_idempotent(recipe) -> None:
    once = print_cook(recipe, recipe.source_lang)
    twice = print_cook(parse_cook(once), recipe.source_lang)
    assert once == twice


@pytest.mark.parametrize("recipe", corpus_recipes(), ids=lambda r: r.id)
def test_parsed_recipe_is_a_valid_graph(recipe) -> None:
    """Parsing lowers to a real graph: same number of steps, terminals exist."""
    parsed = parse_cook(print_cook(recipe, recipe.source_lang))
    assert len(parsed.actions) == len(recipe.actions)
    assert parsed.terminal_state_ids


@pytest.mark.parametrize("recipe", corpus_recipes(), ids=lambda r: r.id)
def test_parsed_recipe_renders_the_same_step_text(recipe) -> None:
    """What the reader sees survives the round trip through text."""
    lang = recipe.source_lang
    parsed = parse_cook(print_cook(recipe, lang))
    original = build_render_model(recipe, RenderOptions(lang=lang))
    reparsed = build_render_model(parsed, RenderOptions(lang=lang))
    assert [s.text for s in reparsed.steps] == [s.text for s in original.steps]


def test_round_trip_preserves_frontmatter() -> None:
    from snapcook_core.testing import get_recipe

    recipe = get_recipe("006-roesti")
    parsed = parse_cook(print_cook(recipe, "de"))
    assert parsed.source_lang == "de"
    assert parsed.title.values["de"] == "Rösti"
    assert parsed.servings == recipe.servings
    assert parsed.visibility == recipe.visibility
    assert parsed.tags == recipe.tags
