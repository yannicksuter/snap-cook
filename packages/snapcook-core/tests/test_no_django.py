# SPDX-License-Identifier: Apache-2.0
"""Enforce that snapcook-core never imports Django.

This is the one architectural rule in the project that erodes *silently*. A
single `from django.utils.text import slugify` for convenience would work fine,
pass every other test, and quietly make the package unusable from a Flutter
backend, a CLI or the LLM service -- with nothing to signal the loss until
someone tries. So it is checked mechanically rather than left to review.

An AST walk is used rather than grep so that a string mentioning Django in a
docstring or a comment does not trip it.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "snapcook_core"

FORBIDDEN_ROOTS = {"django", "psycopg", "celery", "django_q"}


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Relative imports have no module root to check.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_core_never_imports_django() -> None:
    offenders: list[str] = []

    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = _imported_roots(tree) & FORBIDDEN_ROOTS
        if bad:
            rel = path.relative_to(SRC.parent.parent)
            offenders.append(f"{rel}: {', '.join(sorted(bad))}")

    assert not offenders, (
        "snapcook-core must stay free of web-framework and database imports.\n"
        "The whole point of this package is that a Flutter client, a CLI and the\n"
        "LLM service can all use it. Move the offending code into apps/web.\n\n"
        + "\n".join(offenders)
    )


def test_source_tree_is_not_empty() -> None:
    """Guard against the above passing vacuously if the layout ever moves."""
    assert list(SRC.rglob("*.py")), f"no modules found under {SRC}"
