#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Build the image with the current commit stamped in, so /up reports it.
set -euo pipefail
cd "$(dirname "$0")/.."
GIT_COMMIT="$(git rev-parse HEAD)" docker compose build "$@"
echo "built snap-cook:0.1.0 @ $(git rev-parse --short HEAD)"
