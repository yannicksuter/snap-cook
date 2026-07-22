# Runbook: restore from backup

## What is actually needed

**`/data/store` is the only irreplaceable thing.** Everything else is
reconstructible:

| Lost | Cost |
|---|---|
| `/data/store` | **Everything.** All recipes and all history. |
| `pgdata` | Social data — comments, likes, follows. Recipes are unaffected. |
| the image | Nothing. Rebuild from source. |

## Procedure

```bash
docker compose down

# 1. Restore the store.
rsync -a /backup/snap-cook/data/ /mnt/user/appdata/snap-cook/data/

# 2. Bring up the database and apply the schema.
docker compose up -d db
docker compose run --rm web python manage.py migrate

# 3. Rebuild the projection from the restored files.
docker compose run --rm web python manage.py reindex --full --yes

# 4. Start.
docker compose up -d

# 5. Verify.
curl -s http://localhost:8931/up
docker compose exec web python manage.py check_consistency --deep
```

## Verifying a backup is good

Content addressing makes this checkable rather than a matter of faith — every
version's hash is recomputable from its own bytes:

```bash
docker compose run --rm web python manage.py verify_store --deep
```

Run it against the *backup* periodically, not just after a restore. A backup you
have never verified is a hypothesis.
