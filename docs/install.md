# Installing snap-cook

snap-cook runs as one container, `ghcr.io/yannicksuter/snap-cook`: the site, the
background worker that reads new recipes, and a Postgres database of its own.
Everything it keeps lives in one folder, mounted at `/data`.

`stable` is the newest release ([how releases work](runbooks/release.md)).
`GET /up` returns `{"status": "ok", "commit": "<Git commit SHA>"}` without
signing in, so you can tell which build is live.

> **Back up `/data`.** It holds the recipe store, the only copy of every recipe
> and its history, and the database with the accounts, settings, API tokens and
> drafts. Back it up while the container is stopped, as CA Appdata Backup does,
> so the database files are consistent. See
> [restore-from-backup](runbooks/restore-from-backup.md).

## Unraid setup

In **Docker → Add Container**, enable **Advanced View** and use these settings:

| Setting | Value |
|---|---|
| Name | `snap-cook` |
| Repository | `ghcr.io/yannicksuter/snap-cook:stable` |
| Network Type | `Bridge` |
| Port (HTTP) | Config Type **Port**: Container Port `8931`, Host Port `8931`, TCP |
| Path (data) | Config Type **Path**: Container Path `/data`, Host Path `/mnt/user/appdata/snap-cook`, Access Mode **Read/Write** |
| Variables | See [Environment variables](#environment-variables) |
| WebUI | `http://[IP]:[PORT:8931]/` |
| Extra Parameters | `--restart=unless-stopped --stop-timeout=30` |
| Autostart | Enabled |

- `--stop-timeout=30` gives the container time to stop the site, the worker and
  the database in turn. With Docker's default of 10 seconds the database may be
  cut off, and it then recovers on the next start.
- Keep the `appdata` share on a cache pool, as Unraid sets it up by default. A
  database on the array is slow.
- The database listens only inside the container. Nothing else on your network
  can reach it, so it needs no password or port.

### Environment variables

Configure these in the container editor; no `.env` file is needed. Choose **Add
another Path, Port, Variable, Label or Device → Config Type: Variable**, enter
the **Key** and **Value**, and set **Password Mask: Yes** for every secret.

| Variable (Key) | Required | Value |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | `openssl rand -hex 32`. Password Mask. Changing it signs everyone out. |
| `DJANGO_ALLOWED_HOSTS` | yes | Every host name the site is reached by, comma-separated, e.g. `cook.example.com,192.168.1.42`. Others get `400 Bad Request`. |
| `GOOGLE_CLIENT_ID` | yes | From [Google sign-in](#google-sign-in) |
| `GOOGLE_CLIENT_SECRET` | yes | Password Mask |
| `SNAPCOOK_API_TOKEN_PEPPER` | yes | `openssl rand -hex 32`. Password Mask. Changing it invalidates every Personal Access Token users have made. |
| `SNAPCOOK_LLM_API_KEY` | to add recipes | An API key from the [Claude Console](https://platform.claude.com/), billed separately from a Claude subscription. Password Mask. Without it, "Add a recipe" says it is not set up. |
| `SNAPCOOK_LLM_MODEL` | no | Default `claude-opus-5-5` |
| `SNAPCOOK_LLM_EFFORT` | no | `low`, `medium` (default) or `high`. More effort reads hard sources better and costs more. |
| `SNAPCOOK_API_ENABLED` | no | `1` (default) serves the product API at `/api/v1/` |
| `SNAPCOOK_OPS_API_ENABLED` | no | `0` (default). Read the [ops API's warning](reference/api-ops.md) before turning it on. |
| `SNAPCOOK_OPS_API_TOKEN` | with the ops API | 32 characters or more, `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Password Mask. The app refuses to start with a weak one. |
| `SNAPCOOK_OPS_API_WRITE` | no | `1` allows the ops API's mutating endpoints. Default `0`. |
| `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA` | no | `1` opts in to ODbL ingredient data. Default `0`; see [THIRD_PARTY_DATA.md](../THIRD_PARTY_DATA.md). |
| `DJANGO_DEBUG` | no | `0`, the image's default. Never `1` on a server: it shows tracebacks to visitors. |

Leave `POSTGRES_HOST` unset: then the container runs its own database. Setting
it is for [a separate database](#a-separate-database). `SNAPCOOK_DATA_DIR`
(`/data`), `SNAPCOOK_EMBEDDED_DB` and `GIT_COMMIT` are set by the image; leave
them alone. The [variable reference](reference/env-vars.md) has the full list.

### First start

Click **Apply**. The first time, the log shows `Creating the database in
/data/postgres`; then, on every start, the migrations, `Listening at:
http://0.0.0.0:8931` and `Q Cluster ... running.`. The container's health turns
**healthy**, and `http://<unraid-ip>:8931/up` answers with the commit.

The folder then holds `store/` (the recipes), `postgres/` (the database),
`sources/` (the photos and pages imports read) and `logs/`.

To start with the six example recipes, run once in the Unraid terminal:

```bash
docker exec snap-cook python manage.py seed_corpus
```

Other `manage.py` commands, such as `reindex --full --yes`
([reindex](runbooks/reindex.md)), run the same way, with `docker exec snap-cook`
in front, or typed into the container's **Console**.

## Google sign-in

The site asks for a Google sign-in on every page (`/up`, the two APIs and
Django's `/admin/` have access rules of their own). Google redirects back only
to `localhost` or a real HTTPS host name, never to a LAN address such as
`192.168.1.42`, so a server needs a public host name. With a Cloudflare Tunnel:
in Cloudflare Zero Trust, open your tunnel → **Public Hostname** → **Add**, e.g.
subdomain `cook`, Service Type `HTTP`, URL `<unraid-ip>:8931`.

1. In [Google Cloud Console](https://console.cloud.google.com/) → **APIs &
   Services → Credentials → Create Credentials → OAuth client ID**, choose
   **Web application**.
2. Under **Authorised redirect URIs**, add one per host you sign in from:

   | Where | Redirect URI |
   |---|---|
   | The server | `https://cook.example.com/accounts/google/login/callback/` |
   | A local checkout | `http://localhost:8931/accounts/google/login/callback/` |

3. Put `cook.example.com` in `DJANGO_ALLOWED_HOSTS`. A LAN address can stay in
   the list for the APIs: the two lists serve different purposes.
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the container (for a
   local checkout, in `.env`), and **Apply**.

The credentials come from the environment only. Do not also add a **Social
application** in Django's admin: with two sets, sign-in fails with
`MultipleObjectsReturned`.

Behind the tunnel, or any other reverse proxy, the site takes the scheme from
`X-Forwarded-Proto` and trusts `https://<host>` for forms, for every host in
`DJANGO_ALLOWED_HOSTS`. Without that, Django would build an `http://` callback,
and Google's exact match would refuse it.

> **The ops API answers only your LAN or a VPN.** It ignores ownership and can
> read every user's private recipe, so the app refuses any request that came
> through the tunnel or another proxy, token or not. With
> `SNAPCOOK_OPS_API_ENABLED=1` it answers at `http://<unraid-ip>:8931/ops/api/`
> and nowhere else ([ops API](reference/api-ops.md)).

## Logs

Everything logs to the container log (**Docker → container icon → Logs**): the
site's requests, the worker's jobs, the database's messages, and an
`ops-access` line for every ops API request, granted or refused. Docker deletes
the log whenever Unraid recreates the container, e.g. on an update.

## Updates

Enable **CA Auto Update Applications** for `snap-cook` to deploy new `stable`
images automatically. Every release is also tagged `v<version>` and
`sha-<full-commit>`; for a rollback, put an earlier one in **Repository**.

A rollback does not undo the newer release's migrations: the older image runs
on the newer schema. If it fails there, restore `/data` from before the update.

The image runs PostgreSQL 17, and a database folder only opens with the major
version that wrote it. A release that moves to a newer major will say so, and
until the folder is converted the container stops with a message naming both
versions instead of starting.

To try a release before it is merged, `ghcr.io/yannicksuter/snap-cook:test`
follows the newest release pull request ([how releases
work](runbooks/release.md)). Run it as a second container with its own folder
and another host port, never on the live folder: it migrates its database on
start.

Pulls need no credentials once the package is public. If Unraid asks for
them, set the visibility in the [package
settings](https://github.com/users/yannicksuter/packages/container/snap-cook/settings)
to public, or run `docker login ghcr.io` on Unraid.

## A separate database

The image can also leave the database to its own container, as
`docker-compose.yml` does. Set `POSTGRES_HOST` (and `POSTGRES_PASSWORD`, and
`POSTGRES_DB`, `POSTGRES_USER` or `POSTGRES_PORT` if they differ from
`snapcook` and `5432`), and run the image twice, with the arguments `web`
(migrations, then the site) and `worker` (the jobs). Both need the same `/data`
folder: the worker writes recipes the site reads.

With Docker Compose:

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, POSTGRES_PASSWORD, the Google
# keys and SNAPCOOK_API_TOKEN_PEPPER in .env.
docker compose pull
docker compose up -d --no-build --wait
```

Compose runs `db`, `web` and `worker`, with the store in `./data` and Postgres
in `./pgdata`. `SNAPCOOK_IMAGE` in `.env` picks the image,
`ghcr.io/yannicksuter/snap-cook:stable` by default. Repeat the last two commands
to update. To build from the checkout instead, run `./scripts/build.sh` before
`docker compose up -d --no-build --wait`.

A container set up for 0.1.0 as `snap-cook-web` with empty **Post Arguments**
now starts as `all`, site and worker together. Put `web` in its **Post
Arguments** to keep the split setup.
