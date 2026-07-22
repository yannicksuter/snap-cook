# SPDX-License-Identifier: Apache-2.0
"""Stable, prefixed, sortable identifiers.

Every structural element carries a ULID that survives edits. This is what makes
the diff useful: moving step 5 to position 2 is reported as a single ``move``
rather than a remove-plus-add pair, because the action's ID did not change.

IDs are ULIDs rather than UUID4 so they sort chronologically, which makes
directory listings and debug output readable. The type-prefix (``rcp_``,
``act_``) is not decoration -- it makes a mis-wired ID immediately obvious in a
log line or a traceback, and lets ``parse_id`` reject a wrong-typed reference
before it reaches the graph validator.
"""

from __future__ import annotations

from typing import NewType

from ulid import ULID

RecipeId = NewType("RecipeId", str)
IngredientId = NewType("IngredientId", str)
IngredientUseId = NewType("IngredientUseId", str)
FoodStateId = NewType("FoodStateId", str)
ActionId = NewType("ActionId", str)
CookwareUseId = NewType("CookwareUseId", str)
SectionId = NewType("SectionId", str)

# Not a ULID: a stable human-readable slug, because unit ids appear in authored
# files and in the public API ("unit:cup.us"). A random id here would be hostile.
UnitId = NewType("UnitId", str)

# "sc1:<64 hex>" -- see canonical/hashing.py
VersionId = NewType("VersionId", str)

RECIPE_PREFIX = "rcp"
INGREDIENT_PREFIX = "ing"
INGREDIENT_USE_PREFIX = "iuse"
FOOD_STATE_PREFIX = "nod"
ACTION_PREFIX = "act"
COOKWARE_USE_PREFIX = "cwu"
SECTION_PREFIX = "sec"

_ALL_PREFIXES = frozenset(
    {
        RECIPE_PREFIX,
        INGREDIENT_PREFIX,
        INGREDIENT_USE_PREFIX,
        FOOD_STATE_PREFIX,
        ACTION_PREFIX,
        COOKWARE_USE_PREFIX,
        SECTION_PREFIX,
    }
)


def _mint(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def new_recipe_id() -> RecipeId:
    return RecipeId(_mint(RECIPE_PREFIX))


def new_ingredient_id() -> IngredientId:
    return IngredientId(_mint(INGREDIENT_PREFIX))


def new_ingredient_use_id() -> IngredientUseId:
    return IngredientUseId(_mint(INGREDIENT_USE_PREFIX))


def new_food_state_id() -> FoodStateId:
    return FoodStateId(_mint(FOOD_STATE_PREFIX))


def new_action_id() -> ActionId:
    return ActionId(_mint(ACTION_PREFIX))


def new_cookware_use_id() -> CookwareUseId:
    return CookwareUseId(_mint(COOKWARE_USE_PREFIX))


def new_section_id() -> SectionId:
    return SectionId(_mint(SECTION_PREFIX))


def prefix_of(value: str) -> str | None:
    """Return the type prefix of an id, or None if it is not a snapcook id."""
    head, sep, _ = value.partition("_")
    return head if sep and head in _ALL_PREFIXES else None


def is_id_of(value: str, prefix: str) -> bool:
    """True if ``value`` is a well-formed id of the given type."""
    head, sep, body = value.partition("_")
    if not sep or head != prefix:
        return False
    try:
        ULID.from_str(body)
    except (ValueError, TypeError):
        return False
    return True
