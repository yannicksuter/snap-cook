# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One image, two roles. `web` runs migrations then gunicorn; `worker` runs the
# django-q cluster. Dispatch happens in entrypoint.sh on the first argument, so
# there is exactly one image to build, tag and deploy.
#
# CI publishes it as ghcr.io/yannicksuter/snap-cook (docs/install.md), after
# scripts/test-container.py has run it with no route to the internet.

FROM python:3.13-slim AS base

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
    SNAPCOOK_DATA_DIR=/data

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

# The authoritative recipe store. THIS is the volume that must be backed up --
# Postgres is rebuildable from it via `manage.py reindex --full`.
# On Unraid: /mnt/user/appdata/snap-cook/data -> /data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8931

# Unraid shows this next to the container. `web` answers when /up does; the
# worker serves nothing to probe, so it is healthy while it runs (entrypoint.sh).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["/app/entrypoint.sh", "healthcheck"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
