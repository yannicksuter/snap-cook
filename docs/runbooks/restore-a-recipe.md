# Runbook: bring back a deleted recipe

Deleting a recipe in the app (at the end of its edit page) does not erase it.
Its directory moves, whole and unchanged, from `/data/store/<recipe id>/` to
`/data/store/.trash/<recipe id>/`, where nothing lists or reads it. Every
version is still there, and backups of `/data` include the trash.

What does not come back: the photos or files the recipe was imported from.
Deleting a recipe deletes those, as deleting a draft does.

## Find it

Each recipe in the trash has its last state in `recipe.json`, title included:

```bash
docker exec snap-cook sh -c 'grep -l "Käsekuchen" /data/store/.trash/*/recipe.json'
```

A recipe deleted twice (restored in between) has a second copy named
`<recipe id>.2`; the highest number is the latest.

## Bring it back

Move it back under its own id, then project it into the catalog:

```bash
docker exec snap-cook mv /data/store/.trash/rcp_01J8ZQ... /data/store/rcp_01J8ZQ...
docker exec snap-cook python manage.py reindex --recipe rcp_01J8ZQ...
```

It returns with its owner, who may see it, and its whole history: `reindex`
takes all of that from the store. With `docker compose`, use
`docker compose exec web` instead of `docker exec snap-cook`.

## Empty the trash

Only to free space, which a few kilobytes per recipe rarely need. What is
removed here is gone for good, except from older backups:

```bash
docker exec snap-cook rm -rf /data/store/.trash/rcp_01J8ZQ...
```
