# SPDX-License-Identifier: Apache-2.0
"""Canonical encoding and hashing -- the identity of a recipe."""

from snapcook_core.canonical.encode import to_canonical_doc
from snapcook_core.canonical.hashing import (
    canonical_bytes,
    content_hash,
    hash_bytes,
    is_hash,
    version_id,
)
from snapcook_core.canonical.jcs import dumps

__all__ = [
    "canonical_bytes",
    "content_hash",
    "dumps",
    "hash_bytes",
    "is_hash",
    "to_canonical_doc",
    "version_id",
]
