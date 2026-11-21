# SPDX-License-Identifier: Apache-2.0
"""A recipe in parts, as its source has it: the dough, the filling, the glaze.

A source that lists its ingredients under headings keeps them: each step knows
the part it belongs to, the ingredient list is grouped under the same headings,
and the parts survive printing, editing and translation.
"""

from __future__ import annotations

from snapcook_core.canonical import content_hash
from snapcook_core.cooklang import parse_cook, print_cook
from snapcook_core.editing import carry_translations
from snapcook_core.render import RenderOptions, build_render_model, render_text
from snapcook_core.translating import Translated, apply_translation, pending_pieces

_ZIMTSCHNECKEN = """---
title: Zimtschnecken
lang: de
---
= Teig

@Milch{250%ml} und @Hefe{1%Würfel} verrühren. => Hefemilch

@Mehl{500%g} und die @&{Hefemilch} kneten. => Hefeteig

== Füllung ==
@Butter{100%g} und @Zimt{2%EL} verrühren. => Füllung

= Guss

@Puderzucker{80%g} und @Milch{2%EL} glatt rühren. => Guss

=

Den @&{Hefeteig} mit der @&{Füllung} bestreichen, aufrollen, backen und mit dem \
@&{Guss} bestreichen.
"""


def _sections(recipe) -> list[str | None]:
    return [a.section.values["de"] if a.section else None for a in recipe.actions]


def test_each_step_knows_its_part_however_the_heading_is_written() -> None:
    recipe = parse_cook(_ZIMTSCHNECKEN)
    assert _sections(recipe) == ["Teig", "Teig", "Füllung", "Guss", None]
    assert [a.produces.name.values["de"] for a in recipe.actions[:4]] == [
        "Hefemilch",
        "Hefeteig",
        "Füllung",
        "Guss",
    ], "a heading is never mistaken for what a step makes (=> name)"


def test_the_parts_print_and_read_back_the_same() -> None:
    printed = print_cook(parse_cook(_ZIMTSCHNECKEN))
    assert "\n= Teig\n\n" in printed and "\n= Füllung\n\n" in printed
    assert "\n=\n\nDen @&{Hefeteig}" in printed, "a step after the parts leaves them"
    assert print_cook(parse_cook(printed)) == printed


def test_a_recipe_without_parts_hashes_as_before() -> None:
    plain = "---\ntitle: T\nlang: de\n---\n@Mehl{500%g} kneten.\n"
    recipe = parse_cook(plain)
    assert recipe.actions[0].section is None
    assert "section" not in recipe.actions[0].model_dump(exclude_none=True)
    # The same recipe with an empty heading is the same content.
    with_heading = parse_cook(plain.replace("---\n@", "---\n=\n\n@"))
    assert content_hash(with_heading.model_copy(update={"id": recipe.id})) == content_hash(recipe)


def test_the_ingredients_are_listed_under_the_sources_headings() -> None:
    model = build_render_model(parse_cook(_ZIMTSCHNECKEN), RenderOptions(lang="de"))
    assert [(s.title, [i.name for i in s.ingredients], s.steps) for s in model.sections] == [
        ("Teig", ["Milch", "Hefe", "Mehl"], (1, 2)),
        ("Füllung", ["Butter", "Zimt"], (3,)),
        ("Guss", ["Puderzucker", "Milch"], (4,)),
        (None, [], (5,)),
    ]
    assert [step.section for step in model.steps] == ["Teig", "Teig", "Füllung", "Guss", None]
    text = render_text(model)
    assert "  Füllung\n    - 100 g Butter\n    - 2 EL Zimt\n" in text


def test_a_recipe_without_parts_has_one_plain_list() -> None:
    model = build_render_model(
        parse_cook("---\ntitle: T\nlang: de\n---\n@Mehl{500%g} kneten.\n"), RenderOptions(lang="de")
    )
    assert model.sections == ()


def test_a_parts_name_is_translated_once_and_shown_on_each_of_its_steps() -> None:
    recipe = parse_cook(_ZIMTSCHNECKEN)
    pieces = [piece for piece in pending_pieces(recipe, "en") if piece.key.startswith("section:")]
    assert [piece.text for piece in pieces] == ["Teig", "Füllung", "Guss"]
    english = {"Teig": "Dough", "Füllung": "Filling", "Guss": "Glaze"}
    done = [Translated(piece, english.get(piece.text, piece.text)) for piece in pieces]
    translated, refused = apply_translation(recipe, "en", done)
    assert refused == []
    model = build_render_model(translated, RenderOptions(lang="en"))
    assert [s.title for s in model.sections] == ["Dough", "Filling", "Glaze", None]

    # An edit that keeps a part's name keeps its translation.
    edited = parse_cook(_ZIMTSCHNECKEN.replace("{500%g}", "{550%g}"))
    carried = carry_translations(translated, edited)
    assert carried.actions[1].section.values == {"de": "Teig", "en": "Dough"}
