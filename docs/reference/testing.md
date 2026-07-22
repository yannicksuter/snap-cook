# Testing reference

## Tiers

| Tier | What | Needs | Target | Command |
|---|---|---|---|---|
| 0 | core | nothing | **< 3 s** | `./scripts/test-fast.sh` |
| 1 | Django unit | Postgres | < 30 s | `uv run pytest apps/web -q --reuse-db` |
| 2 | integration | Postgres + migrations | < 90 s | `uv run pytest apps/web -m integration` |
| 3 | LLM evals | live credentials | minutes | `uv run python evals/run.py` |

Roughly 70% of tests live in tier 0, because renderers, units, scaling, hashing
and diff are all pure. The highest-value regression net is also the fastest one.

## Markers

`golden`, `property`, `contract`, `integration`, `eval`.

## Network is blocked

Tier 0 runs with `--disable-socket`. A test that reaches the network fails with
a clear socket error rather than silently depending on connectivity.

## Golden files

```bash
./scripts/update-golden.sh    # regenerate, then READ the diff
```

CI runs goldens **without** `SNAPCOOK_UPDATE_GOLDEN`, so a stale golden fails.

> Golden files are reviewed, not regenerated. A regenerated golden with no
> explanation is indistinguishable from an unnoticed regression.

## Hash contract

`packages/snapcook-core/tests/contract/` runs as its own CI job so that a
failure reads correctly: a red `contract` check means every recipe hash in every
store just changed.

Procedure on an intentional change: bump `FORMAT_VERSION`, add a migration,
regenerate the vectors, label the change breaking.

## Property tests

Hypothesis profiles: `dev` (25 examples), `ci` (200, `derandomize=True`),
`nightly` (2000). A falsifying example gets promoted to an explicit regression
test rather than left to chance.

High-value properties and the bug each catches:

| Property | Catches |
|---|---|
| `convert(convert(q,u2),u1) ≈ q` | asymmetric conversion factors |
| `scale(scale(r,a),b) == scale(r,a*b)` | rounding applied at scale time instead of format time |
| cross-dimension convert **raises** | silent grams to ml without density |
| `scale(to_taste,k) == to_taste` | scaling applied to a non-quantity |
| `format(q)` never `"0"` for non-zero `q` | saffron at 0.5× rendering as "0 g" |
| denominators in {2,3,4,8} | "7/16 tsp" leaking into output |
| fork licence lattice transitively closed | privilege escalation through a fork chain |

## Coverage floors

Core 90%, web 75%. Two floors on purpose: core is pure logic where 90% is
meaningful, whereas Django glue at 90% mostly produces tests asserting that
Django works.
