# SPDX-License-Identifier: Apache-2.0
"""Version store behaviour, both backends.

The no-op rule and lineage are defined on :class:`RecipeStore`, so the same
assertions must hold for the in-memory and filesystem backends. Parametrising
over both is how we know the on-disk store cannot quietly diverge from the one
tests use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from snapcook_core.canonical import content_hash
from snapcook_core.errors import RefNotFoundError
from snapcook_core.store import FilesystemStore, MemoryStore
from snapcook_core.testing import get_recipe


@pytest.fixture(params=["memory", "fs"])
def store(request, tmp_path: Path):
    if request.param == "memory":
        return MemoryStore()
    return FilesystemStore(tmp_path / "store")


def _commit(store, recipe, at="2026-07-20T10:00:00", message="init"):
    return store.commit(recipe, author="user:alice", created_at=at, message=message)


def test_commit_then_head_round_trips(store) -> None:
    recipe = get_recipe("006-roesti")
    _commit(store, recipe)
    assert store.head_recipe(recipe.id).id == recipe.id
    assert content_hash(store.head_recipe(recipe.id)) == content_hash(recipe)


def test_no_op_rule_identical_content_makes_no_version(store) -> None:
    recipe = get_recipe("001-boiled-egg")
    v1 = _commit(store, recipe, at="2026-07-20T10:00:00")
    v2 = _commit(store, recipe, at="2026-07-20T11:00:00", message="again")
    assert v1.version_id == v2.version_id
    assert len(store.history(recipe.id)) == 1


def test_a_real_change_makes_a_new_version_with_a_parent(store) -> None:
    recipe = get_recipe("002-simple-syrup")
    v1 = _commit(store, recipe)
    edited = recipe.model_copy(update={"servings": 4})
    v2 = _commit(store, edited, at="2026-07-20T12:00:00", message="double batch")
    assert v2.version_id != v1.version_id
    assert v2.parents == [v1.version_id]
    assert len(store.history(recipe.id)) == 2


def test_history_is_newest_first(store) -> None:
    recipe = get_recipe("002-simple-syrup")
    _commit(store, recipe, at="2026-07-20T10:00:00")
    _commit(store, recipe.model_copy(update={"servings": 2}), at="2026-07-20T12:00:00")
    _commit(store, recipe.model_copy(update={"servings": 3}), at="2026-07-20T14:00:00")
    history = store.history(recipe.id)
    assert [v.created_at for v in history] == [
        "2026-07-20T14:00:00",
        "2026-07-20T12:00:00",
        "2026-07-20T10:00:00",
    ]


def test_missing_recipe_head_raises(store) -> None:
    with pytest.raises(RefNotFoundError):
        store.head_recipe("rcp_does_not_exist")


def test_list_recipe_ids(store) -> None:
    _commit(store, get_recipe("001-boiled-egg"))
    _commit(store, get_recipe("006-roesti"))
    assert store.list_recipe_ids() == ["rcp_001_boiled_egg", "rcp_006_roesti"]


def test_filesystem_store_reloads_from_disk(tmp_path: Path) -> None:
    """A fresh store object over the same directory sees prior commits."""
    recipe = get_recipe("006-roesti")
    FilesystemStore(tmp_path).commit(recipe, author="user:alice", created_at="2026-07-20T10:00:00")
    reopened = FilesystemStore(tmp_path)
    assert content_hash(reopened.head_recipe(recipe.id)) == content_hash(recipe)


def test_filesystem_recipe_json_is_the_hashed_bytes(tmp_path: Path) -> None:
    from snapcook_core.canonical.hashing import canonical_bytes, hash_bytes

    recipe = get_recipe("006-roesti")
    FilesystemStore(tmp_path).commit(recipe, author="user:alice", created_at="2026-07-20T10:00:00")
    written = (tmp_path / recipe.id / "recipe.json").read_bytes()
    assert written == canonical_bytes(recipe)
    assert hash_bytes(written) == content_hash(recipe)


# -- removing a recipe --------------------------------------------------------------


def test_a_removed_recipe_is_gone(store) -> None:
    egg, roesti = get_recipe("001-boiled-egg"), get_recipe("006-roesti")
    _commit(store, egg)
    _commit(store, roesti)
    assert store.remove(egg.id) is True
    assert store.list_recipe_ids() == [roesti.id]
    assert not store.exists(egg.id)
    with pytest.raises(RefNotFoundError):
        store.head_recipe(egg.id)
    assert store.remove(egg.id) is False, "removing twice finds nothing the second time"


def test_removing_what_was_never_there_finds_nothing(store) -> None:
    assert store.remove("rcp_does_not_exist") is False


def test_the_filesystem_store_keeps_a_removed_recipe_in_its_trash(tmp_path: Path) -> None:
    """Moved aside whole, so whoever runs the server can move it back."""
    recipe = get_recipe("006-roesti")
    store = FilesystemStore(tmp_path)
    store.commit(recipe, author="user:alice", created_at="2026-07-20T10:00:00")
    store.remove(recipe.id)
    assert not (tmp_path / recipe.id).exists()
    kept = tmp_path / ".trash" / recipe.id
    assert (kept / "recipe.json").is_file() and (kept / ".snapcook").is_dir()
    assert FilesystemStore(tmp_path).list_recipe_ids() == []

    (kept).rename(tmp_path / recipe.id)
    assert content_hash(FilesystemStore(tmp_path).head_recipe(recipe.id)) == content_hash(recipe)


def test_a_second_removal_of_the_same_id_does_not_overwrite_the_first(tmp_path: Path) -> None:
    recipe = get_recipe("006-roesti")
    store = FilesystemStore(tmp_path)
    for at in ("2026-07-20T10:00:00", "2026-07-21T10:00:00"):
        store.commit(recipe, author="user:alice", created_at=at)
        store.remove(recipe.id)
    assert sorted(p.name for p in (tmp_path / ".trash").iterdir()) == [recipe.id, f"{recipe.id}.2"]


# -- handing a recipe to someone else -----------------------------------------------


def test_reassigning_makes_a_version_with_the_same_content_and_a_new_author(store) -> None:
    recipe = get_recipe("006-roesti")
    first = _commit(store, recipe)
    moved = store.reassign(recipe.id, author="user:bob", created_at="2026-07-21T10:00:00")
    assert (moved.author, moved.origin, moved.parents) == (
        "user:bob",
        "reassigned",
        [first.version_id],
    )
    assert moved.content_hash == first.content_hash
    assert moved.version_id != first.version_id
    assert store.head(recipe.id).author == "user:bob"
    assert len(store.history(recipe.id)) == 2


def test_reassigning_to_the_author_already_there_changes_nothing(store) -> None:
    recipe = get_recipe("006-roesti")
    first = _commit(store, recipe)
    assert store.reassign(recipe.id, author="user:alice", created_at="2026-07-21T10:00:00") == first
    assert len(store.history(recipe.id)) == 1


def test_reassigning_what_is_not_there_raises(store) -> None:
    with pytest.raises(RefNotFoundError):
        store.reassign("rcp_does_not_exist", author="user:bob", created_at="2026-07-21T10:00:00")
