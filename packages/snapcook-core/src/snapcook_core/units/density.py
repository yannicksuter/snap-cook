# SPDX-License-Identifier: Apache-2.0
"""Volume<->mass conversion, and it refuses to guess.

Converting 1 cup of flour to grams is **not** a unit conversion. It is a
two-argument function of the quantity *and the ingredient*, because 250 g of
flour is not 250 ml of flour. No general unit library can do it from the units
alone; it needs a density.

The rule this module exists to enforce:

> Conversion across dimensions without a density **raises**. It never guesses
> and never falls back to water at 1.0 g/ml.

A wrong density is worse than a refusal because it is *invisible*: the recipe
still renders, the number just quietly lies. A :class:`NoDensityError` is loud,
and loud is recoverable.

Same-dimension conversion (ml to l, g to oz) needs no ingredient and never
raises for a known unit. Only crossing the mass/volume boundary requires
density, and only that path can refuse.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pint import Context

from snapcook_core.errors import (
    IncompatibleDimensionsError,
    NoCountWeightError,
    NoDensityError,
)
from snapcook_core.units.registry import (
    dimension_of,
    pint_quantity,
    registry,
    same_dimension,
    unit_def,
)

if TYPE_CHECKING:
    from snapcook_core.schema.ingredient import Ingredient
    from snapcook_core.schema.quantity import SizeGrade

__all__ = ["convert_value", "count_to_mass_g", "resolve_density_g_per_ml"]


def resolve_density_g_per_ml(
    ingredient: Ingredient | None, prep_state: str | None = None
) -> Decimal | None:
    """The density to use for this ingredient in this prep state.

    ``prep_state`` is threaded through for the day the registry distinguishes
    sifted from scooped flour (a real ~20% difference). In M1 an ingredient
    carries a single density, so the argument is accepted and recorded but does
    not yet select between variants.
    """
    if ingredient is None:
        return None
    return ingredient.density_g_per_ml


def _density_context(density_g_per_ml: Decimal) -> Context:
    """A Pint context bridging mass and volume for one ingredient.

    This is the mechanism the architecture note calls "per-ingredient Pint
    contexts": the density is baked into the transformation, so the bridge only
    exists for the ingredient it was built for and cannot leak a flour density
    into a conversion of oil.
    """
    ureg = registry()
    density = ureg.Quantity(density_g_per_ml, "gram / milliliter")
    ctx = Context()
    ctx.add_transformation("[volume]", "[mass]", lambda _ureg, x: x * density)
    ctx.add_transformation("[mass]", "[volume]", lambda _ureg, x: x / density)
    return ctx


def convert_value(
    value: Decimal,
    from_unit: str,
    to_unit: str,
    *,
    ingredient: Ingredient | None = None,
    prep_state: str | None = None,
) -> Decimal:
    """Convert a magnitude between two units, returning the new magnitude.

    Same dimension goes straight through Pint. Crossing mass<->volume consults
    the ingredient's density and **raises** :class:`NoDensityError` if there is
    none. Any other cross-dimension request (mass to time) raises
    :class:`IncompatibleDimensionsError` -- there is no bridge and inventing one
    would be nonsense.
    """
    if unit_def(from_unit) is None:
        raise IncompatibleDimensionsError(f"unknown source unit: {from_unit!r}")
    if unit_def(to_unit) is None:
        raise IncompatibleDimensionsError(f"unknown target unit: {to_unit!r}")

    quantity = pint_quantity(value, from_unit)
    target_name = unit_def(to_unit).pint_name

    if same_dimension(from_unit, to_unit):
        return quantity.to(target_name).magnitude

    dims = {dimension_of(from_unit), dimension_of(to_unit)}
    if dims != {"mass", "volume"}:
        raise IncompatibleDimensionsError(
            f"cannot convert {from_unit} to {to_unit}: no bridge between "
            f"{dimension_of(from_unit)} and {dimension_of(to_unit)}"
        )

    density = resolve_density_g_per_ml(ingredient, prep_state)
    if density is None:
        name = ingredient.id if ingredient is not None else "<unbound>"
        raise NoDensityError(
            f"cannot convert {from_unit} to {to_unit} for {name}: no known density. "
            "Refusing to guess -- a wrong density is invisible."
        )

    context = _density_context(density)
    return quantity.to(target_name, context).magnitude


def count_to_mass_g(
    value: Decimal, ingredient: Ingredient | None, size: SizeGrade | None = None
) -> Decimal:
    """Grams for a counted quantity ("2 medium onions") via piece weights.

    A count is not a unit, so this is deliberately separate from
    :func:`convert_value`. Raises :class:`NoCountWeightError` when the piece
    weight is unknown -- same refusal-over-guessing rule as density.
    """
    weight = ingredient.piece_weight(size) if ingredient is not None else None
    if weight is None:
        name = ingredient.id if ingredient is not None else "<unbound>"
        raise NoCountWeightError(
            f"no piece weight for {name} at size {size}; cannot turn a count into a mass"
        )
    return value * weight
