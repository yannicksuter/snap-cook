# ADR 0005 — No ODbL seed data in the default dataset

**Status:** accepted

## Context

Unit conversion needs per-ingredient densities, and translation needs
multilingual ingredient names. The obvious sources are open-tandoor-data and
Open Food Facts — both **ODbL-1.0**, which is share-alike.

ODbL's obligation triggers on creating a "Derivative Database", and the Produced
Work rules are genuinely ambiguous for a hosted service that serves the data to
users. The conservative reading is that the entire derived ingredient database
would have to be published under ODbL.

## Decision

Ship **USDA FoodData Central** (CC0) and the **FAO/INFOODS Density Database**
(free, attribution) only. Exclude ODbL sources from the default seed.

Retain the capability behind `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA=1`, so
self-hosters who accept the obligation can opt in while the project's own
dataset stays clean.

Track provenance **per attribute, not per row** — density comes from FAO,
calories from USDA, names from elsewhere. Row-level provenance cannot express
that, which makes removing a source guesswork.

## Consequences

- Fewer ingredient translations at launch; Wikidata (CC0) is the planned filler
- Removing a source is one SQL statement with a provable result
- A CI check asserts no shipped source has `share_alike: true`
