# Runbook: releases

The image `ghcr.io/yannicksuter/snap-cook` is published by CI
(`.github/workflows/ci.yml`), never by hand, and only from the `stable` branch.

1. **Develop on `main`.** Every push and pull request runs the checks, then
   builds the image and runs it as Unraid does, with no route to the internet
   (`scripts/test-container.py`). Nothing is published.
2. **A release is a pull request from `main` into `stable`.** It also
   publishes the test image `test-pr<N>`, and `test-pr<N>-<commit>` for each
   commit, to try on a server before merging. `test` always points to the
   newest of them, so a test container with the repository
   `ghcr.io/yannicksuter/snap-cook:test` follows every release pull request.
   The test images are removed when the pull request closes
   (`test-images.yml`).
3. **Merging publishes the release.** CI pushes `sha-<full-commit>`, tags it
   `v<version>`, `stable` and `latest`, and publishes the GitHub release
   `v<version>`. Its title is always `v<version> – <pull request title>`, and
   its notes are the pull request's description, so write both as release
   notes: a short title without the version (CI adds it), and a short
   description. Unraid's auto-update then deploys it.
4. **Rollback:** use an earlier `v<version>` or `sha-<full-commit>` as the
   repository tag ([install.md](../install.md#updates)). A release published by
   hand, such as an older draft, tags its image the same way (`release.yml`).

## Before the release pull request

The version is the one in `apps/web/pyproject.toml`, the deployable's SemVer
(see the version planes in `CHANGELOG.md`). A version that is already released
or drafted is not released again: the merge still publishes `sha-<commit>`, but
`stable` does not move.

```bash
# 1. Raise the version in apps/web/pyproject.toml, then refresh the lock file.
uv lock
# 2. Move CHANGELOG.md's [Unreleased] entries under the new version.
# 3. Open the pull request from main into stable.
```

A release containing a `FORMAT_VERSION` bump is a breaking change; say so in
the title.

## Checking an image locally

What CI runs, against an image built from your checkout:

```bash
docker build -t snap-cook:test --build-arg GIT_COMMIT="$(git rev-parse HEAD)" .
python3 scripts/test-container.py snap-cook:test "$(git rev-parse HEAD)"
```

## One-time setup

- Create the branch: `git push origin main:stable`. CI treats that push like a
  merged release: it publishes the version in `apps/web/pyproject.toml`, with
  generated notes since no release pull request exists yet. `main` stays the
  default branch, so Dependabot's pull requests keep going there.
- Protect `stable` (**Settings → Branches**): require a pull request, and the
  checks `lint`, `core`, `contract`, `web`, `security` and `image`.
- After the first image is published, open the [package
  settings](https://github.com/users/yannicksuter/packages/container/snap-cook/settings):
  - **Danger Zone → Change visibility → Public**, if it is not already, so
    Unraid pulls without credentials.
  - **Manage Actions access**: give `snap-cook` the role **Admin** (add the
    repository if it is not listed), so `test-images.yml` may delete test
    images.
