# CLAUDE.md

**Read [`AGENTS.md`](AGENTS.md) first — it is the source of truth for this
repository.** Everything about architecture, load-bearing rules, commands and
conventions lives there. This file holds only what is specific to Claude Code.

A pointer rather than a copy, deliberately: duplicated instructions drift, and
the drift is silent. A symlink was considered and rejected — GitHub renders a
symlinked Markdown file as its target path rather than its content, so the web
view of this file would show the literal text `AGENTS.md`.

## Commits

Repeated here because it is the highest-consequence rule and Claude's default
behaviour contradicts it:

> Use [Conventional Commits](https://www.conventionalcommits.org/), and
> **never add a `Co-Authored-By` footer.** The commit author is whoever ran the
> tooling; an assistant trailer makes `git shortlog` meaningless.

`Signed-off-by:` (DCO) is separate and **is** required — `git commit -s`.

## Fast feedback

```bash
./scripts/test-fast.sh      # tier 0, < 3s, no Django and no database
```

Prefer this while iterating. It covers the schema, canonical encoding, hashing,
units and renderers — roughly 70% of the test suite — because
`packages/snapcook-core` has no framework dependency. Reach for the Django tiers
only when the change actually touches `apps/web`.

## Permissions

`.claude/settings.json` carries a Bash allowlist for the commands used routinely
here (`uv`, `pytest`, `ruff`, `docker compose`, `manage.py`, `git`). Extend it
rather than approving the same command repeatedly.

## Things worth knowing before making changes

- `packages/snapcook-core` must never import Django. A test enforces it.
- Changing `canonical/` changes every recipe hash that has ever been written.
  Read the warning in `canonical/hashing.py` before touching it.
- Golden files under `tests/golden/` are reviewed, not regenerated. If a change
  updates them, explain each one in the PR body.
