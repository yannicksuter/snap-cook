# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Three version planes are tracked independently — see `AGENTS.md`:

| Plane | Where | Meaning |
|---|---|---|
| Release | git tags, image tag | SemVer of the deployable |
| Library | `snapcook_core.LIB_VERSION` | SemVer of the core package |
| **Format** | `snapcook_core.FORMAT_VERSION` | The on-disk / hash contract |

A `FORMAT_VERSION` bump is the most expensive change this project can make: it
invalidates stored content hashes. Any release containing one is a **breaking
change** and says so explicitly here.

## [Unreleased]

### Added — Milestone 1, the vertical slice

The thesis test: one recipe, rendered three ways, in two languages and two unit
systems. `FORMAT_VERSION` stays at `1` — this milestone adds schema *breadth*
under the existing canonical form, not a new wire contract.

- **Schema**: the recipe graph (`FoodState`, `Action`, prose `TextTemplate`
  chunks incl. `@&{}` state consumption), quantities
  (`Scalar | Range | Count | Approx` with scaling policy), ingredients, cookware,
  localised text with per-string staleness, provenance. Graph invariants
  (acyclic, single-writer outputs, no dangling refs) are enforced at
  construction, so an invalid graph is unhashable.
- **Units**: a Pint registry with `non_int_type=Decimal` and locale-qualified
  cups; density-aware volume↔mass conversion that **raises rather than guessing**;
  exact scaling separated from display rounding (fraction ladders, metric bands).
- **Rendering**: one `RenderModel`, three pure renderers (text, Mermaid, print);
  deterministic Kahn toposort; golden files for the declared matrix.
- **Store**: content-addressed, git-shaped version store (memory + filesystem)
  with the no-op commit rule and `recipe.json` / `recipe.cook` / `README.md`
  projections of HEAD.
- **Authoring**: a Cooklang-flavoured parser and printer, gated on round-trip
  idempotence (`print(parse(T)) == T`).
- **Corpus**: six recipes, `001-boiled-egg` … `006-roesti`, from a degenerate
  linear list up to a branching bilingual graph.
- **Web**: `reindex` now projects the store into `catalog` (byte-identical
  rebuild, asserted by a test); a `seed_corpus` command; a recipe detail view
  with HTMX language / unit / scale toggles and an inline flowchart.

### Added — Milestone 0, the skeleton
- Repository skeleton: uv workspace, Ruff, tiered pytest configuration
- `snapcook-core`: canonical encoding and content/version hashing
  (`FORMAT_VERSION = 1`), prefixed ULID identifiers, error tree
- 19 frozen cross-language hash vectors, run as their own `contract` CI job
- AST-enforced rule that `snapcook-core` never imports Django
- Django project: flat settings, Google SSO via allauth, `LoginRequiredMiddleware`,
  `/up` health probe, build-commit footer
- `catalog` projection with `visible_recipes()` as the single authorization
  funnel, and a `reindex` command
- Per-user Personal Access Tokens for the product API
- Two feature-flagged API surfaces: `/api/v1/` and `/ops/api/`, with boot-time
  refusal on a weak ops token
- Docker: one image, `web` and `worker` roles; compose with Postgres
- Documentation: README, AGENTS, CLAUDE, CONTRIBUTING, LICENSING,
  THIRD_PARTY_DATA, SECURITY, RECIPE_SPEC

[Unreleased]: https://github.com/yannicksuter/snap-cook/commits/main
