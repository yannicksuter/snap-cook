# ADR 0002 — Hash the data structure, not the file bytes

**Status:** accepted

## Context

Content addressing requires byte-stability. YAML has no canonical form —
round-tripping through a library can change quoting, key order and line
wrapping. If the hash covered file bytes, reformatting would produce a new
version and lineage would fork on whitespace.

## Decision

Hash the **validated data structure**, serialised to RFC 8785 canonical JSON.
Git hashes bytes; we hash meaning.

A corollary that took a while to see: RFC 8785 mandates ECMAScript double
serialisation for JSON numbers. Encoding a `Decimal` as a number would make a
Python backend and a Dart client compute *different hashes for the same recipe*.
So **all non-integer numerics serialise as JSON strings**, and `float` is banned
from every schema field and rejected at encode time.

## Consequences

- Reformatting is correctly a no-op version
- YAML comments are not part of identity and are dropped by machine rewrites.
  Anything semantically meaningful — provenance, translator notes, rationale —
  must be a **schema field, not a comment**. This is right anyway: those things
  should be queryable and renderable.
- Two hashes are needed: `content_hash` (content) and `version_id` (commit)
