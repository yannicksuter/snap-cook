# ADR 0006 — Commit uv.lock

**Status:** accepted

## Context

The reference project this codebase inherits its style from gitignores
`uv.lock`, on the reasoning that an application run from source does not need a
committed lock.

## Decision

**Commit `uv.lock`.** A deliberate divergence from house style, recorded here so
it is traceable rather than looking like an oversight.

Three reasons specific to this project:

1. A public repository with CI needs reproducible builds — CI must resolve to
   the same versions the author tested
2. `uv sync --frozen` in the Dockerfile requires it
3. Supply-chain auditing (`pip-audit`, Dependabot) needs a lock to audit

## Consequences

- Dependabot opens lock-update PRs, grouped for minor and patch
- `uv sync --frozen` in CI and Docker; plain `uv sync` locally
