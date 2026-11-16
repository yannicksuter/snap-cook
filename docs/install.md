# Installing snap-cook

snap-cook runs as three containers: Postgres, and two from one image,
`ghcr.io/yannicksuter/snap-cook`, that differ only in their argument.

| Container | Image | What it does |
|---|---|---|
| `snap-cook-db` | `postgres:17-alpine` | The projection, plus accounts and social data |
| `snap-cook-web` | `ghcr.io/yannicksuter/snap-cook:stable` | Applies migrations, then serves the site on port 8931 |
| `snap-cook-worker` | `ghcr.io/yannicksuter/snap-cook:stable`, argument `worker` | Runs background jobs such as recipe import. Never migrates. |

`stable` is the newest release ([how releases work](runbooks/release.md)).
`GET /up` returns `{"status": "ok", "commit": "<Git commit SHA>"}` without
signing in, so you can tell which build is live.

> **Back up `/data`.** It holds the recipe store, the only copy of every recipe
> and its history. Postgres is rebuildable from it with `reindex --full`, except
> accounts, preferences, API tokens and social data, which live only there. See
> [restore-from-backup](runbooks/restore-from-backup.md).

## Unraid setup

### The network

`snap-cook-web` and `snap-cook-worker` reach the database by its container name
on a Docker network of their own. Create it once in the Unraid terminal:

```bash
docker network create snap-cook
```

Unraid keeps networks made this way across restarts with **Settings → Docker →
Preserve user defined networks: Yes** (Advanced View, with Docker stopped). It
then lists the network under **Network Type** as `Custom : snap-cook`.

### The database container

In **Docker → Add Container**, enable **Advanced View** and use these settings:

| Setting | Value |
|---|---|
| Name | `snap-cook-db` |
| Repository | `postgres:17-alpine`. Keep the major version: Postgres 18 cannot open a data folder that 17 wrote. |
| Network Type | `Custom : snap-cook` |
| Path (SQL data) | Config Type **Path**: Container Path `/var/lib/postgresql/data`, Host Path `/mnt/user/appdata/snap-cook/pgdata`, Access Mode **Read/Write** |
| Variable | `POSTGRES_PASSWORD`, **Password Mask: Yes**. Generate it with `openssl rand -hex 32`. |
| Variables | `POSTGRES_DB` = `snapcook`, `POSTGRES_USER` = `snapcook` |
| Extra Parameters | `--restart=unless-stopped` |
| Autostart | Enabled |

It needs no **Port**: only the other two containers reach it, over the
network. `POSTGRES_*` initialise an empty data folder only; changing them later
does not change an existing database or its password.

### The web container

| Setting | Value |
|---|---|
| Name | `snap-cook-web` |
| Repository | `ghcr.io/yannicksuter/snap-cook:stable` |
| Network Type | `Custom : snap-cook` |
| Port (HTTP) | Config Type **Port**: Container Port `8931`, Host Port `8931`, TCP |
| Path (store) | Config Type **Path**: Container Path `/data`, Host Path `/mnt/user/appdata/snap-cook/data`, Access Mode **Read/Write** |
| Variables | See [Environment variables](#environment-variables) |
| WebUI | `http://[IP]:[PORT:8931]/` |
| Post Arguments | `web`, or leave it empty: `web` is the default |
| Extra Parameters | `--restart=unless-stopped --stop-timeout=30` |
| Autostart | Enabled |

`--restart=unless-stopped` matters at boot: `web` migrates first, and exits if
the database is not up yet. Docker then starts it again until it is.
`--stop-timeout=30` gives gunicorn time to finish the requests in flight.

### The worker container

Make it from the web container's template, so the two cannot drift apart: in
**Docker → Add Container**, choose **Template → User templates →
my-snap-cook-web**, then change only:

| Setting | Value |
|---|---|
| Name | `snap-cook-worker` |
| Post Arguments | `worker` |
| Port (HTTP) | Remove it |
| WebUI | Clear it |

Keep **Path (store)** exactly as on the web container. The worker writes the
store objects that `web` reads; if the two paths differ, imports succeed and
their recipes never appear.

In the **Docker** tab, keep `snap-cook-db` above `snap-cook-web`, and
`snap-cook-web` above `snap-cook-worker`, so they autostart in that order.

### Environment variables

Configure these in the container editor; no `.env` file is needed. Choose **Add
another Path, Port, Variable, Label or Device → Config Type: Variable**, enter
the **Key** and **Value**, and set **Password Mask: Yes** for every secret.
Give `snap-cook-web` and `snap-cook-worker` the same set: both load the same
settings, and the worker template above copies them.

| Variable (Key) | Required | Value |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | `openssl rand -hex 32`. Password Mask. Changing it signs everyone out. |
| `DJANGO_ALLOWED_HOSTS` | yes | Every host name the site is reached by, comma-separated, e.g. `cook.example.com,192.168.1.42`. Others get `400 Bad Request`. |
| `POSTGRES_HOST` | yes | `snap-cook-db`, the database container's name |
| `POSTGRES_PASSWORD` | yes | The database container's `POSTGRES_PASSWORD`. Password Mask. |
| `POSTGRES_DB`, `POSTGRES_USER` | no | Default `snapcook`, as on the database container |
| `POSTGRES_PORT` | no | Default `5432` |
| `GOOGLE_CLIENT_ID` | yes | From [Google sign-in](#google-sign-in) |
| `GOOGLE_CLIENT_SECRET` | yes | Password Mask |
| `SNAPCOOK_API_TOKEN_PEPPER` | yes | `openssl rand -hex 32`. Password Mask. Changing it invalidates every Personal Access Token users have made. |
| `SNAPCOOK_LLM_PROVIDER` | for imports | `anthropic` (default), `openai` or `local` |
| `SNAPCOOK_LLM_API_KEY` | for imports | Password Mask. Imports run on the worker, so it needs this one. |
| `SNAPCOOK_LLM_BASE_URL` | no | A self-hosted inference service |
| `SNAPCOOK_API_ENABLED` | no | `1` (default) serves the product API at `/api/v1/` |
| `SNAPCOOK_OPS_API_ENABLED` | no | `0` (default). Read the [ops API's warning](reference/api-ops.md) before turning it on. |
| `SNAPCOOK_OPS_API_TOKEN` | with the ops API | 32 characters or more, `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Password Mask. The app refuses to start with a weak one. |
| `SNAPCOOK_OPS_API_WRITE` | no | `1` allows the ops API's mutating endpoints. Default `0`. |
| `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA` | no | `1` opts in to ODbL ingredient data. Default `0`; see [THIRD_PARTY_DATA.md](../THIRD_PARTY_DATA.md). |
| `DJANGO_DEBUG` | no | `0`, the image's default. Never `1` on a server: it shows tracebacks to visitors. |

`SNAPCOOK_DATA_DIR` (`/data`) and `GIT_COMMIT` are set by the image; leave them
alone. The [variable reference](reference/env-vars.md) has the full list.

### First start

Click **Apply** on `snap-cook-db`, then `snap-cook-web`. Its log shows the
migrations, then `Listening at: http://0.0.0.0:8931`. Then apply
`snap-cook-worker`; its log ends in `Q Cluster ... running.`.
`http://<unraid-ip>:8931/up` answers with the commit, and the container's
health turns **healthy**.

To start with the six example recipes, run once in the Unraid terminal:

```bash
docker exec snap-cook-web python manage.py seed_corpus
```

Other `manage.py` commands, such as `reindex --full --yes`
([reindex](runbooks/reindex.md)), run the same way: `docker exec snap-cook-web`
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
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on both containers (for a
   local checkout, in `.env`), and **Apply**.

The credentials come from the environment only. Do not also add a **Social
application** in Django's admin: with two sets, sign-in fails with
`MultipleObjectsReturned`.

Behind the tunnel, or any other reverse proxy, the site takes the scheme from
`X-Forwarded-Proto` and trusts `https://<host>` for forms, for every host in
`DJANGO_ALLOWED_HOSTS`. Without that, Django would build an `http://` callback,
and Google's exact match would refuse it.

> **The tunnel must not carry `/ops/api/`.** It ignores ownership and can read
> every user's private recipe. Leave `SNAPCOOK_OPS_API_ENABLED` at `0` on a
> tunnelled server, or block `/ops/api/` for the tunnel's host name (e.g. with
> a Cloudflare WAF rule) and use it from the LAN only. It is not nested under
> `/api/` precisely so a proxy can treat the two differently.

## Logs

The app logs to the container log (**Docker → container icon → Logs**):
gunicorn's requests on `web`, the jobs on `worker`, and an `ops-access` line for
every ops API request, granted or refused. Docker deletes it whenever Unraid
recreates the container, e.g. on an update.

## Updates

Enable **CA Auto Update Applications** for `snap-cook-web` and
`snap-cook-worker` to deploy new `stable` images automatically. Every release is
also tagged `v<version>` and `sha-<full-commit>`; for a rollback, put an earlier
one in **Repository**. Keep `web` and `worker` on the same tag: `web` applies
the migrations, and the worker expects the schema they make.

A rollback does not undo the newer release's migrations: the older image
runs on the newer schema. If it fails there, restore the database backup from
before the update.

To try a release before it is merged, `ghcr.io/yannicksuter/snap-cook:test`
follows the newest release pull request ([how releases
work](runbooks/release.md)). Give a test setup its own database container and
its own **Path (store)**: `web` migrates the database on start, so a test build
would upgrade the live one.

Pulls need no credentials once the package is public. If Unraid asks for
them, set the visibility in the [package
settings](https://github.com/users/yannicksuter/packages/container/snap-cook/settings)
to public, or run `docker login ghcr.io` on Unraid.

## Docker Compose

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, POSTGRES_PASSWORD, the Google
# keys and SNAPCOOK_API_TOKEN_PEPPER in .env.
docker compose pull
docker compose up -d --no-build --wait
```

Compose runs the same three containers as above: `db`, `web` and `worker`, with
the store in `./data` and Postgres in `./pgdata`. `SNAPCOOK_IMAGE` in `.env`
picks the image, `ghcr.io/yannicksuter/snap-cook:stable` by default. Repeat the
last two commands to update. To build from the checkout instead, run
`./scripts/build.sh` before `docker compose up -d --no-build --wait`.
