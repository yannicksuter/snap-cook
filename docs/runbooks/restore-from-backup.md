# Runbook: restore from backup

## What is actually needed

**`/data/store` is the only irreplaceable thing.** Everything else is
reconstructible:

| Lost | Cost |
|---|---|
| `/data/store` | **Everything.** All recipes and all history. |
| the database (`/data/postgres`, or `pgdata` with a separate database) | Accounts, settings, API tokens, drafts and social data. Recipes are safe in the store. |
| the image | Nothing. Rebuild from source. |

## Procedure: one container (Unraid)

The backup of `/data` holds the store and the database together.

1. Stop `snap-cook`.
2. Restore the backup into `/mnt/user/appdata/snap-cook`, replacing what is
   there.
3. Start `snap-cook`. It opens the restored database and applies any newer
   migrations.
4. Check: `curl -s http://<unraid-ip>:8931/up`, and
   `docker exec snap-cook python manage.py reindex --full --yes`, which
   rebuilds the projection from the restored store and reports how many recipes
   it found.

If only the store survived, delete `/mnt/user/appdata/snap-cook/postgres`
before step 3: the container makes an empty database, and step 4 brings the
recipes back. The accounts do not come back; see below.

## Procedure: a separate database (Docker Compose)

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
expect the backup to hold. If the database was lost too, the accounts went
with it, and `reindex` skips, with a warning, every recipe whose author matches
no account by username or email. Restore the database from the same backup if
you have it; otherwise recreate those accounts, then reindex again.

## Verifying a backup is good

Restore it into a scratch setup and run the procedure above: a store that
`reindex --full` reads completely is at least structurally sound. Run this
against the *backup* periodically, not just after a restore. A backup you have
never verified is a hypothesis.

Content addressing allows a stronger check, since every version's hash is
recomputable from its own bytes. A command that re-hashes every version
(`verify_store`) is planned for M2.
