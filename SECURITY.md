# Security Policy

## Reporting a vulnerability

Report privately through **GitHub Security Advisories** — the "Report a
vulnerability" button under this repository's Security tab. Please do not open a
public issue for a security problem.

Expect an acknowledgement within 7 days and an assessment within 14. We follow
**90-day coordinated disclosure**. There is no bug bounty; this is a personal
open-source project and it would be dishonest to imply otherwise.

## Supported versions

Pre-1.0, only the latest release is supported. There are no backports.

## Scope

**In scope**
- The code in this repository
- The hosted instance, if one is running
- Default configuration produced by `docker-compose.yml` and `.env.example`

**Out of scope**
- Self-hosted deployments misconfigured by their operator, except where the
  default configuration or the documentation led them there — that *is* in scope
  and worth reporting
- The CDN-hosted Tailwind and HTMX assets
- Third-party seed data sources

## Known high-severity classes

Stated plainly because they are design consequences rather than bugs, and an
operator should know about them before deploying.

### The ops API is the highest-value secret in the system

`/ops/api/` deliberately ignores ownership. `/ops/api/versions/{hash}` returns
the canonical bytes of **any** recipe, including private ones belonging to other
users. That is the endpoint's purpose — diagnosing a live server without
database access — and it is why the token guarding it matters more than any
other credential here.

Mitigations in place:

- Disabled by default (`SNAPCOOK_OPS_API_ENABLED=0`)
- The application **refuses to boot** if enabled with a token that is shorter
  than 32 characters, contains a placeholder marker, or has fewer than 8
  distinct characters
- Mutating endpoints need a second flag (`SNAPCOOK_OPS_API_WRITE=1`)
- A session grants ops access only if the user is `is_staff` — a bare
  authenticated session does not, since anyone with a Google account can sign in
- Every ops request is logged with actor and source IP, including refusals

**The mitigation that actually matters: do not route `/ops/api/` through a
public tunnel.** Keep it LAN-only or behind a VPN. It is deliberately not nested
under `/api/` so your reverse proxy can treat the two differently.

If `SNAPCOOK_OPS_API_TOKEN` leaks, treat it as a full disclosure of every
private recipe on the instance. Rotation procedure:
[`docs/runbooks/rotate-secrets.md`](docs/runbooks/rotate-secrets.md).

### `/up` reveals the build commit

The health endpoint reports the exact git SHA the running image was built from,
which lets anyone diff it against public source to enumerate unpatched issues.
This is accepted — reporting the deployed version is the endpoint's whole
purpose, and the repository is public regardless — but it does raise the
obligation to patch promptly rather than relying on version obscurity.

### API tokens

Personal Access Tokens are stored as SHA-256 hashes with a server-side pepper
(`SNAPCOOK_API_TOKEN_PEPPER`), so a database dump alone does not permit offline
brute-forcing. Rotating the pepper invalidates every issued token.

Tokens carry the fixed prefixes `snck_pat_` and `snck_ops_` so that secret
scanners — GitHub push protection, gitleaks — can match them with high
precision. If you ever see one in a commit, in a log, or in a support ticket,
revoke it rather than assessing whether it was exposed.

## Reporting a leaked secret

If you find a credential committed to this repository, please report it
privately as above rather than opening an issue. It will be revoked and the
history scrubbed.
