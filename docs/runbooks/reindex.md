# Runbook: rebuild the projection

Postgres is a derived index. This rebuilds it from the authoritative store.

## When

- After restoring `/data` from backup
- After editing the store outside the app (a pull, a hand edit)
- When `/ops/api/consistency` reports drift
- After a `FORMAT_VERSION` migration

## Safe by construction

`reindex` only touches `catalog` tables. Accounts, preferences, API tokens and
social data are in different apps and are never in scope, so this is safe to run
in production.

## Full rebuild

```bash
docker compose exec web python manage.py reindex --full --yes
```

## Single recipe

```bash
docker compose exec web python manage.py reindex --recipe rcp_01J8ZQ...
```

## Verify

```bash
docker compose exec web python manage.py check_consistency --deep
```

Should report zero drift. `--deep` re-hashes every object, so it is slow but
authoritative.

## If it fails

A failure means a `catalog` field is not derivable from the store — the
architecture's core invariant has been broken. Find the field and move it to
`social` or `accounts`, or derive it properly. Do not paper over it by
back-filling from a database dump; that hides the bug and it will return.
