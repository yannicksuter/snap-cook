# todo

Working list for progressive iteration. `planning/ROADMAP.md` is the strategic
plan and `planning/MILESTONE_1.md` the milestone contract; this file is the
day-to-day surface — what to pick up next, roughly in priority order.

Convention: `[ ]` open, `[x]` done, `[~]` partial. Each item points at the file
it touches so it can be picked up cold.

---

## M1 — done

The vertical slice is feature-complete and meets every acceptance criterion
(see `planning/MILESTONE_1.md`). Tier-0 is green: **190 tests, ~0.9 s.** The
end-to-end path — author → commit to store → `reindex` → render three ways in
two languages, two unit systems, two scales — works, and `reindex --full`
rebuilds the projection byte-identically.

## Verify before calling M1 shipped

- [ ] **Run tiers 1–2 against real Postgres.** Local dev here had no database,
      so `apps/web` tests (including `tests/test_projection_rebuildable.py`) were
      verified against in-memory SQLite, not Postgres. Bring the stack up
      (`./scripts/local_start.sh`) and run `uv run pytest apps/web -q --reuse-db`
      and `-m integration`. `JSONField`, `SlugField` and the datetime handling
      all behave differently enough on Postgres to be worth confirming.
- [ ] **Add web (tier-1) tests for the detail view.** `recipes/tests/` is empty.
      Cover: toggles change the rendered output; an HTMX request returns the
      fragment, not the full page; a private recipe 404s for a stranger through
      the view; the store is read through `catalog.access`, never `Recipe.objects`.
- [ ] **Seed on boot / document it.** `entrypoint.sh` and the run docs should
      mention `manage.py seed_corpus` so a fresh `docker compose up` shows the
      thesis instead of an empty list.

## M1 polish — known limitations

These are cosmetic or scoped-down, not bugs. Each has a pointer.

- [ ] **Ingredient pluralisation.** Renders "2 egg", "6 tomato", "2 garlic".
      Display names come from the registry singular; there is no pluraliser.
      Needs a per-language plural rule or a `names_plural` field.
      `render/build.py:_render_ingredient`, `registry.py`.
- [ ] **Ingredient-line aggregation.** The ingredient list is one line per use,
      in step order; the same ingredient across two steps is not summed. The
      rendering doc calls for aggregation. `render/build.py:build_render_model`.
- [ ] **Oven-temperature snapping.** Snaps to 5° (356 °F → 355 °F). Real dials
      go 350/375/400 °F and 180/200 °C — a coarser, unit-aware ladder would read
      better. `render/build.py:_render_temperature`.
- [ ] **Scaling warnings are not localised.** "not scaled automatically…" stays
      English in a German render. It is a diagnostic string, not prose, but a DE
      reader still sees English. `units/scaling.py` (`CODE_SCALING_MANUAL`).
- [ ] **Density is available but not used for display.** Volume↔mass conversion
      is implemented and tested, but the renderer only converts within a
      dimension. A US reader who wants flour in cups (not grams) needs the
      display path to opt into density. `render/build.py:_choose_display_unit`.
- [ ] **Curated registry is ~20 ingredients, not ~200.** Enough for the corpus.
      Grow it — and move the data out of `registry.py` into `seeds/` — before it
      is load-bearing. Full USDA/FAO ingestion stays deferred (ADR 0005).
- [ ] **Cooklang round-trip is guaranteed for the source language only.**
      Printed in another language, ingredient tokens use registry display names,
      which do not reliably re-bind. Sibling translation files (`recipe.de.cook`)
      per RECIPE_SPEC §7 are not written yet. `cooklang/print_.py`, `store/fs.py`.
- [ ] **No implicit linear chaining in the parser.** Every consumed state must be
      referenced explicitly (`@&{…}`); a plain hand-authored linear list without
      state markers will not chain. The canonical printed form is always
      explicit, so the round-trip gate is unaffected — this only bites
      hand-authoring. `cooklang/parse.py`.
- [ ] **Sections are not modelled.** RECIPE_SPEC hints at them; the corpus does
      not need them. Add when a recipe does.

## Docs to keep honest

- [ ] Flip the *(planned)* markers in `RECIPE_SPEC.md` §5 (storage) and §6
      (authoring syntax) now that both are implemented; leave §7 (i18n sibling
      files) marked planned until translation files are written.
- [ ] `CHANGELOG.md` — add the M1 entry (done in this change set; keep current).

## M2 — next (see ROADMAP)

- [ ] Lineage already exists (linear); add **structural diff** over the graph,
      keyed on the stable element ids that `ids.py` exists to provide.
- [ ] **Fork** with the licence lattice (`LICENSING.md`); forks start private.
- [ ] **Ops API** (`/ops/api/`) read-only endpoints first — jobs, consistency.
      The store reader and `history()` it needs already exist.
- [ ] Version-history UI over `catalog.RecipeVersion`.
