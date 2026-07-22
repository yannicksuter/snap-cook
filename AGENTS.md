# AGENTS.md

The repo contract for coding agents and humans alike. Agent-neutral on purpose —
this repository is public and contributors use different tools. Anything
specific to one tool belongs in that tool's own file (see `CLAUDE.md`).

## Git commits

Always use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` new features
- `fix:` bug fixes
- `chore:` maintenance
- `docs:` documentation
- `refactor:` restructuring with no behaviour change
- `style:` formatting
- `test:` adding or changing tests
- `perf:` performance work

> **Never add a `Co-Authored-By` footer to commit messages.** The commit author
> is whoever ran the tooling; a co-author trailer for an assistant makes
> `git shortlog` and contribution statistics meaningless. Some agents add one
> by default — turn it off rather than stripping it afterwards.

`Signed-off-by:` (DCO) is **required** and is a different thing entirely — it is
a legal attestation under the [Developer Certificate of
Origin](https://developercertificate.org/), not a credit line. Use `git commit -s`.

## Project overview

**snap-cook** is a recipe platform built on one claim: *a recipe is structured
data, and every readable form of it is a view*. Recipes are stored as files, not
database rows. They model steps as a graph, so the same recipe renders as an
ordered list, a flowchart, or a printed page. Units and language are per-reader
render options rather than properties baked in at authoring time.

## Architecture

| Layer | Location | Notes |
|---|---|---|
| Domain library | `packages/snapcook-core/` | Pure Python, Apache-2.0. **No Django.** |
| Web application | `apps/web/` | Django 5 + HTMX, AGPL-3.0 |
| Authoritative store | `$SNAPCOOK_DATA_DIR/store` | Content-addressed files. Back this up. |
| Projection | Postgres | Derived. Rebuildable. Not a source of truth. |
| Jobs | django-q2, ORM broker | No Redis; Postgres is already a dependency |

Recipes are a **DAG**: nodes are food-states ("the dough"), edges are actions
carrying verb, duration, temperature and tools. A step list is a topological
sort of that graph; a flowchart is a drawing of it. One model, many views.

## Load-bearing rules

> **`snapcook-core` must never import Django.** `tests/test_no_django.py`
> enforces it with an AST walk. The package is the shared brain for the web app,
> a future Flutter client, a CLI and a self-hosted LLM service — a single
> convenience import of `django.utils` would quietly destroy that, and nothing
> else would fail to signal the loss.

> **Postgres is a cache.** Every field on a `catalog` model must be derivable
> from the file store. `manage.py reindex --full` truncates and rebuilds it, and
> a test asserts the result is byte-identical. Anything not derivable belongs in
> `social` or `accounts` — never in `catalog`.

> **Content hashes are a frozen wire contract.** Existing stores on disk, and
> any non-Python client, reference these exact values. Changing
> `canonical/encode.py` or `canonical/hashing.py` requires a `FORMAT_VERSION`
> bump, a migration, and regenerating `tests/contract/hash_vectors.json`.

> **Hash the data structure, never the file bytes.** Reformatting a file must be
> a no-op version. Corollary: **non-integer numerics serialise as JSON strings**
> — RFC 8785 emits JSON numbers as ECMAScript doubles, so encoding a `Decimal`
> as a number makes Python and Dart compute different hashes for one recipe.
> `float` is banned from every schema field.

> **`/api/` and `/ops/api/` are exempt from `LoginRequiredMiddleware`, so
> neither gets any protection from it.** All API authorization is explicit, in
> the django-ninja `auth=` declaration and in `require_ops_access`. An endpoint
> added without an auth declaration is published to the internet. This is the
> single most likely way this design gets breached.

> **Every recipe query starts from `catalog.access.visible_recipes(user)`.**
> Never build a queryset from `Recipe.objects` in a view or endpoint. One funnel
> means visibility is enforced in one reviewable place.

> **Recipe import never runs in the request cycle.** It is always a background
> job returning `202` and a job id. LLM extraction takes tens of seconds.

> **Golden files are reviewed, not regenerated.** A regenerated golden with no
> explanation in the PR will be rejected — it is indistinguishable from an
> unnoticed rendering regression.

> **Keep `RECIPE_SPEC.md` current in the same change set as any schema change.**
> It is the contract that clients and importers read.

## Key files

```
packages/snapcook-core/src/snapcook_core/
├── canonical/encode.py     # canonical form; the Decimal-as-string rule lives here
├── canonical/hashing.py    # content_hash + version_id. The frozen contract.
├── schema/base.py          # SnapcookModel: frozen, extra=forbid, NonSemantic
├── ids.py                  # prefixed ULIDs; stable across edits, so diff can match
└── errors.py               # error tree + ValidationIssue (non-fatal diagnostics)

apps/web/
├── snapcookweb/settings.py # single flat settings; env-var docstring at the top
├── snapcookweb/urls.py     # conditional mounting of the two API surfaces
├── accounts/middleware.py  # LoginRequiredMiddleware + its exempt prefixes
├── accounts/models.py      # UserPreferences, ApiToken (per-user PATs)
├── catalog/models.py       # the derived projection -- read the warning first
├── catalog/access.py       # visible_recipes(): the ONE authorization funnel
├── catalog/management/commands/reindex.py   # proof that Postgres is a cache
├── api/auth.py             # PatAuth + require_ops_access
├── api/product.py          # /api/v1/  -- per-user scoped
└── api/ops.py              # /ops/api/ -- ignores ownership. Read the danger note.
```

## Commands

```bash
# Setup
uv sync

# Tests
./scripts/test-fast.sh              # tier 0: no Django, no DB, < 3s. The inner loop.
uv run pytest packages/snapcook-core -m contract   # hash stability only
uv run pytest apps/web -q --reuse-db               # tier 1
uv run pytest apps/web -m integration              # tier 2
./scripts/test.sh                   # everything except evals

# Lint
uv run ruff check .
uv run ruff format --check .

# Golden files
./scripts/update-golden.sh          # regenerate, then READ the diff

# Local stack
./scripts/local_start.sh            # compose up + wait for /up
./scripts/local_stop.sh

# Operations
uv run python apps/web/manage.py reindex --full --yes
uv run python apps/web/manage.py migrate
```

## Environment variables

The authoritative list is the docstring at the top of
`apps/web/snapcookweb/settings.py`; `.env.example` mirrors it. Required in
production: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_PASSWORD`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SNAPCOOK_API_TOKEN_PEPPER`.

`SNAPCOOK_OPS_API_TOKEN` is the highest-value secret in the system — it bypasses
per-user scoping. The app refuses to boot if the ops API is enabled with a weak,
placeholder or low-entropy token.

## Conventions

Negative space is as informative as what we do use:

- **No DRF** — django-ninja, because the schema is already Pydantic
- **No npm, no build step** — Tailwind and HTMX from a CDN
- **No class hierarchies** — plain module-level functions, `_`-prefixed privates
- **No settings package** — one flat `settings.py` driven by the environment
- **No black / flake8 / mypy / pre-commit** — Ruff only
- **No `==` pins** — `>=` lower bounds; reproducibility comes from `uv.lock`
- **No VCR cassettes** — LLM fixtures at the provider boundary, because
  cassettes capture `Authorization` headers and this repo is public
- **No ODbL seed data by default** — CC0 and attribution-only sources
- **No shared bearer token on the product API** — per-user PATs; a shared token
  has no identity and therefore cannot scope private content
- **No inline LLM calls** — always a background job
- **No `float` anywhere in a schema** — `Decimal`, always
- **All times stored as UTC**
