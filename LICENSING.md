# Licensing

Three planes, routinely conflated, tracked separately here. *Not legal advice.*

| Plane | Governs | License |
|---|---|---|
| **Code** | The software in this repository | AGPL-3.0-or-later, except `packages/snapcook-core/` which is Apache-2.0 |
| **Seed data** | The shipped ingredient registry | Per-record, per-source. See [`THIRD_PARTY_DATA.md`](THIRD_PARTY_DATA.md) |
| **User content** | Recipes users write or import | Per-recipe `license_spdx`, private by default |

---

## 1. Code

### The map

| Path | License | SPDX header |
|---|---|---|
| `packages/snapcook-core/**` | Apache-2.0 | `# SPDX-License-Identifier: Apache-2.0` |
| everything else | AGPL-3.0-or-later | `# SPDX-License-Identifier: AGPL-3.0-or-later` |

Every source file carries an SPDX header. Per-directory licensing confuses
people, and a machine-readable marker on each file removes the ambiguity.

### Why AGPL for the application

snap-cook is a self-hostable **social web application**. The value at risk is
someone running it as a hosted service with improvements and contributing
nothing back — precisely the gap AGPL closes and that MIT and Apache leave open.

[Mealie](https://github.com/mealie-recipes/mealie), the closest comparable
project, is AGPL-3.0 and has a healthy contributor base, so the "AGPL deters
contributors" concern is not borne out by the nearest real-world data point.

For a solo developer, AGPL is also the only **reversible** choice. Holding
copyright plus AGPL preserves the option to dual-license commercially later.
Releasing under MIT or Apache is a one-way door.

Tandoor's custom non-commercial license is the alternative we deliberately
avoided: it is not OSI-approved, which makes a project ineligible for many
packaging ecosystems and generates endless "is my use commercial?" questions.

### Why Apache-2.0 for `snapcook-core`

The core is Django-free *so that it can be reused* — by a Flutter client, a CLI,
third-party importers, and a future self-hosted LLM service. That reuse is only
real if the library is not copyleft. Permissive core, copyleft server is a
common and well-understood split.

Apache-2.0 rather than MIT because it carries an explicit patent grant and a
trademark clause, which matters more for a library others may build on.

### Contributions

**DCO, not a CLA.** Every commit needs `Signed-off-by:` (`git commit -s`), which
attests under the [Developer Certificate of
Origin](https://developercertificate.org/) that you have the right to submit the
work. A CLA would be required for unilateral relicensing, but CLAs are heavy for
a project this size and deter casual contributors.

`Signed-off-by:` is unrelated to the repository's rule against
`Co-Authored-By:` footers — different footer, different purpose. Do not strip
sign-offs.

---

## 2. Seed data

The ingredient registry is assembled from sources with **incompatible**
licenses. This is the plane people miss, and getting it wrong is hard to undo.

| Source | License | Share-alike? | Shipped by default |
|---|---|---|---|
| USDA FoodData Central | CC0-1.0 | No | **Yes** |
| FAO/INFOODS Density DB | Free, attribution expected | No | **Yes** |
| open-tandoor-data | ODbL-1.0 + DbCL-1.0 | **Yes** | No |
| Open Food Facts | ODbL-1.0 | **Yes** | No |

**ODbL sources are excluded from the default dataset.** ODbL's share-alike
obligation triggers on creating a "Derivative Database", and the Produced Work
rules are genuinely ambiguous for a hosted service that serves the data to
users. The conservative reading is that the entire derived ingredient database
would have to be published under ODbL. That is an unforced risk with modest
upside: USDA covers nutrition comprehensively under CC0, and FAO/INFOODS fills
the real gap, which is densities.

The *capability* is retained — set `SNAPCOOK_ALLOW_SHARE_ALIKE_DATA=1` to opt
in. Self-hosters who accept the obligation can use those sources; the project's
own shipped dataset stays clean.

Provenance is tracked **per attribute, not per row**, because density comes from
FAO while calories come from USDA and a name may come from somewhere else
entirely. Row-level provenance cannot express that, which makes removing a
source guesswork. See [`THIRD_PARTY_DATA.md`](THIRD_PARTY_DATA.md) for the model
and the strip runbook.

---

## 3. User content

Each recipe carries `license_spdx`, `source` and `visibility` **in the file**,
so they are part of the content hash. A relicense is therefore a new version
with lineage, and the full license history of any recipe is auditable.

Recipes are **private by default**. Publishing is a deliberate act that requires
choosing a license.

### Fork semantics

A fork inherits its parent's license and records immutable provenance
(`derived_from`: recipe id, version hash, license, author). Relicensing a fork is
permitted only where the parent allows it:

| Parent license | A fork may be |
|---|---|
| `CC0-1.0` | anything, including all-rights-reserved |
| `CC-BY-4.0` | `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-4.0` — attribution cannot be dropped |
| `CC-BY-SA-4.0` | `CC-BY-SA-4.0` only |
| `CC-BY-NC-4.0` | `CC-BY-NC-4.0` only |
| `all-rights-reserved` | private forks only; publishing is blocked |

This is a pure function in `snapcook_core.schema.licensing`, so it is testable
without a database. The lattice must be **transitively closed** — if C is
reachable from B and B from A, then C must be reachable from A — or a chain of
forks becomes a privilege-escalation path. A property test asserts it.

### An honest note on recipe copyright

In the US and EU, a bare list of ingredients plus functional instructions is
largely **uncopyrightable**. *Publications International v. Meredith*, 88 F.3d
473 (7th Cir. 1996) held that an ingredient list is a statement of facts with
"no expressive element", and the US Copyright Office says the same in
[Circular 33](https://www.copyright.gov/circs/circ33.pdf).

What *is* protected is the expression around the recipe: headnotes, personal
narrative, and photographs. snap-cook's structured model strips most of that by
design — parsing prose into a graph is a re-expression of fact and procedure
rather than a copy.

So the `license_spdx` field exists to respect the source's wishes and community
norms, not to assert that the underlying recipe is a protected work. Two risks
the private-by-default posture addresses anyway: **compilation copyright**, which
can attach to systematically importing an entire cookbook even where each recipe
is individually unprotected, and in the EU the **sui generis database right**
plus contractually enforceable scraping terms of service.

On import, snap-cook keeps ingredients, quantities and functional step text;
drops headnotes, narrative and images by default; and always records the source
URL for attribution.
