# SPDX-License-Identifier: Apache-2.0
"""Quantities.

"250 g" and "a pinch" are not the same kind of thing, and flattening them into a
nullable number destroys information that cannot be recovered. So a quantity is
a discriminated union of four shapes:

``Scalar``
    A number and a unit. ``250 g``.

``Range``
    Two numbers and a unit. ``200-300 ml``. First-class rather than a string,
    because a range must survive scaling and unit conversion intact.

``Count``
    Countable pieces, with an optional size grade. ``1 medium onion``. The unit
    is always absent -- "medium" is a size, not a unit, and conflating the two
    is what makes "1 medium onion" unconvertible in other systems.

``Approx``
    ``a pinch``, ``to taste``. **Never coerced to a number by any code path.**

Every quantity is paired with a :class:`ScalingPolicy` in a :class:`QuantitySpec`,
because how a quantity responds to doubling a recipe is a property of the
quantity's role, not of its magnitude.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from snapcook_core.ids import UnitId
from snapcook_core.schema.base import SnapcookModel

__all__ = [
    "Approx",
    "ApproxToken",
    "Count",
    "Quantity",
    "QuantitySpec",
    "Range",
    "Scalar",
    "ScalingPolicy",
    "SizeGrade",
    "UnitRef",
]


class SizeGrade(StrEnum):
    """The size of a countable piece.

    Resolved to a mass through the ingredient registry's piece-weight table --
    a medium onion is ~150 g. Separate from density, and needs its own data.
    """

    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


class ApproxToken(StrEnum):
    """Quantities that are not numbers.

    A controlled vocabulary rather than free text, so that a renderer can
    translate "a pinch" into any language and a shopping list can decide how to
    treat it.
    """

    PINCH = "pinch"
    DASH = "dash"
    SPLASH = "splash"
    DRIZZLE = "drizzle"
    HANDFUL = "handful"
    KNOB = "knob"
    TO_TASTE = "to_taste"
    AS_NEEDED = "as_needed"
    FOR_GARNISH = "for_garnish"
    FOR_FRYING = "for_frying"
    TO_COVER = "to_cover"


class ScalingPolicy(StrEnum):
    """How a quantity responds to scaling a recipe."""

    LINEAR = "linear"
    """Multiply. Flour, water, most ingredients."""

    INVARIANT = "invariant"
    """Never changed. Salt to taste, pan dimensions."""

    MANUAL = "manual"
    """Never changed, and the reader is warned to check it.

    Bake times and oven temperatures. Doubling a recipe does not double bake
    time -- it may not change it at all -- and reduction times scale with
    surface area rather than volume. Silently doubling them ruins the dish, so
    the default is to leave them alone and say so.
    """

    NONLINEAR = "nonlinear"
    """Reserved. Behaves as MANUAL until real curve data exists."""


class UnitRef(SnapcookModel):
    """A reference to a unit, retaining what the author actually wrote.

    ``surface`` is preserved so a recipe can be reprinted as authored, and so a
    failure to resolve a unit is visible rather than silently normalised away.

    ``unit_id`` being ``None`` is a *warning*, not an error: an unrecognised
    unit blocks conversion, not storage. Refusing to store the recipe would
    make the importer useless on real-world input.
    """

    unit_id: UnitId | None = None
    surface: str
    locale: str | None = None
    """The locale that disambiguated a bare unit, if one was needed.

    A bare "cup" is 236.6 ml in the US, 250 ml metric, 200 ml in Japan.
    Resolution happens at authoring time and is frozen here, so a recipe never
    silently changes meaning when read in another country.
    """

    @property
    def resolved(self) -> bool:
        return self.unit_id is not None


class Scalar(SnapcookModel):
    """A number with a unit. ``250 g``."""

    kind: Literal["scalar"] = "scalar"
    value: Decimal
    unit: UnitRef | None = None


class Range(SnapcookModel):
    """An inclusive range. ``200-300 ml``, ``6-8 wings``."""

    kind: Literal["range"] = "range"
    low: Decimal
    high: Decimal
    unit: UnitRef | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.low > self.high:
            raise ValueError(f"range low {self.low} exceeds high {self.high}")
        return self


class Count(SnapcookModel):
    """Countable pieces. ``2 eggs``, ``1 medium onion``, ``6-8 wings``.

    Deliberately has no unit field. "medium" is a size grade, not a unit, and
    the conversion to mass goes through the ingredient's piece-weight table
    rather than through the unit registry.
    """

    kind: Literal["count"] = "count"
    value: Decimal
    high: Decimal | None = None
    """Set for a counted range: ``value`` is the low bound."""
    size: SizeGrade | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Count:
        if self.high is not None and self.value > self.high:
            raise ValueError(f"count low {self.value} exceeds high {self.high}")
        return self

    @property
    def is_range(self) -> bool:
        return self.high is not None


class Approx(SnapcookModel):
    """A quantity that is not a number. ``a pinch``, ``to taste``.

    ``nominal`` is **advisory only**. A shopping list may use it to estimate
    how much salt to buy; scaling and conversion must ignore it entirely. The
    moment an approximation is treated as a number, "salt to taste" starts
    doubling when you double a recipe.
    """

    kind: Literal["approx"] = "approx"
    token: ApproxToken
    surface: str
    nominal: Scalar | None = None


Quantity = Annotated[Scalar | Range | Count | Approx, Field(discriminator="kind")]


class QuantitySpec(SnapcookModel):
    """A quantity together with how it scales.

    These travel as a pair everywhere. Separating them would let a caller scale
    a quantity without consulting its policy, which is the bug this type exists
    to make impossible.
    """

    quantity: Quantity
    scaling: ScalingPolicy = ScalingPolicy.LINEAR

    @model_validator(mode="after")
    def _approx_is_never_scaled(self) -> QuantitySpec:
        """An approximation cannot scale linearly -- there is nothing to multiply.

        Enforced in the type rather than left to the scaling function, so an
        invalid pairing cannot be constructed, stored or hashed.
        """
        if isinstance(self.quantity, Approx) and self.scaling is ScalingPolicy.LINEAR:
            raise ValueError(
                f"Approx quantity ({self.quantity.token}) cannot have LINEAR scaling; "
                "use INVARIANT. There is no number to multiply."
            )
        return self


def approx_spec(token: ApproxToken, surface: str, nominal: Scalar | None = None) -> QuantitySpec:
    """Build an ``Approx`` spec with the only policy that makes sense for it."""
    return QuantitySpec(
        quantity=Approx(token=token, surface=surface, nominal=nominal),
        scaling=ScalingPolicy.INVARIANT,
    )
