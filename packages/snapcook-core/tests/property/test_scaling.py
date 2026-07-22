# SPDX-License-Identifier: Apache-2.0
"""Scaling properties.

The two the milestone singles out, each catching a specific bug:

``scale(scale(r, a), b) == scale(r, a*b)``
    Catches rounding applied at *scale* time instead of *format* time. Scaling is
    exact Decimal multiplication, so composing two scales must equal scaling by
    the product with no drift. If this fails, someone rounded in the wrong place.

``scale(to_taste, k) == to_taste``
    Catches scaling applied to a non-quantity. An approximation has no number to
    multiply; doubling a recipe must leave "salt to taste" exactly as it was.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from snapcook_core.schema.quantity import (
    Approx,
    ApproxToken,
    Count,
    Range,
    Scalar,
    UnitRef,
)
from snapcook_core.units.scaling import scale_quantity

pytestmark = __import__("pytest").mark.property

_positive = st.decimals(
    min_value=Decimal("0.001"),
    max_value=Decimal("100000"),
    allow_nan=False,
    allow_infinity=False,
    places=3,
)
_factors = st.decimals(
    min_value=Decimal("0.1"),
    max_value=Decimal("10"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


@given(value=_positive, a=_factors, b=_factors)
def test_scaling_composes_exactly(value: Decimal, a: Decimal, b: Decimal) -> None:
    q = Scalar(value=value, unit=UnitRef(unit_id="unit:g", surface="g"))
    twice = scale_quantity(scale_quantity(q, a), b)
    once = scale_quantity(q, a * b)
    assert twice.value == once.value


@given(low=_positive, high=_positive, a=_factors, b=_factors)
def test_range_scaling_composes_exactly(
    low: Decimal, high: Decimal, a: Decimal, b: Decimal
) -> None:
    lo, hi = sorted((low, high))
    q = Range(low=lo, high=hi, unit=UnitRef(unit_id="unit:ml", surface="ml"))
    twice = scale_quantity(scale_quantity(q, a), b)
    once = scale_quantity(q, a * b)
    assert (twice.low, twice.high) == (once.low, once.high)


@given(value=_positive, a=_factors, b=_factors)
def test_count_scaling_composes_exactly(value: Decimal, a: Decimal, b: Decimal) -> None:
    q = Count(value=value)
    twice = scale_quantity(scale_quantity(q, a), b)
    once = scale_quantity(q, a * b)
    assert twice.value == once.value


@given(
    token=st.sampled_from(list(ApproxToken)),
    k=_factors,
)
def test_approx_is_scale_invariant(token: ApproxToken, k: Decimal) -> None:
    """scale(to_taste, k) == to_taste for every approximation token."""
    q = Approx(token=token, surface=token.value)
    assert scale_quantity(q, k) == q


@given(value=_positive)
def test_scaling_by_one_is_identity(value: Decimal) -> None:
    q = Scalar(value=value, unit=UnitRef(unit_id="unit:g", surface="g"))
    assert scale_quantity(q, Decimal(1)).value == value
