#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Regenerate golden renderer outputs, then show what changed.
#
# Golden files are REVIEWED, not regenerated blindly. That is the whole value of
# the mechanism: the diff is the review surface, and a rubber-stamped golden
# update is indistinguishable from an unnoticed rendering regression.
set -euo pipefail
cd "$(dirname "$0")/.."

SNAPCOOK_UPDATE_GOLDEN=1 uv run pytest packages/snapcook-core -m golden -q

echo
echo "==================== READ THIS DIFF ===================="
git diff --stat -- packages/snapcook-core/tests/golden || true
echo
echo "Review every changed line before committing. If you cannot explain a"
echo "change, it is a regression, not an update."
