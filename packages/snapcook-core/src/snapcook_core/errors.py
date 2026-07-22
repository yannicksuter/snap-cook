# SPDX-License-Identifier: Apache-2.0
"""Error tree and the non-fatal diagnostic type.

The distinction that matters here: an *error* means the operation cannot
proceed, a *ValidationIssue* means something is imperfect but the recipe is
still storable. Import throughput depends on that difference -- a recipe whose
ingredient could not be bound to the registry, or whose unit is unrecognised, is
still a legitimate recipe worth keeping. Refusing to store it would make the
importer useless on real-world input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["info", "warn", "error"]


class SnapcookError(Exception):
    """Base for every error raised by this library."""


# -- canonical / hashing ------------------------------------------------------


class CanonicalizationError(SnapcookError):
    """The model could not be reduced to canonical form."""


class NonCanonicalFloatError(CanonicalizationError):
    """A float reached the encoder.

    Floats are banned from every schema field. RFC 8785 serialises JSON numbers
    as ECMAScript doubles, so a float's canonical form is implementation
    sensitive -- the Python backend and a Dart client would compute *different
    hashes for the same recipe* and silently fork the lineage DAG. All
    non-integer numerics are Decimal, and are encoded as JSON strings.
    """


# -- units --------------------------------------------------------------------


class UnitError(SnapcookError):
    """Base for unit and quantity conversion failures."""


class IncompatibleDimensionsError(UnitError):
    """Conversion across dimensions with no bridging context.

    Never degrade this to a best-effort guess. Silently treating grams as
    millilitres is a correctness disaster in baking.
    """


class NoDensityError(UnitError):
    """Volume<->mass was requested but no density is known for this ingredient.

    Deliberately fatal rather than defaulting to water at 1.0 g/ml. A wrong
    density is worse than a refusal because it is invisible.
    """


class NoCountWeightError(UnitError):
    """A counted ingredient ('1 medium onion') has no piece-weight table."""


class NotScalableError(UnitError):
    """Scaling was requested on a quantity that has no numeric meaning."""


# -- schema / graph -----------------------------------------------------------


class SchemaError(SnapcookError):
    """Base for structural problems in a recipe."""


class GraphError(SchemaError):
    """The action graph is malformed."""


class CyclicGraphError(GraphError):
    """The action graph contains a cycle, so it cannot be a recipe."""


class DanglingReferenceError(GraphError):
    """An action input references a food-state or ingredient that does not exist."""


class SchemaVersionError(SchemaError):
    """A document declares a FORMAT_VERSION this build cannot migrate."""


# -- store --------------------------------------------------------------------


class StoreError(SnapcookError):
    """Base for version-store failures."""


class ObjectNotFoundError(StoreError):
    """No object exists at the requested hash."""


class RefNotFoundError(StoreError):
    """No such ref (branch) for this recipe."""


class ConcurrentWriteError(StoreError):
    """Optimistic concurrency check failed: HEAD moved under us."""


# -- diagnostics --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A non-fatal finding. Collected, surfaced to the user, never raised.

    ``path`` is an RFC 6901 JSON Pointer into the recipe so a UI can jump
    straight to the offending element.
    """

    code: str
    severity: Severity
    message: str
    path: str | None = None
    element_id: str | None = None

    def __str__(self) -> str:
        loc = f" at {self.path}" if self.path else ""
        return f"[{self.severity}] {self.code}{loc}: {self.message}"


@dataclass(slots=True)
class IssueCollector:
    """Accumulates issues during parse/lower/render without aborting."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: Severity = "warn",
        path: str | None = None,
        element_id: str | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                severity=severity,
                message=message,
                path=path,
                element_id=element_id,
            )
        )

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


# Stable issue codes. Keep in sync with docs/reference/testing.md.
CODE_UNIT_UNRESOLVED = "UNIT_UNRESOLVED"
CODE_UNIT_UNKNOWN = "UNIT_UNKNOWN"
CODE_INGREDIENT_UNBOUND = "INGREDIENT_UNBOUND"
CODE_NO_DENSITY = "NO_DENSITY"
CODE_STALE_TRANSLATION = "STALE_TRANSLATION"
CODE_SCALING_MANUAL = "SCALING_MANUAL"
CODE_ORPHAN_INGREDIENT = "ORPHAN_INGREDIENT"
