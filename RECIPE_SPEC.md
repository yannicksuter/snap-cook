# RECIPE_SPEC.md

**The domain contract.** This is what a client, an importer or a renderer must
understand to interoperate with snap-cook. It sits at the repository root rather
than in `docs/` because it is impossible to miss here.

> **Keep this current in the same change set as any schema change.** It is the
> contract the Flutter client, the LLM importer and any third-party tool read.
> A stale spec is worse than none — it is a promise that no longer holds.

Status: **milestone 1 landed.** The model, identity, quantities, units, storage
layout and authoring syntax below are implemented. Sections still marked
*(planned)* — currently only §7's sibling translation files — are designed but
not yet built.

---

## 1. The model

A recipe is a **directed acyclic graph**.

- **Nodes** are *food-states*: a named, referenceable thing — "the dough",
  "the roux", "the rested batter".
- **Edges** are *actions*: a verb plus attributes (duration, temperature,
  tools) that consume one or more inputs and produce exactly one output state.

Tools, durations, temperatures and quantities are **attributes of an action**,
not nodes in their own right. This is a deliberate simplification of the
academic recipe-flow-graph ontologies (Kyoto r-FG has 8 node types and 13 edge
labels); those are annotation schemas for NLP research, and promoting durations
to graph nodes makes every renderer and the editor harder for fidelity a cooking
app does not need.

```
flour ──┐
        ├─[mix, 3 min]──→ "the dough" ──┐
water ──┘                               │
                          [rest, 1 h @ 4 °C]
                                        │
butter ──[fold]─────────────────────────┴──→ "laminated dough"
```

### Views derive from the graph

| View | Derivation |
|---|---|
| Ordered step list | Topological sort (Kahn, min-heap on `(action.order, action.id)`) |
| Flowchart | Direct rendering of nodes and edges |
| Print page | Same render model, paginated |

A linear recipe is a **degenerate DAG** — every action consumes the previous
action's output. It needs no special case anywhere.

The toposort is **deterministic**: the same graph renders identically on every
machine and in every language. Diffing and translation-isomorphism checks depend
on that.

---

## 2. Identity

### Hash the data structure, not the file

Reformatting a recipe file, reordering keys, or writing `@onion{}` instead of
`@onion` produces **no new version**. Identity is meaning, not layout.

Two hashes exist:

| Hash | Covers | Purpose |
|---|---|---|
| `content_hash` | The recipe content | The no-op rule: equal content, no new version |
| `version_id` | Content + author + time + parents | Commit identity; two people authoring identical content still get distinct versions |

Both are `sha256` over [RFC 8785](https://datatracker.ietf.org/doc/rfc8785/)
canonical JSON, prefixed `sc1:`. Standard-library SHA-256 rather than BLAKE3, so
a Dart, Rust or JavaScript client can verify a hash with no native dependencies.

### Canonical encoding rules

Each rule prevents a specific way two clients could disagree:

| Rule | Prevents |
|---|---|
| Non-integer numerics encode as **JSON strings** | RFC 8785 emits JSON numbers as ECMAScript doubles; `Decimal("0.1")` through a float is lossy and implementation-sensitive. Python and Dart would compute different hashes. |
| `float` is **rejected**, not converted | Converting hides the bug |
| `NonSemantic` fields are stripped | Re-importing tomorrow must hash like today |
| `null`, `[]` and `{}` are all **absent** | A default changing from `None` to `[]` would rewrite every stored hash |
| Text is **NFC-normalised** | Decomposed "café" (macOS) vs precomposed (Linux) |
| List order is **preserved, never sorted** | Order is semantic — prose chunks, action sequence |
| Mapping key order is irrelevant | JCS sorts keys |

Conformance vectors: `packages/snapcook-core/tests/contract/hash_vectors.json`.
A client reproducing all 19 has a correct implementation.

---

## 3. Quantities

Quantities are a discriminated union, because "250 g" and "a pinch" are not the
same kind of thing and flattening them into a nullable number loses information
that cannot be recovered.

| Kind | Example | Notes |
|---|---|---|
| `scalar` | `250 g` | value + unit |
| `range` | `200–300 ml` | first-class, not a string |
| `count` | `1 medium onion` | countable pieces; unit is always null, size grade optional |
| `approx` | `a pinch`, `to taste` | **never coerced to a number by any code path** |

### Scaling policy

Every quantity carries one:

| Policy | Behaviour | Applies to |
|---|---|---|
| `linear` | multiply, then round | flour, water, most ingredients |
| `invariant` | never changed | salt to taste, pan size |
| `manual` | never changed, emits a warning | **bake time, oven temperature** |
| `nonlinear` | *(planned)* — behaves as `manual` | reserved |

> **Timers never auto-scale.** Doubling a recipe does not double bake time; it
> may not change it at all. Simmer and reduction times scale with surface area,
> not volume. Silently doubling them would ruin the dish, so the default is to
> leave them alone and tell the reader to check.

`approx` quantities are scale-invariant by construction — `scale(a_pinch, k)` is
the identity function. There is no code path that produces a number from an
`approx`.

### Rounding

Display-only. `RenderedQuantity` keeps both `exact` and `display`, so
re-scaling always re-derives from the exact value and rounding never compounds.

- Fraction-friendly units snap to a ladder (`1/8, 1/4, 1/3, 1/2, 2/3, 3/4`) and
  render as mixed numbers: `1.125 tsp` → `1 1/8 tsp`, never `1.125 tsp`
- Unit promotion is tried before falling back to a decimal: `0.25 cup` → `4 tbsp`
- Metric snaps to magnitude-appropriate steps, then promotes: `1500 g` → `1.5 kg`
- Counts respect `Ingredient.divisible` — you cannot buy 1.4 eggs

---

## 4. Units

Units are **locale-qualified**, because a bare "cup" is ambiguous:

| Unit id | Value |
|---|---|
| `unit:cup.us` | 236.588 ml |
| `unit:cup.metric` | 250 ml |
| `unit:cup.jp` | 200 ml |
| `unit:cup.uk` | 284.131 ml |

Resolution happens **at authoring time** and is frozen in the version, so a
recipe never silently changes meaning when read in another country.

### Volume↔mass needs density

This is a two-argument function `(quantity, ingredient)`, not a unit conversion.
No general unit library can do it.

Conversions follow Tandoor's table shape, extended with prep state:

```
UnitConversion(base_amount, base_unit, converted_amount, converted_unit,
               food_id?, prep_state?)
```

- `food_id` **null** → universal conversion (`ml` → `l`)
- `food_id` **set** → ingredient-specific (`1 cup flour` → `125 g`)
- `prep_state` disambiguates state-dependent density: sifted vs scooped flour
  differs by roughly 20%, which is a real baking failure

> Conversion across dimensions without a density **raises**. It never guesses,
> and it never falls back to water at 1.0 g/ml. A wrong density is worse than a
> refusal because it is invisible.

Temperature is a dedicated type rather than a scalar with a unit, because
°C↔°F is affine, not multiplicative, and unit libraries refuse arithmetic on
offset units for good reason.

---

## 5. Storage layout

One directory per recipe. `git init && git push` works with no export step, and
the pushed repository contains the full lineage.

```
<store>/<recipe_id>/
├── .snapcook/
│   ├── HEAD                            {"ref": "refs/heads/main"}
│   ├── refs/heads/main                 sc1:9f2a…
│   ├── versions/9f/2a/9f2a….json       immutable version records
│   └── config.json                     store version, recipe id
├── recipe.cook                         projection of HEAD
├── recipe.en.cook                      translation
├── recipe.json                         canonical bytes of HEAD
├── media/<sha256>.jpg                  content-addressed blobs
└── README.md                           generated; renders on GitHub
```

`.snapcook/versions/**` is committed, so a `git clone` is a complete replica of
the lineage DAG.

---

## 6. Authoring syntax

A Cooklang-flavoured text format compiles into the canonical model. It is an
**input and export format**, not a stored source of truth — one mutable
representation, not two.

| Syntax | Meaning |
|---|---|
| `@flour{500%g}` | ingredient with quantity and unit |
| `@?yeast{7%g}` | optional |
| `@=salt{1%tsp}` | **snap-cook**: scaling policy `invariant` |
| `@eggs{2-4}` | range |
| `@onion{1%medium}` | count with size grade |
| `@salt{a pinch}` | `approx` |
| `#stand mixer{}` | cookware |
| `~{30%min}` / `~proof{2%h}` | timer, optionally named |
| `^{220%C}` | **snap-cook**: temperature |
| `=> dough` | **snap-cook**: names this action's output state |
| `@&{dough}` | **snap-cook**: consumes a named state |

### Named references, not positional

Cooklang's `@&(~1)dough{}` means "the output of one step back". snap-cook uses
`@&{dough}` instead.

Positional references break under step reordering, insertion, or moving a step
between sections — which is exactly what a graph editor does constantly. Named
references survive all three.

Anonymous chaining still works: an action with no `=> name` produces an
anonymous state, and the next action consumes it implicitly if it declares no
inputs. **A plain linear step list is therefore valid with zero extra syntax.**

### Canonical vs. authored form

The parser accepts the readable authored forms above; the **printer** emits a
single *canonical* form that round-trips exactly (`print(parse(T)) == T`): every
ingredient and tool is brace-delimited (`@salt{}`, never bare `@salt`), state
consumption is always explicit (`@&{the dough}`), and steps are emitted in
deterministic topological order. This is what `recipe.cook` in the store holds.
Implicit linear chaining is a hand-authoring convenience on the parser's roadmap
(see `todo.md`); the canonical form does not rely on it.

### Why Cooklang cannot be the canonical format

It has no i18n and no ingredient identity — `@onion` and `@Zwiebel` can never
resolve to one entity — and its units are free-text strings. Two of snap-cook's
three pillars are structurally absent. It is an excellent authoring surface and
a poor storage model.

---

## 7. Internationalisation *(planned)*

- Ingredient names resolve through `binding.ingredient_id → Ingredient.names[lang]`
  at render time. They are **not** stored in translation files.
- Only prose — title, description, step literals, notes — is translated
  per recipe, in sibling files (`recipe.de.cook`).
- Each translated string records the `sha256` of its **source** string.
  Staleness is therefore detected per string, so fixing one typo does not
  invalidate an entire translation.
- A translation must lower to a graph with the same action ids and slot
  sequence. Translators translate text; they cannot alter the graph.
