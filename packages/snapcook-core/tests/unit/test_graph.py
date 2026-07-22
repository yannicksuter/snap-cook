# SPDX-License-Identifier: Apache-2.0
"""Graph construction invariants.

The whole point of enforcing these at construction is that an invalid graph is
*unhashable* -- it cannot be built, so it can never reach the store. These tests
pin each refusal, because a regression here would let a malformed recipe be
committed and only surface as a broken render much later.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snapcook_core.canonical import content_hash
from snapcook_core.errors import CyclicGraphError, DanglingReferenceError, GraphError
from snapcook_core.schema.graph import (
    Action,
    FoodState,
    IngredientChunk,
    LiteralChunk,
    Temperature,
    TextTemplate,
    TimerChunk,
)
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.ingredient import IngredientUse
from snapcook_core.schema.recipe import Recipe


def _loc(text: str) -> LocalizedText:
    return LocalizedText.mono("en", text)


def _state(sid: str, name: str | None = None) -> FoodState:
    return FoodState(id=sid, name=_loc(name) if name else None)


def _recipe(actions) -> Recipe:
    return Recipe(id="rcp_t", source_lang="en", title=_loc("t"), actions=actions)


def test_linear_recipe_is_valid_and_hashable() -> None:
    a1 = Action(id="act_1", order=0, produces=_state("nod_1"))
    a2 = Action(id="act_2", order=1, uses=["nod_1"], produces=_state("nod_2"))
    recipe = _recipe([a1, a2])
    assert recipe.terminal_state_ids == ["nod_2"]
    assert content_hash(recipe).startswith("sc1:")


def test_cycle_is_rejected() -> None:
    a1 = Action(id="act_1", uses=["nod_2"], produces=_state("nod_1"))
    a2 = Action(id="act_2", uses=["nod_1"], produces=_state("nod_2"))
    with pytest.raises(CyclicGraphError):
        _recipe([a1, a2])


def test_self_loop_is_rejected() -> None:
    a1 = Action(id="act_1", uses=["nod_1"], produces=_state("nod_1"))
    with pytest.raises(CyclicGraphError):
        _recipe([a1])


def test_dangling_input_is_rejected() -> None:
    a1 = Action(id="act_1", uses=["nod_missing"], produces=_state("nod_1"))
    with pytest.raises(DanglingReferenceError):
        _recipe([a1])


def test_two_actions_producing_one_state_is_rejected() -> None:
    a1 = Action(id="act_1", produces=_state("nod_shared"))
    a2 = Action(id="act_2", produces=_state("nod_shared"))
    with pytest.raises(GraphError):
        _recipe([a1, a2])


def test_recipe_with_no_actions_is_rejected() -> None:
    with pytest.raises(GraphError):
        _recipe([])


def test_text_referencing_absent_ingredient_is_rejected() -> None:
    with pytest.raises(DanglingReferenceError):
        Action(
            id="act_1",
            produces=_state("nod_1"),
            text=TextTemplate(chunks=[IngredientChunk(ref="iuse_ghost")]),
        )


def test_text_referencing_out_of_range_timer_is_rejected() -> None:
    with pytest.raises(DanglingReferenceError):
        Action(
            id="act_1",
            produces=_state("nod_1"),
            text=TextTemplate(chunks=[TimerChunk(index=3)]),
        )


def test_duplicate_ingredient_use_id_is_rejected() -> None:
    use_a = IngredientUse(id="iuse_dup", name="flour")
    use_b = IngredientUse(id="iuse_dup", name="sugar")
    with pytest.raises(DanglingReferenceError):
        Action(id="act_1", produces=_state("nod_1"), ingredients=[use_a, use_b])


def test_valid_internal_reference_is_accepted() -> None:
    use = IngredientUse(id="iuse_1", name="flour")
    action = Action(
        id="act_1",
        produces=_state("nod_1"),
        ingredients=[use],
        text=TextTemplate(chunks=[LiteralChunk(text=_loc("Add ")), IngredientChunk(ref="iuse_1")]),
    )
    assert action.ingredients[0].id == "iuse_1"


def test_multiple_terminals_are_allowed() -> None:
    """A recipe may set two things aside -- a sauce and a garnish."""
    a1 = Action(id="act_1", produces=_state("nod_a"))
    a2 = Action(id="act_2", produces=_state("nod_b"))
    recipe = _recipe([a1, a2])
    assert set(recipe.terminal_state_ids) == {"nod_a", "nod_b"}


@pytest.mark.parametrize(
    ("celsius", "fahrenheit"),
    [
        (Decimal("0"), Decimal("32")),
        (Decimal("100"), Decimal("212")),
        (Decimal("180"), Decimal("356")),
    ],
)
def test_temperature_is_affine_not_multiplicative(celsius: Decimal, fahrenheit: Decimal) -> None:
    temp = Temperature(value=celsius, unit="C")
    assert temp.value_in("F") == fahrenheit
    assert Temperature(value=fahrenheit, unit="F").value_in("C") == celsius
