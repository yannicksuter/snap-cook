# Import pipeline

```
image / PDF / URL / pasted text
            │
            ▼
  [ 202 job_id ]  ── never in the request cycle
       │
       ▼
  django-q worker
       │
       ├─ URL:         recipe-scrapers (JSON-LD, microdata)
       ├─ image/PDF:   text extraction / OCR
       ├─ pasted text: retain the complete, potentially noisy selection
       └─ all:         LLM isolates recipe → RawExtraction
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
6. **Do not require clean pasted text.** The textarea accepts a full webpage
   selection. Navigation, ads, comments, recommendations and unrelated prose
   are filtered by extraction, not manually by the user.

## What is kept and what is dropped

| Kept | Dropped |
|---|---|
| ingredients, quantities, units | headnotes and narrative |
| functional step text | author's stylistic asides |
| times, temperatures, yield | ads, comments, other recipes on the page |
| source URL for attribution | |
| a photo of the dish, **with its source** | |

Ingredient lists are uncopyrightable facts; prose and images are not. Parsing
prose into a graph is a re-expression of fact and procedure rather than a copy —
a materially stronger position than storing verbatim text.

## Photos

A recipe may carry a photo of the finished dish. Photos are protected works, so
unlike the recipe itself they are kept only with a record of where they came
from.

1. **Every photo has a source.** Either it is the household's own (who took
   it), or it names where it came from: the page URL, or the book's title,
   author and page.
2. **No source, no photo.** The review screen asks for the source of a photo
   someone else took; a photo without one is not saved.
3. **Someone else's photo stays private.** It shows only on recipes that are
   private, and the page shows its source under it. Publishing a recipe shows
   only the household's own photos.
4. **A crop is a suggestion.** On a cookbook page the extraction proposes the
   region that shows the dish. Image coordinates from a model are approximate,
   so the reader confirms the crop or removes the photo.

## Testing

Fixtures at the **provider boundary**, never HTTP cassettes. Cassettes capture
`Authorization` headers, and this repository is public; scrubbing is opt-in and
easy to get wrong.

The valuable tests are pure functions over `RawExtraction`: wrong units,
ambiguous ingredient names, missing amounts, hallucinated steps, non-DAG
ordering, mixed-language output. Provider evals also include noisy pasted
webpages and assert that surrounding navigation, ads, comments and recommended
content do not leak into the extracted recipe.
