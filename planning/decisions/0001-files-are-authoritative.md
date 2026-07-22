# ADR 0001 — Files are authoritative, Postgres is a projection

**Status:** accepted

## Context

Recipes need to be searchable, sortable and joinable, which is what a relational
database is for. They also need to be portable, forkable and hostable on GitHub,
which is what files are for. Doing both invites keeping two mutable stores in
sync — a distributed-systems problem nobody wants in a hobby project.

## Decision

The filesystem is authoritative for recipe content. Postgres is a **derived
projection**, rebuilt by `reindex --full`. Writes go one direction only:
validate → write file → reindex.

The boundary test: **drop the database and rebuild from files — did anything
about a recipe get lost?** If yes, the boundary leaked.

Social data (users, comments, likes, follows) is *not* recipe content and lives
only in Postgres. This is why `catalog` and `social` are separate Django apps:
the invariant "every `catalog` field is derivable" is only enforceable if
non-derivable things cannot be added to it by accident.

## Consequences

- `reindex --full` is an executable proof, and a test asserts byte-identical
  rebuild
- Comments must anchor to an immutable version hash, not a mutable path, or they
  drift off what they commented on
- The filesystem has no transactions, so concurrency is handled by the
  content-addressed store, not by locking
