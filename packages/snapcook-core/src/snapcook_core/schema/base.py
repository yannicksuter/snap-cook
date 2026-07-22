# SPDX-License-Identifier: Apache-2.0
"""Base model and the semantic/non-semantic field distinction.

Two configuration choices here are load-bearing and worth the explanation:

``frozen=True``
    Versions are values, not objects. An edit produces a new ``Recipe``, never a
    mutation of an existing one. This is what lets a version be hashed once and
    cached forever.

``extra="forbid"``
    A newer-schema document read by an older client fails loudly instead of
    silently dropping the fields it does not recognise. In a content-addressed
    store, silently dropping fields and then re-committing is unrecoverable data
    destruction: the new hash looks legitimate and nothing records what was
    lost. A hard error is strictly better than quiet corruption.

``NonSemantic``
    Marks a field as *not part of the recipe's identity*. Timestamps, review
    metadata and retrieval dates describe bookkeeping, not content. They are
    stripped before hashing, so re-importing the same recipe tomorrow produces
    the same content hash as today.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

NON_SEMANTIC_KEY = "snapcook_non_semantic"


class SnapcookModel(BaseModel):
    """Immutable, strict base for every schema model."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=False,
        validate_default=True,
    )


NonSemantic = Annotated[T, Field(json_schema_extra={NON_SEMANTIC_KEY: True})]
"""Field excluded from the content hash. See module docstring."""


def non_semantic_fields(model_cls: type[BaseModel]) -> frozenset[str]:
    """Field names on ``model_cls`` marked NonSemantic.

    Resolved from the field's json_schema_extra rather than a hand-maintained
    list, so marking a field and excluding it from the hash are the same edit --
    they cannot drift apart.
    """
    out: set[str] = set()
    for name, info in model_cls.model_fields.items():
        extra: Any = info.json_schema_extra
        if isinstance(extra, dict) and extra.get(NON_SEMANTIC_KEY) is True:
            out.add(name)
    return frozenset(out)
