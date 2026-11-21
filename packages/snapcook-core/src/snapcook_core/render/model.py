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
    seconds: int | None = None
    """How long to count down: a range from its lower end, when to first check.
    None when the time cannot be read as a duration."""


@dataclass(frozen=True, slots=True)
class RenderedTemperature:
    display: str
    """The value with its oven setting, if any: "155 °C fan", "155 °C Umluft"."""
    mode: str | None = None
    value: str = ""
    """The value alone, "155 °C", for where the setting is named apart from it."""
    setting: str | None = None
    """The setting's name alone, in the reader's language: "Umluft"."""


@dataclass(frozen=True, slots=True)
class RenderedTime:
    """The recipe's times as a reader sees them: "2 h 10 min"."""

    total: str | None = None
    at_least: bool = False
    """True when ``total`` is a lower bound worked out from the timers along
    the longest chain of steps, because the source states none."""
    prep: str | None = None
    cook: str | None = None
    rest: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedStep:
    """One step: its prose already substituted, plus its structured parts."""

    action_id: str
    index: int
    text: str
    section: str | None = None
    """The part of the recipe the step is in, as the source names it ("Teig")."""
    summary: str = ""
    """The step's first sentence with ingredient names but no amounts, short
    enough for a box in the flowchart, where the amounts have boxes of their own."""
    verb: str | None = None
    ingredients: tuple[RenderedIngredient, ...] = ()
    cookware: tuple[str, ...] = ()
    timers: tuple[RenderedTimer, ...] = ()
    temperatures: tuple[RenderedTemperature, ...] = ()
    produces: str | None = None
    uses: tuple[str, ...] = ()
    after: tuple[int, ...] = ()
    """Indices of the earlier steps whose results this step uses, ascending.

    The graph's edges in a reader's terms: step 3 of a tomato sauce combines
    what steps 1 and 2 made, so ``after == (1, 2)``. Indices rather than state
    labels, because two states may share a label and a step number is what a
    page can show."""


@dataclass(frozen=True, slots=True)
class RenderNode:
    """One shape in the flowchart, with its parts kept apart for a renderer to set."""

    id: str
    label: str
    """The name: an ingredient's, a step's summary, a result's, the dish's."""
    kind: str  # "ingredient" | "step" | "state" | "dish"
    number: int | None = None
    """A step's number, as in the method."""
    amount: str = ""
    """An ingredient's amount; after the name when ``amount_after`` ("to taste")."""
    amount_after: bool = False
    times: tuple[str, ...] = ()
    """A step's timers, as displayed."""
    temperatures: tuple[RenderedTemperature, ...] = ()
    """A step's temperatures, each with its oven setting."""


@dataclass(frozen=True, slots=True)
class RenderEdge:
    src: str
    dst: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class RenderedSection:
    """A part of the recipe as its source names it, such as the dough or the glaze."""

    title: str | None
    """None for the steps outside every part, in a recipe that has parts."""
    ingredients: tuple[RenderedIngredient, ...] = ()
    """What the part's steps use, in their order."""
    steps: tuple[int, ...] = ()


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
    sections: tuple[RenderedSection, ...] = ()
    """The recipe's parts, each once, in the order they start, with their
    ingredients: a page lists the ingredients under the same headings as the
    source. Empty when the source has no parts, which is most recipes."""
    side_by_side: tuple[tuple[int, ...], ...] = ()
    """Runs of consecutive steps that do not depend on one another.

    Each run lists step indices that a cook can work on in parallel, such as
    ``(1, 2)`` when the onions soften while the tomatoes are crushed. A linear
    recipe has none. Only consecutive steps are grouped, because "steps 1 and
    4 are independent" is true of many recipes and useful in none."""
    graph: RenderGraph = field(default_factory=RenderGraph)
    warnings: tuple[ValidationIssue, ...] = ()
    time: RenderedTime | None = None
    oven: tuple[RenderedTemperature, ...] = ()
    """The oven settings the recipe uses, each once, in the order it uses them."""
