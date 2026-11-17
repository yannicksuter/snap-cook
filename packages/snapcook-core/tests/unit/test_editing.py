# SPDX-License-Identifier: Apache-2.0
"""Editing a saved recipe as text keeps it the same recipe, translations and all."""

from __future__ import annotations

from snapcook_core.cooklang import parse_cook
from snapcook_core.editing import revise, text_for_editing
from snapcook_core.render import RenderOptions, build_render_model
from snapcook_core.schema import Provenance
from snapcook_core.translating import Translated, apply_translation, pending_pieces

_KAESEKUCHEN = """---
title: Käsekuchen
lang: de
---
@Magerquark{1%kg} und @Zucker{75%g} glatt rühren.

Bei ^conventional{175%C} (^fan{155%C}) ~{55%min} backen.
"""


def _saved():
    """An imported, shared and fully translated recipe, as the store holds it."""
    recipe = parse_cook(_KAESEKUCHEN).model_copy(
        update={
            "visibility": "public",
            "provenance": Provenance(origin="imported", source_url="https://example.com/k"),
        }
    )
    done = [Translated(piece, f"EN {piece.text}") for piece in pending_pieces(recipe, "en")]
    translated, refused = apply_translation(recipe, "en", done)
    assert refused == [] and pending_pieces(translated, "en") == []
    return translated


def test_the_text_offered_is_the_recipe_without_what_it_cannot_set() -> None:
    text = text_for_editing(_saved())
    assert text.startswith("---\ntitle: Käsekuchen\nlang: de\n---\n")
    assert "visibility" not in text
    assert "^conventional{175%C} (^fan{155%C})" in text


def test_an_edit_stays_the_same_recipe() -> None:
    saved = _saved()
    edited = text_for_editing(saved).replace("@Zucker{75%g}", "@Zucker{80%g}")
    recipe = revise(saved, edited).recipe
    assert recipe is not None
    assert (recipe.id, recipe.visibility, recipe.provenance) == (
        saved.id,
        "public",
        saved.provenance,
    )
    assert recipe.glossary == saved.glossary
    step = build_render_model(recipe, RenderOptions(lang="de")).steps[0]
    assert step.text.startswith("1 kg Magerquark und 80 g Zucker")


def test_an_edited_step_loses_only_its_own_translation() -> None:
    saved = _saved()
    edited = text_for_editing(saved).replace("glatt rühren", "cremig rühren")
    recipe = revise(saved, edited).recipe
    assert [piece.key.split(":")[0] for piece in pending_pieces(recipe, "en")] == ["step"]
    english = build_render_model(recipe, RenderOptions(lang="en"))
    assert english.title == "EN Käsekuchen"
    assert english.steps[1].text.startswith("EN Bei")


def test_visibility_is_not_set_by_the_text() -> None:
    saved = _saved()
    sneaky = text_for_editing(saved).replace("lang: de\n", "lang: de\nvisibility: private\n")
    assert revise(saved, sneaky).recipe.visibility == "public"


def test_text_that_does_not_read_says_why() -> None:
    revision = revise(_saved(), "---\ntitle: [\n---\n")
    assert revision.recipe is None
    assert revision.problem == "unreadable"
    assert revision.detail


# -- search ---------------------------------------------------------------------------


def test_a_recipe_is_found_by_its_ingredients_in_every_language() -> None:
    from snapcook_core.search import search_terms

    terms = search_terms(_saved())
    assert {"Magerquark", "Zucker", "sugar", "EN Käsekuchen"} <= set(terms)
    assert terms == search_terms(_saved())  # stable, for a reproducible projection
