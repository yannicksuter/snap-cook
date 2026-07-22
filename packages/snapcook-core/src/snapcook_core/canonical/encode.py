# SPDX-License-Identifier: Apache-2.0
"""Reduce a validated model to a canonical, hashable document.

This module and :mod:`snapcook_core.canonical.hashing` together define the
identity of a recipe. Everything else in the project depends on them being
right, which is why they are built before any feature code.

The rules, and why each exists:

**Decimals encode as JSON strings.**
    RFC 8785 mandates ECMAScript double serialisation for JSON *numbers*.
    Round-tripping ``Decimal("0.1")`` through a float is lossy, and its
    shortest-representation is implementation sensitive. If quantities were
    encoded as numbers, the Python backend and a Dart mobile client would
    compute different hashes for the same recipe and silently fork the lineage
    DAG. Encoding them as strings sidesteps the entire class of problem.

**Floats are rejected, not converted.**
    Converting would hide the bug. ``float`` is banned from every schema field;
    reaching the encoder with one means a schema mistake, and it should fail
    loudly at the point of the mistake.

**NonSemantic fields are stripped.**
    So that re-importing the same recipe tomorrow hashes identically to today.

**Absent is identical to empty.**
    ``None``, ``[]`` and ``{}`` all encode as absent. Otherwise a field
    defaulting from ``None`` to ``[]`` in a later release would change every
    stored hash without changing any recipe.

**Text is NFC-normalised.**
    "café" typed on macOS (decomposed) and on Linux (composed) are the same
    word and must hash identically.

**List order is preserved and never sorted.**
    Order is semantic here: the chunks of a step's prose, and the authored
    sequence of actions. Sorting them generically would be a correctness bug.
    Where a collection genuinely has no meaningful order, the *model* sorts it
    at construction time -- that is a schema concern, not an encoding one.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from snapcook_core.errors import CanonicalizationError, NonCanonicalFloatError
from snapcook_core.schema.base import non_semantic_fields

__all__ = ["to_canonical_doc", "encode_decimal", "normalize_text"]


def normalize_text(value: str) -> str:
    """NFC-normalise a string so equivalent Unicode forms hash identically."""
    return unicodedata.normalize("NFC", value)


def encode_decimal(value: Decimal) -> str:
    """Render a Decimal in a single unambiguous textual form.

    Trailing zeros are stripped and exponent notation is never emitted, so
    ``1.50``, ``1.5`` and ``1.500`` all produce ``"1.5"`` -- three ways of
    typing the same quantity must not be three different recipes.
    """
    if not value.is_finite():
        raise CanonicalizationError(f"non-finite Decimal is not canonicalizable: {value!r}")
    if value == 0:
        # Collapses both "0.000" and "-0" to a single form.
        return "0"
    return format(value.normalize(), "f")


def _encode(value: Any) -> Any:
    # bool before int: bool is a subclass of int and must stay a JSON boolean.
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, float):
        raise NonCanonicalFloatError(
            f"float reached the canonical encoder: {value!r}. "
            "Use Decimal -- see the module docstring for why floats break "
            "cross-language hash agreement."
        )

    if isinstance(value, Decimal):
        return encode_decimal(value)

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        return normalize_text(value)

    if isinstance(value, Enum):
        return _encode(value.value)

    if isinstance(value, BaseModel):
        return _encode_model(value)

    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"non-string mapping key is not canonicalizable: {key!r}"
                )
            encoded = _encode(val)
            if _is_absent(encoded):
                continue
            out[normalize_text(key)] = encoded
        return out

    raise CanonicalizationError(f"type {type(value).__name__} has no canonical encoding: {value!r}")


def _is_absent(value: Any) -> bool:
    """Absent, empty list and empty mapping are the same thing."""
    return value is None or value == [] or value == {}


def _encode_model(model: BaseModel) -> dict[str, Any]:
    skip = non_semantic_fields(type(model))
    out: dict[str, Any] = {}
    for name in type(model).model_fields:
        if name in skip:
            continue
        encoded = _encode(getattr(model, name))
        if _is_absent(encoded):
            continue
        out[name] = encoded
    return out


def to_canonical_doc(model: BaseModel) -> dict[str, Any]:
    """Reduce a validated model to a plain dict ready for JCS serialisation.

    Key ordering is not applied here -- RFC 8785 sorts keys by UTF-16 code unit
    during serialisation, which is stricter and more portable than anything
    done at this layer.
    """
    return _encode_model(model)
