# Ingredient data provenance

See [`THIRD_PARTY_DATA.md`](../../THIRD_PARTY_DATA.md) for sources, licenses and
the strip runbook.

## Per-attribute, not per-row

The design decision that makes the licensing plane workable.

An ingredient's density may come from FAO, its calories from USDA, its German
name from somewhere else. Row-level provenance cannot express that, so "remove
everything from source X" becomes guesswork — and a laundered value with no
traceable origin is exactly what you cannot afford when the question is legal
rather than aesthetic.

```
IngredientAttribute(ingredient, key, value,
                    source, source_ref, source_license_spdx, import_batch)
```

## Two rules

1. **Never merge values from different sources into one field.** Store each
   source's value and resolve at read time by documented precedence:
   `usda_fdc > fao_infoods > open_tandoor > manual > llm`. Removing a source
   then degrades gracefully instead of leaving an untraceable value behind.

2. **`source_license_spdx` is frozen at import.** Upstream projects relicense;
   what matters is the license the data carried when we took it.

## Resolution

```python
# Highest-precedence source that has the attribute wins.
density = resolve(ingredient, "density_g_per_ml")
```

A resolved value carries its source and confidence forward into the render
model, so a converted quantity can be shown as approximate ("≈ 145 g") rather
than implying a precision the underlying data does not have.
