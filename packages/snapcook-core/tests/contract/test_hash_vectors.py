# SPDX-License-Identifier: Apache-2.0
"""Frozen hash vectors -- the cross-language contract.

These run as their own CI job (`contract`) so that a failure here reads very
differently from an ordinary test failure. A red `core` job means someone broke
some code. A red `contract` job means **every recipe hash in every store on
every machine just changed**, including stores we do not control.

The vectors are deliberately primitive rather than full recipes: they pin the
*encoding*, which is the layer a Dart or Rust client must reimplement from the
RFC. A client that reproduces these 19 hashes has a correct implementation.

If a change here is intentional, the procedure is:

1. bump ``FORMAT_VERSION`` in ``snapcook_core/version.py``
2. add a migration under ``snapcook_core/migrate/``
3. regenerate this file
4. review it as a breaking change, and say so in the changelog

If it is *not* intentional, canonicalisation is broken -- do not regenerate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from snapcook_core.canonical import dumps, hash_bytes

VECTORS_PATH = Path(__file__).parent / "hash_vectors.json"
_DATA: dict[str, Any] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
_VECTORS: dict[str, Any] = _DATA["vectors"]

pytestmark = pytest.mark.contract

_BREAKAGE_HINT = (
    "\n\n"
    "Content hashes are a FROZEN WIRE CONTRACT. Existing stores on disk -- and "
    "any Flutter/CLI client -- reference these exact values.\n"
    "If this change is intentional: bump FORMAT_VERSION, add a migration, "
    "regenerate hash_vectors.json, and review it as a breaking change.\n"
    "If it is not intentional: canonicalisation is broken. Do not regenerate."
)


@pytest.mark.parametrize("name", sorted(_VECTORS))
def test_vector_hash_is_stable(name: str) -> None:
    vector = _VECTORS[name]
    actual = hash_bytes(dumps(vector["doc"]))
    assert actual == vector["hash"], f"hash drift for vector {name!r}{_BREAKAGE_HINT}"


@pytest.mark.parametrize("name", sorted(_VECTORS))
def test_vector_jcs_bytes_are_stable(name: str) -> None:
    """Pins the serialisation itself, not just its digest.

    Checked separately so that when something does break, the failure says
    whether the *bytes* changed or only the hashing of them -- which is the
    difference between an encoder bug and a digest bug.
    """
    vector = _VECTORS[name]
    actual = dumps(vector["doc"]).decode()
    assert actual == vector["jcs"], f"JCS drift for vector {name!r}{_BREAKAGE_HINT}"


def test_key_order_does_not_change_the_hash() -> None:
    """JCS sorts keys, so two orderings of one object are one object."""
    assert _VECTORS["key-order-a"]["hash"] == _VECTORS["key-order-z-first"]["hash"]


def test_vectors_cover_the_known_failure_modes() -> None:
    """Guard against someone thinning the vector set during a refactor."""
    required = {
        "decimal-as-string",  # the ECMAScript-double trap
        "unicode-nfc",  # composed vs decomposed
        "unicode-cjk",
        "unicode-emoji",  # surrogate pairs, where UTF-16 ordering bites
        "escapes",
        "boolean-true",  # bool-is-a-subclass-of-int
        "null-value",
        "key-order-a",
    }
    missing = required - set(_VECTORS)
    assert not missing, f"hash vectors lost coverage of: {sorted(missing)}"


def test_all_hashes_are_well_formed() -> None:
    for name, vector in _VECTORS.items():
        prefix, _, digest = vector["hash"].partition(":")
        assert prefix == "sc1", name
        assert len(digest) == 64, name
