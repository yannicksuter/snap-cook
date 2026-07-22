# SPDX-License-Identifier: Apache-2.0
"""Content and version hashing -- the frozen wire contract.

Two hashes exist and the distinction is deliberate:

``content_hash``
    Identity of the recipe *content*. Drives the no-op rule: if a commit's
    content hash equals HEAD's, no version is written. Reformatting a ``.cook``
    file, reordering frontmatter keys or writing ``@onion{}`` instead of
    ``@onion`` therefore produce no new version. Identity is meaning, not bytes.

``version_id``
    Identity of the *commit*. Includes author, timestamp and parents, so two
    people who independently author byte-identical recipes still get distinct
    versions -- the same semantics git has.

SHA-256 from the standard library, not BLAKE3: a Dart, Rust or JavaScript
client must be able to verify a version id with no native dependencies. That
portability is worth more here than hashing speed, since recipes are kilobytes.

.. warning::
   Changing anything in this module or in :mod:`snapcook_core.canonical.encode`
   changes every hash in every store that exists. It requires a FORMAT_VERSION
   bump, a store migration, and regeneration of ``tests/contract/hashes.json``.
   ``tests/contract/`` exists to make that impossible to do by accident.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from snapcook_core.canonical.encode import normalize_text, to_canonical_doc
from snapcook_core.canonical.jcs import dumps
from snapcook_core.version import HASH_ALGO_PREFIX

if TYPE_CHECKING:
    from snapcook_core.ids import VersionId

__all__ = [
    "canonical_bytes",
    "content_hash",
    "hash_bytes",
    "version_id",
    "is_hash",
]


def hash_bytes(payload: bytes) -> str:
    """Hash raw bytes into the prefixed form used everywhere in the store."""
    return f"{HASH_ALGO_PREFIX}:{hashlib.sha256(payload).hexdigest()}"


def canonical_bytes(model: BaseModel) -> bytes:
    """The exact bytes a model hashes over.

    Exposed because the store writes these bytes to disk and the API serves
    them verbatim: the bytes a client verifies are the bytes we hashed, with no
    re-serialisation in between that could introduce a discrepancy.
    """
    return dumps(to_canonical_doc(model))


def content_hash(model: BaseModel) -> str:
    """Identity of recipe content. See module docstring."""
    return hash_bytes(canonical_bytes(model))


def version_id(
    *,
    schema_version: int,
    content_hash_value: str,
    parents: list[str],
    author_key: str,
    created_at_iso: str,
    message: str | None,
    origin: str,
) -> VersionId:
    """Identity of a commit.

    ``parents`` is sorted so that a merge's identity does not depend on the
    order the parents happened to be supplied in.
    """
    header: dict[str, Any] = {
        "schema_version": schema_version,
        "content_hash": content_hash_value,
        "parents": sorted(parents),
        "author": normalize_text(author_key),
        "created_at": created_at_iso,
        "message": normalize_text(message or ""),
        "origin": origin,
    }
    from snapcook_core.ids import VersionId as _VersionId

    return _VersionId(hash_bytes(dumps(header)))


def is_hash(value: str) -> bool:
    """True if ``value`` is a well-formed snapcook hash string."""
    prefix, sep, digest = value.partition(":")
    if not sep or prefix != HASH_ALGO_PREFIX or len(digest) != 64:
        return False
    return all(c in "0123456789abcdef" for c in digest)
