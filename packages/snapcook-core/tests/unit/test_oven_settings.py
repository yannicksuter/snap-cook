# SPDX-License-Identifier: Apache-2.0
"""A temperature keeps the oven setting it is meant for.

Sources often give one temperature per setting: 175 °C top and bottom heat,
155 °C fan. Without the setting the two numbers are a trap, so it is data on the
temperature, written ``^fan{155%C}``, and labelled in the reader's language.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snapcook_core.canonical.encode import to_canonical_doc
from snapcook_core.cooklang import parse_cook, print_cook
from snapcook_core.importing import system_prompt
from snapcook_core.render import RenderOptions, build_render_model
from snapcook_core.schema import Temperature

_CHEESECAKE = """---
title: Käsekuchen
lang: de
---
Im vorgeheizten Ofen ~{55%min} bei ^conventional{175%C} (^fan{155%C}) backen.
"""


def _temperatures(text: str) -> list[Temperature]:
    return parse_cook(text).actions[0].temperatures


def test_each_temperature_keeps_its_setting() -> None:
    assert [(t.value, t.mode) for t in _temperatures(_CHEESECAKE)] == [
        (Decimal(175), "conventional"),
        (Decimal(155), "fan"),
    ]


@pytest.mark.parametrize(
    ("written", "mode"),
    [
        ("Umluft", "fan"),
        ("convection", "fan"),
        ("Heißluft", "hot_air"),
        ("Heissluft", "hot_air"),
        ("Umluft mit Unterhitze", "fan_bottom"),
        ("Pizzastufe", "fan_bottom"),
        ("Umluft mit Ober-/Unterhitze", "fan_conventional"),
        ("Grill mit Umluft", "fan_grill"),
        ("Ober- und Unterhitze", "conventional"),
        ("Ober-/Unterhitze", "conventional"),
        ("top and bottom heat", "conventional"),
        ("Oberhitze", "top"),
        ("Unterhitze", "bottom"),
        ("broil", "grill"),
    ],
)
def test_the_words_people_write_for_a_setting_are_understood(written: str, mode: str) -> None:
    text = f"---\ntitle: T\nlang: de\n---\nBei ^{written}{{180%C}} backen.\n"
    assert [t.mode for t in _temperatures(text)] == [mode]


def test_an_unknown_setting_is_left_as_written_not_dropped() -> None:
    text = "---\ntitle: T\nlang: de\n---\nBei ^Gas Stufe{3} backen.\n"
    recipe = parse_cook(text)
    assert recipe.actions[0].temperatures == []
    assert "^Gas Stufe{3}" in build_render_model(recipe, RenderOptions(lang="de")).steps[0].text


def test_a_setting_survives_printing_and_reading_again() -> None:
    printed = print_cook(parse_cook(_CHEESECAKE))
    assert "^conventional{175%C}" in printed
    assert "^fan{155%C}" in printed
    assert print_cook(parse_cook(printed)) == printed


@pytest.mark.parametrize(
    ("lang", "system", "expected"),
    [
        ("de", "metric", "bei 175 °C Ober-/Unterhitze (155 °C Umluft) backen."),
        ("en", "metric", "bei 175 °C conventional (155 °C fan) backen."),
        ("en", "us", "bei 345 °F conventional (310 °F fan) backen."),
    ],
)
def test_the_setting_is_labelled_in_the_readers_language(
    lang: str, system: str, expected: str
) -> None:
    step = build_render_model(
        parse_cook(_CHEESECAKE), RenderOptions(lang=lang, system=system)
    ).steps[0]
    assert step.text.endswith(expected)
    assert [t.mode for t in step.temperatures] == ["conventional", "fan"]


def test_a_temperature_without_a_setting_encodes_as_before() -> None:
    # Absent is identical to empty, so every hash written before settings
    # existed stays valid.
    assert to_canonical_doc(Temperature(value=Decimal(180))) == {"unit": "C", "value": "180"}


def test_the_reader_is_told_to_keep_the_setting() -> None:
    prompt = system_prompt()
    assert "^conventional{175%C} (^fan{155%C})" in prompt
    assert "Umluft" in prompt
