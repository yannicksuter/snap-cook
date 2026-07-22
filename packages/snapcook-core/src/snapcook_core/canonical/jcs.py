# SPDX-License-Identifier: Apache-2.0
"""RFC 8785 JSON Canonicalization Scheme serialisation.

Thin wrapper over ``rfc8785`` that adds one guard: a float must never reach the
serialiser. :mod:`snapcook_core.canonical.encode` already rejects floats when
walking a model, but ``dumps`` is also called on hand-built dicts (the version
header, test vectors), so the check is repeated at the boundary where the bytes
are actually produced.

Why RFC 8785 rather than ``json.dumps(sort_keys=True)``: JCS pins the details
that bite across languages -- key ordering by UTF-16 code unit rather than
code point, string escaping, and the absence of insignificant whitespace. A
Dart or Rust client can implement it from the spec and agree with us byte for
byte.
"""

from __future__ import annotations

from typing import Any

import rfc8785

from snapcook_core.errors import CanonicalizationError, NonCanonicalFloatError

__all__ = ["dumps"]


def _assert_no_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        raise NonCanonicalFloatError(
            f"float at {path} would serialise as an ECMAScript double, which is not "
            "portable across languages. Encode non-integer numerics as strings."
        )
    if isinstance(value, dict):
        for key, val in value.items():
            _assert_no_floats(val, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, val in enumerate(value):
            _assert_no_floats(val, f"{path}[{index}]")


def dumps(doc: Any) -> bytes:
    """Serialise a canonical document to RFC 8785 bytes."""
    _assert_no_floats(doc)
    try:
        return rfc8785.dumps(doc)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise CanonicalizationError(f"JCS serialisation failed: {exc}") from exc
