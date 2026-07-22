# User content licensing

See [`LICENSING.md`](../../LICENSING.md) §3 for the fork lattice. This page
covers the reasoning. *Not legal advice.*

## Recipes are largely uncopyrightable

Worth stating plainly, because it makes the fork feature look reasonable rather
than reckless.

In the US, *Publications International v. Meredith*, 88 F.3d 473 (7th Cir. 1996)
held that an ingredient list is a statement of facts with "no expressive
element". The US Copyright Office says the same in
[Circular 33](https://www.copyright.gov/circs/circ33.pdf): "a mere listing of
ingredients or contents, or a simple set of directions, is uncopyrightable."

What **is** protected: headnotes, personal narrative, "tales of historical or
ethnic origin", serving suggestions, and unambiguously **photographs**.

In the EU, *Levola Hengelo* (CJEU C-310/17) held that the taste of a food
product is not a copyright work, and analogous reasoning supports
non-protection of the functional recipe.

## What this means for snap-cook

The structured model strips protected expression **by design**. Parsing prose
into a graph is a re-expression of fact and procedure, not a copy — a materially
stronger position than storing verbatim text.

So the `license_spdx` field exists to respect the source's wishes and community
norms, not to assert that the underlying recipe is a protected work.

## Residual risks the private default addresses

- **Compilation copyright.** A cookbook as a whole has a thin copyright over
  selection and arrangement. Systematically importing an *entire* book is
  riskier than importing one recipe, even where each recipe is individually
  unprotected.
- **EU sui generis database right.** Protects substantial investment in a
  collection even without originality — a large recipe site's database may
  qualify.
- **Terms of service.** Contractually enforceable independently of copyright.

Hence: imports land private, attribution is always recorded, headnotes and
images are dropped, and bulk ingestion is not a supported workflow.
