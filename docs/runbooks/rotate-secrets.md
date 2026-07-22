# Runbook: rotate secrets

## Ops API token — highest priority

Rotate immediately if it may have leaked. It bypasses per-user scoping, so
exposure means every private recipe on the instance should be considered
disclosed.

```bash
NEW=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')
# update SNAPCOOK_OPS_API_TOKEN in .env (or the Unraid template)
docker compose up -d web worker      # restart picks up the new value
```

No user-visible impact — nothing else authenticates with it.

Then check `/data/logs/ops-access.log` for requests you did not make.

## API token pepper

> **Rotating `SNAPCOOK_API_TOKEN_PEPPER` invalidates every issued Personal
> Access Token.** Every user must create new ones. Announce it before rotating.

## Google OAuth client secret

1. Google Cloud Console, Credentials, your OAuth client, **Add secret**
2. Put the new one in `.env`, restart
3. Verify a login works
4. Only then delete the old secret in the Console

Adding before removing means a failed login does not lock everyone out.

## Django secret key

Rotating invalidates all sessions; users must sign in again. Harmless but
noticeable — do it during a quiet period.

## Postgres password

```bash
docker compose exec db psql -U snapcook -c "ALTER USER snapcook WITH PASSWORD 'new';"
# update POSTGRES_PASSWORD in .env
docker compose up -d
```

## After any suspected leak

1. Rotate the affected secret first, investigate second
2. Check `/data/logs/ops-access.log`
3. If it was committed, rotation is not enough — the value is in the history and
   in every clone. Rotate, then scrub.
4. Report per `SECURITY.md`
