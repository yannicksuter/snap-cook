#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Tier 0 only: no Django, no database, no network. The inner dev loop.
# Target runtime is under 3 seconds -- if it creeps past that, something has
# grown a dependency it should not have.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run pytest packages/snapcook-core --disable-socket "$@"
