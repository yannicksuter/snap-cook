# SPDX-License-Identifier: Apache-2.0
"""Rendering: one intermediate model, three pure renderers.

``build_render_model`` resolves a recipe for one reader -- language, unit
system, scale -- and each renderer is a pure walk over the result. See
``docs/architecture/rendering.md`` for why the intermediate exists.
"""

from snapcook_core.render.build import RenderOptions, build_render_model
from snapcook_core.render.mermaid import render_mermaid
from snapcook_core.render.model import RenderModel
from snapcook_core.render.print_ import render_print_html
from snapcook_core.render.text import render_text
from snapcook_core.render.toposort import topological_actions

__all__ = [
    "RenderModel",
    "RenderOptions",
    "build_render_model",
    "render_mermaid",
    "render_print_html",
    "render_text",
    "topological_actions",
]
