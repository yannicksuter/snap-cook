#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Every tier except evals (which cost money and are non-deterministic).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== lint =="
uv run ruff check .
uv run ruff format --check .

echo "== tier 0: core =="
uv run pytest packages/snapcook-core --disable-socket -q

echo "== tier 1+2: web =="
uv run pytest apps/web -q "$@"
