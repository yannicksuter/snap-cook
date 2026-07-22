# Third-party data

The ingredient registry is assembled from external datasets whose licenses are
**not mutually compatible**. This file records what came from where, so that any
source can be removed cleanly and provably.

*Not legal advice.* See [`LICENSING.md`](LICENSING.md) for the wider picture.

## Sources

| Source | SPDX | Share-alike | Feeds | Default seed |
|---|---|---|---|---|
| [USDA FoodData Central](https://fdc.nal.usda.gov/) | `CC0-1.0` | No | `nutrition.*`, `count_weight.*` | **Yes** |
| [FAO/INFOODS Density DB v2.0](https://www.fao.org/infoods/infoods/tables-and-databases/faoinfoods-databases/en/) | Free download, attribution expected | No | `density_g_per_ml` | **Yes** |
| [open-tandoor-data](https://github.com/TandoorRecipes/open-tandoor-data) | `ODbL-1.0` + `DbCL-1.0` | **Yes** | `names.*`, `category`, `unit_conversion.*` | No |
| [Open Food Facts](https://world.openfoodfacts.org/data) | `ODbL-1.0` | **Yes** | `names.*`, `allergens.*` | No |
| [Wikidata](https://www.wikidata.org/) | `CC0-1.0` | No | `names.*` (translations) | Planned |

### Attribution

Required in any distribution that includes the default seed:

> Nutrient and portion data from **USDA FoodData Central**, U.S. Department of
> Agriculture, Agricultural Research Service (public domain, CC0).
>
> Density data from the **FAO/INFOODS Density Database version 2.0**, Food and
> Agriculture Organization of the United Nations.

## Why ODbL sources are excluded by default

ODbL's share-alike obligation triggers on creating a "Derivative Database". For
a hosted service that serves the data to users, the Produced Work rules are
genuinely ambiguous, and the conservative reading is that the *entire* derived
ingredient database would have to be published under ODbL.

That is an unforced risk for modest gain: USDA covers nutrition comprehensively
under CC0, and FAO/INFOODS fills the actual gap, which is densities for
volume↔mass conversion.

The capability is retained rather than removed. Setting
`SNAPCOOK_ALLOW_SHARE_ALIKE_DATA=1` permits `seed_ingredients` to load ODbL
sources — self-hosters who accept the obligation can use them, while the
project's own shipped dataset stays clean.

A CI check (`test_default_seed_has_no_share_alike_sources`) asserts every source
in `seeds/manifest.yaml` has `share_alike: false`. It exists to stop a
well-meaning pull request from quietly tainting the dataset.

## Provenance is tracked per attribute, not per row

This is the design decision that makes everything above workable.

An ingredient's density may come from FAO, its calories from USDA, and its
German name from somewhere else. Row-level provenance cannot express that, so
"remove everything from source X" becomes guesswork — and a laundered value with
no traceable origin is exactly what you cannot afford here.

```
catalog.IngredientSource
    code                  usda_fdc | fao_infoods | open_tandoor | off | manual | llm
    name, url, version, retrieved_at
    license_spdx
    share_alike           bool
    attribution_required, redistributable

catalog.IngredientAttribute          <-- the key table
    ingredient            FK
    key                   e.g. "density_g_per_ml"
    value
    source                FK
    source_ref            e.g. FDC id "171705"
    source_license_spdx   FROZEN at import -- upstream can relicense later
    import_batch          FK -> IngredientImportBatch(manifest_hash, started_at)
```

Two rules follow:

1. **Never merge values from different sources into one field.** Store each
   source's value separately and resolve at read time by a documented
   precedence (`usda_fdc > fao_infoods > open_tandoor > manual > llm`). Removing
   a source then degrades gracefully instead of leaving a value behind with no
   provenance.

2. **`source_license_spdx` is frozen at import time**, not read from the source
   record. Upstream projects do relicense, and what matters is the license the
   data carried when we took it.

## Runbook: removing a source

```bash
# 1. What would be affected?
uv run python apps/web/manage.py shell -c "
from catalog.models import IngredientAttribute
print(IngredientAttribute.objects.filter(source__code='off').count())
"

# 2. Remove it.
uv run python apps/web/manage.py shell -c "
from catalog.models import IngredientAttribute
IngredientAttribute.objects.filter(source__code='off').delete()
"

# 3. Rebuild the projection so resolved values fall back correctly.
uv run python apps/web/manage.py reindex --full --yes

# 4. Remove it from the manifest so it is not re-seeded.
#    edit seeds/manifest.yaml, then update the table above.
```

Because provenance is per attribute, step 2 is a single statement with a
provable result — you can demonstrate to a third party exactly what was removed
and that nothing derived from it remains.

## Keeping this file honest

`seeds/manifest.yaml` is the machine-readable twin of the table above, and a
test asserts the two agree. Without that check they drift apart within a couple
of months, and a licensing document that is out of date is worse than none —
it is a claim you cannot back up.
