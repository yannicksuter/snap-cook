# Rendering

One intermediate model; every renderer is a pure walk over it.

```
Recipe ──build_render_model(lang, units, scale, rounding)──→ RenderModel
                                                                 │
                                         ┌───────────────────────┼──────────────┐
                                         ▼                       ▼              ▼
                                       text                  mermaid          print
```

`build_render_model` does, in order: resolve translations with a fallback chain,
scale, convert units, round, topologically sort, aggregate ingredient lines,
build the graph, collect warnings.

## Why one intermediate

Because otherwise there are three implementations of "what does 250 g of flour
look like in US customary at 1.5×", and they drift. Renderers become pure
functions of a data structure, which also makes them trivially golden-testable.

## Deterministic toposort

Kahn's algorithm with a min-heap keyed on `(action.order, action.id)`.

Two consequences that matter: a linear recipe renders in exactly authored order,
and the same graph renders identically on every machine and in every language.
Diffing and translation-isomorphism checks depend on the second.

## The renderers

**text** walks the prose chunks, substituting display values into slots.

**mermaid** ignores prose and walks the graph. Ingredients become stadium nodes,
states become boxes. An action with one input is a labelled edge; an action with
several inputs needs a join node, because a labelled edge cannot express a
hyperedge.

**print** is the hardest and lands last, but it is the **design constraint** on
the model. Pagination, typography and image placement are unforgiving, and if
print works, screen and diagram trivially do.

## Golden files

Plain committed `.txt`, `.mmd` and `.html` — not opaque snapshot blobs. A `.mmd`
pastes into the Mermaid live editor; a `.html` opens in a browser.

The reason is review, not convenience: pull-request diffs are where rendering
regressions get caught, and escaped-string snapshot diffs get rubber-stamped,
which defeats the mechanism entirely.

The full matrix (fixtures × renderers × languages × unit systems × scales) is
unmaintainable, so each fixture declares 3–6 combinations covering *its* reason
for existing. The rest get a smoke test asserting they render without raising.
