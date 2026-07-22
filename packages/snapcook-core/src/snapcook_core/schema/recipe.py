# SPDX-License-Identifier: Apache-2.0
"""The recipe: a validated directed acyclic graph of actions.

This is the top of the schema. Everything below it -- quantities, ingredients,
the graph edges -- exists to be assembled here into one immutable, hashable
value.

The graph invariants are enforced **at construction**, so an invalid graph can
never be built, hashed or stored. ``docs/architecture/dag-model.md`` states the
rule plainly: an invalid graph must be unhashable. A cyclic recipe is not a
recipe with a bug in it, it is not a recipe, and the type system should say so
before any hash is computed.

The four invariants and the failure each prevents:

single-writer outputs
    Two actions producing the same food-state id means the state has no defined
    value -- which action's output *is* "the dough"? Rejected as a
    :class:`~snapcook_core.errors.GraphError`.

no dangling references
    An action consuming a food-state that nothing produces is a step that reads
    from nowhere. Rejected as a
    :class:`~snapcook_core.errors.DanglingReferenceError`.

acyclic
    A cycle means a step depends, transitively, on its own output. There is no
    order to cook it in. Rejected as a
    :class:`~snapcook_core.errors.CyclicGraphError`.

at least one terminal
    A recipe with no final state produces nothing. The terminals are the dish
    (or dishes); a recipe must have one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from snapcook_core.errors import CyclicGraphError, DanglingReferenceError, GraphError
from snapcook_core.ids import ActionId, FoodStateId, RecipeId
from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.graph import Action
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.ingredient import IngredientUse
from snapcook_core.schema.provenance import Provenance

__all__ = ["Recipe", "Visibility"]

Visibility = Literal["private", "unlisted", "public"]


class Recipe(SnapcookModel):
    """One recipe, as authoritative content.

    Carries only what belongs in the file store. Access control that is *about*
    a recipe but not *part* of it -- who liked it, who may comment -- lives in
    Postgres, never here. ``visibility``, ``license`` and ``source`` are the
    exception: they are properties of the published recipe itself, which is why
    ``docs/architecture/projection.md`` lists them under "lives in files".
    """

    id: RecipeId
    source_lang: str = "en"
    """The language the prose was authored in. The fallback of last resort when
    resolving any :class:`LocalizedText`, and the ``source`` a translation is
    checked stale against."""

    title: LocalizedText
    description: LocalizedText | None = None
    servings: int | None = None

    visibility: Visibility = "private"
    tags: list[str] = []

    actions: list[Action]
    provenance: Provenance = Provenance()

    # -- graph invariants, enforced at construction ---------------------------

    @model_validator(mode="after")
    def _validate_graph(self) -> Recipe:
        if not self.actions:
            raise GraphError(f"recipe {self.id} has no actions")

        producer: dict[FoodStateId, ActionId] = {}
        for action in self.actions:
            state_id = action.produces.id
            if state_id in producer:
                raise GraphError(
                    f"food-state {state_id} is produced by two actions "
                    f"({producer[state_id]} and {action.id}); outputs are single-writer"
                )
            producer[state_id] = action.id

        for action in self.actions:
            for used in action.uses:
                if used not in producer:
                    raise DanglingReferenceError(
                        f"action {action.id} consumes food-state {used}, which no action produces"
                    )

        self._assert_acyclic(producer)

        if not self.terminal_state_ids:
            raise GraphError(
                f"recipe {self.id} has no terminal state; every food-state is consumed"
            )
        return self

    def _assert_acyclic(self, producer: dict[FoodStateId, ActionId]) -> None:
        """Kahn's algorithm over the action dependency graph.

        Action A depends on action B when A consumes a state B produces. If a
        topological order cannot cover every action, a cycle remains.
        """
        by_id = {action.id: action for action in self.actions}
        indegree: dict[ActionId, int] = {action.id: 0 for action in self.actions}
        dependents: dict[ActionId, list[ActionId]] = {action.id: [] for action in self.actions}

        for action in self.actions:
            for used in action.uses:
                upstream = producer[used]
                if upstream == action.id:
                    raise CyclicGraphError(f"action {action.id} consumes its own output")
                indegree[action.id] += 1
                dependents[upstream].append(action.id)

        ready = [aid for aid, deg in indegree.items() if deg == 0]
        emitted = 0
        while ready:
            current = ready.pop()
            emitted += 1
            for nxt in dependents[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)

        if emitted != len(by_id):
            stuck = sorted(aid for aid, deg in indegree.items() if deg > 0)
            raise CyclicGraphError(
                f"recipe {self.id} action graph contains a cycle involving {stuck}"
            )

    # -- derived accessors ----------------------------------------------------

    @property
    def produced_states(self) -> dict[FoodStateId, ActionId]:
        """Map every food-state id to the action that produces it."""
        return {action.produces.id: action.id for action in self.actions}

    @property
    def terminal_state_ids(self) -> list[FoodStateId]:
        """Food-states produced but consumed by nothing -- the dish(es)."""
        consumed = {used for action in self.actions for used in action.uses}
        return [action.produces.id for action in self.actions if action.produces.id not in consumed]

    @property
    def ingredient_uses(self) -> list[IngredientUse]:
        """Every ingredient use in the recipe, in authored action order."""
        return [use for action in self.actions for use in action.ingredients]
