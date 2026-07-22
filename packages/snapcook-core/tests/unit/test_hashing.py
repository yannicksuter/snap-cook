# SPDX-License-Identifier: Apache-2.0
"""Content and version hashing.

The two hashes exist for different jobs, and conflating them would break either
the no-op rule or git-like commit semantics.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snapcook_core.canonical import content_hash, hash_bytes, is_hash, version_id
from snapcook_core.errors import IssueCollector, ValidationIssue
from snapcook_core.schema.base import SnapcookModel


class Sample(SnapcookModel):
    name: str
    qty: Decimal


def _version(**overrides) -> str:
    kwargs = {
        "schema_version": 1,
        "content_hash_value": f"sc1:{'a' * 64}",
        "parents": [],
        "author_key": "user:alice",
        "created_at_iso": "2026-07-20T12:00:00",
        "message": "initial",
        "origin": "authored",
    }
    kwargs.update(overrides)
    return version_id(**kwargs)


# -- shape --------------------------------------------------------------------


def test_hashes_are_prefixed_and_well_formed() -> None:
    value = content_hash(Sample(name="bread", qty=Decimal("1")))
    prefix, _, digest = value.partition(":")
    assert prefix == "sc1"
    assert len(digest) == 64
    assert is_hash(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "deadbeef",
        "sha256:" + "a" * 64,  # wrong algorithm prefix
        "sc1:" + "a" * 63,  # too short
        "sc1:" + "a" * 65,  # too long
        "sc1:" + "z" * 64,  # not hex
        "sc1:" + "A" * 64,  # uppercase hex is not our canonical form
    ],
)
def test_is_hash_rejects_malformed_values(value: str) -> None:
    assert not is_hash(value)


def test_hash_bytes_is_stable() -> None:
    assert hash_bytes(b"snap-cook") == hash_bytes(b"snap-cook")
    assert hash_bytes(b"snap-cook") != hash_bytes(b"snap-cooked")


# -- content vs version -------------------------------------------------------


def test_identical_content_hashes_identically() -> None:
    a = Sample(name="bread", qty=Decimal("1.5"))
    b = Sample(name="bread", qty=Decimal("1.50"))
    assert content_hash(a) == content_hash(b)


def test_version_id_distinguishes_authors_of_identical_content() -> None:
    """Git semantics: same content, different commit.

    Two people independently writing the same recipe have not made one version
    -- they have made two, with different provenance.
    """
    assert _version(author_key="user:alice") != _version(author_key="user:bob")


def test_version_id_distinguishes_timestamps() -> None:
    assert _version(created_at_iso="2026-07-20T12:00:00") != _version(
        created_at_iso="2026-07-20T12:00:01"
    )


def test_version_id_distinguishes_messages() -> None:
    assert _version(message="a") != _version(message="b")


def test_version_id_treats_absent_message_as_empty() -> None:
    assert _version(message=None) == _version(message="")


def test_version_id_is_independent_of_parent_order() -> None:
    """A merge's identity must not depend on which parent was listed first."""
    a = f"sc1:{'1' * 64}"
    b = f"sc1:{'2' * 64}"
    assert _version(parents=[a, b]) == _version(parents=[b, a])


def test_version_id_changes_with_content() -> None:
    assert _version(content_hash_value=f"sc1:{'a' * 64}") != _version(
        content_hash_value=f"sc1:{'b' * 64}"
    )


def test_version_id_is_deterministic() -> None:
    assert _version() == _version()


# -- diagnostics --------------------------------------------------------------


def test_issue_collector_accumulates_without_raising() -> None:
    """Non-fatal findings must not abort an import.

    A recipe whose ingredient could not be bound, or whose unit is unknown, is
    still worth storing. Refusing it would make the importer useless on real
    input.
    """
    collector = IssueCollector()
    collector.add("UNIT_UNRESOLVED", "unknown unit 'knob'", path="/ingredients/0")
    assert not collector.has_errors
    assert len(collector.issues) == 1

    collector.add("CYCLE", "graph is cyclic", severity="error")
    assert collector.has_errors


def test_validation_issue_renders_readably() -> None:
    issue = ValidationIssue(
        code="INGREDIENT_UNBOUND",
        severity="warn",
        message="no match for 'Sauerteig'",
        path="/ingredients/3",
    )
    assert str(issue) == "[warn] INGREDIENT_UNBOUND at /ingredients/3: no match for 'Sauerteig'"


def test_validation_issue_without_a_path_still_renders() -> None:
    issue = ValidationIssue(code="X", severity="info", message="hello")
    assert str(issue) == "[info] X: hello"
