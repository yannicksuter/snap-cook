# SPDX-License-Identifier: Apache-2.0
"""Turning an exact quantity into something a human wants to read.

Everything here is **display only**. The exact value is always retained
alongside the rendered string, so re-scaling re-derives from the exact value and
rounding never compounds. Scaling a recipe to 1.5x and back to 1x must return
the original number, not something that has drifted through two roundings.

The hard part is not arithmetic, it is plausibility. After scaling by 1.5,
``3/4 tsp`` should read ``1 1/8 tsp`` rather than ``1.125 tsp`` -- the first is
a measurement someone can make with the spoons in their drawer, the second is a
number. Fraction-friendly rounding is therefore a real subsystem rather than a
call to ``round()``.

Two failure modes this module is specifically built to avoid:

* **Rendering a non-zero quantity as "0".** A pinch of saffron scaled to 0.5x
  must never display as ``0 g``. Better an awkward ``0.05 g`` than a confident
  lie.
* **Emitting fractions nobody uses.** ``7/16 tsp`` is arithmetically closer than
  ``1/2 tsp`` but useless in a kitchen. Ladders constrain output to denominators
  people actually own measuring spoons for.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Literal

from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.quantity import (
    Approx,
    Count,
    Quantity,
    Range,
    Scalar,
    SizeGrade,
)

__all__ = [
    "FRACTION_LADDERS",
    "RoundingProfile",
    "format_quantity",
    "metric_profile",
    "snap_metric",
    "to_mixed_number",
    "us_profile",
]

# Denominators restricted to what a kitchen actually has: halves, thirds,
# quarters and eighths. Thirds are included because US measuring-cup sets ship
# a 1/3 cup, so "1/3" reads naturally even though it is not a binary fraction.
_DEFAULT_LADDER: tuple[Fraction, ...] = (
    Fraction(1, 8),
    Fraction(1, 4),
    Fraction(1, 3),
    Fraction(1, 2),
    Fraction(2, 3),
    Fraction(3, 4),
)

FRACTION_LADDERS: dict[str, tuple[Fraction, ...]] = {
    "unit:tsp": _DEFAULT_LADDER,
    "unit:tbsp": (Fraction(1, 4), Fraction(1, 3), Fraction(1, 2), Fraction(2, 3), Fraction(3, 4)),
    "unit:cup.us": _DEFAULT_LADDER,
    "unit:cup.metric": _DEFAULT_LADDER,
    "unit:cup.uk": _DEFAULT_LADDER,
    "unit:cup.jp": _DEFAULT_LADDER,
    # Weights in imperial recipes are usually quarters at finest.
    "unit:oz": (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)),
    "unit:lb": (Fraction(1, 4), Fraction(1, 3), Fraction(1, 2), Fraction(2, 3), Fraction(3, 4)),
    "unit:pint": (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)),
    "unit:quart": (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)),
}

# (exclusive upper bound, step). Below 1 unit, tenths; up to 10, halves; and so
# on. This is what turns 1487.3 g into 1485 g rather than a false-precision
# 1487.3 g that implies a scale nobody has.
_METRIC_BANDS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("1"), Decimal("0.1")),
    (Decimal("10"), Decimal("0.5")),
    (Decimal("100"), Decimal("1")),
    (Decimal("1000"), Decimal("5")),
    (Decimal("Infinity"), Decimal("25")),
)


class RoundingProfile(SnapcookModel):
    """How to render numbers for one reader."""

    system: Literal["metric", "us", "imperial"] = "metric"

    fraction_tolerance: Decimal = Decimal("0.05")
    """Maximum relative error accepted when snapping to a fraction.

    5% is generous for cooking but not for baking, and it is deliberately a
    *relative* bound: snapping 0.4 cup to 1/3 cup is a 17% error and is
    correctly rejected, leaving the caller to render a decimal or promote the
    unit instead of quietly lying about the amount.
    """

    prefer_fractions: bool = True

    def ladder_for(self, unit_id: str | None) -> tuple[Fraction, ...] | None:
        if not self.prefer_fractions or unit_id is None:
            return None
        return FRACTION_LADDERS.get(unit_id)


def metric_profile() -> RoundingProfile:
    """Metric readers get decimals; fractions are not idiomatic."""
    return RoundingProfile(system="metric", prefer_fractions=False)


def us_profile() -> RoundingProfile:
    return RoundingProfile(system="us", prefer_fractions=True)


# -- primitives ---------------------------------------------------------------


def _strip(value: Decimal) -> str:
    """Render a Decimal without trailing zeros or exponent notation."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _round_significant(value: Decimal, digits: int = 2) -> Decimal:
    """Round to N significant figures, keeping small values visible."""
    if value == 0:
        return value
    exponent = value.adjusted()  # position of the most significant digit
    quantum = Decimal(1).scaleb(exponent - digits + 1)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def snap_metric(
    value: Decimal, bands: tuple[tuple[Decimal, Decimal], ...] = _METRIC_BANDS
) -> Decimal:
    """Snap to a step appropriate to the value's magnitude.

    Never returns zero for a non-zero input: below the smallest band the value
    is rendered with significant figures instead, because "0 g of saffron" is
    worse than an awkward number.
    """
    if value == 0:
        return value

    magnitude = abs(value)
    step = bands[-1][1]
    for upper, band_step in bands:
        if magnitude < upper:
            step = band_step
            break

    snapped = (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step

    if snapped == 0:
        return _round_significant(value, 2)
    return snapped


def to_mixed_number(
    value: Decimal,
    ladder: tuple[Fraction, ...],
    tolerance: Decimal = Decimal("0.05"),
) -> str | None:
    """Render as a mixed number, or ``None`` if no ladder entry is close enough.

    ``None`` is a real answer, not a failure: it tells the caller that this
    quantity has no plausible fractional form and should be rendered another
    way -- as a decimal, or by promoting to a smaller unit (``0.25 cup`` reads
    better as ``4 tbsp``).
    """
    if value == 0:
        return "0"

    negative = value < 0
    magnitude = abs(value)

    whole = int(magnitude)
    remainder = magnitude - whole

    # 0 and 1 are candidates too: a remainder of 0.98 should round the whole
    # number up rather than being reported as an unrepresentable fraction.
    candidates: list[Fraction] = [Fraction(0), *ladder, Fraction(1)]
    best = min(candidates, key=lambda f: abs(remainder - Decimal(f.numerator) / f.denominator))
    error = abs(remainder - Decimal(best.numerator) / best.denominator)

    if error > tolerance * magnitude:
        return None

    if best == 1:
        whole += 1
        best = Fraction(0)

    # A value that rounds away to nothing must not be rendered as "0".
    if whole == 0 and best == 0:
        return None

    if best == 0:
        text = str(whole)
    elif whole == 0:
        text = f"{best.numerator}/{best.denominator}"
    else:
        text = f"{whole} {best.numerator}/{best.denominator}"

    return f"-{text}" if negative else text


def format_number(value: Decimal, unit_id: str | None, profile: RoundingProfile) -> str:
    """Render a bare number for display, without its unit."""
    ladder = profile.ladder_for(unit_id)
    if ladder is not None:
        mixed = to_mixed_number(value, ladder, profile.fraction_tolerance)
        if mixed is not None:
            return mixed
    return _strip(snap_metric(value))


def format_count(value: Decimal, *, divisible: bool = True) -> str:
    """Render a piece count.

    Indivisible ingredients round to whole pieces -- "1.5 large eggs" is not an
    instruction anyone can follow. Positive amounts never round down to zero,
    because a recipe that lists an ingredient needs at least one of it.
    """
    if not divisible:
        rounded = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if rounded == 0 and value > 0:
            rounded = Decimal(1)
        return _strip(rounded)

    halves = (value * 2).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 2
    if halves == 0 and value > 0:
        return _strip(_round_significant(value, 2))
    return _strip(halves)


# -- the public entry point ---------------------------------------------------


def format_quantity(
    quantity: Quantity,
    profile: RoundingProfile | None = None,
    *,
    divisible: bool = True,
) -> str:
    """Render a quantity for a human, unit included.

    Display only. The exact value is retained by the caller so that re-scaling
    never compounds rounding error.
    """
    profile = profile or metric_profile()

    if isinstance(quantity, Approx):
        # Never a number. The authored surface form is what the reader sees.
        return quantity.surface

    if isinstance(quantity, Count):
        low = format_count(quantity.value, divisible=divisible)
        if quantity.high is not None:
            high = format_count(quantity.high, divisible=divisible)
            if high != low:
                return _with_size(f"{low}–{high}", quantity.size)
        return _with_size(low, quantity.size)

    if isinstance(quantity, Scalar):
        unit_id = quantity.unit.unit_id if quantity.unit else None
        return _with_unit(format_number(quantity.value, unit_id, profile), quantity)

    if isinstance(quantity, Range):
        unit_id = quantity.unit.unit_id if quantity.unit else None
        low = format_number(quantity.low, unit_id, profile)
        high = format_number(quantity.high, unit_id, profile)
        if low == high:
            return _with_unit(low, quantity)
        return _with_unit(f"{low}–{high}", quantity)

    raise TypeError(f"unformattable quantity type: {type(quantity).__name__}")


def _with_unit(text: str, quantity: Scalar | Range) -> str:
    unit = quantity.unit
    if unit is None:
        return text
    return f"{text} {unit.surface}"


def _with_size(text: str, size: SizeGrade | None) -> str:
    return f"{text} {size.value}" if size is not None else text
