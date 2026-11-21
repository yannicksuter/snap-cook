# Installing snap-cook

snap-cook runs as one container, `ghcr.io/yannicksuter/snap-cook`: the site, the
background worker that reads new recipes, and a Postgres database of its own.
Everything it keeps lives in one folder, mounted at `/data`; the originals
recipes were read from (photos, PDFs, pages) can live in a second one, mounted
at `/sources`.

`stable` is the newest release ([how releases work](runbooks/release.md)).
`GET /up` returns `{"status": "ok", "commit": "<Git commit SHA>"}` without
signing in, so you can tell which build is live.

> **Back up `/data`.** It holds the recipe store, the only copy of every recipe
> and its history, and the database with the accounts, settings, API tokens and
> drafts. Back it up while the container is stopped, as CA Appdata Backup does,
> so the database files are consistent. See
> [restore-from-backup](runbooks/restore-from-backup.md). Back up `/sources`
> too if you mount it: it is the only copy of each recipe's original.

## Unraid setup

In **Docker → Add Container**, enable **Advanced View** and use these settings:

| Setting | Value |
|---|---|
| Name | `snap-cook` |
| Repository | `ghcr.io/yannicksuter/snap-cook:stable` |
| Network Type | `Bridge` |
| Port (HTTP) | Config Type **Port**: Container Port `8931`, Host Port `8931`, TCP |
| Path (data) | Config Type **Path**: Container Path `/data`, Host Path `/mnt/user/appdata/snap-cook`, Access Mode **Read/Write** |
| Path (originals) | Config Type **Path**: Container Path `/sources`, Host Path a share of your choice, e.g. `/mnt/user/snap-cook-sources`, Access Mode **Read/Write**. Optional: without it the originals stay in `/data/sources`. Once mounted, the next start moves them there. |
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
| `SNAPCOOK_ADMIN_EMAILS` | for `/admin` | The addresses that may open `/admin`, comma-separated. They must sign in and be confirmed like everyone else. |
| `SNAPCOOK_SMTP_HOST` | for passwords | The mail server for confirmation and password-reset mails, e.g. `smtp.gmail.com`. Without it, signing up with a password is closed and only Google works. See [Mail](#mail). |
| `SNAPCOOK_SMTP_PORT` | no | `587` (default, STARTTLS) or `465` (TLS) |
| `SNAPCOOK_SMTP_USER` | with SMTP | The mail account's user name |
| `SNAPCOOK_SMTP_PASSWORD` | with SMTP | Password Mask. For Gmail, an app password, not the account's own. |
| `SNAPCOOK_MAIL_FROM` | no | The sender, e.g. `snap-cook <you@gmail.com>`. Default: the SMTP user. |
| `SNAPCOOK_PUBLIC_HOST` | no | The host name mails link to. Default: the first public name in `DJANGO_ALLOWED_HOSTS`. |
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
`secrets/` (the key people's ids are made with; never delete it), `logs/`, and,
without a `/sources` mount, `sources/` (the originals recipes were read from,
one folder per recipe).

To start with the six example recipes, run once in the Unraid terminal:

```bash
docker exec snap-cook python manage.py seed_corpus
```

Other `manage.py` commands, such as `reindex --full --yes`
([reindex](runbooks/reindex.md)), run the same way, with `docker exec snap-cook`
in front, or typed into the container's **Console**. A deleted recipe can be
brought back the same way: [restore a recipe](runbooks/restore-a-recipe.md).

## Who may do what

Anyone may read the shared recipes, without an account. Signing in, with Google
or with an address and a password, keeps a person's settings. Adding, changing,
deleting and translating recipes spends API credit, so a new account only reads
until an admin switches **May cook** on for it in `/admin`. Admins are the
confirmed addresses in `SNAPCOOK_ADMIN_EMAILS`; they always may cook.

An address counts once it is confirmed: Google confirms it, a password account
by the link in the mail it gets. Until then the account reads as anyone does.
People appear by two or three initials (yannick.suter@… is **YS**); no page
shows an address, and `/admin` shows it masked. Accounts that existed before
keep cooking.

`/admin` lists everyone with the switch, and recipes, which an admin can read
again from their kept original, and an archive: deleting an account moves its
recipes there, where they can be given to someone else.

## Mail

Confirmation and password-reset mails go out over SMTP. With Gmail: turn on
2-step verification for the account, create an **app password** at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
and set `SNAPCOOK_SMTP_HOST=smtp.gmail.com`, `SNAPCOOK_SMTP_USER=<the address>`
and `SNAPCOOK_SMTP_PASSWORD=<the app password>`. Without `SNAPCOOK_SMTP_HOST`
only Google sign-in is offered.

## Google sign-in

Google redirects back only
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

The credentials come from the environment only.

Behind the tunnel, or any other reverse proxy, the site takes the scheme from
`X-Forwarded-Proto` and trusts `https://<host>` for forms, for every host in
`DJANGO_ALLOWED_HOSTS`. Without that, Django would build an `http://` callback,
and Google's exact match would refuse it.

> **The ops API answers only your LAN or a VPN.** It ignores ownership and can
> read every user's private recipe, so the app refuses every request that came
> through the tunnel or another proxy, even one with the right token. Switched
> on, it answers at `http://<unraid-ip>:8931/ops/api/` and nowhere else
> ([ops API](reference/api-ops.md)).

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
