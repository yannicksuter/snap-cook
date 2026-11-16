#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Role dispatch. One image serves both the web tier and the job worker; which
# one you get depends on the first argument (see CMD in the Dockerfile,
# `command:` in docker-compose.yml, and Post Arguments on Unraid). Any other
# first argument runs as a command instead.
#
# `python` and `gunicorn` are the image's virtualenv (PATH, in the Dockerfile).
# Not `uv run`: it re-syncs on every start and needs PyPI to do it.
set -e

ROLE="${1:-web}"
# The HEALTHCHECK runs as a separate process and cannot see this one's
# arguments, so the running role leaves its name here for it.
ROLE_FILE=/tmp/snapcook-role
cd /app/apps/web

case "$ROLE" in
  web)
    echo web > "$ROLE_FILE"
    python manage.py migrate --noinput
    exec gunicorn snapcookweb.wsgi:application \
        --bind 0.0.0.0:8931 \
        --workers 2 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -
    ;;
  worker)
    echo worker > "$ROLE_FILE"
    # Deliberately does NOT migrate. The web container owns the schema; two
    # containers racing `migrate` on startup is a real way to corrupt a
    # database, and it only shows up under the exact timing that a restart
    # produces.
    exec python manage.py qcluster
    ;;
  shell)
    exec python manage.py shell
    ;;
  healthcheck)
    # Shallow on purpose, like /up itself: a check that touches Postgres would
    # mark the app unhealthy during a routine database restart.
    if [ "$(cat "$ROLE_FILE" 2>/dev/null)" = web ]; then
      exec python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8931/up', timeout=4)"
    fi
    # The worker has no endpoint; Docker already sees its process exit.
    exit 0
    ;;
  *)
    # Anything else is a one-off command, so the runbooks' form works as
    # written: `docker compose run --rm web python manage.py migrate`.
    exec "$@"
    ;;
esac
