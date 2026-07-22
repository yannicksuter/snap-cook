# SPDX-License-Identifier: Apache-2.0
"""An in-memory version store.

The reference backend and the one tests use. It holds the same lineage
semantics as the filesystem store -- the no-op rule, parent resolution, history
-- because both inherit them from :class:`RecipeStore`; only the storage
primitives differ. That shared base is what lets a test assert a behaviour once
and trust it holds on disk too.

Nothing here touches the filesystem, so it stays inside tier 0's no-IO budget.
"""

from __future__ import annotations

from snapcook_core.store.base import RecipeStore, VersionRecord

__all__ = ["MemoryStore"]


class MemoryStore(RecipeStore):
    def __init__(self) -> None:
        # recipe_id -> {version_id -> record}
        self._versions: dict[str, dict[str, VersionRecord]] = {}
        # recipe_id -> HEAD version_id
        self._heads: dict[str, str] = {}

    def _put_version(self, recipe_id: str, record: VersionRecord) -> None:
        self._versions.setdefault(recipe_id, {})[record.version_id] = record

    def _get_version(self, recipe_id: str, version: str) -> VersionRecord | None:
        return self._versions.get(recipe_id, {}).get(version)

    def _read_head_ref(self, recipe_id: str) -> str | None:
        return self._heads.get(recipe_id)

    def _write_head_ref(self, recipe_id: str, version: str) -> None:
        self._heads[recipe_id] = version

    def list_recipe_ids(self) -> list[str]:
        return sorted(self._heads)
