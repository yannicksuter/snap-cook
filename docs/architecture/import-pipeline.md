# Import pipeline

```
image / PDF / URL
       │
       ▼
  [ 202 job_id ]  ── never in the request cycle
       │
       ▼
  django-q worker
       │
       ├─ URL:   recipe-scrapers (JSON-LD, microdata)
       ├─ image: OCR
       └─ all:   LLM → RawExtraction
       │
       ▼
  normalize()  ── pure Python in snapcook-core, fully testable
       │
       ▼
  DRAFT  ── always private, always human-reviewed
       │
       ▼
  commit to store → reindex
```

## Why the importer matters more than it looks

Structure is a tax on the author, and **nobody will hand-author a graph.** The
importer is not a convenience feature — it is the primary data-entry path, and
the editor for correcting an extracted draft is the real authoring interface.

That reprioritises it well above where a feature list would put it.

## Rules

1. **Always async.** LLM extraction takes 10–60 seconds.
2. **Always a draft.** Nothing is published without human confirmation.
3. **Retain the source.** Kept for re-extraction when the schema or prompt
   improves.
4. **Provider abstraction from day one.** A self-hosted model is planned; the
   boundary is `RecipeImporter` returning `RawExtraction`.
5. **Imports land private.** See the legal note in `LICENSING.md`.

## What is kept and what is dropped

| Kept | Dropped |
|---|---|
| ingredients, quantities, units | headnotes and narrative |
| functional step text | photographs |
| times, temperatures, yield | author's stylistic asides |
| source URL for attribution | |

Ingredient lists are uncopyrightable facts; prose and images are not. Parsing
prose into a graph is a re-expression of fact and procedure rather than a copy —
a materially stronger position than storing verbatim text.

## Testing

Fixtures at the **provider boundary**, never HTTP cassettes. Cassettes capture
`Authorization` headers, and this repository is public; scrubbing is opt-in and
easy to get wrong.

The valuable tests are pure functions over `RawExtraction`: wrong units,
ambiguous ingredient names, missing amounts, hallucinated steps, non-DAG
ordering, mixed-language output.
