---
name: Maintainer Release
about: Internal tracking for preparing and publishing a sfdctrust stable release
title: "[CHORE] Prepare sfdctrust <version> stable release"
labels: maintainer, chore
assignees: []
---

## Release Summary

Promote the active development version to a stable release and publish it.

- Current version (from): `X.Y.Z.devN`
- Target stable version (to): `X.Y.Z`
- Target release date: `YYYY-MM-DD`

This issue is the single tracking record for one release window. A written release
procedure does not yet exist in this repository; once one is added (for example
under `docs/maintainers/`), link it here and treat it as authoritative. Until then,
follow `AGENTS.md` and `CLAUDE.md`: no tags, pushes, releases, or uploads without
explicit maintainer approval.

---

## Motivation

Why is this release being cut now?

Examples:
- Completed feature or compatibility work is merged and ready to ship
- Security fixes need to reach users
- A planned milestone or version boundary has been reached

---

## Release Facts to Confirm

Resolve every value before starting; do not guess.

- PyPI / distribution name: `sfdctrust`
- Primary branch: `main`
- Previous reachable stable tag: `X.Y.Z`
- Target tag (bare, annotated): `X.Y.Z`
- Release branch: `chore/<this-issue>-prepare-<version>-release`
- Next development version (after release): `X.Y.(Z+1).dev0`
- Supported Python versions / dependency floors: derive from current
  `pyproject.toml` and CI, not from previous releases

---

## Change Set Since Last Stable Tag

Summarize what ships in this release (features, fixes, security, breaking
changes, dependency and Python-support changes). Link the relevant issues and
pull requests.

---

## Authorization Checkpoints

The default request authorizes only reversible local preparation. Each of the
following requires explicit, separate maintainer approval and must be checked off
here when granted:

- [ ] Stage and commit the release-preparation changes
- [ ] Push the release branch and open the preparation pull request
- [ ] Merge the preparation pull request
- [ ] Create and push the annotated release tag
- [ ] Upload distributions to TestPyPI (optional rehearsal)
- [ ] Upload distributions to production PyPI
- [ ] Publish the GitHub Release

---

## Checklist

Preparation (reversible):

- [ ] Release scope and version confirmed; target version absent from PyPI and GitHub
- [ ] Clean release branch created from current `main`
- [ ] Version promoted with `poetry version`; `poetry.lock` handled deliberately
- [ ] `docs/CHANGELOG.md` finalized (dated section, reset `Unreleased` skeleton,
      renamed MyST targets, updated comparison links)
- [ ] Other version-sensitive content reviewed for stale prerelease wording
- [ ] Full check suite passes: `poetry check`, Ruff lint + format check, pytest,
      Bandit, docs build (if configured), `git diff --check`; no live My Trust
      Center API calls were made
- [ ] Clean candidate archives built (`poetry build`); `twine check --strict` passes
- [ ] Wheel smoke-tested in clean virtual environments (metadata + public import)

Publication (each gated by the checkpoints above):

- [ ] Preparation PR merged; required CI green (if configured) on the exact `main` commit
- [ ] Artifacts rebuilt from the merged commit (candidate archives never reused)
- [ ] Annotated tag created on the verified commit and pushed
- [ ] Draft GitHub Release created with verified artifacts and `SHA256SUMS`
- [ ] Distributions uploaded to PyPI; clean-environment install verified
- [ ] GitHub Release published and marked latest
- [ ] Post-release verification complete; next `.dev0` cycle started separately

---

## Done When

- Stable version is present in every authoritative version source
- Dated changelog section and comparison links are correct; `Unreleased` is an
  empty skeleton
- Primary branch, annotated tag, GitHub Release, and PyPI all reference the same
  commit and version
- PyPI installation succeeds in a clean environment
- GitHub Release is published with verified artifacts and checksums
- Stable documentation build points at the new release
- The next development version is started in a separate pull request
