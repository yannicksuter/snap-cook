# SPDX-License-Identifier: Apache-2.0
"""A metric reader keeps the recipe's own unit for a volume while it reads well.

"2 dl Rahm" is how a Swiss recipe says it and "2 EL" is easier to measure than
30 ml, so neither becomes millilitres just because millilitres are metric.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snapcook_core.cooklang import parse_cook
from snapcook_core.render import RenderOptions, build_render_model


def _shown(amount: str, scale: str = "1", lang: str = "de", system: str = "metric") -> str:
    recipe = parse_cook(f"---\ntitle: T\nlang: de\n---\n@Rahm{{{amount}}} rühren.\n")
    model = build_render_model(
        recipe, RenderOptions(lang=lang, system=system, scale=Decimal(scale))
    )
    return model.ingredients[0].quantity.display


@pytest.mark.parametrize(
    ("amount", "scale", "shown"),
    [
        ("2%dl", "1", "2 dl"),
        ("2%dl", "1.5", "3 dl"),
        ("2%dl", "0.25", "0.5 dl"),
        ("2%dl", "0.2", "40 ml"),
        ("2%dl", "5", "1 l"),
        ("2.5%dl", "1", "2.5 dl"),
        ("200%ml", "1", "200 ml"),
        ("1%l", "0.5", "0.5 l"),
        ("1%l", "0.2", "200 ml"),
    ],
)
def test_dl_and_litres_stay_while_they_read_well(amount, scale, shown) -> None:
    assert _shown(amount, scale) == shown


@pytest.mark.parametrize(
    ("amount", "scale", "lang", "shown"),
    [
        ("2%EL", "1", "de", "2 EL"),
        ("2%EL", "1", "en", "2 tbsp"),
        ("1%TL", "1", "de", "1 TL"),
        ("1%TL", "3", "de", "1 EL"),
        ("1%EL", "0.5", "de", "1.5 TL"),
        ("2%EL", "4", "de", "120 ml"),
    ],
)
def test_spoons_stay_spoons_up_to_six(amount, scale, lang, shown) -> None:
    assert _shown(amount, scale, lang=lang) == shown


def test_us_units_are_unchanged() -> None:
    assert "cup" in _shown("2.5%dl", system="us")
