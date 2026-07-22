#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Role dispatch. One image serves both the web tier and the job worker; which
# one you get depends on the first argument (see CMD in the Dockerfile and
# `command:` in docker-compose.yml).
set -e

ROLE="${1:-web}"
cd /app/apps/web

case "$ROLE" in
  web)
    uv run python manage.py migrate --noinput
    exec uv run gunicorn snapcookweb.wsgi:application \
        --bind 0.0.0.0:8931 \
        --workers 2 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -
    ;;
  worker)
    # Deliberately does NOT migrate. The web container owns the schema; two
    # containers racing `migrate` on startup is a real way to corrupt a
    # database, and it only shows up under the exact timing that a restart
    # produces.
    exec uv run python manage.py qcluster
    ;;
  shell)
    exec uv run python manage.py shell
    ;;
  *)
    echo "Unknown role: $ROLE (expected: web | worker | shell)" >&2
    exit 1
    ;;
esac
