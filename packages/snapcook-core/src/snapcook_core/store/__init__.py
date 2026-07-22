# SPDX-License-Identifier: Apache-2.0
"""The version store: content-addressed, git-shaped lineage.

Two backends share one set of lineage rules (the no-op commit, parent
resolution, history) from :class:`RecipeStore`: :class:`MemoryStore` for tests
and :class:`FilesystemStore` for the authoritative on-disk store.
"""

from snapcook_core.store.base import RecipeStore, VersionRecord, build_version_record
from snapcook_core.store.fs import FilesystemStore
from snapcook_core.store.memory import MemoryStore

__all__ = [
    "FilesystemStore",
    "MemoryStore",
    "RecipeStore",
    "VersionRecord",
    "build_version_record",
]
