# SPDX-License-Identifier: Apache-2.0
"""The Mermaid renderer: the recipe as a flowchart.

Unlike the text renderer, this one walks the graph rather than reading the
method top to bottom. Every step is a numbered box with its times and
temperatures on a second line; its ingredients, stadiums, flow into it; a result
a later step names is a box of its own; and the dish the recipe ends with closes
the chart. The build step decides all of that, and this renderer just draws what
it is given.

Each node carries a class -- ``ingredient``, ``step``, ``state`` or ``dish`` --
and so does each part of a label: ``n`` a step's number, ``qty`` an amount,
``time`` and ``temp`` a step's timers and temperatures. There are no colours:
how they look is the page's business (``recipes/_chart_assets.html``), so the
same text pastes into the Mermaid live editor as plain shapes.

Output is a committed ``.mmd`` golden that pastes straight into that editor,
which is the point: a rendering regression is caught by a human reading the
diff, and a ``.mmd`` is legible where a snapshot blob is not.
"""

from __future__ import annotations

from snapcook_core.render.model import RenderGraph, RenderModel, RenderNode

__all__ = ["render_mermaid"]

# Mermaid shape delimiters per node kind: a stadium for what goes in and what
# comes out, rounded boxes for the steps, plain boxes for named results.
_SHAPES = {
    "ingredient": ("([", "])"),
    "step": ("(", ")"),
    "state": ("[", "]"),
    "dish": ("([", "])"),
}


def render_mermaid(model: RenderModel) -> str:
    lines = ["flowchart TD"]
    graph: RenderGraph = model.graph

    for node in graph.nodes:
        lines.append(f"    {_node(node)}")
    if graph.nodes and graph.edges:
        lines.append("")
    for edge in graph.edges:
        lines.append(f"    {_safe_id(edge.src)} --> {_safe_id(edge.dst)}")

    return "\n".join(lines).rstrip() + "\n"


def _node(node: RenderNode) -> str:
    opening, closing = _SHAPES.get(node.kind, ("[", "]"))
    return f'{_safe_id(node.id)}{opening}"{_label(node)}"{closing}:::{node.kind}'


def _label(node: RenderNode) -> str:
    text = _escape(node.label)
    if node.amount:
        amount = f"<span class=qty>{_escape(node.amount)}</span>"
        text = f"{text} {amount}" if node.amount_after else f"{amount} {text}"
    if node.number is not None:
        text = f"<span class=n>{node.number}</span> {text}"
    chips = [f"<span class=time>{_escape(time)}</span>" for time in node.times]
    chips += [_temperature_chip(temp) for temp in node.temperatures]
    if chips:
        text = f"{text}<br>{''.join(chips)}"
    return text


def _temperature_chip(temperature) -> str:
    """A temperature, with its oven setting as a class (``m-fan``) to draw its symbol."""
    if temperature.mode:
        return f"<span class='temp m-{temperature.mode}'>{_escape(temperature.display)}</span>"
    return f"<span class=temp>{_escape(temperature.display)}</span>"


def _safe_id(node_id: str) -> str:
    """Mermaid node ids allow word characters; our prefixed ULIDs already are.

    A defensive replace keeps a stray separator from producing invalid syntax.
    """
    return node_id.replace(":", "_").replace(".", "_").replace("-", "_")


def _escape(text: str) -> str:
    """Label text as Mermaid entities, so a recipe's words are never markup."""
    return (
        text.replace("&", "#amp;").replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")
    )
