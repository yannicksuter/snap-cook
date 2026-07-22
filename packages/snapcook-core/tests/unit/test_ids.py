# SPDX-License-Identifier: Apache-2.0
"""Identifier minting and validation.

IDs matter more than they look: a stable id on every structural element is what
lets the diff report "step 5 moved to position 2" as a single move rather than a
remove-plus-add pair. If ids were regenerated on edit, every diff would be
useless noise.
"""

from __future__ import annotations

import pytest

from snapcook_core import ids


@pytest.mark.parametrize(
    ("mint", "prefix"),
    [
        (ids.new_recipe_id, ids.RECIPE_PREFIX),
        (ids.new_ingredient_id, ids.INGREDIENT_PREFIX),
        (ids.new_ingredient_use_id, ids.INGREDIENT_USE_PREFIX),
        (ids.new_food_state_id, ids.FOOD_STATE_PREFIX),
        (ids.new_action_id, ids.ACTION_PREFIX),
        (ids.new_cookware_use_id, ids.COOKWARE_USE_PREFIX),
        (ids.new_section_id, ids.SECTION_PREFIX),
    ],
)
def test_minted_ids_carry_their_type_prefix(mint, prefix: str) -> None:
    value = mint()
    assert value.startswith(f"{prefix}_")
    assert ids.prefix_of(value) == prefix
    assert ids.is_id_of(value, prefix)


def test_ids_are_unique() -> None:
    minted = {ids.new_action_id() for _ in range(1000)}
    assert len(minted) == 1000


def test_ids_sort_chronologically() -> None:
    """ULIDs, not UUID4, so directory listings and logs read in time order."""
    first = ids.new_action_id()
    second = ids.new_action_id()
    assert first < second


def test_wrong_type_prefix_is_rejected() -> None:
    """Catches a mis-wired reference before it reaches the graph validator."""
    action = ids.new_action_id()
    assert ids.is_id_of(action, ids.ACTION_PREFIX)
    assert not ids.is_id_of(action, ids.FOOD_STATE_PREFIX)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "no-underscore",
        "act_",
        "act_not-a-valid-ulid",
        "unknown_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "act_01ARZ3NDEKTSV4RRFFQ69G5FA",  # one char short
    ],
)
def test_malformed_ids_are_rejected(value: str) -> None:
    assert not ids.is_id_of(value, ids.ACTION_PREFIX)


@pytest.mark.parametrize(
    "value",
    ["", "no-underscore", "unknown_01ARZ3NDEKTSV4RRFFQ69G5FAV", "unit:cup.us"],
)
def test_prefix_of_returns_none_for_foreign_values(value: str) -> None:
    assert ids.prefix_of(value) is None


def test_unit_ids_are_readable_slugs_not_ulids() -> None:
    """Unit ids appear in authored files and in the public API.

    A random identifier there would be hostile to anyone reading a `.cook` file
    or an API response, so unit ids are stable human-readable slugs and are
    deliberately not part of the ULID scheme.
    """
    unit = ids.UnitId("unit:cup.us")
    assert ids.prefix_of(unit) is None
