# SPDX-License-Identifier: Apache-2.0
"""Cookware: tools used by an action.

Cookware is an *attribute of an action*, not a node in the graph. The DAG models
food-states and the actions between them; a whisk is neither. Promoting tools to
nodes is the academic-ontology mistake ``docs/architecture/dag-model.md`` argues
against -- it complicates every renderer for fidelity a cooking app does not use.

Unlike ingredients, cookware has no shared registry in M1: a "large bowl" needs
no density, no nutrition and no piece weight, so there is nothing to normalise
it against. Its name is therefore carried as :class:`LocalizedText` directly on
the use, translated as prose like the rest of a step's text.
"""

from __future__ import annotations

from decimal import Decimal

from snapcook_core.ids import CookwareUseId
from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.i18n import LocalizedText

__all__ = ["CookwareUse"]


class CookwareUse(SnapcookModel):
    """One tool used by an action. "a large bowl", "2 baking sheets"."""

    id: CookwareUseId
    name: LocalizedText
    quantity: Decimal | None = None
    """How many. ``None`` reads as one; kept as a bare number because cookware
    counts do not scale and carry no unit."""

    notes: LocalizedText | None = None
