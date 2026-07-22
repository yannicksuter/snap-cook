# SPDX-License-Identifier: Apache-2.0
"""YAML frontmatter for ``.cook`` files.

Cooklang carries recipe metadata in a leading ``---`` fenced YAML block.
snap-cook needs more than standard Cooklang -- language, visibility, provenance --
so this reads and writes a fixed, ordered set of keys.

``ruamel.yaml`` is used for both directions rather than a hand-rolled dumper:
titles carry apostrophes and umlauts, and getting the quoting exactly reversible
by hand is a bug farm. Feeding it an ordered dict and reading back a plain dict
keeps the projection deterministic, which is what the round-trip gate needs.
"""

from __future__ import annotations

import io
from typing import Any

from ruamel.yaml import YAML

__all__ = ["dump_frontmatter", "parse_document"]

_FENCE = "---"


def _yaml() -> YAML:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096  # never wrap a long description mid-line
    return yaml


def dump_frontmatter(data: dict[str, Any]) -> str:
    """Serialise metadata as a fenced YAML block, keys in insertion order."""
    stream = io.StringIO()
    _yaml().dump(data, stream)
    return f"{_FENCE}\n{stream.getvalue()}{_FENCE}\n"


def parse_document(text: str) -> tuple[dict[str, Any], str]:
    """Split a ``.cook`` document into (frontmatter dict, body).

    A document with no fenced block yields an empty dict and the whole text as
    body, so a bare Cooklang snippet still parses.
    """
    stripped = text.lstrip("﻿")
    if not stripped.startswith(_FENCE):
        return {}, text

    lines = stripped.splitlines()
    end = _closing_fence(lines)
    if end is None:
        return {}, text

    block = "\n".join(lines[1:end])
    data = _yaml().load(block) or {}
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return dict(data), body


def _closing_fence(lines: list[str]) -> int | None:
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            return index
    return None
