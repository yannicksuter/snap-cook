# SPDX-License-Identifier: Apache-2.0
"""The unit registry: locale-qualified units on top of Pint.

Built on Pint, for two reasons Pint is specifically good at and a hand-rolled
factor table is not: **contexts**, which is how per-ingredient density makes
volume->mass a legal conversion (see :mod:`snapcook_core.units.density`), and
**offset units**, which it refuses to do arithmetic on -- correctly, since
degC is affine. Temperature is a dedicated model precisely because of that
refusal, so nothing here touches offset units.

Two design choices are load-bearing:

``non_int_type=Decimal``
    Set at construction. Every magnitude flowing through the registry is a
    Decimal, never a float. Floats are banned from the schema, and a float and a
    Decimal quantity cannot even be added in Pint -- it raises. The ban and the
    registry agree.

Units are defined explicitly, not inherited from Pint's defaults.
    A bare "cup" is ambiguous -- US 236.6 ml, metric 250 ml, Japanese 200 ml, UK
    284.1 ml -- so every locale cup is its own unit with a frozen value. The
    cooking spoon is likewise pinned (tsp = 5 ml, tbsp = 15 ml) rather than left
    to Pint's legal US teaspoon of 4.929 ml, because a recipe means the spoon in
    the drawer. Pinning the values here means a Pint upgrade cannot silently
    change what a recipe converts to.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal, NamedTuple

from pint import UnitRegistry
from pint.facets.plain import PlainQuantity

from snapcook_core.errors import IncompatibleDimensionsError
from snapcook_core.ids import UnitId

__all__ = [
    "Dimension",
    "System",
    "UnitDef",
    "dimension_of",
    "pint_quantity",
    "registry",
    "resolve_unit",
    "same_dimension",
    "system_of",
    "unit_def",
]

Dimension = Literal["mass", "volume", "time"]
System = Literal["metric", "us", "uk", "jp", "universal"]


class UnitDef(NamedTuple):
    """One unit: its slug id, how Pint names it, and how to read and write it."""

    id: UnitId
    pint_name: str
    dimension: Dimension
    system: System
    symbol: str
    """The default surface form when rendering, e.g. ``g`` or ``cup``."""
    aliases: tuple[str, ...]
    """Author-written forms that resolve to this unit, lower-cased."""


def _u(id_: str, pint_name: str, dim: Dimension, system: System, symbol: str, *aliases: str):
    return UnitDef(UnitId(id_), pint_name, dim, system, symbol, aliases)


# The curated M1 unit set. Definitions the registry needs beyond Pint's stock
# units are supplied to _build_registry below; everything else reuses Pint's.
UNIT_DEFS: tuple[UnitDef, ...] = (
    # mass
    _u("unit:g", "gram", "mass", "metric", "g", "g", "gr", "gram", "grams", "gramm"),
    _u("unit:kg", "kilogram", "mass", "metric", "kg", "kg", "kilogram", "kilograms"),
    _u("unit:mg", "milligram", "mass", "metric", "mg", "mg", "milligram", "milligrams"),
    _u("unit:oz", "ounce", "mass", "us", "oz", "oz", "ounce", "ounces"),
    _u("unit:lb", "pound", "mass", "us", "lb", "lb", "lbs", "pound", "pounds"),
    # volume -- metric
    _u(
        "unit:ml",
        "milliliter",
        "volume",
        "metric",
        "ml",
        "ml",
        "milliliter",
        "milliliters",
        "millilitre",
        "millilitres",
    ),
    _u("unit:l", "liter", "volume", "metric", "l", "l", "liter", "liters", "litre", "litres"),
    _u(
        "unit:dl",
        "deciliter",
        "volume",
        "metric",
        "dl",
        "dl",
        "deciliter",
        "deciliters",
        "decilitre",
        "decilitres",
    ),
    # volume -- spoons, pinned to cooking values
    _u("unit:tsp", "tsp_cook", "volume", "universal", "tsp", "tsp", "teaspoon", "teaspoons", "tl"),
    _u(
        "unit:tbsp",
        "tbsp_cook",
        "volume",
        "universal",
        "tbsp",
        "tbsp",
        "tablespoon",
        "tablespoons",
        "el",
        "el",
    ),
    # volume -- locale cups (see RECIPE_SPEC.md section 4)
    _u("unit:cup.us", "cup_us", "volume", "us", "cup", "cup", "cups"),
    _u("unit:cup.metric", "cup_metric", "volume", "metric", "cup", "cup", "cups"),
    _u("unit:cup.uk", "cup_uk", "volume", "uk", "cup", "cup", "cups"),
    _u("unit:cup.jp", "cup_jp", "volume", "jp", "cup", "cup", "cups"),
    _u("unit:floz", "floz_us", "volume", "us", "fl oz", "floz", "fl oz", "fluid ounce"),
    _u("unit:pint", "pint_us", "volume", "us", "pint", "pint", "pints", "pt"),
    _u("unit:quart", "quart_us", "volume", "us", "quart", "quart", "quarts", "qt"),
    # time
    _u("unit:s", "second", "time", "universal", "s", "s", "sec", "second", "seconds"),
    _u("unit:min", "minute", "time", "universal", "min", "min", "minute", "minutes"),
    _u("unit:h", "hour", "time", "universal", "h", "h", "hr", "hour", "hours"),
    _u("unit:day", "day", "time", "universal", "d", "day", "days"),
)

_BY_ID: dict[UnitId, UnitDef] = {d.id: d for d in UNIT_DEFS}

# Author surface -> unit id, for the unambiguous forms. Ambiguous "cup" is
# resolved with a locale by resolve_unit and is intentionally absent here.
_BY_ALIAS: dict[str, UnitId] = {}
for _d in UNIT_DEFS:
    for _alias in _d.aliases:
        _BY_ALIAS.setdefault(_alias.lower(), _d.id)
# "cup"/"cups" are ambiguous across locales; force resolve_unit to demand one.
for _ambiguous in ("cup", "cups"):
    _BY_ALIAS.pop(_ambiguous, None)


@lru_cache(maxsize=1)
def registry() -> UnitRegistry:
    """The process-wide Decimal Pint registry.

    Cached: building a registry is not cheap, and every quantity in the process
    must share one registry or Pint refuses to compare their units.
    """
    ureg = UnitRegistry(non_int_type=Decimal)
    # Cooking spoons and locale cups, with values frozen here rather than
    # inherited, so a Pint upgrade cannot move them.
    ureg.define("tsp_cook = 5 milliliter")
    ureg.define("tbsp_cook = 15 milliliter")
    ureg.define("cup_us = 236.588 milliliter")
    ureg.define("cup_metric = 250 milliliter")
    ureg.define("cup_uk = 284.131 milliliter")
    ureg.define("cup_jp = 200 milliliter")
    ureg.define("floz_us = 29.5735 milliliter")
    ureg.define("pint_us = 473.176 milliliter")
    ureg.define("quart_us = 946.353 milliliter")
    return ureg


def unit_def(unit_id: str) -> UnitDef | None:
    """The definition for a unit id, or ``None`` if it is not a known unit."""
    return _BY_ID.get(UnitId(unit_id))


def dimension_of(unit_id: str) -> Dimension | None:
    d = _BY_ID.get(UnitId(unit_id))
    return d.dimension if d else None


def system_of(unit_id: str) -> System | None:
    d = _BY_ID.get(UnitId(unit_id))
    return d.system if d else None


def same_dimension(a: str, b: str) -> bool:
    da, db = dimension_of(a), dimension_of(b)
    return da is not None and da == db


def resolve_unit(surface: str, *, locale: str | None = None) -> UnitId | None:
    """Map an author-written unit string to a unit id.

    ``locale`` disambiguates a bare "cup": ``resolve_unit("cup", locale="us")``
    is ``unit:cup.us``. Without a locale, an ambiguous form resolves to
    ``None`` -- the caller stores the surface and records an unresolved-unit
    warning rather than silently guessing a country.
    """
    key = surface.strip().lower()
    if key in _BY_ALIAS:
        return _BY_ALIAS[key]
    if key in ("cup", "cups"):
        loc = (locale or "").lower()
        candidate = f"unit:cup.{loc}" if loc else None
        if candidate and UnitId(candidate) in _BY_ID:
            return UnitId(candidate)
    return None


def pint_quantity(value: Decimal, unit_id: str) -> PlainQuantity:
    """A Pint quantity for a value in a known unit.

    Raises :class:`IncompatibleDimensionsError` if the unit id is not one this
    registry defines -- an unknown unit is a caller bug here, distinct from the
    unresolved-*surface* case which :func:`resolve_unit` handles by returning
    ``None``.
    """
    d = _BY_ID.get(UnitId(unit_id))
    if d is None:
        raise IncompatibleDimensionsError(f"unknown unit id: {unit_id!r}")
    return registry().Quantity(value, d.pint_name)
