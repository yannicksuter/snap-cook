# SPDX-License-Identifier: Apache-2.0
"""Tier-0 test configuration.

Tier 0 has no Django, no database and no network. That is what keeps it under
three seconds, and it is why roughly 70% of the suite lives here.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, Verbosity, settings

# Profiles, selected with --hypothesis-profile or HYPOTHESIS_PROFILE.
#
# `ci` is derandomized deliberately: a property test that fails only on some CI
# runs is worse than no test, because it trains people to hit re-run. A
# falsifying example found here should be promoted to an explicit regression
# test in tests/unit/ rather than left to chance.
settings.register_profile(
    "dev",
    max_examples=25,
    verbosity=Verbosity.normal,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("ci", max_examples=200, derandomize=True, deadline=None)
settings.register_profile("nightly", max_examples=2000, deadline=None)

settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
