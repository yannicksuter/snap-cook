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
- **It answers only the LAN or a VPN.** A request that came through a tunnel or
  reverse proxy is refused, token or not: it carries `CF-Connecting-IP`,
  `CF-Ray`, `X-Forwarded-For`, `Forwarded` or `X-Real-IP`, which Cloudflare's
  tunnel adds to everything it carries. So is a request from an address the
  internet routes. LAN addresses, Docker's bridge and VPN ranges such as
  Tailscale's (`100.64.0.0/10`) are let through (`api.auth.direct_from_the_lan`).

> A server whose site runs through a Cloudflare tunnel can therefore switch the
> ops API on: `https://<your host>/ops/api/` refuses, and
> `http://<server's LAN address>:8931/ops/api/` answers. It is still not nested
> under `/api/`, so a reverse proxy can treat the two differently too.

## Auth

Staff session, or `Authorization: Bearer <SNAPCOOK_OPS_API_TOKEN>`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB reachable, store writable, worker heartbeat |
| GET | `/settings` | Effective flags — **redacted**, presence only |
| GET | `/imports?limit=20` | Recent imports, anyone's: kind, status, source files, problem, recipe |
| GET | `/imports/{id}` | One import: source text, the model's reading as returned, the checked draft, questions, what it left out, and the recipe as stored now |
| GET | `/imports/{id}/sources/{file}` | A source file as uploaded (`1.pdf`, `1.jpg`) |
| GET | `/recipes/{slug}` | A stored recipe, anyone's: owner, versions, how HEAD was made, Cooklang |
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

# Check an import against its source: the model's reading, what was saved,
# and the PDF it read.
curl -H "Authorization: Bearer $SNAPCOOK_OPS_API_TOKEN" \
     "http://snapcook.lan:8931/ops/api/imports?limit=5"
curl -H "Authorization: Bearer $SNAPCOOK_OPS_API_TOKEN" \
     http://snapcook.lan:8931/ops/api/imports/<id>
curl -H "Authorization: Bearer $SNAPCOOK_OPS_API_TOKEN" -o source.pdf \
     http://snapcook.lan:8931/ops/api/imports/<id>/sources/1.pdf

# With the flag off, the same call returns 404 -- not 403. Through the tunnel,
# or from a public address, it returns 401.
```

`/settings` reports whether each secret is configured, never its value.
Otherwise the ops token becomes a way to exfiltrate every other credential.
