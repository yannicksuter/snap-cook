# SPDX-License-Identifier: Apache-2.0
"""Project a recipe back to Cooklang-flavoured text.

Cooklang is an **input and export** format, not the stored source of truth --
one mutable representation, not two. This printer is the export half: it walks a
:class:`Recipe` and emits a ``.cook`` document that :mod:`snapcook_core.cooklang.parse`
reads back into an equivalent recipe.

The output is a *canonical* form -- every ingredient and tool is brace-delimited
(``@salt{}``, never bare ``@salt``), state consumption is explicit
(``@&{the dough}``), and steps come out in deterministic topological order. That
canonical shape is what makes the round trip idempotent: printing a parsed
document reproduces it byte for byte, which is the gate the authoring layer is
tested against.

Round-trip fidelity is guaranteed for the recipe's **source language**, where an
ingredient token carries the surface the author actually wrote. Printed in
another language, ingredient names come from the registry -- a readable
projection, but not a reversible one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from snapcook_core.canonical.encode import encode_decimal
from snapcook_core.registry import IngredientRegistry, default_registry
from snapcook_core.render.toposort import topological_actions
from snapcook_core.schema.graph import (
    Action,
    CookwareChunk,
    IngredientChunk,
    LiteralChunk,
    StateChunk,
    TemperatureChunk,
    TextTemplate,
    TimerChunk,
)
from snapcook_core.schema.quantity import Approx, Count, QuantitySpec, Range, Scalar, ScalingPolicy

if TYPE_CHECKING:
    from snapcook_core.schema.graph import Temperature, Timer
    from snapcook_core.schema.ingredient import IngredientUse
    from snapcook_core.schema.recipe import Recipe

__all__ = ["print_cook"]

# Frontmatter keys in a fixed order, so the projection is deterministic.
_FRONTMATTER_ORDER = (
    "title",
    "description",
    "servings",
    "lang",
    "visibility",
    "tags",
    "source_url",
    "license",
    "author",
)


def print_cook(
    recipe: Recipe, lang: str | None = None, *, registry: IngredientRegistry | None = None
) -> str:
    """Render a recipe as a Cooklang document in ``lang`` (default: source)."""
    from snapcook_core.cooklang.frontmatter import dump_frontmatter

    lang = lang or recipe.source_lang
    registry = registry or default_registry()

    ordered = topological_actions(recipe)
    state_names = _state_names(ordered, recipe, lang)

    front = _frontmatter(recipe, lang)
    steps = [_print_step(action, recipe, lang, registry, state_names) for action in ordered]
    body = "\n\n".join(steps)
    return f"{dump_frontmatter(front)}\n{body}\n"


def _frontmatter(recipe: Recipe, lang: str) -> dict:
    title, _ = recipe.title.resolve(lang, source=recipe.source_lang)
    values: dict = {"title": title}
    if recipe.description is not None:
        values["description"], _ = recipe.description.resolve(lang, source=recipe.source_lang)
    if recipe.servings is not None:
        values["servings"] = recipe.servings
    values["lang"] = lang
    values["visibility"] = recipe.visibility
    if recipe.tags:
        values["tags"] = list(recipe.tags)
    if recipe.provenance.source_url:
        values["source_url"] = recipe.provenance.source_url
    if recipe.provenance.license_spdx:
        values["license"] = recipe.provenance.license_spdx
    if recipe.provenance.author:
        values["author"] = recipe.provenance.author
    return {key: values[key] for key in _FRONTMATTER_ORDER if key in values}


def _state_names(ordered: list[Action], recipe: Recipe, lang: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for index, action in enumerate(ordered, start=1):
        state = action.produces
        if state.name is not None:
            names[state.id], _ = state.name.resolve(lang, source=recipe.source_lang)
        else:
            names[state.id] = f"s{index}"
    return names


def _print_step(
    action: Action,
    recipe: Recipe,
    lang: str,
    registry: IngredientRegistry,
    state_names: dict[str, str],
) -> str:
    template = action.text
    chunk_states = {
        c.ref for c in (template.chunks if template else []) if isinstance(c, StateChunk)
    }
    # Uses not already placed inline by a StateChunk are emitted up front.
    leading = "".join(
        f"@&{{{state_names[used]}}}" for used in action.uses if used not in chunk_states
    )

    body = _print_body(action, template, recipe, lang, registry, state_names)

    produced = action.produces
    suffix = ""
    if produced.name is not None:
        name, _ = produced.name.resolve(lang, source=recipe.source_lang)
        suffix = f" => {name}"

    return f"{leading}{body}{suffix}"


def _print_body(
    action: Action,
    template: TextTemplate | None,
    recipe: Recipe,
    lang: str,
    registry: IngredientRegistry,
    state_names: dict[str, str],
) -> str:
    if template is None:
        # No prose: emit the ingredient tokens so the step still round-trips to
        # something, though a template-less step is not a fidelity guarantee.
        tokens = [_ingredient_token(use, recipe, lang, registry) for use in action.ingredients]
        return " ".join(tokens)

    by_ing = {use.id: use for use in action.ingredients}
    by_cook = {item.id: item for item in action.cookware}
    parts: list[str] = []
    for chunk in template.chunks:
        if isinstance(chunk, LiteralChunk):
            resolved, _ = chunk.text.resolve(lang, source=recipe.source_lang)
            parts.append(resolved)
        elif isinstance(chunk, IngredientChunk):
            parts.append(_ingredient_token(by_ing[chunk.ref], recipe, lang, registry))
        elif isinstance(chunk, CookwareChunk):
            parts.append(_cookware_token(by_cook[chunk.ref], recipe, lang))
        elif isinstance(chunk, StateChunk):
            parts.append(f"@&{{{state_names[chunk.ref]}}}")
        elif isinstance(chunk, TimerChunk):
            parts.append(_timer_token(action.timers[chunk.index], recipe, lang))
        elif isinstance(chunk, TemperatureChunk):
            parts.append(_temperature_token(action.temperatures[chunk.index]))
    return "".join(parts)


# -- tokens -------------------------------------------------------------------


def _ingredient_token(
    use: IngredientUse, recipe: Recipe, lang: str, registry: IngredientRegistry
) -> str:
    mods = ""
    if use.optional:
        mods += "?"
    if use.quantity is not None and use.quantity.scaling is ScalingPolicy.INVARIANT:
        mods += "="

    if lang == recipe.source_lang:
        name = use.name
    else:
        ingredient = registry.get(use.ingredient_id)
        name = (
            ingredient.name_for(lang, source=recipe.source_lang) if ingredient else None
        ) or use.name

    return f"@{mods}{name}{{{_quantity_body(use.quantity)}}}"


def _cookware_token(item, recipe: Recipe, lang: str) -> str:
    name, _ = item.name.resolve(lang, source=recipe.source_lang)
    amount = "" if item.quantity is None else encode_decimal(item.quantity)
    return f"#{name}{{{amount}}}"


def _timer_token(timer: Timer, recipe: Recipe, lang: str) -> str:
    name = ""
    if timer.name is not None:
        name, _ = timer.name.resolve(lang, source=recipe.source_lang)
    return f"~{name}{{{_bare_quantity_body(timer.quantity)}}}"


def _temperature_token(temperature: Temperature) -> str:
    return f"^{{{encode_decimal(temperature.value)}%{temperature.unit}}}"


def _quantity_body(spec: QuantitySpec | None) -> str:
    if spec is None:
        return ""
    return _bare_quantity_body(spec.quantity)


def _bare_quantity_body(quantity) -> str:
    if isinstance(quantity, Scalar):
        if quantity.unit is not None:
            return f"{encode_decimal(quantity.value)}%{quantity.unit.surface}"
        return encode_decimal(quantity.value)
    if isinstance(quantity, Range):
        body = f"{encode_decimal(quantity.low)}-{encode_decimal(quantity.high)}"
        if quantity.unit is not None:
            return f"{body}%{quantity.unit.surface}"
        return body
    if isinstance(quantity, Count):
        if quantity.size is not None:
            return f"{encode_decimal(quantity.value)}%{quantity.size.value}"
        if quantity.high is not None:
            return f"{encode_decimal(quantity.value)}-{encode_decimal(quantity.high)}"
        return encode_decimal(quantity.value)
    if isinstance(quantity, Approx):
        return quantity.surface
    raise TypeError(f"unprintable quantity: {type(quantity).__name__}")
