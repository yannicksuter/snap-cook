# SPDX-License-Identifier: Apache-2.0
"""Where a recipe came from.

Provenance is a **schema field, not a comment**. ADR 0002 dropped YAML comments
from identity, so anything that must survive a machine rewrite -- the source
URL, the licence it arrived under, the attribution a licence obliges us to keep
-- has to be a real field. It is right anyway: attribution you cannot query or
render is attribution you will eventually lose.

The line between semantic and non-semantic runs through this model. *What* the
recipe is and *whose* work it derives from is content and is hashed. *When we
happened to fetch it* and *which importer build ran* is bookkeeping: it must not
change the recipe's identity, or re-importing the same page tomorrow would fork
the lineage. Those fields are :data:`NonSemantic`.
"""

from __future__ import annotations

from typing import Literal

from snapcook_core.schema.base import NonSemantic, SnapcookModel

__all__ = ["Origin", "Provenance"]

Origin = Literal["authored", "imported", "forked"]


class Provenance(SnapcookModel):
    """The origin and licensing of a recipe's content."""

    origin: Origin = "authored"

    source_url: str | None = None
    source_title: str | None = None
    author: str | None = None
    """The upstream author, when the recipe derives from a named source. This is
    attribution, distinct from the *committer* recorded in the version header."""

    license_spdx: str | None = None
    """SPDX identifier of the licence the source content carries. Drives the fork
    licence lattice; a missing value is treated as all-rights-reserved."""

    attribution: str | None = None
    """The exact attribution string a licence obliges us to display. Kept
    verbatim because paraphrasing an attribution can itself breach the licence."""

    notes: str | None = None

    # -- bookkeeping: describes our handling, not the recipe. Never hashed. -----
    retrieved_at: NonSemantic[str | None] = None
    importer: NonSemantic[str | None] = None
