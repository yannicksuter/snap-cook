# SPDX-License-Identifier: Apache-2.0
"""The Mermaid renderer: the recipe as a flowchart.

Unlike the text renderer, this one **ignores the prose entirely** and walks the
graph. Ingredients become stadium nodes, food-states become boxes, and an
action is the edge between them carrying its verb, duration and temperature. An
action with several inputs cannot be one labelled edge -- a labelled edge is not
a hyperedge -- so the build step inserts a diamond join node, and this renderer
just draws what it is given.

Output is a committed ``.mmd`` golden that pastes straight into the Mermaid live
editor, which is the point: a rendering regression is caught by a human reading
the diff, and a ``.mmd`` is legible where a snapshot blob is not.
"""

from __future__ import annotations

from snapcook_core.render.model import RenderGraph, RenderModel

__all__ = ["render_mermaid"]


def render_mermaid(model: RenderModel) -> str:
    lines = ["flowchart TD"]
    graph: RenderGraph = model.graph

    for node in graph.nodes:
        lines.append(f"    {_node(node.id, node.label, node.kind)}")
    if graph.nodes and graph.edges:
        lines.append("")
    for edge in graph.edges:
        lines.append(f"    {_edge(edge.src, edge.dst, edge.label)}")

    return "\n".join(lines).rstrip() + "\n"


def _node(node_id: str, label: str, kind: str) -> str:
    safe = _safe_id(node_id)
    text = _escape(label)
    if kind == "ingredient":
        return f'{safe}(["{text}"])'  # stadium
    if kind == "join":
        return f'{safe}{{"{text}"}}'  # diamond
    return f'{safe}["{text}"]'  # box (state)


def _edge(src: str, dst: str, label: str) -> str:
    src_id, dst_id = _safe_id(src), _safe_id(dst)
    if label:
        return f"{src_id} -->|{_escape(label)}| {dst_id}"
    return f"{src_id} --> {dst_id}"


def _safe_id(node_id: str) -> str:
    """Mermaid node ids allow word characters; our prefixed ULIDs already are.

    A defensive replace keeps a stray separator from producing invalid syntax.
    """
    return node_id.replace(":", "_").replace(".", "_").replace("-", "_")


def _escape(text: str) -> str:
    """Quote-safe label text. Mermaid uses ``#quot;`` for a literal quote."""
    return text.replace('"', "#quot;")
