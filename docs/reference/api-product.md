# Product API

`/api/v1/` — the client-facing surface. Consumed by the web UI, and by the
Flutter client later.

## Auth

Session (for the HTMX UI) **or** a per-user Personal Access Token:

```
Authorization: Bearer snck_pat_<prefix>_<secret>
```

A shared bearer token would be categorically wrong here. Content is private by
default, and a shared token carries no user identity, so it cannot scope
anything.

Tokens are stored as SHA-256 with a server-side pepper; lookup is a point query
on the indexed prefix followed by a constant-time comparison.

## The authorization rule

> Every endpoint starts from `catalog.access.visible_recipes(user)`. No endpoint
> builds its own queryset from `Recipe.objects`.

`api/tests/test_no_leaks.py` introspects every registered route, calls it as
user B with user A's private recipe ids, and asserts **404** — not 403, because
403 confirms the recipe exists.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Identity and render preferences |
| GET | `/recipes` | Cursor pagination, not offset |
| POST | `/recipes` | Writes a store object, then projects *(M4)* |
| GET | `/recipes/{slug}` | `?lang&units&scale&render=text\|mermaid\|print\|model` |
| PUT | `/recipes/{slug}` | Requires `parent_hash`; 409 on mismatch *(M4)* |
| GET | `/recipes/{slug}/versions` | Lineage *(M2)* |
| GET | `/recipes/{slug}/versions/{hash}` | Authoritative canonical bytes *(M2)* |
| GET | `/recipes/{slug}/diff` | `?from=&to=` structural diff *(M2)* |
| POST | `/recipes/{slug}/fork` | Applies the license lattice *(M2)* |
| POST | `/recipes/{slug}/publish` | 422 if license missing or not permitted *(M2)* |
| POST | `/imports` | **202 + job_id**, never inline *(M3)* |

## Conventions

- **Cursor pagination**, so a page does not shift under insertion
- **Optimistic concurrency** on update via `parent_hash`, giving 409 rather than
  a silent lost update
- **404 over 403** for anything the caller may not see
- OpenAPI schema at `/api/v1/openapi.json`
