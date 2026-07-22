# The version store

Git-*shaped*, not git. Immutable content-addressed versions with parent
pointers, forming a lineage DAG.

## Why not real git

Git's three-way merge is line-based and textual. For a structured recipe you
want field-level semantic merge — "they changed cream to coconut milk, you
changed 200 g to 250 g, both apply" — not conflict markers inside a YAML file.

Git also forces an awkward repo-per-recipe or repo-per-user choice, and shelling
out to it at request latency is slow.

So: our own store, with a directory layout that a plain `git init` followed by a
remote push accepts as an **export and mirror**. You get GitHub hosting and
portability without putting git in the request path.

## Layout

See `RECIPE_SPEC.md` §5. `.snapcook/versions/**` is committed, so a clone is a
complete replica of the lineage DAG.

## Two hashes

| Hash | Covers | Purpose |
|---|---|---|
| `content_hash` | recipe content | the no-op rule |
| `version_id` | content + author + time + parents | commit identity |

**The no-op rule:** `commit()` returns the existing HEAD unchanged if the
content hash matches. Reformatting produces no version. This is a store-level
invariant, not a UI nicety — it is what stops whitespace churn from forking
lineage.

## Versions are stored whole

Not as deltas. A recipe is a few kilobytes; a thousand versions is a few
megabytes. Delta compression is git's job on export, and full snapshots make
reads O(1) with no chain walk — which matters precisely because git is not in
the request path.

## Forking

A fork mints a new recipe id and records `forked_from` (recipe id, version hash,
license, author). Cross-recipe lineage is tracked separately from a recipe's own
version DAG, so a public recipe never leaks the existence of its private forks.

Forks always start **private**, and license inheritance follows the lattice in
`LICENSING.md`.
