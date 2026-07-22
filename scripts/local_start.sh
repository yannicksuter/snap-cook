#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Start the stack and wait until it actually answers.
#
# Note: a plain `docker compose restart` keeps the OLD image. To pick up code
# changes the containers must be recreated, which --build does.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "no .env -- copy .env.example and fill it in" >&2; exit 1; }

GIT_COMMIT="$(git rev-parse HEAD)" docker compose up -d --build

printf 'waiting for /up '
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8931/up >/dev/null 2>&1; then
    echo
    curl -sS http://localhost:8931/up
    echo
    exit 0
  fi
  printf '.'
  sleep 1
done
echo
echo "timed out; recent logs:" >&2
docker compose logs --tail 40 web >&2
exit 1
