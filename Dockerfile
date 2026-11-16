# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One image. By default (role `all`) it is the whole app in one container: web,
# worker and, without POSTGRES_HOST, a Postgres of its own with its data in
# /data. The roles `web` and `worker` split it for a setup with a separate
# database (docker-compose.yml). Dispatch is in entrypoint.sh.
#
# CI publishes it as ghcr.io/yannicksuter/snap-cook (docs/install.md), after
# scripts/test-container.py has run it with no route to the internet.

# The Debian release is pinned, not just Python: it decides the Postgres major
# version, and a data folder cannot be opened by a different major.
FROM python:3.13-slim-trixie AS base

# PATH puts the image's own virtualenv first, so `python`, `gunicorn` and
# `docker exec <container> python manage.py ...` all run in it. Never `uv run`
# at runtime: it re-syncs the environment on every start, rebuilding
# snapcook-core with hatchling fetched from PyPI, so a container without
# internet access never starts.
#
# DJANGO_DEBUG=0 because an image is a deployment. settings.py defaults to "1"
# for a local checkout; a container that forgets the variable would otherwise
# serve tracebacks.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_DEBUG=0 \
    SNAPCOOK_DATA_DIR=/data \
    SNAPCOOK_EMBEDDED_DB=/run/postgresql

# PostgreSQL 17 for the one-container setup. Three trims:
# - no default cluster: the entrypoint makes one in /data/postgres;
# - no JIT: Debian's server package pulls in LLVM (about 130 MB) for query
#   compilation that a recipe database never needs. Postgres runs without it,
#   and the server starts with jit=off. Nothing installs packages after this
#   layer, so forcing the libraries out leaves no apt run to trip over them;
# - no package lists.
RUN mkdir -p /etc/postgresql-common \
 && echo "create_main_cluster = false" > /etc/postgresql-common/createcluster.conf \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17 \
 && rm -rf /usr/lib/postgresql/17/lib/llvmjit* /usr/lib/postgresql/17/lib/bitcode \
 && dpkg --remove --force-depends libllvm19 libz3-4 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pinned for reproducible builds. uv, not pip -- it resolves the workspace.
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

# Dependency manifests first, so this layer survives code changes.
#
# uv needs every workspace member's pyproject.toml present to read the
# workspace. --no-install-workspace installs the third-party dependencies only:
# snapcook-core is a real hatchling package and cannot be built before its
# source is copied in.
COPY pyproject.toml uv.lock ./
COPY packages/snapcook-core/pyproject.toml packages/snapcook-core/
COPY apps/web/pyproject.toml apps/web/
RUN uv sync --no-dev --frozen --no-install-workspace

COPY . .

# Now snapcook-core itself, as a regular wheel in the virtualenv rather than an
# editable link back into /app/packages.
RUN uv sync --no-dev --frozen --no-editable \
 && chmod +x /app/entrypoint.sh

# Where entrypoint.sh runs, and where `docker exec` lands, so the runbooks'
# `python manage.py ...` works in a running container as written.
WORKDIR /app/apps/web

# Static is collected at build time, not at startup: it never changes for a
# given image, so doing it per-container-start is wasted time on every restart.
RUN DJANGO_SECRET_KEY=build-placeholder python manage.py collectstatic --noinput

LABEL org.opencontainers.image.title="snap-cook" \
      org.opencontainers.image.description="Recipes as structured data: one recipe graph, many readings." \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

# The commit this image was built from, so /up and the page footer can report
# it. Passed at build time:
#   docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) .
# Kept late in the file so changing it only invalidates this cheap final layer.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

# Everything worth keeping: the recipe store (the authoritative copy of every
# recipe) and, in the one-container setup, the database in /data/postgres.
# THIS is the volume that must be backed up.
# On Unraid: /mnt/user/appdata/snap-cook -> /data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8931

# Unraid shows this next to the container. `all` and `web` answer when /up
# does; the worker serves nothing to probe, so it is healthy while it runs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["/app/entrypoint.sh", "healthcheck"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["all"]
