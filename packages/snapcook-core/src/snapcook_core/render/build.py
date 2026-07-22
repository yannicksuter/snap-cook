# SPDX-License-Identifier: Apache-2.0
"""Build a :class:`RenderModel` from a recipe for one reader.

This is the funnel ``docs/architecture/rendering.md`` describes. It does, in
order: resolve translations with a fallback chain, scale, convert units, round,
topologically sort, collect the ingredient lines, build the graph, and gather
warnings. Every renderer downstream is then a pure walk with no decisions left
to make -- which is the whole reason the intermediate exists.

The order is not arbitrary. Scaling happens on the *exact* stored value before
any rounding, so a 1.5x view and the 1x it came from never disagree by a
rounding step. Unit selection happens after scaling, because the right display
unit depends on the scaled magnitude (1500 g wants to read as 1.5 kg). Rounding
is dead last and display-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from snapcook_core.errors import (
    CODE_INGREDIENT_UNBOUND,
    CODE_UNIT_UNRESOLVED,
    IssueCollector,
)
from snapcook_core.registry import IngredientRegistry, default_registry
from snapcook_core.render.model import (
    RenderEdge,
    RenderedIngredient,
    RenderedQuantity,
    RenderedStep,
    RenderedTemperature,
    RenderedTimer,
    RenderGraph,
    RenderModel,
    RenderNode,
)
from snapcook_core.render.toposort import topological_actions
from snapcook_core.schema.graph import (
    Action,
    CookwareChunk,
    IngredientChunk,
    LiteralChunk,
    StateChunk,
    Temperature,
    TemperatureChunk,
    Timer,
    TimerChunk,
)
from snapcook_core.schema.ingredient import Ingredient, IngredientUse
from snapcook_core.schema.quantity import (
    Approx,
    Count,
    QuantitySpec,
    Range,
    Scalar,
    ScalingPolicy,
    UnitRef,
)
from snapcook_core.schema.recipe import Recipe
from snapcook_core.units.density import convert_value
from snapcook_core.units.registry import System, dimension_of, unit_def
from snapcook_core.units.rounding import (
    RoundingProfile,
    format_quantity,
    metric_profile,
    us_profile,
)
from snapcook_core.units.scaling import scale_spec

__all__ = ["RenderOptions", "build_render_model"]

_QUARTER_CUP_ML = Decimal("59")  # promote to cups above ~1/4 cup


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """What one reader wants: language, unit system, scale."""

    lang: str = "en"
    system: System = "metric"
    scale: Decimal = Decimal(1)
    registry: IngredientRegistry | None = None
    rounding: RoundingProfile | None = None

    def profile(self) -> RoundingProfile:
        if self.rounding is not None:
            return self.rounding
        return us_profile() if self.system in ("us", "imperial") else metric_profile()


def build_render_model(recipe: Recipe, options: RenderOptions | None = None) -> RenderModel:
    """Resolve a recipe for one reader into a walkable render model."""
    opts = options or RenderOptions()
    registry = opts.registry or default_registry()
    issues = IssueCollector()

    ordered = topological_actions(recipe)
    state_names = _state_labels(recipe, ordered, opts, registry)

    steps: list[RenderedStep] = []
    all_ingredient_lines: list[RenderedIngredient] = []
    for index, action in enumerate(ordered, start=1):
        step = _render_step(action, index, recipe, opts, registry, issues, state_names)
        steps.append(step)
        all_ingredient_lines.extend(step.ingredients)
    steps_by_action = {step.action_id: step for step in steps}

    title, _ = recipe.title.resolve(opts.lang, source=recipe.source_lang)
    description = None
    if recipe.description is not None:
        description, _ = recipe.description.resolve(opts.lang, source=recipe.source_lang)

    return RenderModel(
        recipe_id=recipe.id,
        title=title,
        lang=opts.lang,
        system=opts.system,
        scale=opts.scale,
        description=description,
        servings=_scaled_servings(recipe.servings, opts.scale),
        ingredients=tuple(all_ingredient_lines),
        steps=tuple(steps),
        graph=_build_graph(recipe, ordered, steps_by_action, state_names),
        warnings=tuple(issues.issues),
    )


# -- steps --------------------------------------------------------------------


def _render_step(
    action: Action,
    index: int,
    recipe: Recipe,
    opts: RenderOptions,
    registry: IngredientRegistry,
    issues: IssueCollector,
    state_names: dict[str, str],
) -> RenderedStep:
    rendered_ings = {
        use.id: _render_ingredient(use, recipe, opts, registry, issues)
        for use in action.ingredients
    }
    rendered_cook = {
        item.id: _resolve_localized(item.name, recipe, opts) for item in action.cookware
    }
    rendered_timers = [_render_timer(t, recipe, opts, issues, action.id) for t in action.timers]
    rendered_temps = [_render_temperature(t, opts) for t in action.temperatures]

    text = _render_text(
        action,
        recipe,
        opts,
        rendered_ings,
        rendered_cook,
        rendered_timers,
        rendered_temps,
        state_names,
    )
    verb = _resolve_localized(action.verb, recipe, opts) if action.verb else None

    return RenderedStep(
        action_id=action.id,
        index=index,
        text=text,
        verb=verb,
        ingredients=tuple(rendered_ings[use.id] for use in action.ingredients),
        cookware=tuple(rendered_cook.values()),
        timers=tuple(rendered_timers),
        temperatures=tuple(rendered_temps),
        produces=state_names.get(action.produces.id),
        uses=tuple(state_names.get(sid, sid) for sid in action.uses),
    )


def _render_text(
    action: Action,
    recipe: Recipe,
    opts: RenderOptions,
    rendered_ings: dict[str, RenderedIngredient],
    rendered_cook: dict[str, str],
    rendered_timers: list[RenderedTimer],
    rendered_temps: list[RenderedTemperature],
    state_names: dict[str, str],
) -> str:
    if action.text is None:
        return _fallback_text(action, rendered_ings, recipe, opts)

    parts: list[str] = []
    for chunk in action.text.chunks:
        if isinstance(chunk, LiteralChunk):
            resolved, _ = chunk.text.resolve(opts.lang, source=recipe.source_lang)
            parts.append(resolved)
        elif isinstance(chunk, IngredientChunk):
            parts.append(_ingredient_inline(rendered_ings[chunk.ref]))
        elif isinstance(chunk, CookwareChunk):
            parts.append(rendered_cook[chunk.ref])
        elif isinstance(chunk, StateChunk):
            parts.append(state_names.get(chunk.ref, chunk.ref))
        elif isinstance(chunk, TimerChunk):
            parts.append(rendered_timers[chunk.index].display)
        elif isinstance(chunk, TemperatureChunk):
            parts.append(rendered_temps[chunk.index].display)
    return "".join(parts)


def _fallback_text(
    action: Action,
    rendered_ings: dict[str, RenderedIngredient],
    recipe: Recipe,
    opts: RenderOptions,
) -> str:
    """A readable line for a step with no authored prose.

    A linear step needs no prose to be renderable -- "Combine flour and water"
    is derivable from the verb and the ingredients -- so a missing template is
    not an error, just a plainer sentence.
    """
    verb = _resolve_localized(action.verb, recipe, opts) if action.verb else "Combine"
    names = [_ingredient_inline(rendered_ings[use.id]) for use in action.ingredients]
    if names:
        return f"{verb} {', '.join(names)}.".strip()
    return f"{verb}.".strip()


def _ingredient_inline(ri: RenderedIngredient) -> str:
    if ri.quantity is None:
        return ri.name
    if ri.quantity.after_name:
        return f"{ri.name} {ri.quantity.display}"
    return f"{ri.quantity.display} {ri.name}"


# Size grades are a small closed vocabulary, so a lookup table localises them
# without the weight of routing every count through the registry.
_SIZE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "tiny": "tiny",
        "small": "small",
        "medium": "medium",
        "large": "large",
        "xlarge": "extra-large",
    },
    "de": {
        "tiny": "winzige",
        "small": "kleine",
        "medium": "mittlere",
        "large": "große",
        "xlarge": "sehr große",
    },
}


def _size_label(size, lang: str) -> str | None:
    if size is None:
        return None
    table = _SIZE_LABELS.get(lang.split("-", 1)[0], _SIZE_LABELS["en"])
    return table.get(size.value, size.value)


# An approximation is a closed vocabulary too, so "to taste" reads as "nach
# Geschmack" for a German reader rather than staying stubbornly English. The
# authored surface is the fallback for a language not covered here.
_APPROX_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "pinch": "a pinch",
        "dash": "a dash",
        "splash": "a splash",
        "drizzle": "a drizzle",
        "handful": "a handful",
        "knob": "a knob",
        "to_taste": "to taste",
        "as_needed": "as needed",
        "for_garnish": "for garnish",
        "for_frying": "for frying",
        "to_cover": "to cover",
    },
    "de": {
        "pinch": "eine Prise",
        "dash": "ein Spritzer",
        "splash": "ein Schuss",
        "drizzle": "etwas zum Beträufeln",
        "handful": "eine Handvoll",
        "knob": "ein Stück",
        "to_taste": "nach Geschmack",
        "as_needed": "nach Bedarf",
        "for_garnish": "zum Garnieren",
        "for_frying": "zum Braten",
        "to_cover": "zum Bedecken",
    },
}


def _approx_label(token: str, lang: str, surface: str) -> str:
    table = _APPROX_LABELS.get(lang.split("-", 1)[0])
    if table is None:
        return surface
    return table.get(token, surface)


# -- ingredients --------------------------------------------------------------


def _render_ingredient(
    use: IngredientUse,
    recipe: Recipe,
    opts: RenderOptions,
    registry: IngredientRegistry,
    issues: IssueCollector,
) -> RenderedIngredient:
    ingredient = registry.get(use.ingredient_id)
    if use.ingredient_id is not None and ingredient is None:
        issues.add(
            CODE_INGREDIENT_UNBOUND, f"unknown ingredient id {use.ingredient_id}", element_id=use.id
        )
    if ingredient is None:
        name = use.name
        if use.ingredient_id is None:
            issues.add(
                CODE_INGREDIENT_UNBOUND,
                f"ingredient {use.name!r} is not bound to the registry; cannot translate",
                severity="info",
                element_id=use.id,
            )
    else:
        name = ingredient.name_for(opts.lang, source=recipe.source_lang) or use.name

    quantity = None
    unresolved = False
    if use.quantity is not None:
        quantity, unresolved = _render_quantity(use.quantity, ingredient, opts, issues, use.id)

    prep = _resolve_localized(use.prep, recipe, opts) if use.prep else None
    notes = _resolve_localized(use.notes, recipe, opts) if use.notes else None

    return RenderedIngredient(
        use_id=use.id,
        name=name,
        quantity=quantity,
        optional=use.optional,
        prep=prep,
        notes=notes,
        unresolved=unresolved or (ingredient is None and use.ingredient_id is not None),
    )


def _render_quantity(
    spec: QuantitySpec,
    ingredient: Ingredient | None,
    opts: RenderOptions,
    issues: IssueCollector,
    element_id: str,
) -> tuple[RenderedQuantity, bool]:
    scaled = scale_spec(spec, opts.scale, issues=issues, element_id=element_id)
    quantity = scaled.quantity
    profile = opts.profile()
    divisible = ingredient.divisible if ingredient is not None else True

    if isinstance(quantity, Approx):
        label = _approx_label(quantity.token.value, opts.lang, quantity.surface)
        return RenderedQuantity(display=label, after_name=True), False

    if isinstance(quantity, Count):
        bare = quantity.model_copy(update={"size": None})
        number = format_quantity(bare, profile, divisible=divisible)
        size_word = _size_label(quantity.size, opts.lang)
        display = f"{number} {size_word}" if size_word else number
        return RenderedQuantity(display=display, exact=quantity.value), False

    unit_id = quantity.unit.unit_id if quantity.unit else None
    if unit_id is None or unit_def(unit_id) is None:
        if quantity.unit is not None and unit_id is None:
            issues.add(
                CODE_UNIT_UNRESOLVED,
                f"unit {quantity.unit.surface!r} not resolved; cannot convert",
                element_id=element_id,
            )
        return RenderedQuantity(
            display=format_quantity(quantity, profile)
        ), unit_id is None and quantity.unit is not None

    if isinstance(quantity, Scalar):
        target, value = _choose_display_unit(quantity.value, unit_id, opts.system)
        shown = Scalar(value=value, unit=_unit_ref(target))
        return (
            RenderedQuantity(
                display=format_quantity(shown, profile, divisible=divisible),
                exact=value,
                exact_unit=target,
            ),
            False,
        )

    if isinstance(quantity, Range):
        target, _ = _choose_display_unit(quantity.high, unit_id, opts.system)
        low = convert_value(quantity.low, unit_id, target)
        high = convert_value(quantity.high, unit_id, target)
        shown = Range(low=low, high=high, unit=_unit_ref(target))
        return (
            RenderedQuantity(
                display=format_quantity(shown, profile, divisible=divisible),
                exact=high,
                exact_unit=target,
            ),
            False,
        )

    return RenderedQuantity(display=format_quantity(quantity, profile)), False


def _unit_ref(unit_id: str) -> UnitRef:
    definition = unit_def(unit_id)
    symbol = definition.symbol if definition else unit_id
    return UnitRef(unit_id=unit_id, surface=symbol)


def _choose_display_unit(value: Decimal, source_unit: str, system: System) -> tuple[str, Decimal]:
    """Pick the unit to show a magnitude in, and convert to it.

    Promotion is by magnitude: grams become kilograms past 1 kg; millilitres in
    US customary become teaspoons, tablespoons or cups by size. This is what
    turns 1500 g into 1.5 kg and 15 ml into 1 tbsp rather than leaving a reader
    to divide in their head.
    """
    dimension = dimension_of(source_unit)
    is_us = system in ("us", "imperial")

    if dimension == "mass":
        if is_us:
            ounces = convert_value(value, source_unit, "unit:oz")
            if abs(ounces) >= 16:
                return "unit:lb", convert_value(value, source_unit, "unit:lb")
            return "unit:oz", ounces
        grams = convert_value(value, source_unit, "unit:g")
        if abs(grams) >= 1000:
            return "unit:kg", convert_value(value, source_unit, "unit:kg")
        return "unit:g", grams

    if dimension == "volume":
        millilitres = convert_value(value, source_unit, "unit:ml")
        if is_us:
            if abs(millilitres) >= _QUARTER_CUP_ML:
                return "unit:cup.us", convert_value(value, source_unit, "unit:cup.us")
            if abs(millilitres) >= 15:
                return "unit:tbsp", convert_value(value, source_unit, "unit:tbsp")
            return "unit:tsp", convert_value(value, source_unit, "unit:tsp")
        if abs(millilitres) >= 1000:
            return "unit:l", convert_value(value, source_unit, "unit:l")
        return "unit:ml", millilitres

    return source_unit, value


# -- timers, temperatures -----------------------------------------------------


def _render_timer(
    timer: Timer,
    recipe: Recipe,
    opts: RenderOptions,
    issues: IssueCollector,
    element_id: str,
) -> RenderedTimer:
    # A timer never auto-scales; routing it through scale_spec with a MANUAL
    # policy records the "check this for a larger batch" warning when scaled.
    spec = QuantitySpec(quantity=timer.quantity, scaling=ScalingPolicy.MANUAL)
    scaled = scale_spec(spec, opts.scale, issues=issues, element_id=element_id)
    display = format_quantity(scaled.quantity, metric_profile())
    label = _resolve_localized(timer.name, recipe, opts) if timer.name else None
    return RenderedTimer(label=label, display=display)


def _render_temperature(temperature: Temperature, opts: RenderOptions) -> RenderedTemperature:
    unit = "F" if opts.system in ("us", "imperial") else "C"
    value = temperature.value_in(unit)
    # Ovens are set in steps, not to the exact conversion; snapping to 5°
    # turns 356 °F into a dial a reader actually has.
    rounded = (value / 5).quantize(Decimal(1)) * 5
    return RenderedTemperature(display=f"{rounded} °{unit}")


# -- graph --------------------------------------------------------------------


def _state_labels(
    recipe: Recipe,
    ordered: list[Action],
    opts: RenderOptions,
    registry: IngredientRegistry,
) -> dict[str, str]:
    """A display label for every produced food-state.

    Named states use their name; an anonymous intermediate borrows its action's
    verb, or the step number as a last resort, so the graph never shows a raw id.
    """
    labels: dict[str, str] = {}
    for index, action in enumerate(ordered, start=1):
        state = action.produces
        if state.name is not None:
            labels[state.id], _ = state.name.resolve(opts.lang, source=recipe.source_lang)
        elif action.verb is not None:
            verb, _ = action.verb.resolve(opts.lang, source=recipe.source_lang)
            labels[state.id] = verb
        else:
            labels[state.id] = f"step {index}"
    return labels


def _build_graph(
    recipe: Recipe,
    ordered: list[Action],
    steps_by_action: dict[str, RenderedStep],
    state_names: dict[str, str],
) -> RenderGraph:
    nodes: list[RenderNode] = []
    edges: list[RenderEdge] = []
    seen: set[str] = set()

    def add_node(node: RenderNode) -> None:
        if node.id not in seen:
            seen.add(node.id)
            nodes.append(node)

    for action in ordered:
        add_node(
            RenderNode(id=action.produces.id, label=state_names[action.produces.id], kind="state")
        )

    for action in ordered:
        step = steps_by_action[action.id]
        inputs: list[str] = list(action.uses)
        for use, rendered in zip(action.ingredients, step.ingredients):
            add_node(RenderNode(id=use.id, label=_ingredient_inline(rendered), kind="ingredient"))
            inputs.append(use.id)

        label = _edge_label(step)
        target = action.produces.id
        if len(inputs) <= 1:
            for src in inputs:
                edges.append(RenderEdge(src=src, dst=target, label=label))
            if not inputs:  # a source step with no inputs at all
                add_node(RenderNode(id=f"start_{action.id}", label="start", kind="state"))
                edges.append(RenderEdge(src=f"start_{action.id}", dst=target, label=label))
        else:
            # A hyperedge (many inputs, one output) cannot be one labelled edge,
            # so a join node carries the verb.
            join = f"join_{action.id}"
            add_node(RenderNode(id=join, label=step.verb or "combine", kind="join"))
            for src in inputs:
                edges.append(RenderEdge(src=src, dst=join))
            edges.append(RenderEdge(src=join, dst=target, label=label))

    return RenderGraph(nodes=tuple(nodes), edges=tuple(edges))


def _edge_label(step: RenderedStep) -> str:
    """The action label for a flowchart edge: verb, duration and temperature.

    The Mermaid renderer ignores prose and walks the graph, so the edge is where
    a reader learns "mix, 3 min @ 220 °C". Assembled from the already-rendered
    step so scaling and unit choice are not redone.
    """
    parts: list[str] = []
    if step.verb:
        parts.append(step.verb)
    for timer in step.timers:
        parts.append(f"{timer.label + ' ' if timer.label else ''}{timer.display}")
    label = ", ".join(parts)
    if step.temperatures:
        label = f"{label} @ {' / '.join(t.display for t in step.temperatures)}".strip(" @")
    return label


# -- helpers ------------------------------------------------------------------


def _resolve_localized(text, recipe: Recipe, opts: RenderOptions) -> str:
    resolved, _ = text.resolve(opts.lang, source=recipe.source_lang)
    return resolved


def _scaled_servings(servings: int | None, scale: Decimal) -> str | None:
    if servings is None:
        return None
    scaled = Decimal(servings) * scale
    if scaled == scaled.to_integral_value():
        return str(int(scaled))
    return format(scaled.normalize(), "f")
