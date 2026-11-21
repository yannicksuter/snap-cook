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

from dataclasses import dataclass, replace
from decimal import Decimal

from snapcook_core.durations import minutes_text
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
    RenderedSection,
    RenderedStep,
    RenderedTemperature,
    RenderedTime,
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
# A metric reader keeps the recipe's own unit while its number reads well:
# "2 dl Rahm" is how a Swiss recipe says it, and two spoons are easier to
# measure than 30 ml. Outside these ranges an amount moves to ml or l.
_SPOONS_UP_TO_ML = Decimal(90)  # six tablespoons
_DL_FROM_ML, _DL_BELOW_ML = Decimal(50), Decimal(1000)  # 0.5 dl to 9.9 dl
_LITRES_FROM_ML = Decimal(250)  # 0.25 l, for a recipe that says litres
# Spoons as a German cook writes them; other units read the same everywhere.
_UNIT_LABELS = {"de": {"unit:tbsp": "EL", "unit:tsp": "TL"}}


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
    # Every action produces exactly one state, so a state names its step.
    step_of_state = {action.produces.id: index for index, action in enumerate(ordered, start=1)}

    steps: list[RenderedStep] = []
    all_ingredient_lines: list[RenderedIngredient] = []
    for index, action in enumerate(ordered, start=1):
        step = _render_step(
            action, index, recipe, opts, registry, issues, state_names, step_of_state
        )
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
        sections=_sections(steps),
        side_by_side=_side_by_side(steps),
        graph=_build_graph(recipe, ordered, steps_by_action, state_names, title),
        warnings=tuple(issues.issues),
        time=_render_time(recipe, ordered),
        oven=_oven_settings(steps),
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
    step_of_state: dict[str, int],
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
    names_only = {ref: replace(ri, quantity=None) for ref, ri in rendered_ings.items()}
    plain = _render_text(
        action,
        recipe,
        opts,
        names_only,
        rendered_cook,
        rendered_timers,
        rendered_temps,
        state_names,
    )

    return RenderedStep(
        action_id=action.id,
        index=index,
        text=text,
        section=(
            action.section.resolve(opts.lang, source=recipe.source_lang)[0]
            if action.section is not None
            else None
        ),
        summary=_summary(plain),
        verb=verb,
        ingredients=tuple(rendered_ings[use.id] for use in action.ingredients),
        cookware=tuple(rendered_cook.values()),
        timers=tuple(rendered_timers),
        temperatures=tuple(rendered_temps),
        produces=state_names.get(action.produces.id),
        uses=tuple(state_names.get(sid, sid) for sid in action.uses),
        after=tuple(sorted({step_of_state[sid] for sid in action.uses if sid in step_of_state})),
    )


def _side_by_side(steps: list[RenderedStep]) -> tuple[tuple[int, ...], ...]:
    """Group consecutive steps that share no dependency path.

    Walks the steps in order, growing a run while the next step depends on
    none of the run's steps, directly or through intermediate steps. A run of
    one is no information, so only runs of two or more are returned.
    """
    ancestors: dict[int, set[int]] = {}
    for step in steps:
        reached = set(step.after)
        for earlier in step.after:
            reached |= ancestors[earlier]
        ancestors[step.index] = reached

    runs: list[tuple[int, ...]] = []
    run: list[int] = []
    for step in steps:
        if run and any(member in ancestors[step.index] for member in run):
            if len(run) > 1:
                runs.append(tuple(run))
            run = []
        run.append(step.index)
    if len(run) > 1:
        runs.append(tuple(run))
    return tuple(runs)


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
# Geschmack" for a German reader rather than staying stubbornly English. Words
# outside it come from the recipe's glossary, or stay as authored.
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


def _approx_label(token: str, lang: str) -> str | None:
    return _APPROX_LABELS.get(lang.split("-", 1)[0], {}).get(token)


def _gloss(recipe: Recipe, lang: str, word: str) -> str:
    """``word`` in ``lang`` from the recipe's glossary, or as authored."""
    if lang == recipe.source_lang:
        return word
    table = recipe.glossary.get(lang) or recipe.glossary.get(lang.split("-", 1)[0]) or {}
    return table.get(word, word)


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
        name = _gloss(recipe, opts.lang, use.name)
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
        quantity, unresolved = _render_quantity(
            use.quantity, ingredient, recipe, opts, issues, use.id
        )

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
    recipe: Recipe,
    opts: RenderOptions,
    issues: IssueCollector,
    element_id: str,
) -> tuple[RenderedQuantity, bool]:
    scaled = scale_spec(spec, opts.scale, issues=issues, element_id=element_id)
    quantity = scaled.quantity
    profile = opts.profile()
    divisible = ingredient.divisible if ingredient is not None else True

    if isinstance(quantity, Approx):
        label = _approx_label(quantity.token.value, opts.lang)
        if label is None:
            label = _gloss(recipe, opts.lang, quantity.surface)
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
            shown_unit = quantity.unit.model_copy(
                update={"surface": _gloss(recipe, opts.lang, quantity.unit.surface)}
            )
            quantity = quantity.model_copy(update={"unit": shown_unit})
        return RenderedQuantity(
            display=format_quantity(quantity, profile)
        ), unit_id is None and quantity.unit is not None

    if isinstance(quantity, Scalar):
        target, value = _choose_display_unit(quantity.value, unit_id, opts.system)
        shown = Scalar(value=value, unit=_unit_ref(target, opts.lang))
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
        shown = Range(low=low, high=high, unit=_unit_ref(target, opts.lang))
        return (
            RenderedQuantity(
                display=format_quantity(shown, profile, divisible=divisible),
                exact=high,
                exact_unit=target,
            ),
            False,
        )

    return RenderedQuantity(display=format_quantity(quantity, profile)), False


def _unit_ref(unit_id: str, lang: str = "en") -> UnitRef:
    definition = unit_def(unit_id)
    symbol = definition.symbol if definition else unit_id
    label = _UNIT_LABELS.get(lang.split("-", 1)[0], {}).get(unit_id, symbol)
    return UnitRef(unit_id=unit_id, surface=label)


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
        size = abs(millilitres)
        if source_unit in ("unit:tsp", "unit:tbsp") and size <= _SPOONS_UP_TO_ML:
            spoon = "unit:tsp" if size < 15 else "unit:tbsp"
            return spoon, convert_value(value, source_unit, spoon)
        if source_unit == "unit:dl" and _DL_FROM_ML <= size < _DL_BELOW_ML:
            return "unit:dl", convert_value(value, source_unit, "unit:dl")
        if size >= 1000 or (source_unit == "unit:l" and size >= _LITRES_FROM_ML):
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


# The oven setting after a temperature, in the reader's language. English as
# British recipes write it, "180 °C (160 °C fan)"; German as the dial says it.
_OVEN_MODE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "conventional": "conventional",
        "top": "top heat",
        "bottom": "bottom heat",
        "fan": "fan",
        "hot_air": "hot air",
        "fan_bottom": "fan with bottom heat",
        "fan_conventional": "fan with top and bottom heat",
        "grill": "grill",
        "fan_grill": "fan grill",
    },
    "de": {
        "conventional": "Ober-/Unterhitze",
        "top": "Oberhitze",
        "bottom": "Unterhitze",
        "fan": "Umluft",
        "hot_air": "Heissluft",
        "fan_bottom": "Umluft mit Unterhitze",
        "fan_conventional": "Umluft mit Ober-/Unterhitze",
        "grill": "Grill",
        "fan_grill": "Grill mit Umluft",
    },
}


def _render_temperature(temperature: Temperature, opts: RenderOptions) -> RenderedTemperature:
    unit = "F" if opts.system in ("us", "imperial") else "C"
    # Ovens are set in steps, not to the exact conversion; snapping to 5°
    # turns 356 °F into a dial a reader actually has.
    rounded = (temperature.value_in(unit) / 5).quantize(Decimal(1)) * 5
    shown = f"{rounded} °{unit}"
    setting = None
    if temperature.mode:
        labels = _OVEN_MODE_LABELS.get(opts.lang.split("-", 1)[0], _OVEN_MODE_LABELS["en"])
        setting = labels[temperature.mode]
    return RenderedTemperature(
        display=f"{shown} {setting}" if setting else shown,
        mode=temperature.mode,
        value=shown,
        setting=setting,
    )


def _sections(steps: list[RenderedStep]) -> tuple[RenderedSection, ...]:
    """The steps' parts, each once, in the order they start, with what they use."""
    if not any(step.section for step in steps):
        return ()
    parts: dict[str | None, tuple[list[RenderedIngredient], list[int]]] = {}
    for step in steps:
        ingredients, indices = parts.setdefault(step.section, ([], []))
        ingredients.extend(step.ingredients)
        indices.append(step.index)
    return tuple(
        RenderedSection(title=title, ingredients=tuple(ingredients), steps=tuple(indices))
        for title, (ingredients, indices) in parts.items()
    )


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
    title: str,
) -> RenderGraph:
    """The recipe as a flowchart a cook can follow.

    Every step is a numbered box, so the chart and the method point at each
    other; its ingredients flow into it. A result a later step names (a dough,
    a sauce) gets a box of its own, and an unnamed one is skipped, the next step
    following straight on. What the recipe ends with is the dish, under its own
    name or, unnamed, the recipe's title. Nothing here is English unless the
    reader's language is: an imported recipe has no verbs, and placeholder words
    like "combine" read as noise in a German recipe.
    """
    nodes: list[RenderNode] = []
    edges: list[RenderEdge] = []
    terminal = set(recipe.terminal_state_ids)
    # Where a later step that uses a state connects from: the state's own box,
    # or, for an unnamed state, the step that made it.
    source_of: dict[str, str] = {}

    for action in ordered:
        step = steps_by_action[action.id]
        step_node = f"step_{action.id}"
        nodes.append(
            RenderNode(
                id=step_node,
                label=step.verb or step.summary,
                kind="step",
                number=step.index,
                times=tuple(
                    f"{timer.label + ' ' if timer.label else ''}{timer.display}"
                    for timer in step.timers
                ),
                temperatures=step.temperatures,
            )
        )
        for use, rendered in zip(action.ingredients, step.ingredients):
            quantity = rendered.quantity
            nodes.append(
                RenderNode(
                    id=use.id,
                    label=rendered.name,
                    kind="ingredient",
                    amount=quantity.display if quantity is not None else "",
                    amount_after=quantity is not None and quantity.after_name,
                )
            )
            edges.append(RenderEdge(src=use.id, dst=step_node))
        for used in action.uses:
            edges.append(RenderEdge(src=source_of.get(used, used), dst=step_node))

        state = action.produces
        if state.id in terminal:
            label = state_names[state.id] if state.name is not None else title
            nodes.append(RenderNode(id=state.id, label=label, kind="dish"))
            edges.append(RenderEdge(src=step_node, dst=state.id))
            source_of[state.id] = state.id
        elif state.name is not None:
            nodes.append(RenderNode(id=state.id, label=state_names[state.id], kind="state"))
            edges.append(RenderEdge(src=step_node, dst=state.id))
            source_of[state.id] = state.id
        else:
            source_of[state.id] = step_node

    return RenderGraph(nodes=tuple(nodes), edges=tuple(edges))


def _summary(text: str, limit: int = 90) -> str:
    """A step's first sentence; a long one keeps its start and its end.

    The middle goes, not the end, because German puts the verb last: "Die
    Quarkmasse auf den Boden geben … (155 °C Umluft) backen" still says what to
    do, where a cut at the end would drop "backen".
    """
    sentence = text.strip().split(". ", 1)[0].rstrip(".")
    if len(sentence) <= limit:
        return sentence
    head = sentence[: limit * 3 // 5].rsplit(" ", 1)[0].rstrip(",;:")
    tail = sentence[-(limit * 2 // 5) :].split(" ", 1)[-1]
    return f"{head} … {tail}"


# -- time and oven ------------------------------------------------------------


def _render_time(recipe: Recipe, ordered: list[Action]) -> RenderedTime | None:
    """The stated times; without a stated total, a lower bound from the timers."""
    stated = recipe.time
    prep = stated.prep if stated else None
    cook = stated.cook if stated else None
    rest = stated.rest if stated else None
    total = stated.total if stated else None
    at_least = False
    if total is None:
        parts = sum(minutes for minutes in (prep, cook, rest) if minutes)
        best = max(_timed_path_minutes(ordered), parts)
        if best:
            total, at_least = best, True
    if total is None and prep is None and cook is None and rest is None:
        return None

    def shown(minutes: int | None) -> str | None:
        return minutes_text(minutes) if minutes is not None else None

    return RenderedTime(
        total=shown(total), at_least=at_least, prep=shown(prep), cook=shown(cook), rest=shown(rest)
    )


def _timed_path_minutes(ordered: list[Action]) -> int:
    """The longest chain of timed steps, in minutes: steps side by side overlap.

    Only timers count -- chopping and stirring have none -- which is why the
    result is shown as "at least". A range counts with its lower end.
    """
    finish: dict[str, Decimal] = {}
    for action in ordered:
        start = max((finish.get(used, Decimal(0)) for used in action.uses), default=Decimal(0))
        own = Decimal(0)
        for timer in action.timers:
            quantity = timer.quantity
            value = quantity.value if isinstance(quantity, Scalar) else quantity.low
            unit = quantity.unit.unit_id if quantity.unit else "unit:min"
            try:
                own += convert_value(value, unit or "unit:min", "unit:min")
            except Exception:  # noqa: BLE001 - an odd timer must not cost the whole page
                continue
        finish[action.produces.id] = start + own
    longest = max(finish.values(), default=Decimal(0))
    return int(longest.to_integral_value())


def _oven_settings(steps: list[RenderedStep]) -> tuple[RenderedTemperature, ...]:
    seen: dict[str, RenderedTemperature] = {}
    for step in steps:
        for temperature in step.temperatures:
            if temperature.mode:
                seen.setdefault(temperature.display, temperature)
    return tuple(seen.values())


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
