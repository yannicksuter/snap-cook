# SPDX-License-Identifier: Apache-2.0
"""The text renderer: a plain-text reading of a recipe.

A pure walk over a :class:`RenderModel`. It makes no decisions -- language,
units, scale and rounding are already resolved -- so it is small, and its output
is a committed ``.txt`` golden that a reviewer reads directly in a diff rather
than an escaped snapshot blob.

The step body is the already-substituted prose. Timers, temperatures and
cookware are woven into that prose at build time, so the sentence reads
naturally ("Bake at 220 °C for 30 min") instead of trailing a machine-looking
list of attributes.
"""

from __future__ import annotations

from snapcook_core.render.model import RenderedIngredient, RenderModel

__all__ = ["render_text"]

_RULE = "=" * 60


def render_text(model: RenderModel) -> str:
    lines: list[str] = []
    lines.append(model.title)
    lines.append(_RULE)
    if model.description:
        lines.append(model.description)
        lines.append("")

    meta: list[str] = []
    if model.servings:
        meta.append(f"Serves {model.servings}")
    if model.scale != 1:
        meta.append(f"scaled {_scale_label(model.scale)}")
    meta.append(f"{model.lang} / {model.system}")
    lines.append(" · ".join(meta))
    lines.append("")

    lines.append("Ingredients")
    lines.append("-" * 11)
    if model.ingredients:
        for ingredient in model.ingredients:
            lines.append(f"  - {_ingredient_line(ingredient)}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Steps")
    lines.append("-" * 5)
    for step in model.steps:
        lines.append(f"  {step.index}. {step.text}")
    lines.append("")

    warnings = [w for w in model.warnings if w.severity in ("warn", "error")]
    if warnings:
        lines.append("Notes")
        lines.append("-" * 5)
        for warning in warnings:
            lines.append(f"  ! {warning.message}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _ingredient_line(ingredient: RenderedIngredient) -> str:
    quantity = ingredient.quantity
    if quantity is None:
        line = ingredient.name
    elif quantity.after_name:
        line = f"{ingredient.name} {quantity.display}"
    else:
        line = f"{quantity.display} {ingredient.name}"
    if ingredient.prep:
        line = f"{line}, {ingredient.prep}"
    if ingredient.optional:
        line = f"{line} (optional)"
    if ingredient.unresolved:
        line = f"{line}  [unresolved]"
    return line


def _scale_label(scale) -> str:
    if scale == scale.to_integral_value():
        return f"{int(scale)}x"
    return f"{format(scale.normalize(), 'f')}x"
