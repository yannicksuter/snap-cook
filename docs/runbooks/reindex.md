# Runbook: rebuild the projection

Postgres is a derived index. This rebuilds it from the authoritative store.

## When

- After restoring `/data` from backup
- After editing the store outside the app (a pull, a hand edit)
- When a recipe page disagrees with the store
- After a `FORMAT_VERSION` migration

## Safe by construction

`reindex` only touches `catalog` tables. Accounts, preferences, API tokens and
social data are in different apps and are never in scope, so this is safe to run
in production.

## Full rebuild

```bash
docker compose exec web python manage.py reindex --full --yes
```

On Unraid: `docker exec snap-cook python manage.py reindex --full --yes`.

## Single recipe

```bash
docker compose exec web python manage.py reindex --recipe rcp_01J8ZQ...
```

## Verify

`reindex` reports what it rebuilt and what the projection held before:

```
reindexed 6 recipe(s) from /data/store (projection held 6)
```

The two counts should match unless recipes were added to or removed from the
store outside the app. A recipe whose author matches no account in this
database, by username or email, is left out with a warning, `skipped N
recipe(s) with no matching local owner`; once that account exists, run
`reindex` again. A drift check that compares
the projection with the store without rebuilding it (`/ops/api/consistency`) is
planned for M2.

## If it fails

A failure means a `catalog` field is not derivable from the store — the
architecture's core invariant has been broken. Find the field and move it to
`social` or `accounts`, or derive it properly. Do not paper over it by
back-filling from a database dump; that hides the bug and it will return.
