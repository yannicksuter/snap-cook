# Roadmap

Milestones are ordered by **what they prove**, not by how much they build. The
thesis — that a structured recipe model produces better readings than a document
does — is either true or it is not, and M1 is designed to find out before
anything is built on top of it.

---

## M0 — Skeleton ✅

Repository, licenses, CI, Docker, Google SSO, health probe.

**Acceptance:** a stranger can clone, `docker compose up`, sign in with Google,
and see an empty recipe list. `/up` reports the build commit and the footer
shows the same one.

---

## M1 — The vertical slice ✅

**One recipe, rendered three ways, in two languages, in two unit systems.**

This is the thesis test. If this slice does not sing, no amount of social
features rescues it — and if it does, everything after is execution.

Build order (all landed):

1. ✅ `ids`, `errors`, `schema/base`
2. ✅ `canonical/` + `hashing` with frozen cross-language vectors
3. ✅ `schema/quantity` + `units/rounding` + `units/scaling` — the highest-risk
   logic, built standalone under heavy property tests
4. ✅ remaining `schema/*` + graph validators
5. ✅ `cooklang/` parse → lower → print, gated on round-trip idempotence
6. ✅ `store/memory` then `store/fs` — linear lineage only
7. ✅ `units/` registry, locales, density — curated subset (~20), not a full import
8. ✅ `render/build` + `toposort` + `text` + `mermaid` + `print`
9. ✅ `catalog` projection + `reindex`; recipe UI with language/unit/scale toggles

**Out of scope:** forking, diff, import, the product API, social, search.

**Acceptance — all met:**
- ✅ `006-roesti` renders as text, Mermaid and print, in DE and EN, in metric and
  US, at 1× and 2×
- ✅ truncating `catalog` and running `reindex --full` reproduces the projection
  byte-identically
- ✅ the hash contract passes
- ✅ tier 0 runs in under 3 seconds (~0.9 s)

Remaining polish and known limitations are tracked in [`../todo.md`](../todo.md).

---

## M2 — Versioning, forking, ops API ◀ next

Lineage, structural diff, fork with the license lattice, publish flow,
version-history UI.

**The ops API ships here, not later.** The motivating need — inspecting a live
server with real users and no database access — is an M2-era need, not an M4-era
one. Read-only endpoints first; write endpoints stay behind a second flag.

---

## M3 — Import pipeline

django-q2 and the worker container, import UI (image / PDF / URL / pasted text),
the provider adapter, `importing/normalize.py`, the draft review UI, fixture
capture, the `pytest-socket` ban, and the eval harness. Pasted text may be a
full, noisy webpage selection; extraction must isolate the recipe rather than
requiring the user to clean it first.

Worth stating plainly: **structure is a tax on the author, and nobody will hand-
author a graph.** The importer is not a convenience feature — it is the primary
data-entry path, and the editor for correcting an extracted draft is the real
authoring interface.

---

## M4 — Product API

django-ninja product surface, PAT management UI, cursor pagination,
`test_no_leaks.py`.

---

## M5 — Social, search, ingredient registry

Follows, likes, collections, comments. Postgres full-text plus trigram search.
The ingredient registry with per-attribute provenance and `seed_ingredients`.

---

## M6+ — Deferred

Flutter client, self-hosted LLM service, Playwright end-to-end smoke tests,
store garbage collection and packfiles, collaborative editing.

---

## Open questions

Genuinely unresolved, recorded so they are not silently decided by accident:

- **Print rendering technology.** WeasyPrint, headless Chromium, or Typst? The
  model is designed so print is a renderer over `RenderModel`, but "cookbook as
  a gift" implies typographic quality that HTML-to-PDF may not reach.
- **Merge.** The store accommodates multiple parents, but semantic three-way
  merge of a recipe graph is a project in itself. Fork plus manual diff may be
  sufficient for a long time.
- **Ingredient registry seeding at scale.** M1 uses ~200 curated ingredients.
  Full USDA ingestion is a data pipeline, and doing it early risks distorting
  the schema toward whatever those datasets happen to contain.
