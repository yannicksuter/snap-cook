#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Role dispatch. One image runs the whole app or one part of it; the first
# argument decides (CMD in the Dockerfile, `command:` in docker-compose.yml,
# Post Arguments on Unraid):
#
#   all     The default: web and worker in one container. Without POSTGRES_HOST
#           it also runs a Postgres of its own, its data in /data/postgres, so
#           a home server needs one container and one folder.
#   web     Migrations, then gunicorn. Needs POSTGRES_HOST.
#   worker  The django-q cluster. Needs POSTGRES_HOST.
#
# Any other first argument runs as a command instead.
#
# `python` and `gunicorn` are the image's virtualenv (PATH, in the Dockerfile).
# Not `uv run`: it re-syncs on every start and needs PyPI to do it.
set -e

ROLE="${1:-all}"
# The HEALTHCHECK runs as a separate process and cannot see this one's
# arguments, so the running role leaves its name here for it.
ROLE_FILE=/tmp/snapcook-role
cd /app/apps/web

# The embedded database. It listens on a Unix socket only, never on a TCP port,
# so nothing outside the container can reach it; settings.py finds the socket
# through SNAPCOOK_EMBEDDED_DB, which `docker exec ... manage.py` sees too.
PG_MAJOR=17
PG_BIN=/usr/lib/postgresql/$PG_MAJOR/bin
PG_DATA=/data/postgres
PG_SOCKET=${SNAPCOOK_EMBEDDED_DB:-/run/postgresql}

as_postgres() {
  # Postgres refuses to run as root, which is what the container runs as.
  setpriv --reuid=postgres --regid=postgres --init-groups -- "$@"
}

start_postgres() {
  install -d -o postgres -g postgres -m 2775 "$PG_SOCKET"
  if [ ! -s "$PG_DATA/PG_VERSION" ]; then
    echo "Creating the database in $PG_DATA"
    install -d -o postgres -g postgres -m 700 "$PG_DATA"
    # The builtin C.UTF-8 collation does not change when the system's C library
    # does, so a newer image never meets indexes sorted by different rules.
    as_postgres "$PG_BIN/initdb" --pgdata="$PG_DATA" --username=snapcook \
        --auth-local=trust --auth-host=reject --encoding=UTF8 \
        --locale-provider=builtin --builtin-locale=C.UTF-8 >/dev/null
  fi
  local found
  found=$(cat "$PG_DATA/PG_VERSION")
  if [ "$found" != "$PG_MAJOR" ]; then
    echo "$PG_DATA was written by PostgreSQL $found, and this image runs $PG_MAJOR." >&2
    echo "Run the image that wrote it, dump the database, and load the dump here." >&2
    exit 1
  fi
  # A restored backup can arrive with other owners; Postgres insists on its own.
  if [ "$(stat -c %U "$PG_DATA")" != postgres ]; then
    chown -R postgres:postgres "$PG_DATA"
  fi
  chmod 700 "$PG_DATA"
  # Nothing else runs yet, so a pid file is left over from a container that was
  # killed. Its pid may belong to another process now, which would stop
  # Postgres from starting.
  rm -f "$PG_DATA/postmaster.pid" "$PG_SOCKET"/.s.PGSQL.*
  as_postgres "$PG_BIN/pg_ctl" --pgdata="$PG_DATA" --wait --timeout=120 --silent \
      -o "-c listen_addresses='' -c unix_socket_directories=$PG_SOCKET -c jit=off" start
  if [ -z "$(as_postgres "$PG_BIN/psql" -h "$PG_SOCKET" -U snapcook -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname = 'snapcook'")" ]; then
    as_postgres "$PG_BIN/createdb" -h "$PG_SOCKET" -U snapcook snapcook
  fi
}

stop_postgres() {
  as_postgres "$PG_BIN/pg_ctl" --pgdata="$PG_DATA" --mode=fast --wait --silent stop || true
}

gunicorn_args=(
  snapcookweb.wsgi:application
  --bind 0.0.0.0:8931
  --workers 2
  --timeout 120
  --access-logfile -
  --error-logfile -
)

case "$ROLE" in
  all)
    echo web > "$ROLE_FILE"
    embedded=
    if [ -z "${POSTGRES_HOST:-}" ]; then
      start_postgres
      embedded=1
    fi
    stop_all() {
      kill -TERM "${children[@]}" 2>/dev/null || true
      wait "${children[@]}" 2>/dev/null || true
      if [ -n "$embedded" ]; then stop_postgres; fi
    }
    children=()
    trap 'stop_all; exit 0' TERM INT
    if ! python manage.py migrate --noinput; then
      stop_all
      exit 1
    fi
    # A short grace period, so web, worker and database all stop inside the
    # 30 seconds `--stop-timeout=30` gives the container.
    gunicorn "${gunicorn_args[@]}" --graceful-timeout 10 &
    children+=("$!")
    python manage.py qcluster &
    children+=("$!")
    status=0
    wait -n "${children[@]}" || status=$?
    # One of them stopped on its own: stop the rest, and let Docker restart it.
    trap - TERM INT
    echo "A process stopped (exit status $status); stopping the container." >&2
    stop_all
    exit "$status"
    ;;
  web)
    echo web > "$ROLE_FILE"
    python manage.py migrate --noinput
    exec gunicorn "${gunicorn_args[@]}"
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
