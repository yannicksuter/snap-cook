# Self-hosted LLM service

**Placeholder.** Not built. This directory exists to explain why the import
pipeline is structured the way it is.

## Why a separate service

Recipe extraction (image / PDF / URL → structured draft) currently calls a
hosted model API. The intent is to run inference locally, which means:

- **GPU-bound and slow to start.** It cannot live in the web container, whose
  restart time should stay in seconds.
- **A different scaling and failure profile.** Model loading, VRAM, batching.
- **Optional.** A self-hoster without a GPU should be able to run snap-cook
  against a hosted provider, or without import at all.

So it is a separate process behind a provider interface, not a library import.

## The interface it must satisfy

`snapcook_core.importing.contracts` — a `RecipeImporter` protocol returning a
`RawExtraction`. That boundary lands in milestone 3 and is deliberately narrow:
the LLM produces a *raw extraction*, and normalising it into a valid recipe
graph is pure Python in core, where it is testable without a model.

See [`docs/interface.md`](docs/interface.md).

## Why the boundary exists now

Defining it early is what keeps the model-specific code from leaking into the
domain. Everything downstream of `RawExtraction` is deterministic and unit
testable; everything upstream is swappable.
