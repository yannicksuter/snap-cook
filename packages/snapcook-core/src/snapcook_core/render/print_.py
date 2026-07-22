# SPDX-License-Identifier: Apache-2.0
"""The print renderer: a self-contained HTML page.

Print is the hardest renderer and, per ``docs/architecture/rendering.md``, the
**design constraint** on the whole model: pagination, typography and image
placement are unforgiving, so if the model can drive a good printed page, screen
and diagram fall out trivially. M1 lands an HTML page with print-oriented CSS;
whether the final production path is WeasyPrint, headless Chromium or Typst is a
deliberately open question in the roadmap, and all three consume HTML or a model
this shape.

The output is deterministic -- no timestamps, no generated ids beyond the
recipe's own -- so it is a committed ``.html`` golden that opens in a browser and
diffs cleanly. Everything is inline; there is no build step and no external
asset, matching the repo's no-npm rule.
"""

from __future__ import annotations

from html import escape

from snapcook_core.render.model import RenderedIngredient, RenderModel

__all__ = ["render_print_html"]

_CSS = """\
:root { --ink: #1a1a1a; --muted: #6b6b6b; --rule: #e0ddd6; --accent: #b5651d; }
* { box-sizing: border-box; }
body { font-family: Georgia, 'Times New Roman', serif; color: var(--ink);
       max-width: 40rem; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5; }
h1 { font-size: 2rem; margin: 0 0 .25rem; }
.meta { color: var(--muted); font-size: .9rem; margin-bottom: 1.5rem; }
.desc { font-style: italic; color: #333; margin-bottom: 1.5rem; }
h2 { font-size: 1.1rem; text-transform: uppercase; letter-spacing: .08em;
     border-bottom: 2px solid var(--rule); padding-bottom: .25rem; margin-top: 2rem; }
ul.ingredients { list-style: none; padding: 0; }
ul.ingredients li { padding: .3rem 0; border-bottom: 1px solid var(--rule); }
.qty { font-weight: bold; }
.opt { color: var(--muted); font-style: italic; }
ol.steps { padding-left: 1.4rem; }
ol.steps li { margin: .6rem 0; padding-left: .3rem; }
.notes { background: #faf6ef; border-left: 3px solid var(--accent);
         padding: .5rem .9rem; font-size: .9rem; color: #5a4a34; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; }
               ol.steps li, ul.ingredients li { page-break-inside: avoid; } }
"""


def render_print_html(model: RenderModel) -> str:
    meta: list[str] = []
    if model.servings:
        meta.append(f"Serves {escape(model.servings)}")
    meta.append(f"{escape(model.lang)} · {escape(model.system)}")
    if model.scale != 1:
        meta.append(f"{_scale_label(model.scale)}")

    parts: list[str] = [
        "<!doctype html>",
        f'<html lang="{escape(model.lang)}">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape(model.title)}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(model.title)}</h1>",
        f'<p class="meta">{" · ".join(meta)}</p>',
    ]
    if model.description:
        parts.append(f'<p class="desc">{escape(model.description)}</p>')

    parts.append("<h2>Ingredients</h2>")
    parts.append('<ul class="ingredients">')
    for ingredient in model.ingredients:
        parts.append(f"<li>{_ingredient_html(ingredient)}</li>")
    parts.append("</ul>")

    parts.append("<h2>Method</h2>")
    parts.append('<ol class="steps">')
    for step in model.steps:
        parts.append(f"<li>{escape(step.text)}</li>")
    parts.append("</ol>")

    warnings = [w for w in model.warnings if w.severity in ("warn", "error")]
    if warnings:
        parts.append("<h2>Notes</h2>")
        for warning in warnings:
            parts.append(f'<p class="notes">{escape(warning.message)}</p>')

    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def _ingredient_html(ingredient: RenderedIngredient) -> str:
    quantity = ingredient.quantity
    name = escape(ingredient.name)
    if quantity is None:
        line = name
    else:
        qty = f'<span class="qty">{escape(quantity.display)}</span>'
        line = f"{name} {qty}" if quantity.after_name else f"{qty} {name}"
    if ingredient.prep:
        line = f"{line}, {escape(ingredient.prep)}"
    if ingredient.optional:
        line = f'{line} <span class="opt">(optional)</span>'
    return line


def _scale_label(scale) -> str:
    if scale == scale.to_integral_value():
        return f"{int(scale)}×"
    return f"{format(scale.normalize(), 'f')}×"
