# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One image, two roles. `web` runs migrations then gunicorn; `worker` runs the
# django-q cluster. Dispatch happens in entrypoint.sh on the first argument, so
# there is exactly one image to build, tag and deploy.

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SNAPCOOK_DATA_DIR=/data

WORKDIR /app

# Pinned for reproducible builds. uv, not pip -- it resolves the workspace.
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

# Dependency manifests first, so this layer survives code changes.
#
# uv needs every workspace member's pyproject.toml present to resolve the
# workspace, AND a source directory for the buildable member -- snapcook-core is
# a real hatchling package, so without a package dir `uv sync` fails here and
# the whole layer-caching benefit is lost. Hence the stub __init__.py, which is
# overwritten by the real source in the COPY below.
COPY pyproject.toml uv.lock ./
COPY packages/snapcook-core/pyproject.toml packages/snapcook-core/README.md packages/snapcook-core/
COPY apps/web/pyproject.toml apps/web/
RUN mkdir -p packages/snapcook-core/src/snapcook_core \
 && touch packages/snapcook-core/src/snapcook_core/__init__.py \
 && uv sync --no-dev --frozen

COPY . .

RUN chmod +x /app/entrypoint.sh

# Static is collected at build time, not at startup: it never changes for a
# given image, so doing it per-container-start is wasted time on every restart.
RUN DJANGO_SECRET_KEY=build-placeholder \
    uv run python apps/web/manage.py collectstatic --noinput

# The commit this image was built from, so /up and the page footer can report
# it. Passed at build time:
#   docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) .
# Kept late in the file so changing it only invalidates this cheap final layer.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

# The authoritative recipe store. THIS is the volume that must be backed up --
# Postgres is rebuildable from it via `manage.py reindex --full`.
# On Unraid: /mnt/user/appdata/snap-cook/data -> /data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8931

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
