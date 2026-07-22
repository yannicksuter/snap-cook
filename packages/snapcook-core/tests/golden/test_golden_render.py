# SPDX-License-Identifier: Apache-2.0
"""Golden renderer output.

Golden files are committed ``.txt``, ``.mmd`` and ``.html`` -- legible artifacts,
not opaque snapshot blobs -- because the pull-request diff is the review surface
where a rendering regression gets caught. An escaped snapshot diff gets
rubber-stamped; a readable one does not.

The full matrix (fixtures x renderers x languages x systems x scales) is
unmaintainable, so each fixture declares a handful of combinations covering *its*
reason for existing, and a separate smoke test asserts the rest render without
raising.

Regenerate with ``./scripts/update-golden.sh`` and then READ the diff. CI runs
without ``SNAPCOOK_UPDATE_GOLDEN``, so a stale golden fails rather than passing
silently.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from snapcook_core.render import (
    RenderOptions,
    build_render_model,
    render_mermaid,
    render_print_html,
    render_text,
)
from snapcook_core.testing import corpus_recipes, get_recipe

GOLDEN_DIR = Path(__file__).parent
_UPDATING = os.environ.get("SNAPCOOK_UPDATE_GOLDEN") == "1"

_RENDERERS = {"txt": render_text, "mmd": render_mermaid, "html": render_print_html}

# Each entry: (fixture slug, lang, system, scale, renderer). Chosen to cover each
# fixture's reason for existing; 006-roesti carries the milestone's full matrix.
_MATRIX: list[tuple[str, str, str, str, str]] = [
    ("001-boiled-egg", "en", "metric", "1", "txt"),
    ("002-simple-syrup", "en", "us", "1", "txt"),
    ("003-herb-omelette", "en", "metric", "1", "txt"),
    ("003-herb-omelette", "en", "us", "2", "txt"),
    ("004-tomato-sauce", "en", "metric", "1", "txt"),
    ("004-tomato-sauce", "en", "metric", "1", "mmd"),
    ("005-pancakes", "en", "us", "1", "txt"),
    # 006-roesti: text + mermaid + print, DE and EN, metric and US, 1x and 2x.
    ("006-roesti", "en", "metric", "1", "txt"),
    ("006-roesti", "en", "us", "2", "txt"),
    ("006-roesti", "de", "metric", "2", "txt"),
    ("006-roesti", "de", "us", "1", "txt"),
    ("006-roesti", "en", "metric", "1", "mmd"),
    ("006-roesti", "de", "us", "2", "html"),
]


def _render(slug: str, lang: str, system: str, scale: str, ext: str) -> str:
    recipe = get_recipe(slug)
    model = build_render_model(
        recipe, RenderOptions(lang=lang, system=system, scale=Decimal(scale))
    )
    return _RENDERERS[ext](model)


def _golden_path(slug: str, lang: str, system: str, scale: str, ext: str) -> Path:
    return GOLDEN_DIR / slug / f"{lang}-{system}-{scale}x.{ext}"


@pytest.mark.golden
@pytest.mark.parametrize(
    ("slug", "lang", "system", "scale", "ext"),
    _MATRIX,
    ids=[f"{s}-{lang}-{sys}-{sc}x-{ext}" for s, lang, sys, sc, ext in _MATRIX],
)
def test_golden(slug: str, lang: str, system: str, scale: str, ext: str) -> None:
    produced = _render(slug, lang, system, scale, ext)
    path = _golden_path(slug, lang, system, scale, ext)

    if _UPDATING:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(produced, encoding="utf-8")
        return

    assert path.is_file(), f"missing golden {path}; run ./scripts/update-golden.sh"
    expected = path.read_text(encoding="utf-8")
    assert produced == expected, (
        f"render drift for {path.name}. If intended, run ./scripts/update-golden.sh "
        "and explain the diff in the PR."
    )


@pytest.mark.parametrize("recipe", corpus_recipes(), ids=lambda r: r.id)
def test_every_fixture_renders_across_the_matrix(recipe) -> None:
    """The combinations not pinned by a golden must still render without raising."""
    for lang in ("en", "de"):
        for system in ("metric", "us"):
            for scale in (Decimal(1), Decimal("1.5"), Decimal(2)):
                model = build_render_model(
                    recipe, RenderOptions(lang=lang, system=system, scale=scale)
                )
                assert render_text(model)
                assert render_mermaid(model).startswith("flowchart TD")
                assert render_print_html(model).startswith("<!doctype html>")
