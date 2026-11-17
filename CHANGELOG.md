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

### Added

- A recipe shown in another language is translated as a whole: its name,
  description, steps and notes, and the ingredient names and units the
  ingredient registry does not know. The first time, the worker translates it
  (usually under a minute) and the page updates by itself; after that it opens
  translated. Editing a step makes only that step's translation stale.
- A temperature keeps the oven setting it is for. A recipe that gives 175 °C top
  and bottom heat and 155 °C fan shows both, labelled in the reader's language
  ("Ober-/Unterhitze", "Umluft"), in the step and on its chips. The importer
  writes it as `^fan{155%C}`.
- Every recipe ends with its chart, "At a glance": numbered steps with their
  times and oven settings, the ingredients with their amounts flowing in, and
  the finished dish last. It opens full screen, where it pans and zooms, and
  prints on a page of its own.
- The ops API can show every import, to check the importer against its sources:
  the uploaded file itself, the model's reading as it came back, the draft as
  checked, what it left out, and the recipe as stored now
  (`/ops/api/imports`, `/ops/api/recipes/{slug}`).

### Changed

- The ops API answers only the LAN or a VPN. It refuses any request that came
  through a tunnel or reverse proxy, or from a public address, even with the
  token, so it can be switched on where the site runs through Cloudflare.

- The "More" section is gone. Language and units come from your settings;
  a recipe in another language is translated for you. The plain-text view is
  gone too.
- The chart no longer shows English placeholders ("combine", "step 2") in a
  recipe without verbs, which is every imported one.

### Fixed

- A word written in front of a temperature, such as `^Umluft{155%C}`, was
  silently dropped. A word that names no oven setting now stays in the text.

### Notes

- A recipe that has an oven setting, or has been translated, cannot be opened by
  0.4.0 or older. Rolling back past this release needs the `/data` backup from
  before it.

## [0.4.0] - 2026-11-17

### Added

- On a computer, "Add a recipe" reads whatever you paste with Ctrl+V (⌘V on a
  Mac): a whole web page or PDF copied with Ctrl+A and Ctrl+C, a link, or a
  copied image. A PDF or a photo can also be dropped onto the page.

### Changed

- A PDF can be up to 32 MB, so a web page printed to PDF fits. Photos stay at
  7 MB each, and all files together can be at most 50 MB.
- Pasted text can be up to 200,000 characters, enough for a page with its
  comments. A longer paste gets a message saying to copy only the recipe,
  instead of a technical error.

## [0.3.0] - 2026-11-16

### Changed

- The image runs as one container by default: the site, the worker and,
  without `POSTGRES_HOST`, its own PostgreSQL 17, with its data in
  `/data/postgres` and reachable only through a socket. Unraid needs one
  container and one folder (`docs/install.md`). The image without arguments
  now starts as `all`, not `web`; Compose keeps the separate database and
  names `web` and `worker` explicitly.
- The image is based on Debian 13 (trixie) by name, which fixes the Postgres
  major version.

## [0.2.0] - 2026-11-16

### Added — adding a recipe from a photo, a link or text

- "Add a recipe" takes a photo of a cookbook page, photos or a PDF, a link or
  pasted text. The worker reads it with Claude (`SNAPCOOK_LLM_API_KEY`) and
  keeps only the recipe; the reader answers open questions, checks the draft
  and saves it, private. Drafts wait on Home.
- Links are fetched from the public internet only, never from the server's own
  network.

### Added — reading pages for the phone, in English and German

- The recipe list and the recipe page are rebuilt for reading on a phone: dark
  text on white, 18 px and larger type in Atkinson Hyperlegible Next, amounts
  before ingredient names, and a servings stepper in place of `½× 1× 2× 3×`.
  Hints say which steps build on earlier ones and which can be done side by
  side, from the new `RenderedStep.after` and `RenderModel.side_by_side` in
  core.
- The recipe list has a search for words in titles and descriptions.
- The interface speaks English and German. A settings page (`/settings/`)
  stores language and units once per person; without saved settings the
  browser's language applies, and recipes open in the same language.

### Changed

- GitHub releases are titled `v<version> – <pull request title>`, also
  when published by hand.

### Fixed

- Product API tokens whose secret contains `_`, about half of all tokens
  issued, were rejected: the token was split at every `_`.

## [0.1.0] - 2026-11-16

### Added — the published image

- CI publishes the image as `ghcr.io/yannicksuter/snap-cook` for Unraid and
  Docker Compose: release pull requests into `stable` publish test images, and
  merging tags `v<version>`, `stable` and `latest` and publishes the GitHub
  release (`docs/runbooks/release.md`). `docs/install.md` covers installing.
- `scripts/test-container.py`, run by the new `image` check: Postgres, `web`
  and `worker` on a network with no route out, covering migrations, `/up`,
  static files, the worker cluster, the shared store and clean shutdown.
- The image has a `HEALTHCHECK`, runs `docker exec … python manage.py` from the
  app directory, runs a command given in place of a role (`docker compose run
  --rm web python manage.py migrate`), and defaults to `DJANGO_DEBUG=0`.

### Fixed

- The image no longer needs the internet to start. `uv run` re-synced the
  environment on every start and fetched hatchling from PyPI; the image now
  runs its virtualenv directly, and no longer ships the dev dependencies.

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

[Unreleased]: https://github.com/yannicksuter/snap-cook/compare/v0.4.0...main
[0.4.0]: https://github.com/yannicksuter/snap-cook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/yannicksuter/snap-cook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/yannicksuter/snap-cook/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yannicksuter/snap-cook/releases/tag/v0.1.0
