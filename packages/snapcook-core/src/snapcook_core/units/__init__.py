# SPDX-License-Identifier: Apache-2.0
"""Units: the registry, density-aware conversion, scaling and rounding.

The layering matters. :mod:`registry` knows units but not ingredients.
:mod:`density` adds the ingredient so volume<->mass becomes possible -- and
refuses when it cannot. :mod:`scaling` multiplies exactly and never rounds;
:mod:`rounding` rounds for display and never scales. Keeping those two apart is
what stops rounding error compounding every time a reader changes the servings.
"""

from snapcook_core.units.density import (
    convert_value,
    count_to_mass_g,
    resolve_density_g_per_ml,
)
from snapcook_core.units.registry import (
    dimension_of,
    pint_quantity,
    registry,
    resolve_unit,
    same_dimension,
    system_of,
    unit_def,
)
from snapcook_core.units.rounding import (
    RoundingProfile,
    format_quantity,
    metric_profile,
    us_profile,
)
from snapcook_core.units.scaling import scale_quantity, scale_spec, scales_with_factor

__all__ = [
    "RoundingProfile",
    "convert_value",
    "count_to_mass_g",
    "dimension_of",
    "format_quantity",
    "metric_profile",
    "pint_quantity",
    "registry",
    "resolve_density_g_per_ml",
    "resolve_unit",
    "same_dimension",
    "scale_quantity",
    "scale_spec",
    "scales_with_factor",
    "system_of",
    "unit_def",
    "us_profile",
]
