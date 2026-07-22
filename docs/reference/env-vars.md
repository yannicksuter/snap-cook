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
| `SNAPCOOK_DATA_DIR` | `/data` | **The only thing that must be backed up** |

## API surfaces

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_API_ENABLED` | `1` | Off means `/api/v1/` returns 404, not 403 |
| `SNAPCOOK_OPS_API_ENABLED` | `0` | Opt in deliberately |
| `SNAPCOOK_OPS_API_TOKEN` | — | 32+ chars; app refuses to boot otherwise |
| `SNAPCOOK_OPS_API_WRITE` | `0` | Allows mutating ops endpoints |

The app rejects an ops token that is too short, contains a placeholder marker
(`change-me`, `example`, `insecure`), or has fewer than 8 distinct characters.

## Seed data

| Variable | Default | Notes |
|---|---|---|
| `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA` | `0` | Opt in to ODbL sources. See ADR 0005. |

## Build

| Variable | Notes |
|---|---|
| `GIT_COMMIT` | Baked at image build; reported by `/up` and the footer |
