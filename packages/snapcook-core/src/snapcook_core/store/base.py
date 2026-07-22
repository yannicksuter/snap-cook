# SPDX-License-Identifier: Apache-2.0
"""The version store: git-shaped, not git.

Immutable, content-addressed versions with parent pointers form a lineage DAG.
The store is deliberately *not* git: git's merge is line-based and textual, and a
recipe wants field-level semantic merge; git also forces an awkward
repo-per-recipe choice and is too slow to sit in the request path. So this is our
own store, with a layout a plain ``git init`` will happily mirror for export.

Two rules are load-bearing and live here rather than in any one backend:

**The no-op rule.** ``commit`` returns the existing HEAD unchanged when the new
content hash equals HEAD's. Reformatting a file, reordering keys, writing
``@onion{}`` for ``@onion`` -- none of these produce a version. This is a
store-level invariant, not a UI nicety: it is what stops whitespace churn from
forking lineage.

**Versions are stored whole**, never as deltas. A recipe is a few kilobytes and
a thousand versions is a few megabytes, so full snapshots keep reads O(1) with no
chain to walk -- which matters precisely because git, and its delta
reconstruction, is not in the request path.

M1 is **linear lineage only**: a commit's single parent is the previous HEAD.
The record already carries a ``parents`` *list*, so the merge machinery of M2
slots in without a format change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from snapcook_core.canonical.hashing import content_hash, version_id
from snapcook_core.errors import ObjectNotFoundError, RefNotFoundError
from snapcook_core.ids import VersionId
from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.recipe import Recipe
from snapcook_core.version import FORMAT_VERSION

__all__ = ["RecipeStore", "VersionRecord"]

DEFAULT_BRANCH = "main"


class VersionRecord(SnapcookModel):
    """One immutable commit: the recipe content plus who and when.

    ``content_hash`` is the identity of the *content* (the no-op rule keys on
    it); ``version_id`` is the identity of the *commit*, which additionally
    folds in author, time and parents so two people authoring byte-identical
    recipes still get distinct versions.
    """

    version_id: VersionId
    content_hash: str
    schema_version: int = FORMAT_VERSION
    parents: list[VersionId] = []
    author: str
    created_at: str
    message: str = ""
    origin: str = "authored"
    recipe: Recipe


def build_version_record(
    recipe: Recipe,
    *,
    parents: list[str],
    author: str,
    created_at: str,
    message: str = "",
    origin: str = "authored",
    schema_version: int = FORMAT_VERSION,
) -> VersionRecord:
    """Compute both hashes and assemble an immutable version record."""
    content = content_hash(recipe)
    vid = version_id(
        schema_version=schema_version,
        content_hash_value=content,
        parents=parents,
        author_key=author,
        created_at_iso=created_at,
        message=message,
        origin=origin,
    )
    return VersionRecord(
        version_id=vid,
        content_hash=content,
        schema_version=schema_version,
        parents=[VersionId(p) for p in parents],
        author=author,
        created_at=created_at,
        message=message,
        origin=origin,
        recipe=recipe,
    )


class RecipeStore(ABC):
    """The store interface, with lineage logic shared across backends.

    Subclasses implement only the storage primitives -- read/write a version,
    read/write the branch ref, enumerate recipes. Everything with a rule in it --
    the no-op check, parent resolution, history walking -- lives here so the two
    backends cannot drift on semantics.
    """

    # -- primitives a backend must provide ------------------------------------

    @abstractmethod
    def _put_version(self, recipe_id: str, record: VersionRecord) -> None: ...

    @abstractmethod
    def _get_version(self, recipe_id: str, version: str) -> VersionRecord | None: ...

    @abstractmethod
    def _read_head_ref(self, recipe_id: str) -> str | None:
        """The version id the branch points at, or ``None`` if the recipe is new."""

    @abstractmethod
    def _write_head_ref(self, recipe_id: str, version: str) -> None: ...

    @abstractmethod
    def list_recipe_ids(self) -> list[str]: ...

    # -- shared lineage logic -------------------------------------------------

    def commit(
        self,
        recipe: Recipe,
        *,
        author: str,
        created_at: str,
        message: str = "",
        origin: str = "authored",
        parents: list[str] | None = None,
    ) -> VersionRecord:
        """Store a new version and advance HEAD, or return HEAD if unchanged.

        With ``parents`` omitted the single parent is the current HEAD -- the
        linear-lineage default. The no-op rule is applied first: an identical
        content hash yields the existing HEAD and writes nothing.
        """
        head = self.head(recipe.id)
        if head is not None and head.content_hash == content_hash(recipe):
            return head

        if parents is None:
            parents = [head.version_id] if head is not None else []

        record = build_version_record(
            recipe,
            parents=parents,
            author=author,
            created_at=created_at,
            message=message,
            origin=origin,
        )
        self._put_version(recipe.id, record)
        self._write_head_ref(recipe.id, record.version_id)
        return record

    def head(self, recipe_id: str) -> VersionRecord | None:
        """The current HEAD version, or ``None`` if the recipe does not exist."""
        ref = self._read_head_ref(recipe_id)
        if ref is None:
            return None
        record = self._get_version(recipe_id, ref)
        if record is None:
            raise ObjectNotFoundError(f"HEAD of {recipe_id} points at missing version {ref}")
        return record

    def head_recipe(self, recipe_id: str) -> Recipe:
        """The recipe content at HEAD, or raise if there is no such recipe."""
        head = self.head(recipe_id)
        if head is None:
            raise RefNotFoundError(f"no such recipe in store: {recipe_id}")
        return head.recipe

    def get_version(self, recipe_id: str, version: str) -> VersionRecord:
        record = self._get_version(recipe_id, version)
        if record is None:
            raise ObjectNotFoundError(f"no version {version} for {recipe_id}")
        return record

    def history(self, recipe_id: str) -> list[VersionRecord]:
        """HEAD-first lineage. Linear in M1; a DFS of first parents beyond it."""
        head = self.head(recipe_id)
        if head is None:
            return []
        out: list[VersionRecord] = []
        seen: set[str] = set()
        frontier = [head.version_id]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            record = self._get_version(recipe_id, current)
            if record is None:
                continue
            out.append(record)
            frontier.extend(record.parents)
        out.sort(key=lambda record: record.created_at, reverse=True)
        return out

    def exists(self, recipe_id: str) -> bool:
        return self._read_head_ref(recipe_id) is not None
