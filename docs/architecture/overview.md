# Architecture overview

## The ideas

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

## The shape

```
                    ┌──────────────────────────────────────┐
                    │  packages/snapcook-core (Apache-2.0) │
                    │  schema · canonical · units          │
                    │  store · render · diff               │
                    │  NO Django. Enforced by a test.      │
                    └──────────────┬───────────────────────┘
                                   │
          ┌────────────────┬───────┴────────┬──────────────────┐
          │                │                │                  │
     Django web       django-ninja      (future) CLI     (future) Flutter
     templates+HTMX   /api/v1/                            via /api/v1/
          │                │
          └────────┬───────┘
                   │
     ┌─────────────┴─────────────┐
     │                           │
  /data/store                Postgres
  AUTHORITATIVE              DERIVED PROJECTION
  content-addressed          rebuildable: reindex --full
  back this up               losing it costs social data only
```

## The layers

**`snapcook-core`** holds everything that is true about a recipe regardless of
how you reach it. It is framework-free so that a mobile client, a CLI and a
self-hosted LLM service can share one brain rather than three drifting
reimplementations.

**`apps/web`** is one consumer. Its Django apps split by *who owns the truth*:

| App | Truth |
|---|---|
| `catalog` | derived — must be rebuildable |
| `accounts`, `social`, `imports` | database-authoritative |
| `recipes`, `api` | presentation only, no domain logic |

That split is what makes "Postgres is a cache" enforceable rather than
aspirational: `reindex --full` truncates exactly `catalog` and nothing else.

## Request paths

- **Web UI** — Django view → `catalog.access` for visibility → `snapcook_core`
  for rendering → template
- **API** — django-ninja → same two calls → JSON
- **Import** — source submission → `202 {job_id}` → django-q worker → LLM → draft →
  human review → commit to store → reindex

## See also

- [`version-store.md`](version-store.md) — content addressing and lineage
- [`projection.md`](projection.md) — why Postgres is a cache
- [`dag-model.md`](dag-model.md) — the recipe graph
- [`rendering.md`](rendering.md) — one model, three renderers
- [`units-and-i18n.md`](units-and-i18n.md) — conversion and translation
- [`import-pipeline.md`](import-pipeline.md) — image/PDF/URL/pasted text to draft
