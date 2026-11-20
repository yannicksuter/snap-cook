# SPDX-License-Identifier: AGPL-3.0-or-later
"""The oven settings' symbols, drawn the way an oven's dial shows them.

A frame, with a line along the top for top heat and along the bottom for bottom
heat, a zigzag for the grill, a fan, and the fan in a ring for hot air. One
drawing per setting, used two ways: inline on the page, and as a mask on the
chart's temperature chips, where Mermaid allows no inline SVG.
"""

from __future__ import annotations

from urllib.parse import quote

__all__ = ["oven_mask_css", "oven_svg"]

_FRAME = '<rect x="3" y="3" width="18" height="18" rx="3.5"/>'
_TOP = '<path d="M7.5 7.5h9"/>'
_BOTTOM = '<path d="M7.5 16.5h9"/>'
_GRILL = (
    '<path d="M7 7.25l1.25 1.25 1.25-1.25 1.25 1.25 1.25-1.25 1.25 1.25'
    ' 1.25-1.25 1.25 1.25 1.25-1.25"/>'
)
_BLADE = "M12 12c-.45-1.75 0-3.05 1.25-3.45.85-.25 1.55.4 1.25 1.25-.3 1-1.15 1.7-2.5 2.2z"
_FAN = (
    '<g fill="currentColor" stroke="none">'
    + "".join(
        f'<path d="{_BLADE}" transform="rotate({turn} 12 12)"/>' for turn in (0, 90, 180, 270)
    )
    + "</g>"
)
_RING = '<circle cx="12" cy="12" r="5.6"/>'

_PARTS = {
    "conventional": (_TOP, _BOTTOM),
    "top": (_TOP,),
    "bottom": (_BOTTOM,),
    "fan": (_FAN,),
    "hot_air": (_RING, _FAN),
    "fan_bottom": (_FAN, _BOTTOM),
    "fan_conventional": (_TOP, _FAN, _BOTTOM),
    "grill": (_GRILL,),
    "fan_grill": (_GRILL, _FAN),
}


def oven_svg(mode: str | None, size: int = 22) -> str:
    """The setting's symbol as inline SVG; empty for no setting or an unknown one."""
    parts = _PARTS.get(mode or "")
    if parts is None:
        return ""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{_FRAME}{"".join(parts)}</svg>'
    )


def oven_mask_css() -> str:
    """CSS giving each of the chart's ``.temp.m-<setting>`` chips its symbol."""
    rules = []
    for mode in _PARTS:
        svg = oven_svg(mode).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        uri = "data:image/svg+xml;utf8," + quote(svg.replace("currentColor", "black"), safe="")
        rules.append(f'.nodeLabel .temp.m-{mode} {{ --icon: url("{uri}"); }}')
    return "\n".join(rules)
