# SPDX-License-Identifier: Apache-2.0
"""Conversion properties.

``convert(convert(q, u2), u1) ≈ q``
    Catches asymmetric conversion factors -- a table where g->oz and oz->g do
    not agree. The round trip must return the original within a tight relative
    tolerance (not exact, because Decimal division through an irrational-ish
    factor is not perfectly reversible, but close enough that a real asymmetry
    would fail).

**Cross-dimension convert raises.**
    Catches a silent grams-to-millilitres with no density. This is the single
    most dangerous unit bug in a cooking app, so it gets a property test of its
    own: for every mass/volume pair, converting without an ingredient density
    must raise, never guess.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapcook_core.errors import IncompatibleDimensionsError, NoDensityError
from snapcook_core.units.density import convert_value

pytestmark = pytest.mark.property

_MASS = ["unit:g", "unit:kg", "unit:oz", "unit:lb"]
_VOLUME = ["unit:ml", "unit:l", "unit:tsp", "unit:tbsp", "unit:cup.us", "unit:cup.metric"]
_TIME = ["unit:s", "unit:min", "unit:h"]

_amount = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


@given(value=_amount, a=st.sampled_from(_MASS), b=st.sampled_from(_MASS))
def test_mass_conversion_round_trips(value: Decimal, a: str, b: str) -> None:
    there = convert_value(value, a, b)
    back = convert_value(there, b, a)
    assert abs(back - value) <= abs(value) * Decimal("1e-6")


@given(value=_amount, a=st.sampled_from(_VOLUME), b=st.sampled_from(_VOLUME))
def test_volume_conversion_round_trips(value: Decimal, a: str, b: str) -> None:
    there = convert_value(value, a, b)
    back = convert_value(there, b, a)
    assert abs(back - value) <= abs(value) * Decimal("1e-6")


@given(
    value=_amount,
    mass=st.sampled_from(_MASS),
    volume=st.sampled_from(_VOLUME),
)
def test_cross_dimension_without_density_raises(value: Decimal, mass: str, volume: str) -> None:
    """No density → refuse, in both directions. Never fall back to water."""
    with pytest.raises(NoDensityError):
        convert_value(value, mass, volume)
    with pytest.raises(NoDensityError):
        convert_value(value, volume, mass)


@given(value=_amount, mass=st.sampled_from(_MASS), time=st.sampled_from(_TIME))
def test_incoherent_dimensions_raise(value: Decimal, mass: str, time: str) -> None:
    """Mass to time has no bridge at all -- not even a density could help."""
    with pytest.raises(IncompatibleDimensionsError):
        convert_value(value, mass, time)
