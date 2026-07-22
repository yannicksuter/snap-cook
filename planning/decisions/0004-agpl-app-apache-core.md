# ADR 0004 — AGPL for the app, Apache-2.0 for the core

**Status:** accepted

## Context

The repository is public from day one. snap-cook is a self-hostable social web
application, but `snapcook-core` is deliberately framework-free so it can be
reused by a Flutter client, a CLI and a future LLM service.

## Decision

- `apps/web/` and the repository as a whole: **AGPL-3.0-or-later**
- `packages/snapcook-core/`: **Apache-2.0**

AGPL closes the SaaS loophole that MIT and Apache leave open. Mealie is AGPL
with a healthy contributor base, so the "AGPL deters contributors" worry is not
supported by the nearest comparable project. It is also the only reversible
choice: copyright plus AGPL preserves a future dual-licensing option, whereas
permissive licensing is a one-way door.

Apache-2.0 for the core because a Django-free library is only genuinely reusable
if it is not copyleft — otherwise the whole reason for the split evaporates.
Apache rather than MIT for its explicit patent grant.

**DCO, not a CLA.** A CLA would be needed for unilateral relicensing but is
heavy for a project this size and deters casual contributors.

## Consequences

- SPDX headers on every source file, since per-directory licensing confuses
  people
- `Signed-off-by:` is required and must not be confused with the repository's
  rule against `Co-Authored-By:` footers — different footer, different purpose
