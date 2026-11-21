# Environment variables

The authoritative list is the docstring at the top of
`apps/web/snapcookweb/settings.py`. `.env.example` mirrors it. This table is a
convenience copy — if they disagree, the docstring wins.

## Required in production

| Variable | Notes |
|---|---|
| `DJANGO_SECRET_KEY` | Random. Rotating it invalidates sessions. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated. Every host the app is reached by. |
| `POSTGRES_PASSWORD` | |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `SNAPCOOK_API_TOKEN_PEPPER` | Rotating it invalidates every issued PAT |

## Storage

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_DATA_DIR` | `/data` | **Must be backed up**: the recipes, the database, the uid key |
| `SNAPCOOK_SOURCES_DIR` | `/sources` if mounted, else `<data>/sources` | The originals recipes were read from. Back it up too. |

## Accounts and mail

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_ADMIN_EMAILS` | — | Comma-separated addresses that may open `/admin`, once confirmed |
| `SNAPCOOK_UID_KEY` | made on first start, kept in `<data>/secrets/uid.key` | Keys the hash people are known by. Never change it. |
| `SNAPCOOK_SMTP_HOST` | — | Without it no mail goes out, and only Google sign-in is offered |
| `SNAPCOOK_SMTP_PORT` | `587` | `465` for TLS from the start, else STARTTLS |
| `SNAPCOOK_SMTP_USER` / `SNAPCOOK_SMTP_PASSWORD` | — | |
| `SNAPCOOK_MAIL_FROM` | the SMTP user | Sender of confirmation and reset mails |
| `SNAPCOOK_PUBLIC_HOST` | first public `DJANGO_ALLOWED_HOSTS` entry | The host mails link to |

## API surfaces

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_API_ENABLED` | `1` | Off means `/api/v1/` returns 404, not 403 |
| `SNAPCOOK_OPS_API_ENABLED` | `0` | Opt in deliberately |
| `SNAPCOOK_OPS_API_TOKEN` | — | 32+ chars; app refuses to boot otherwise |
| `SNAPCOOK_OPS_API_WRITE` | `0` | Allows mutating ops endpoints |

The app rejects an ops token that is too short, contains a placeholder marker
(`change-me`, `example`, `insecure`), or has fewer than 8 distinct characters.

## Adding recipes

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_LLM_PROVIDER` | `anthropic` | `fake` reads every source as the corpus tomato sauce: development only |
| `SNAPCOOK_LLM_API_KEY` | — | On web and worker. Without it, adding recipes says it is not set up |
| `SNAPCOOK_LLM_MODEL` | `claude-opus-5-5` | |
| `SNAPCOOK_LLM_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh` or `max` |
| `SNAPCOOK_LLM_BASE_URL` | — | Route the provider through a proxy |

## Seed data

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA` | `0` | Opt in to ODbL sources. See ADR 0005. |

## Build

| Variable | Notes |
|---|---|
| `GIT_COMMIT` | Baked at image build; reported by `/up` and the footer |
