# SPDX-License-Identifier: Apache-2.0
"""Scaling a recipe up or down.

Two properties this module is built around, both of which are easy to lose:

**Scaling is exact.** No rounding happens here. ``Decimal`` multiplication is
exact, so ``scale(scale(q, 2), Decimal("0.5"))`` returns the original value
rather than something that has drifted. Rounding is a *display* concern and
lives in :mod:`snapcook_core.units.rounding`; keeping the two apart is what
stops rounding error from compounding every time a reader changes the serving
count.

**Scaling is a view, not an edit.** Doubling a recipe produces a scaled
rendering, never a new version. There is an explicit "save this scaled version"
action elsewhere; it is not a side effect of looking at a recipe.
"""

from __future__ import annotations

from decimal import Decimal

from snapcook_core.errors import CODE_SCALING_MANUAL, IssueCollector
from snapcook_core.schema.quantity import (
    Approx,
    Count,
    Quantity,
    QuantitySpec,
    Range,
    Scalar,
    ScalingPolicy,
)

__all__ = ["scale_quantity", "scale_spec", "scales_with_factor"]


def scales_with_factor(policy: ScalingPolicy) -> bool:
    """Whether a policy multiplies at all.

    ``NONLINEAR`` is treated as ``MANUAL`` until real curve data exists.
    Guessing a curve is worse than declining to scale, because a wrong bake
    time looks authoritative.
    """
    return policy is ScalingPolicy.LINEAR


def scale_quantity(quantity: Quantity, factor: Decimal) -> Quantity:
    """Multiply a quantity, ignoring policy.

    Prefer :func:`scale_spec`, which consults the policy. This exists for the
    cases where the caller has already decided that scaling applies.
    """
    if factor <= 0:
        raise ValueError(f"scale factor must be positive, got {factor}")

    if isinstance(quantity, Approx):
        # The identity function, always. `nominal` is advisory and is not
        # scaled either -- treating it as a number is how "salt to taste"
        # starts doubling.
        return quantity

    if isinstance(quantity, Scalar):
        return quantity.model_copy(update={"value": quantity.value * factor})

    if isinstance(quantity, Range):
        return quantity.model_copy(
            update={"low": quantity.low * factor, "high": quantity.high * factor}
        )

    if isinstance(quantity, Count):
        return quantity.model_copy(
            update={
                "value": quantity.value * factor,
                "high": None if quantity.high is None else quantity.high * factor,
            }
        )

    raise TypeError(f"unscalable quantity type: {type(quantity).__name__}")


def scale_spec(
    spec: QuantitySpec,
    factor: Decimal,
    *,
    issues: IssueCollector | None = None,
    element_id: str | None = None,
) -> QuantitySpec:
    """Scale a quantity according to its policy.

    ``MANUAL`` and ``NONLINEAR`` quantities are returned unchanged and, when an
    :class:`IssueCollector` is supplied, recorded so the renderer can tell the
    reader to check them. A silently unscaled bake time is indistinguishable
    from a correctly scaled one, which is exactly the failure this warning
    exists to prevent.
    """
    if factor == 1:
        # Not merely an optimisation: it guarantees scaling by 1 is bit-for-bit
        # identity, so a "1x" view can never differ from the stored recipe.
        return spec

    if not scales_with_factor(spec.scaling):
        if spec.scaling in (ScalingPolicy.MANUAL, ScalingPolicy.NONLINEAR) and issues is not None:
            issues.add(
                CODE_SCALING_MANUAL,
                f"not scaled automatically ({spec.scaling.value}); check this value "
                f"for a {factor}x batch",
                severity="warn",
                element_id=element_id,
            )
        return spec

    return spec.model_copy(update={"quantity": scale_quantity(spec.quantity, factor)})
