# SPDX-License-Identifier: Apache-2.0
"""The filesystem version store.

One directory per recipe, laid out so a plain ``git init && git push`` mirrors
the full lineage with no export step (see ``RECIPE_SPEC.md`` section 5):

    <store>/<recipe_id>/
    ├── .snapcook/
    │   ├── HEAD                       {"ref": "refs/heads/main"}
    │   ├── refs/heads/main            the HEAD version id
    │   ├── versions/9f/2a/<digest>.json   immutable version records
    │   └── config.json               store + format version, recipe id
    ├── recipe.json                    canonical bytes of HEAD content
    ├── recipe.cook                    Cooklang projection of HEAD
    └── README.md                      generated; renders on GitHub

``recipe.json``, ``recipe.cook`` and ``README.md`` are **projections** of HEAD,
rewritten on every commit; the authoritative record is the immutable JSON under
``versions/``. The version files are sharded two hex levels deep by digest, the
same fan-out git uses on its object store, so a recipe with thousands of
versions does not put thousands of files in one directory.

The bytes written to ``recipe.json`` are exactly the bytes that were hashed --
``canonical_bytes`` -- so a client verifying the content hash re-hashes what it
downloaded with no re-serialisation in between that could disagree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from snapcook_core.canonical.hashing import canonical_bytes
from snapcook_core.store.base import DEFAULT_BRANCH, RecipeStore, VersionRecord
from snapcook_core.version import FORMAT_VERSION

if TYPE_CHECKING:
    from snapcook_core.schema.recipe import Recipe

__all__ = ["FilesystemStore"]

_STORE_VERSION = 1


class FilesystemStore(RecipeStore):
    """A store backed by a directory tree. See the module docstring for layout."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths ----------------------------------------------------------------

    def _recipe_dir(self, recipe_id: str) -> Path:
        return self.root / recipe_id

    def _meta_dir(self, recipe_id: str) -> Path:
        return self._recipe_dir(recipe_id) / ".snapcook"

    def _ref_path(self, recipe_id: str) -> Path:
        return self._meta_dir(recipe_id) / "refs" / "heads" / DEFAULT_BRANCH

    def _version_path(self, recipe_id: str, version: str) -> Path:
        digest = version.split(":", 1)[-1]
        return self._meta_dir(recipe_id) / "versions" / digest[:2] / digest[2:4] / f"{digest}.json"

    # -- primitives -----------------------------------------------------------

    def _put_version(self, recipe_id: str, record: VersionRecord) -> None:
        path = self._version_path(recipe_id, record.version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        self._ensure_config(recipe_id)

    def _get_version(self, recipe_id: str, version: str) -> VersionRecord | None:
        path = self._version_path(recipe_id, version)
        if not path.is_file():
            return None
        return VersionRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def _read_head_ref(self, recipe_id: str) -> str | None:
        ref_path = self._ref_path(recipe_id)
        if not ref_path.is_file():
            return None
        return ref_path.read_text(encoding="utf-8").strip() or None

    def _write_head_ref(self, recipe_id: str, version: str) -> None:
        ref_path = self._ref_path(recipe_id)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(version + "\n", encoding="utf-8")
        head = self._meta_dir(recipe_id) / "HEAD"
        head_ref = json.dumps({"ref": f"refs/heads/{DEFAULT_BRANCH}"})
        head.write_text(head_ref + "\n", encoding="utf-8")
        self._write_projections(recipe_id, version)

    def list_recipe_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_dir() and (child / ".snapcook").is_dir()
        )

    # -- projections ----------------------------------------------------------

    def _ensure_config(self, recipe_id: str) -> None:
        config = self._meta_dir(recipe_id) / "config.json"
        if config.is_file():
            return
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {
                    "store_version": _STORE_VERSION,
                    "format_version": FORMAT_VERSION,
                    "recipe_id": recipe_id,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_projections(self, recipe_id: str, version: str) -> None:
        record = self._get_version(recipe_id, version)
        if record is None:  # pragma: no cover - written immediately before this
            return
        recipe = record.recipe
        recipe_dir = self._recipe_dir(recipe_id)

        (recipe_dir / "recipe.json").write_bytes(canonical_bytes(recipe))

        cook = _project_cook(recipe)
        if cook is not None:
            (recipe_dir / "recipe.cook").write_text(cook, encoding="utf-8")

        (recipe_dir / "README.md").write_text(_project_readme(recipe), encoding="utf-8")


def _project_cook(recipe: Recipe) -> str | None:
    """Cooklang projection of HEAD, if the printer is available.

    Imported lazily so the store does not hard-depend on the authoring layer: a
    store can be read and reindexed even in a build where cooklang is absent.
    """
    try:
        from snapcook_core.cooklang import print_cook
    except Exception:  # pragma: no cover - defensive
        return None
    return print_cook(recipe, recipe.source_lang)


def _project_readme(recipe: Recipe) -> str:
    """A GitHub-rendered README for the recipe directory."""
    from snapcook_core.render import RenderOptions, build_render_model

    model = build_render_model(recipe, RenderOptions(lang=recipe.source_lang))
    lines = [f"# {model.title}", ""]
    if model.description:
        lines += [f"*{model.description}*", ""]
    if model.servings:
        lines += [f"**Serves {model.servings}**", ""]
    lines += ["## Ingredients", ""]
    for ingredient in model.ingredients:
        quantity = ingredient.quantity.display + " " if ingredient.quantity else ""
        optional = " *(optional)*" if ingredient.optional else ""
        lines.append(f"- {quantity}{ingredient.name}{optional}")
    lines += ["", "## Method", ""]
    for step in model.steps:
        lines.append(f"{step.index}. {step.text}")
    lines += [
        "",
        "---",
        "",
        "*Generated by snap-cook. Recipes are structured data — this file is one view of it.*",
        "",
    ]
    return "\n".join(lines)
