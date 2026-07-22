# Postgres is a cache

## The invariant

> Every field on a `catalog` model must be derivable from the file store.

The test: **drop the database, rebuild from files — did anything about a recipe
get lost?** If yes, the boundary leaked.

## Why it is enforceable

Because `catalog` is a separate Django app from the database-authoritative ones.
`reindex --full` truncates exactly `catalog`'s tables and nothing else — a
mechanical rule, not a matter of discipline. If the projection and the social
graph shared an app, the invariant could not even be stated.

| Lives in files | Lives only in Postgres |
|---|---|
| ingredients, steps, quantities | users, sessions |
| lineage, versions | comments, likes, follows |
| license, visibility, source | preferences, API tokens |
| translations | import jobs and drafts |

## What this buys

- Back up one directory
- Host recipes anywhere; read them with any client
- Rebuild after corruption without data loss
- Reason about correctness: the database can always be wrong and recoverable

## Comments anchor to hashes

A comment references an immutable `version_id`, never a mutable path. Otherwise
a comment drifts off the thing it was commenting on the moment the recipe is
edited — and "this needs more salt" attached to a recipe that no longer has salt
is worse than no comment.

## Verifying

```bash
docker compose exec web python manage.py dbshell -c 'TRUNCATE catalog_recipe CASCADE;'
docker compose exec web python manage.py reindex --full --yes
```

`apps/web/tests/test_projection_rebuildable.py` asserts a byte-identical rebuild.
