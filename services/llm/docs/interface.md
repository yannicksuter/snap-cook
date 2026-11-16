# LLM provider interface

Any provider — hosted API, local llama.cpp, vLLM — must satisfy this contract.

## The protocol

```python
class RecipeImporter(Protocol):
    def extract(self, source: ImportSource) -> RawExtraction: ...
```

`ImportSource` is photos or a PDF, a page already fetched and read, or plain
text. The provider never fetches anything itself. Both types, and the prompt
every provider sends (`snapcook_core.importing.prompt`), live in core.

## RawExtraction

Deliberately **not** a `Recipe`. It is the model's best effort, and it may be
wrong, incomplete or internally inconsistent. The recipe in it is text in
snap-cook's Cooklang dialect, beside notes for the reviewer: questions, what
was left out, the source's name, which cup it means. Converting it into a valid recipe
graph is `snapcook_core.importing.normalize`, which is pure and fully testable
without a model.

That split is the whole point of the boundary: the non-deterministic part is
small and swappable, and everything downstream of it is ordinary code with
ordinary tests.

## Rules

1. **Never return an invalid `Recipe`.** Return a `RawExtraction` and let
   normalisation decide. A model that emits a cyclic step graph should produce a
   reviewable draft, not a 500.
2. **Preserve the source.** The original artifact is retained for
   re-extraction when the schema or the prompt improves.
3. **Always a draft.** Extraction output is never published automatically. A
   human confirms.
4. **No network access in tests.** Fixtures are captured at *this* boundary,
   not as HTTP cassettes — cassettes capture `Authorization` headers, and this
   repository is public.

## Quality measurement

`evals/` scores extraction against hand-corrected gold recipes: ingredient-set
F1, amount and unit exact-match rates, and DAG edit distance. It runs nightly,
never on pull requests, because it costs money and is non-deterministic. Its
output is a trend, not a gate.
