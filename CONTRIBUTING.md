# Contributing to snap-cook

Thanks for looking. This document covers the mechanics; [`AGENTS.md`](AGENTS.md)
covers the architectural rules, and it is worth reading before your first change
because several of them are non-obvious.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Docker (for Postgres).

```bash
git clone https://github.com/yannicksuter/snap-cook.git
cd snap-cook
uv sync
cp .env.example .env

./scripts/test-fast.sh        # should pass immediately, no Docker required
```

For anything touching `apps/web` you also need Postgres:

```bash
docker compose up -d db
uv run python apps/web/manage.py migrate
```

## Test tiers

The suite is tiered so the inner loop stays fast. `packages/snapcook-core` has
no framework dependency, so most tests need neither Django nor a database.

| Tier | What | Needs | Target | Command |
|---|---|---|---|---|
| 0 | core: schema, hashing, units, renderers | nothing | **< 3 s** | `./scripts/test-fast.sh` |
| 1 | Django unit | Postgres | < 30 s | `uv run pytest apps/web -q --reuse-db` |
| 2 | integration | Postgres + migrations | < 90 s | `uv run pytest apps/web -m integration` |
| 3 | LLM evals | live API credentials | minutes | `uv run python evals/run.py` |

Tier 3 costs money and is non-deterministic. It **never** runs in PR CI; it runs
nightly and its output is a trend, not a gate.

Write new tests in tier 0 wherever the logic allows. If something can be tested
as a pure function over the domain model, it should be.

## Golden files

Renderer output is checked against committed golden files under
`packages/snapcook-core/tests/golden/`. They are plain `.txt`, `.mmd` and
`.html` — a `.mmd` can be pasted straight into the Mermaid live editor, and a
`.html` opened in a browser.

```bash
./scripts/update-golden.sh    # regenerate, then print the diff
```

> **Read the diff line by line.** Golden files are the review surface for
> rendering changes. A regenerated golden with no explanation is
> indistinguishable from an unnoticed regression, and PRs that do this will be
> sent back. If you cannot explain a changed line, it is a bug you just found.

## The hash contract

`packages/snapcook-core/tests/contract/` pins the content-hash of a fixed set of
inputs. Those hashes are a **frozen wire contract**: stores on disk and any
non-Python client reference them.

If a change makes `contract` fail:

1. If it was **not** intentional — canonicalisation is broken. Fix the code. Do
   not regenerate the vectors.
2. If it **was** intentional:
   - bump `FORMAT_VERSION` in `snapcook_core/version.py`
   - add a migration under `snapcook_core/migrate/`
   - regenerate the vectors
   - label the PR a breaking change and say so in `CHANGELOG.md`

This is deliberately more friction than a normal test update, because the blast
radius is every recipe that has ever been stored.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), and sign off:

```bash
git commit -s -m "feat(units): fraction-friendly rounding for imperial volumes"
```

Two footer rules that are easy to conflate:

- **`Signed-off-by:` is required.** `git commit -s` adds it. It is a legal
  attestation under the [Developer Certificate of
  Origin](https://developercertificate.org/) that you have the right to submit
  the code. We use DCO rather than a CLA because a CLA is heavy for a project
  this size and deters casual contributors.
- **`Co-Authored-By:` must not be added.** It is a credit line, not an
  attestation, and an assistant trailer makes contribution statistics
  meaningless. Some coding agents add one by default — turn it off.

## Pull requests

Before opening:

```bash
./scripts/test.sh    # lint + tier 0 + tiers 1–2
```

In the PR body, state:

- what changed and why
- whether golden files changed, and an explanation for each
- whether the hash contract changed (if so, this is a breaking change)
- whether `RECIPE_SPEC.md` needed updating — schema changes must update it in
  the same change set, since it is the contract clients read

Required CI checks: `lint`, `core`, `contract`, `web`, `security`.

## Proposing a schema change

The recipe schema is the product, so changes to it get more scrutiny than code:

1. Open an issue describing the modelling problem — not the proposed field.
   "Recipes with a resting period spanning days render confusingly" is a better
   starting point than "add a `rest_hours` field".
2. Say what it should do to the three renderers and to scaling.
3. If it changes stored data, describe the migration.
4. Update `RECIPE_SPEC.md` in the same PR.

## Code style

Ruff only — no black, flake8, mypy or pre-commit.

```bash
uv run ruff check . && uv run ruff format --check .
```

Beyond that, match the surrounding code. The prevailing style is plain
module-level functions with `_`-prefixed private helpers rather than class
hierarchies, and comments that explain *why* a decision was made — frequently
naming the bug or failure mode that motivated it. A comment restating what the
next line does is noise; a comment explaining why the obvious approach was
rejected is worth keeping.
