# snap-cook mobile (Flutter)

**Stub.** No Dart code yet — this directory exists so the boundary it depends on
is designed now rather than retrofitted later.

## Why it is empty

Camera capture, the feature that most obviously wants a native client, works
fine in a browser today via `getUserMedia` and `<input capture>`. A PWA covers
the "snap a recipe from a book" flow, so a Flutter client is not on the critical
path.

What *is* on the critical path is making sure the architecture can accept one.
That is why `snapcook-core` has no Django dependency and why the product API is
typed and versioned from the start.

## What it will consume

`/api/v1/` — see [`docs/api-contract.md`](docs/api-contract.md) for the subset
this client depends on, and `docs/reference/api-product.md` for the full surface.

## Porting considerations

The core model is Python, so a Dart client reimplements rather than reuses it.
Two things must match **exactly**, or lineage silently forks between clients:

1. **RFC 8785 canonical JSON**, and
2. **the rule that non-integer numerics are JSON strings** — Dart's `double`
   would otherwise reintroduce the exact precision problem that rule exists to
   prevent.

`packages/snapcook-core/tests/contract/hash_vectors.json` is the conformance
suite. A Dart implementation that reproduces all 19 hashes is correct; one that
does not will corrupt version history.

Dart has SHA-256 and JSON in the standard library, so no native dependency is
needed.
