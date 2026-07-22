# SPDX-License-Identifier: Apache-2.0
"""Canonical encoding rules.

Each test here corresponds to a rule stated in canonical/encode.py, and each
rule exists to prevent a specific way that two clients could disagree about a
recipe's identity.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

import pytest
from pydantic import BaseModel

from snapcook_core.canonical import canonical_bytes, content_hash, dumps, to_canonical_doc
from snapcook_core.canonical.encode import encode_decimal, normalize_text
from snapcook_core.errors import CanonicalizationError, NonCanonicalFloatError
from snapcook_core.schema.base import NonSemantic, SnapcookModel


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class Inner(SnapcookModel):
    label: str
    amount: Decimal


class Sample(SnapcookModel):
    name: str
    count: int
    ratio: Decimal
    flag: bool
    colour: Colour | None = None
    tags: list[str] = []
    meta: dict[str, str] = {}
    inner: Inner | None = None
    captured_at: NonSemantic[str | None] = None


# -- decimals -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.50", "1.5"),
        ("1.500", "1.5"),
        ("1.5", "1.5"),
        ("1.00", "1"),
        ("100", "100"),
        ("1E+2", "100"),
        ("0.000", "0"),
        ("-0", "0"),
        ("-0.0", "0"),
        ("0.125", "0.125"),
        ("-2.50", "-2.5"),
        ("0.1", "0.1"),
    ],
)
def test_decimal_has_one_textual_form(raw: str, expected: str) -> None:
    """Three ways of typing the same quantity must not be three recipes."""
    assert encode_decimal(Decimal(raw)) == expected


def test_equal_decimals_hash_identically() -> None:
    a = Sample(name="x", count=1, ratio=Decimal("1.50"), flag=True)
    b = Sample(name="x", count=1, ratio=Decimal("1.5"), flag=True)
    assert content_hash(a) == content_hash(b)


def test_decimals_encode_as_strings_not_numbers() -> None:
    """The rule that keeps Python and Dart agreeing on a hash."""
    doc = to_canonical_doc(Sample(name="x", count=2, ratio=Decimal("0.1"), flag=False))
    assert doc["ratio"] == "0.1"
    assert isinstance(doc["ratio"], str)
    # Integers stay integers -- only non-integer numerics become strings.
    assert doc["count"] == 2
    assert isinstance(doc["count"], int)


def test_non_finite_decimal_is_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        encode_decimal(Decimal("NaN"))
    with pytest.raises(CanonicalizationError):
        encode_decimal(Decimal("Infinity"))


# -- floats -------------------------------------------------------------------


def test_float_is_rejected_by_the_serialiser() -> None:
    with pytest.raises(NonCanonicalFloatError):
        dumps({"value": 0.1})


def test_float_nested_in_a_list_is_rejected() -> None:
    with pytest.raises(NonCanonicalFloatError):
        dumps({"values": [1, 2, 3.5]})


def test_bool_is_not_mistaken_for_a_number() -> None:
    """bool subclasses int; it must survive as a JSON boolean."""
    doc = to_canonical_doc(Sample(name="x", count=0, ratio=Decimal("1"), flag=True))
    assert doc["flag"] is True
    assert b"true" in dumps(doc)


# -- absence ------------------------------------------------------------------


def test_none_empty_list_and_empty_dict_are_all_absent() -> None:
    """Otherwise a default changing from None to [] rewrites every stored hash."""
    a = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, tags=[], meta={})
    b = Sample(name="x", count=1, ratio=Decimal("1"), flag=False)
    assert to_canonical_doc(a) == to_canonical_doc(b)
    assert content_hash(a) == content_hash(b)
    assert "tags" not in to_canonical_doc(a)


# -- non-semantic fields ------------------------------------------------------


def test_non_semantic_fields_do_not_affect_identity() -> None:
    """Re-importing the same recipe tomorrow must hash like it did today."""
    a = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, captured_at="2026-01-01T00:00:00")
    b = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, captured_at="2026-07-20T13:00:00")
    assert content_hash(a) == content_hash(b)
    assert "captured_at" not in to_canonical_doc(a)


# -- unicode ------------------------------------------------------------------


def test_nfc_normalisation_makes_equivalent_text_hash_equally() -> None:
    """'cafe' + combining acute (macOS) vs precomposed 'café' (Linux)."""
    decomposed = "café"
    composed = "café"
    assert decomposed != composed
    assert normalize_text(decomposed) == composed

    a = Sample(name=decomposed, count=1, ratio=Decimal("1"), flag=False)
    b = Sample(name=composed, count=1, ratio=Decimal("1"), flag=False)
    assert content_hash(a) == content_hash(b)


def test_dict_keys_are_normalised_too() -> None:
    a = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, meta={"café": "v"})
    b = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, meta={"café": "v"})
    assert content_hash(a) == content_hash(b)


# -- ordering -----------------------------------------------------------------


def test_list_order_is_preserved_not_sorted() -> None:
    """Order is semantic: step prose chunks and action sequence depend on it."""
    a = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, tags=["b", "a"])
    b = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, tags=["a", "b"])
    assert to_canonical_doc(a)["tags"] == ["b", "a"]
    assert content_hash(a) != content_hash(b)


def test_mapping_key_order_does_not_affect_identity() -> None:
    """JCS sorts keys, so insertion order is irrelevant."""
    a = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, meta={"z": "1", "a": "2"})
    b = Sample(name="x", count=1, ratio=Decimal("1"), flag=False, meta={"a": "2", "z": "1"})
    assert content_hash(a) == content_hash(b)


# -- nesting and enums --------------------------------------------------------


def test_nested_models_and_enums_encode() -> None:
    s = Sample(
        name="x",
        count=1,
        ratio=Decimal("1"),
        flag=False,
        colour=Colour.RED,
        inner=Inner(label="roux", amount=Decimal("2.50")),
    )
    doc = to_canonical_doc(s)
    assert doc["colour"] == "red"
    assert doc["inner"] == {"label": "roux", "amount": "2.5"}


def test_unencodable_type_is_rejected_loudly() -> None:
    class Bad(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        value: object

    with pytest.raises(CanonicalizationError):
        to_canonical_doc(Bad(value=object()))


# -- byte-level guarantees ----------------------------------------------------


def test_canonical_bytes_have_no_insignificant_whitespace() -> None:
    raw = canonical_bytes(Sample(name="x", count=1, ratio=Decimal("1"), flag=False))
    assert b": " not in raw
    assert b", " not in raw


def test_canonical_bytes_are_the_bytes_that_were_hashed() -> None:
    """The API serves these verbatim; a client must be able to verify them."""
    import hashlib

    s = Sample(name="x", count=1, ratio=Decimal("1"), flag=False)
    raw = canonical_bytes(s)
    assert content_hash(s) == f"sc1:{hashlib.sha256(raw).hexdigest()}"
