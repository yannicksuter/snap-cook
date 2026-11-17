# snap-cook

A recipe platform built on one claim: **a recipe is structured data, and every
readable form of it is a view.** snap-cook stores the model and generates the
prose — along with a flowchart, a printable page, and the same recipe in your
language and your units.

Recipes are files rather than database rows, their steps form a graph rather
than a list, and units and language are chosen by whoever reads them.
[How it works](docs/architecture/overview.md).

**Status:** early. See the [roadmap](planning/ROADMAP.md).

## Run it

The image is `ghcr.io/yannicksuter/snap-cook`; `stable` is the newest release.
It runs as one container, database included:

```bash
docker run -d --name snap-cook -p 8931:8931 -v "$PWD/snap-cook:/data" \
  -e DJANGO_SECRET_KEY="$(openssl rand -hex 32)" -e DJANGO_ALLOWED_HOSTS=localhost \
  ghcr.io/yannicksuter/snap-cook:stable
```

[`docs/install.md`](docs/install.md) covers Unraid, Google sign-in, every
setting, updates, and Docker Compose with a separate database. **Back up
`/data`**: it holds the only copy of every recipe, and the database.

## Work on it

```bash
uv sync
./scripts/test-fast.sh               # core tests: no Docker, no database, < 3 s
./scripts/local_start.sh             # the whole stack on http://localhost:8931
```

[`CONTRIBUTING.md`](CONTRIBUTING.md) has the setup, test tiers and pull request
rules; [`AGENTS.md`](AGENTS.md) the architectural rules worth knowing first.

## Documentation

- [`docs/install.md`](docs/install.md) — installing, configuring and updating
- [`docs/architecture/`](docs/architecture/overview.md) — the ideas and how they fit
- [`docs/reference/`](docs/reference/) — the APIs, environment variables, testing
- [`docs/runbooks/`](docs/runbooks/) — releases, reindexing, restoring, rotating secrets
- [`RECIPE_SPEC.md`](RECIPE_SPEC.md) — the recipe format, for clients and importers
- [`CHANGELOG.md`](CHANGELOG.md) — what changed, release by release

## License and security

The application is AGPL-3.0-or-later; `packages/snapcook-core` is Apache-2.0 so
other clients can reuse it. Seed data and your recipes have terms of their own:
see [`LICENSING.md`](LICENSING.md). Report vulnerabilities privately through
GitHub Security Advisories ([`SECURITY.md`](SECURITY.md)).
