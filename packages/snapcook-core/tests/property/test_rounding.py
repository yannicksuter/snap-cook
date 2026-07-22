# SPDX-License-Identifier: Apache-2.0
"""Rounding properties.

``format(q)`` never returns ``"0"`` for a non-zero ``q``
    Catches saffron at 0.5x rendering as "0 g" -- a confident lie. Better an
    awkward "0.05 g" than a zero the reader trusts.

Fraction denominators stay in ``{2, 3, 4, 8}``
    Catches "7/16 tsp" leaking into output. A kitchen has halves, thirds,
    quarters and eighths; an arithmetically-closer sixteenth is useless, so the
    ladder must never emit one.
"""

from __future__ import annotations

import re
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapcook_core.schema.quantity import Scalar, UnitRef
from snapcook_core.units.rounding import format_quantity, us_profile

pytestmark = pytest.mark.property

_ALLOWED_DENOMINATORS = {1, 2, 3, 4, 8}
_FRACTION = re.compile(r"(\d+)/(\d+)")

_nonzero = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("100000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_fraction_units = st.sampled_from(["unit:tsp", "unit:tbsp", "unit:cup.us", "unit:oz"])


@given(value=_nonzero, unit=st.sampled_from(["unit:g", "unit:ml", "unit:tsp", "unit:cup.us"]))
def test_nonzero_never_formats_as_zero(value: Decimal, unit: str) -> None:
    text = format_quantity(
        Scalar(value=value, unit=UnitRef(unit_id=unit, surface=unit)), us_profile()
    )
    number = text.rsplit(" ", 1)[0] if " " in text else text
    assert number not in ("0", "0/1"), f"{value} {unit} rendered as {text!r}"


@given(value=_nonzero, unit=_fraction_units)
def test_fraction_denominators_are_kitchen_friendly(value: Decimal, unit: str) -> None:
    text = format_quantity(
        Scalar(value=value, unit=UnitRef(unit_id=unit, surface=unit)), us_profile()
    )
    for _num, den in _FRACTION.findall(text):
        assert int(den) in _ALLOWED_DENOMINATORS, f"{value} {unit} -> {text!r}"


@given(value=_nonzero, unit=_fraction_units)
def test_reduced_fraction_denominators_are_kitchen_friendly(value: Decimal, unit: str) -> None:
    """Even after reduction, the fraction stays in the ladder's world."""
    text = format_quantity(
        Scalar(value=value, unit=UnitRef(unit_id=unit, surface=unit)), us_profile()
    )
    for num, den in _FRACTION.findall(text):
        reduced = Fraction(int(num), int(den))
        assert reduced.denominator in _ALLOWED_DENOMINATORS, f"{value} {unit} -> {text!r}"
