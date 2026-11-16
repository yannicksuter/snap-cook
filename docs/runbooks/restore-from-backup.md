# Runbook: restore from backup

## What is actually needed

**`/data/store` is the only irreplaceable thing.** Everything else is
reconstructible:

| Lost | Cost |
|---|---|
| `/data/store` | **Everything.** All recipes and all history. |
| `pgdata` | Accounts and social data — comments, likes, follows. Recipes are safe in the store. |
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

# 4. Start, and check that the site answers.
docker compose up -d
curl -s http://localhost:8931/up
```

`reindex` reports how many recipes it projected; it should match what you
expect the backup to hold. If `pgdata` was lost too, the accounts went with
it, and `reindex` skips, with a warning, every recipe whose author matches no
account by username or email. Restore `pgdata` from the same backup if you have
it; otherwise recreate those accounts, then rerun step 3.

On Unraid: stop `snap-cook-worker` and `snap-cook-web`, restore into
`/mnt/user/appdata/snap-cook/data`, start `snap-cook-web` (it applies the
schema itself), then run
`docker exec snap-cook-web python manage.py reindex --full --yes` and start
`snap-cook-worker`.

## Verifying a backup is good

Restore it into a scratch setup and run the procedure above: a store that
`reindex --full` reads completely is at least structurally sound. Run this
against the *backup* periodically, not just after a restore. A backup you have
never verified is a hypothesis.

Content addressing allows a stronger check, since every version's hash is
recomputable from its own bytes. A command that re-hashes every version
(`verify_store`) is planned for M2.
