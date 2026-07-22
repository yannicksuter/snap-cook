# Ops API

`/ops/api/` — diagnostics for a running server.

## Threat model — read before enabling

**This surface deliberately ignores ownership.** `/ops/api/versions/{hash}`
returns the canonical bytes of any recipe, including private ones belonging to
other users. That is the endpoint's purpose: diagnosing a live server without
database access.

`SNAPCOOK_OPS_API_TOKEN` is therefore the **highest-value secret in the
system**. Treat a leak as full disclosure of every private recipe on the
instance.

Mitigations in place:

- Disabled by default
- The app refuses to boot on a weak, placeholder or low-entropy token
- Mutating endpoints need `SNAPCOOK_OPS_API_WRITE=1`
- A session grants access only if the user is `is_staff` — a bare authenticated
  session does not, since anyone with a Google account can sign in
- Every request is logged with actor and source IP, refusals included

> **The mitigation that actually matters: do not route `/ops/api/` through a
> public tunnel.** Keep it LAN-only or behind a VPN. It is not nested under
> `/api/` precisely so your reverse proxy can treat the two differently.

## Auth

Staff session, or `Authorization: Bearer <SNAPCOOK_OPS_API_TOKEN>`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB reachable, store writable, worker heartbeat |
| GET | `/settings` | Effective flags — **redacted**, presence only |
| GET | `/jobs` | Queue inspection *(M3)* |
| POST | `/jobs/{id}/requeue` | write-gated *(M3)* |
| GET | `/versions/{hash}` | Raw canonical bytes, **no ownership filter** *(M2)* |
| GET | `/consistency` | DB-vs-files drift *(M2)* |
| POST | `/reindex` | write-gated; enqueues *(M2)* |
| GET | `/users` | id, email, joined, recipe count *(M2)* |

## Examples

```bash
curl -H "Authorization: Bearer $SNAPCOOK_OPS_API_TOKEN" \
     http://snapcook.lan:8931/ops/api/health

# With the flag off, the same call returns 404 -- not 403.
```

`/settings` reports whether each secret is configured, never its value.
Otherwise the ops token becomes a way to exfiltrate every other credential.
