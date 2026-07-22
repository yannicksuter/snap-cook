# Mobile API contract

The subset of `/api/v1/` the mobile client depends on. Changes here are
breaking changes for the app and need a version bump.

## Auth

Personal Access Token in `Authorization: Bearer snck_pat_<prefix>_<secret>`.

Tokens are per user and scoped. A shared token would be useless here — recipe
content is private by default, so the server must know who is asking.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/me` | Identity, language and unit preferences |
| GET | `/recipes` | List, cursor-paginated |
| GET | `/recipes/{slug}` | `?lang&units&scale&render=model` — fetch the render model |
| GET | `/recipes/{slug}/versions/{hash}` | Authoritative canonical bytes |
| POST | `/imports` | multipart image/PDF or `{url}` → `202 {job_id}` |
| GET | `/imports/{job_id}` | Poll; draft payload when complete |

## Rendering on device

Request `render=model` and render client-side. The server also offers `text`,
`mermaid` and `print`, but the model form lets the app control typography and
lay out for a phone.

## Offline

See [`offline-strategy.md`](offline-strategy.md).
