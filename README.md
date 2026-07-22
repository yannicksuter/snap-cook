# snap-cook

A recipe platform built on one claim: **a recipe is structured data, and every
readable form of it is a view.**

Every recipe site stores prose and hopes you can parse it. snap-cook stores the
model and generates the prose — along with a flowchart, a printable page, and
the same recipe in your language and your units.

```
                      ┌─→  ordered step list
   recipe (a DAG)  ───┼─→  flowchart
                      └─→  printed cookbook page

                    × your language  × your unit system  × your scale
```

## What makes it different

**Recipes are files, not database rows.** The authoritative store is a
content-addressed directory tree. Postgres is a *derived index* — delete it and
`reindex --full` rebuilds it. You can host the store on GitHub, read it with any
client, or walk away with it entirely.

**Steps form a graph, not a list.** Nodes are food-states — "the dough", "the
roux" — and edges are actions carrying a verb, duration, temperature and tools.
An ordered step list is a topological sort of that graph. A flowchart is a
drawing of it. Both come from one model rather than two implementations that
drift apart.

**Units and language are render options.** The same stored recipe reads in
French with metric units for one person and English with US customary for
another. Volume↔mass conversion is per-ingredient, because 250 g of flour is not
250 ml of flour.

**Recipes have lineage.** Fork one, change it, and the ancestry is preserved.
The diff is structural — "replaced cream with coconut milk", not a wall of
changed lines.

**Identity is meaning, not bytes.** Reformat a recipe file and its hash does not
change; only the content matters.

## Status

Early. Milestone 0 (skeleton, auth, deployment) is in place. Milestone 1 — one
recipe rendered three ways, in two languages, in two unit systems — is in
progress. See [`planning/ROADMAP.md`](planning/ROADMAP.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
git clone https://github.com/yannicksuter/snap-cook.git
cd snap-cook
cp .env.example .env          # then fill in POSTGRES_PASSWORD and the Google keys
uv sync

./scripts/test-fast.sh        # core test suite, no Docker needed, < 3s
./scripts/local_start.sh      # bring up the full stack, wait for health
```

Then open <http://localhost:8931>.

```bash
curl -s http://localhost:8931/up
# {"status": "ok", "commit": "a1b2c3d…"}
```

## Development

```bash
uv sync                              # install everything

./scripts/test-fast.sh               # tier 0: no Django, no DB, < 3s
uv run pytest apps/web -q --reuse-db # tier 1: Django + Postgres
./scripts/test.sh                    # everything except paid LLM evals

uv run ruff check . && uv run ruff format --check .
```

The test suite is tiered so the inner loop stays fast: `snapcook-core` has no
framework dependency, so ~70% of the tests need neither a database nor Django.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow and
[`AGENTS.md`](AGENTS.md) for the architectural rules.

## Deployment

One image, two roles (`web` and `worker`), plus Postgres.

```bash
./scripts/build.sh                   # stamps the image with the git commit
docker compose up -d
```

### Unraid

| Setting | Value |
|---|---|
| Repository | `snap-cook:0.1.0` |
| Port | Host `8931` → Container `8931` |
| Path — store | `/mnt/user/appdata/snap-cook/data` → `/data` |
| Path — Postgres | `/mnt/user/appdata/snap-cook/pgdata` → `/var/lib/postgresql/data` |
| Post argument | `web` (and a second container with `worker`) |

Run two containers from the same image, differing only in the post-argument.
Both must map the **same** `/data` path — the worker writes store objects that
the web tier reads.

On Unraid, set environment variables through the container template's webUI
rather than a `.env` file.

> **Back up `/data`. Only `/data`.** It holds the authoritative recipe store.
> Postgres is reconstructible with `manage.py reindex --full`; losing `pgdata`
> costs social data, losing `/data` loses everything.

### Google SSO setup

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services
   → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Web application**
3. Authorised redirect URIs — add one per host you sign in from:

   | Environment | Redirect URI |
   |---|---|
   | Local | `http://localhost:8931/accounts/google/login/callback/` |
   | Production | `https://cook.example.com/accounts/google/login/callback/` |

4. Copy the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`.

> ⚠️ **Google will not accept a private LAN IP** (`192.168.x.x`) as a redirect
> URI. Sign in via `localhost` or a real hostname. A LAN IP can still be listed
> in `DJANGO_ALLOWED_HOSTS` for API access — the two lists serve different
> purposes.

Credentials are read from the environment, **not** from a database `SocialApp`
row. Creating both raises `MultipleObjectsReturned` at login.

### Behind a reverse proxy

`CSRF_TRUSTED_ORIGINS` and `SECURE_PROXY_SSL_HEADER` are configured from
`DJANGO_ALLOWED_HOSTS` automatically. Without them Django builds an `http://`
OAuth callback that fails Google's exact-match check.

> **Do not route `/ops/api/` through a public tunnel.** It deliberately ignores
> ownership and can read any user's private recipe. Keep it LAN-only or behind a
> VPN. It is not nested under `/api/` precisely so your proxy can treat the two
> differently.

## Licensing

Three separate planes — see [`LICENSING.md`](LICENSING.md):

| Plane | Covers | License |
|---|---|---|
| Application | `apps/web/` and the repo as a whole | **AGPL-3.0-or-later** |
| Core library | `packages/snapcook-core/` | **Apache-2.0** |
| Seed data | The ingredient registry | Per-source; see [`THIRD_PARTY_DATA.md`](THIRD_PARTY_DATA.md) |
| Your recipes | Content you author | Per-recipe, private by default |

The core is permissively licensed on purpose: a Django-free domain library is
only genuinely reusable — by a mobile client, a CLI, or your own tooling — if it
is not copyleft.

## Security

Report vulnerabilities privately via GitHub Security Advisories. See
[`SECURITY.md`](SECURITY.md).
