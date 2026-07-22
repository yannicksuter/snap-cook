# snapcook-core

The structured recipe domain model: schema, content-addressed version store,
unit system, and renderers.

**This package never imports Django.** It is the shared brain for the snap-cook
web application, a future Flutter client, a CLI, and a self-hosted LLM service.
A test (`tests/test_no_django.py`) enforces the rule with an AST walk over every
module, because it is the kind of constraint that erodes silently if left to
discipline alone.

Licensed **Apache-2.0**, deliberately more permissive than the AGPL-3.0 web
application in the same repository — see [`LICENSING.md`](../../LICENSING.md).
A Django-free core is only genuinely reusable if it is not copyleft.

## The model in one paragraph

A recipe is a **directed acyclic graph**. Nodes are *food-states* — named,
referenceable things like "the dough" or "the roux". Edges are *actions*
carrying a verb, duration, temperature and tools. Tools and durations are
attributes of an action, not nodes in their own right.

A classic ordered step list is a **topological sort** of that graph, and a
flowchart is a direct drawing of it. Both fall out of one model rather than
being two implementations that drift apart. A linear recipe is simply a
degenerate DAG.

## Identity

Recipes are content-addressed. Two rules matter more than the rest:

1. **We hash the validated data structure, not the file bytes.** Reformatting a
   file, reordering keys, or writing `@onion{}` instead of `@onion` produces
   *no new version*. Identity is meaning, not layout.
2. **Non-integer numerics serialise as JSON strings.** RFC 8785 serialises JSON
   numbers as ECMAScript doubles, so encoding a `Decimal` as a number would make
   Python and Dart compute *different hashes for the same recipe*. `float` is
   banned from every schema field and rejected at encode time.

See [`canonical/encode.py`](src/snapcook_core/canonical/encode.py) for the full
rule set, each with its reason.

## Layout

| Module | Responsibility |
|---|---|
| `schema/` | Pydantic models: recipe, graph, quantity, ingredient, units, i18n |
| `canonical/` | Model → canonical JSON → hash. The frozen wire contract. |
| `cooklang/` | Parse `.cook` text → AST → lower to `Recipe`; and print back |
| `store/` | Content-addressed object store, refs, lineage |
| `units/` | Pint registry, per-ingredient density, scaling, fraction rounding |
| `render/` | `Recipe` → `RenderModel` → text / Mermaid / print |
| `diff/` | Structural diff over the graph, not over text |
| `migrate/` | Pure dict→dict format migrations |
| `testing/` | Corpus loader and golden-file helper, shipped for reuse |

## Usage

```python
from snapcook_core.canonical import content_hash, canonical_bytes

h = content_hash(recipe)          # "sc1:9f2a…"
raw = canonical_bytes(recipe)     # the exact bytes that were hashed
```

The bytes a client verifies are the bytes we hashed — there is no
re-serialisation in between that could introduce a discrepancy.

## Development

```bash
uv sync                                    # from the repository root
uv run pytest packages/snapcook-core       # tier 0: no Django, no database, < 3s
```
