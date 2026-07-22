# SPDX-License-Identifier: Apache-2.0
"""The recipe graph: food-states, actions, and the prose that describes them.

Nodes are :class:`FoodState` values -- "the dough", "the roux". Edges are
:class:`Action` values: a step that consumes one or more inputs and produces
exactly one output state, carrying its verb, timers, temperature and cookware as
*attributes*. A step list is a topological sort of this graph; a flowchart is a
drawing of it. One model, many views.

Two measurement types live here rather than in :mod:`snapcook_core.schema.quantity`
because they behave unlike the scaling union:

:class:`Temperature`
    Affine, not multiplicative. 20 to 40 degC is not "twice as hot", and Pint
    correctly refuses arithmetic on offset units. So a temperature is its own
    type, never a :class:`~snapcook_core.schema.quantity.Scalar` with a unit, and
    it never auto-scales.

:class:`Timer`
    A duration that must never auto-scale. Doubling a recipe does not double the
    bake time. Timers therefore carry no linear scaling path at all.

A step's prose is a :class:`TextTemplate`: a sequence of chunks where literal
text is localised and every non-literal chunk is a *reference* into the action's
own ingredients, cookware, timers or temperatures. The chunk sequence is shared
across languages, which is exactly the "same slot sequence" constraint a
translation must respect -- a translator fills in the literal text between slots
and cannot reorder or invent slots.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from snapcook_core.errors import DanglingReferenceError
from snapcook_core.ids import ActionId, CookwareUseId, FoodStateId, IngredientUseId
from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.cookware import CookwareUse
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.ingredient import IngredientUse
from snapcook_core.schema.quantity import Range, Scalar

__all__ = [
    "Action",
    "CookwareChunk",
    "FoodState",
    "IngredientChunk",
    "LiteralChunk",
    "StateChunk",
    "Temperature",
    "TemperatureChunk",
    "TextChunk",
    "TextTemplate",
    "Timer",
    "TimerChunk",
]

_F_PER_C = Decimal("1.8")
_F_OFFSET = Decimal("32")


class Temperature(SnapcookModel):
    """An oven or liquid temperature. Affine, and never auto-scaled."""

    value: Decimal
    unit: Literal["C", "F"] = "C"

    def value_in(self, unit: Literal["C", "F"]) -> Decimal:
        """Convert, exactly, using the affine relation -- not a ratio."""
        if unit == self.unit:
            return self.value
        if unit == "F":
            return self.value * _F_PER_C + _F_OFFSET
        return (self.value - _F_OFFSET) / _F_PER_C


class Timer(SnapcookModel):
    """A named or anonymous duration. Never auto-scales.

    ``~{30%min}`` is anonymous; ``~proof{2%h}`` is named. The quantity is a
    :class:`Scalar` or :class:`Range` of time; there is deliberately no linear
    scaling path -- see the module docstring.
    """

    name: LocalizedText | None = None
    quantity: Scalar | Range


# -- prose chunks -------------------------------------------------------------


class LiteralChunk(SnapcookModel):
    """Literal prose between slots. The only translated part of a template."""

    kind: Literal["text"] = "text"
    text: LocalizedText


class IngredientChunk(SnapcookModel):
    """A slot rendering one of the action's ingredients."""

    kind: Literal["ingredient"] = "ingredient"
    ref: IngredientUseId


class CookwareChunk(SnapcookModel):
    """A slot rendering one of the action's cookware items."""

    kind: Literal["cookware"] = "cookware"
    ref: CookwareUseId


class StateChunk(SnapcookModel):
    """A slot consuming a prior food-state -- Cooklang's ``@&{the dough}``.

    Its ``ref`` must be one the action already lists in ``uses``: naming a state
    in the prose does not, on its own, add a graph edge. Modelling consumption as
    a prose chunk is what lets the authoring format round-trip -- the state
    reference sits exactly where the author wrote it in the sentence.
    """

    kind: Literal["state"] = "state"
    ref: FoodStateId


class TimerChunk(SnapcookModel):
    """A slot rendering one of the action's timers, by position."""

    kind: Literal["timer"] = "timer"
    index: int = 0


class TemperatureChunk(SnapcookModel):
    """A slot rendering one of the action's temperatures, by position."""

    kind: Literal["temperature"] = "temperature"
    index: int = 0


TextChunk = Annotated[
    LiteralChunk | IngredientChunk | CookwareChunk | StateChunk | TimerChunk | TemperatureChunk,
    Field(discriminator="kind"),
]


class TextTemplate(SnapcookModel):
    """The prose of a step as an ordered list of chunks."""

    chunks: list[TextChunk]


class FoodState(SnapcookModel):
    """A node: a named, referenceable intermediate or final food.

    ``name`` is ``None`` for an anonymous intermediate -- the implicit output of
    a linear step that the next step consumes without naming. Naming every state
    would tax the common linear recipe for no benefit.
    """

    id: FoodStateId
    name: LocalizedText | None = None


class Action(SnapcookModel):
    """An edge: one step, consuming inputs and producing one output state.

    ``uses`` lists the prior food-states this step consumes; ``ingredients`` the
    raw ingredients it introduces. ``produces`` is the single output node -- one
    action, one output state, which is what makes ``produces`` ids a usable
    single-writer key across the graph.

    ``order`` is the authored sequence and the toposort tie-breaker, so a linear
    recipe renders in exactly the order it was written on every machine.
    """

    id: ActionId
    order: int = 0
    verb: LocalizedText | None = None

    uses: list[FoodStateId] = []
    ingredients: list[IngredientUse] = []
    cookware: list[CookwareUse] = []
    timers: list[Timer] = []
    temperatures: list[Temperature] = []

    produces: FoodState

    text: TextTemplate | None = None
    notes: LocalizedText | None = None

    @model_validator(mode="after")
    def _internal_references_resolve(self) -> Action:
        """Every slot in the prose must point at something this action owns.

        Checked at construction, so a template referencing a timer the action
        does not have cannot be stored or hashed -- the renderer can then trust
        every ref without defensive lookups.
        """
        ingredient_ids = {use.id for use in self.ingredients}
        cookware_ids = {item.id for item in self.cookware}
        if len(ingredient_ids) != len(self.ingredients):
            raise DanglingReferenceError(f"duplicate ingredient-use id in action {self.id}")
        if len(cookware_ids) != len(self.cookware):
            raise DanglingReferenceError(f"duplicate cookware-use id in action {self.id}")

        if self.text is None:
            return self
        used_states = set(self.uses)
        for chunk in self.text.chunks:
            if isinstance(chunk, IngredientChunk) and chunk.ref not in ingredient_ids:
                raise DanglingReferenceError(
                    f"action {self.id} text references unknown ingredient {chunk.ref}"
                )
            if isinstance(chunk, CookwareChunk) and chunk.ref not in cookware_ids:
                raise DanglingReferenceError(
                    f"action {self.id} text references unknown cookware {chunk.ref}"
                )
            if isinstance(chunk, StateChunk) and chunk.ref not in used_states:
                raise DanglingReferenceError(
                    f"action {self.id} text consumes state {chunk.ref}, which is not in its uses"
                )
            if isinstance(chunk, TimerChunk) and not 0 <= chunk.index < len(self.timers):
                raise DanglingReferenceError(
                    f"action {self.id} text references timer #{chunk.index} of {len(self.timers)}"
                )
            if isinstance(chunk, TemperatureChunk) and not 0 <= chunk.index < len(
                self.temperatures
            ):
                raise DanglingReferenceError(
                    f"action {self.id} text references temperature #{chunk.index} of "
                    f"{len(self.temperatures)}"
                )
        return self
