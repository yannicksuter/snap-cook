# Extraction evals

Measures how well the import pipeline turns real sources into correct recipes.

**This is not a test suite.** It costs money, it is non-deterministic, and it
never runs in pull-request CI. It runs nightly and on manual dispatch, and its
output is a *trend* — a regression here is a signal to investigate, not a broken
build.

## Layout

```
evals/cases/<id>/
├── source.pdf | source.jpg | source.url | source.txt
└── gold.yaml          # hand-corrected, the ground truth
```

`source.txt` cases should include full webpage selections with realistic noise,
not only pre-cleaned recipe text.

## Running

```bash
SNAPCOOK_LLM_API_KEY=... uv run python evals/run.py
```

## Metrics

| Metric | Measures |
|---|---|
| Ingredient set F1 | Did it find the right ingredients? |
| Amount exact-match | Did it get the quantities right? |
| Unit exact-match | Did it get the units right? |
| Step count delta | Did it over- or under-segment the method? |
| **DAG edit distance** | Did it get the *structure* right? |

The last one is the interesting one, and the reason this harness exists at all.
Extracting a flat ingredient list is a solved problem. Recovering the dependency
structure — which step consumes the output of which — is the part that is
actually hard, and it is what snap-cook needs.
