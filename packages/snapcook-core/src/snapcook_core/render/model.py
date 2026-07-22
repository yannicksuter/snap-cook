# SPDX-License-Identifier: Apache-2.0
"""The render model: one intermediate, three renderers.

Every renderer -- text, Mermaid, print -- is a pure walk over a
:class:`RenderModel`. The alternative is three implementations of "what does
250 g of flour look like in US customary at 1.5x", and they drift. Funnelling
all of language resolution, scaling, conversion, rounding and toposort into a
single build step makes each renderer a pure function of a data structure, which
is also what makes them trivially golden-testable.

These are plain frozen dataclasses, not schema models: a render model is
ephemeral and never hashed or stored, so it carries none of the canonical-form
machinery. Every string here is already resolved for one reader -- one language,
one unit system, one scale -- so a renderer never has to make a choice.

:class:`RenderedQuantity` keeps both ``exact`` and ``display``. The exact value
is what a *re-scale* multiplies, so rounding never compounds: going to 1.5x and
back to 1x returns the original number rather than something that has drifted
through two roundings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from snapcook_core.errors import ValidationIssue

__all__ = [
    "RenderModel",
    "RenderedIngredient",
    "RenderedQuantity",
    "RenderedStep",
    "RenderedTemperature",
    "RenderedTimer",
    "RenderGraph",
    "RenderEdge",
    "RenderNode",
]


@dataclass(frozen=True, slots=True)
class RenderedQuantity:
    """A quantity resolved for display, keeping the exact value alongside."""

    display: str
    exact: Decimal | None = None
    exact_unit: str | None = None
    after_name: bool = False
    """True for an approximation ("to taste"), which reads naturally *after* the
    ingredient name -- "salt to taste", not "to taste salt"."""


@dataclass(frozen=True, slots=True)
class RenderedIngredient:
    """One ingredient line, resolved for one reader."""

    use_id: str
    name: str
    quantity: RenderedQuantity | None = None
    optional: bool = False
    prep: str | None = None
    notes: str | None = None
    unresolved: bool = False
    """True if the binding or unit could not be resolved, so a UI can flag it
    rather than presenting a guess as fact."""


@dataclass(frozen=True, slots=True)
class RenderedTimer:
    label: str | None
    display: str


@dataclass(frozen=True, slots=True)
class RenderedTemperature:
    display: str


@dataclass(frozen=True, slots=True)
class RenderedStep:
    """One step: its prose already substituted, plus its structured parts."""

    action_id: str
    index: int
    text: str
    verb: str | None = None
    ingredients: tuple[RenderedIngredient, ...] = ()
    cookware: tuple[str, ...] = ()
    timers: tuple[RenderedTimer, ...] = ()
    temperatures: tuple[RenderedTemperature, ...] = ()
    produces: str | None = None
    uses: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderNode:
    id: str
    label: str
    kind: str  # "ingredient" | "state" | "join"


@dataclass(frozen=True, slots=True)
class RenderEdge:
    src: str
    dst: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class RenderGraph:
    nodes: tuple[RenderNode, ...] = ()
    edges: tuple[RenderEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderModel:
    """A whole recipe resolved for one reader."""

    recipe_id: str
    title: str
    lang: str
    system: str
    scale: Decimal
    description: str | None = None
    servings: str | None = None
    ingredients: tuple[RenderedIngredient, ...] = ()
    steps: tuple[RenderedStep, ...] = ()
    graph: RenderGraph = field(default_factory=RenderGraph)
    warnings: tuple[ValidationIssue, ...] = ()
