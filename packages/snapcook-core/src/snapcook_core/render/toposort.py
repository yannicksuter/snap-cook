# SPDX-License-Identifier: Apache-2.0
"""Deterministic topological ordering of a recipe's actions.

A step list is a topological sort of the action graph. The sort must be
*deterministic* -- the same graph has to produce the same order on every machine
and in every language -- because diffing and the translation-isomorphism check
both compare orderings and would see phantom differences otherwise.

Kahn's algorithm with a min-heap keyed on ``(action.order, action.id)`` gives
that. ``order`` is the authored sequence, so a linear recipe comes out in
exactly the order it was written; ``id`` breaks the rare tie between two actions
that are ready at the same moment and have the same ``order``, and since ids are
globally unique the tie-break is total. A plain queue would instead leak
insertion order, which is not stable across a reserialise.
"""

from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from snapcook_core.errors import CyclicGraphError
from snapcook_core.ids import ActionId

if TYPE_CHECKING:
    from snapcook_core.schema.graph import Action
    from snapcook_core.schema.recipe import Recipe

__all__ = ["topological_actions"]


def topological_actions(recipe: Recipe) -> list[Action]:
    """Return the recipe's actions in deterministic dependency order.

    Raises :class:`CyclicGraphError` if a cycle remains -- though a constructed
    :class:`Recipe` is already acyclic by validation, so this only fires on a
    graph assembled by bypassing the model.
    """
    by_id: dict[ActionId, Action] = {a.id: a for a in recipe.actions}
    producer = recipe.produced_states

    indegree: dict[ActionId, int] = {aid: 0 for aid in by_id}
    dependents: dict[ActionId, list[ActionId]] = {aid: [] for aid in by_id}
    for action in recipe.actions:
        for used in action.uses:
            upstream = producer[used]
            indegree[action.id] += 1
            dependents[upstream].append(action.id)

    # Heap of (order, id) so the ready action that was authored earliest, then
    # lowest id, is always emitted next.
    ready: list[tuple[int, ActionId]] = [
        (by_id[aid].order, aid) for aid, deg in indegree.items() if deg == 0
    ]
    heapq.heapify(ready)

    ordered: list[Action] = []
    while ready:
        _, current = heapq.heappop(ready)
        ordered.append(by_id[current])
        for nxt in dependents[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (by_id[nxt].order, nxt))

    if len(ordered) != len(by_id):
        raise CyclicGraphError(f"recipe {recipe.id} contains a cycle; cannot topologically sort")
    return ordered
