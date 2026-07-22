## What and why

<!-- What changed, and what problem it solves. -->

## Checklist

- [ ] `./scripts/test.sh` passes locally
- [ ] Commits use Conventional Commits and are signed off (`git commit -s`)
- [ ] No `Co-Authored-By` footer (see AGENTS.md)

### If golden files changed

- [ ] I read the golden diff **line by line** and can explain every change

<!-- Explain each one here. A regenerated golden with no explanation is
     indistinguishable from an unnoticed rendering regression. -->

### If the hash contract changed

A `contract` job failure means every recipe hash in every store changed.

- [ ] This was intentional
- [ ] `FORMAT_VERSION` bumped
- [ ] Migration added under `snapcook_core/migrate/`
- [ ] `CHANGELOG.md` marks this a breaking change

### If the schema changed

- [ ] `RECIPE_SPEC.md` updated in this same change set

### If an API endpoint was added

- [ ] It declares its auth explicitly (`/api/` and `/ops/api/` get **no**
      protection from `LoginRequiredMiddleware`)
- [ ] Product endpoints start from `catalog.access.visible_recipes(user)`
