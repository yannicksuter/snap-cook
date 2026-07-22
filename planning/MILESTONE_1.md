# Milestone 1 — the vertical slice

**One recipe, rendered three ways, in two languages, in two unit systems.**

The point is to test the thesis before building on it. Everything here exists to
answer one question: *does a structured model actually produce better readings
than a document?*

> **Status: feature-complete.** Every task below is implemented and covered by
> tier-0 tests (190 tests, ~0.9 s). Remaining polish and known gaps are tracked
> in [`../todo.md`](../todo.md), not here — this file records what M1 *is*, the
> todo records what is left to sand down.

## Tasks

### Foundations
- [x] `ids.py` — prefixed ULIDs, stable across edits so diff can match elements
- [x] `errors.py` — error tree plus `ValidationIssue` for non-fatal diagnostics
- [x] `schema/base.py` — `SnapcookModel`, `NonSemantic`
- [x] `canonical/` — encode, JCS, hashing
- [x] frozen cross-language hash vectors + `contract` CI job
- [x] AST test: core never imports Django

### Quantities and units (highest risk — build standalone, test hard)
- [x] `schema/quantity.py` — `Scalar | Range | Count | Approx`, `ScalingPolicy`
- [x] `units/rounding.py` — fraction ladders, metric bands, mixed numbers
- [x] `units/scaling.py` — per-policy dispatch; timers never auto-scale
- [x] `units/registry.py` — Pint with `non_int_type=Decimal`, locale-qualified cups
- [x] `units/density.py` — per-ingredient Pint contexts; raise, never guess
- [x] property tests: round-trip, `scale(scale(r,a),b) == scale(r,a*b)`,
      cross-dimension raises, `approx` invariance, no `"0"` for non-zero

### Schema
- [x] `schema/graph.py` — `FoodState`, `Action`, `TextTemplate` chunks
      (incl. `StateChunk` for `@&{}` consumption)
- [x] `schema/ingredient.py`, `cookware.py`, `i18n.py`, `provenance.py`
- [x] `schema/recipe.py` + graph validators (acyclic, no dangling refs,
      single-writer outputs) — an invalid graph is unhashable

### Authoring
- [x] `cooklang/` lexer, parser, frontmatter, lower, printer
- [x] round-trip idempotence property test as the gate (`print(parse(T)) == T`)

### Store
- [x] `store/memory.py`, then `store/fs.py` — linear lineage only
- [x] the no-op commit rule: equal content hash → no new version
- [x] `recipe.json` / `recipe.cook` / `README.md` projections of HEAD

### Rendering
- [x] `render/model.py`, `build.py`, deterministic `toposort.py`
- [x] `render/text.py`, `mermaid.py`, `print_.py`
- [x] golden files for the declared matrix per fixture

### Corpus
- [x] `001-boiled-egg` … `006-roesti` — in `snapcook_core.testing.corpus`

### Django
- [x] `catalog` projection from the store + working `reindex --full`
- [x] `seed_corpus` management command
- [x] recipe list and detail, HTMX toggles for language / units / scale
- [x] `test_projection_rebuildable.py` (tier 2; verified locally on SQLite,
      runs on Postgres in CI)

## Acceptance

- [x] `006-roesti` renders text + Mermaid + print, DE and EN, metric and US, 1× and 2×
- [x] truncate `catalog`, `reindex --full`, projection is byte-identical
- [x] hash contract passes
- [x] tier 0 under 3 seconds (0.9 s)
