# Validate CI and prepare publishing

This runbook implements the repository preparation for
[issue #11](https://github.com/jeffshurtliff/sfdctrust/issues/11).
Implementation and local checks do not complete its acceptance gate: an explicitly
approved TestPyPI rehearsal, hosted CI, and hosted documentation evidence remain
necessary. Production release execution requires separate authorization.

See {doc}`ci-publishing-evidence` for the recorded local source, results, artifact
hashes, reproduction commands and outstanding hosted/rehearsal evidence.

## Boundaries and existing qualification

Keep the development version `1.0.0.dev0` and Python `>=3.12` until the maintainer
approves a version change. Classifiers currently advertise 3.12–3.15.
`tools/ci/matrix.py` derives Linux tests for each advertised minor plus macOS and
Windows on the minimum minor. Native SQLite permission and spawned-process tests,
installed-wheel checks, Bandit, compatibility inventories, and downstream typing
remain in CI. Platform skips remain explicit.

Reuse [#10's accepted compatibility and exact-source hosted evidence](https://github.com/jeffshurtliff/sfdctrust/issues/10#issuecomment-6856289949)
and [#9's completed operator recovery evidence](https://github.com/jeffshurtliff/sfdctrust/issues/9#issuecomment-6810823647).
Existing regression tests and recurring CI checks remain; this task does not
independently rerun the dedicated recovery gate. Exact-release live-service
qualification remains with [#8](https://github.com/jeffshurtliff/sfdctrust/issues/8).
No Salesforce requests or real credentials belong in ordinary CI or release validation.

## CI, required checks, and hosted documentation

`SDK validation` has unfiltered `push` and `pull_request` triggers, manual and
reusable-workflow entry points, and a weekly Monday advisory scan at 09:23 UTC.
The weekly trigger runs the complete validation workflow. Thus code, dependency,
docs-only, contributor-guide, workflow, and `.readthedocs.yaml` changes all run
strict Sphinx and the audit. There are no path filters that can leave a required
check pending. Existing test/quality/compatibility job names are retained, with
new policy/audit jobs and tests for the previously missing Python minors.

Fork PRs use `pull_request`, read-only `contents` permission, no secrets or OIDC,
and checkout credentials are not persisted. GitHub may require a maintainer to
approve a first-time contributor's workflow execution. Never replace this with
`pull_request_target` execution of PR code.

On 2026-11-13, read-only GitHub inspection reported **main not protected**, no
repository rulesets, and no environments. No settings were changed. Before
configuring required checks, obtain a successful hosted run of this source and
select the actual emitted check names, including all six matrix rows, quality,
compatibility, policy, and audit. Do not require release upload jobs on PRs.

Both CI and `.readthedocs.yaml` use Poetry 2.5.1, `poetry check --lock --strict`,
and dependencies from `poetry.lock`. Read the Docs installs `main,docs` into
`READTHEDOCS_VIRTUALENV_PATH`; CI adds development tooling. Sphinx remains
nitpicky with warnings fatal; CI uses `-W --keep-going -E -a`. Inventory download
failures are failures, not permission to disable intersphinx or suppress warnings.
The docs need access to `docs.python.org` during the standard strict build.

After the maintainer authorizes pushing the reviewed source, confirm the Read
the Docs build detail identifies that exact SHA and succeeded. Verify the
rehearsal branch/PR documentation after enabling its build only with approval.
Record build URL/ID, SHA, installed lockfile/tool versions, strict command and
result, plus the rendered version and maintainer page. A reachable older
`latest` site alone is not validation of these changes.

## Dependency vulnerability auditing

`pip-audit` is locked development tooling, restricted to Python 3.12 tooling jobs;
it does not constrain SDK consumers. Run the online advisory step separately:

```sh
poetry run python tools/ci/audit.py --output /tmp/sfdctrust-audit.json
```

The scan takes the **union of every Poetry `main`-group package and version**,
including transitive dependencies. It retains Python requirements and markers in
evidence but deliberately removes marker exclusions from advisory requests. This
conservative superset covers all supported Python/platform/architecture variants,
even variants inactive on the audit runner. Separate batches handle alternative
versions of the same package. Development/docs-only packages are outside this
runtime audit. A future non-PyPI runtime dependency fails until its audit strategy
is reviewed. Keep the lockfile in sync before auditing.

The CLI uses exact pins, `--no-deps --disable-pip`, never installs the packages,
does not resolve current ranges, and does not autofix. Lockfile hashes authenticate
retrieved dependencies during Poetry installation; the audit itself queries advisory
metadata by name/version, without downloading runtime artifacts. Exit codes are
0 for a complete passed scan (including documented exceptions), 1 for actionable
findings, and 2 for tool/service/configuration errors. Reports contain IDs,
aliases, fix versions, complete dependency scope, tool version, lock digest and UTC date.
CI retains audit disposition even on failure.

`test_real_pip_audit_cli_reports_controlled_vulnerable_fixture_without_network`
feeds the real tool a synthetic PyPI response for `requests==2.31.0` and
`CVE-2024-35195`, checks failing status plus upgrade to `2.32.0`, and blocks
socket/DNS use. The vulnerable package is never installed. Additional tests cover
alternative locked variants, incomplete responses, service errors and exception expiry.

For a finding, review the advisory, affected behavior, fixed versions and compatibility
impact. Prefer a focused Poetry update, inspect the lock diff, rerun the audit and
offline checks, and document disposition in the issue/PR. Advisory outages, timeout,
HTTP errors, skipped packages, malformed/incomplete reports, and unexpected exit
statuses fail closed. Retry an identified transient outage with the same lock;
retain the failed report and do not reinterpret it as a passed scan.

`tools/ci/audit-exceptions.json` starts empty. A maintainer-approved exception is
specific to one normalized name, exact locked version, and advisory ID or alias:

```json
{
  "exceptions": [{
    "name": "example-package",
    "version": "1.2.3",
    "id": "CVE-YYYY-NNNNN",
    "rationale": "Explain reachability, mitigations, and planned upgrade",
    "issue": "https://github.com/jeffshurtliff/sfdctrust/issues/NUMBER",
    "approved_by": "Maintainer review reference",
    "expires": "YYYY-MM-DD"
  }]
}
```

Expiry must be current and at most 90 days away. Expired/malformed exceptions fail
even if the advisory disappears. Evidence retains accepted findings and rationale;
exceptions cannot waive service failures, other versions, or other advisories.

## Exact artifacts and offline clean installations

Use a fresh scratch directory. These commands preserve the package version:

```sh
git branch --show-current
git rev-parse HEAD
git status --short --branch
poetry check --lock --strict
poetry run python tests/offline/run.py -m pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry build --output /tmp/sfdctrust-issue11-build/dist
poetry run twine check --strict /tmp/sfdctrust-issue11-build/dist/*
poetry run python tools/ci/artifacts.py inspect \
  --dist /tmp/sfdctrust-issue11-build/dist \
  --manifest /tmp/sfdctrust-issue11-build/evidence/release-manifest.json
# Network-enabled retrieval, constrained to active locked runtime versions:
poetry run python tools/ci/qualify.py prepare \
  --dist /tmp/sfdctrust-issue11-build/dist \
  --wheelhouse /tmp/sfdctrust-issue11-build/wheels \
  --work /tmp/sfdctrust-issue11-build/evidence/installs
# No dependency retrieval or Salesforce calls during behavioral qualification:
poetry run python tools/ci/qualify.py qualify \
  --dist /tmp/sfdctrust-issue11-build/dist \
  --wheelhouse /tmp/sfdctrust-issue11-build/wheels \
  --work /tmp/sfdctrust-issue11-build/evidence/installs
poetry run python tools/ci/artifacts.py transfer \
  --dist /tmp/sfdctrust-issue11-build/dist \
  --manifest /tmp/sfdctrust-issue11-build/evidence/release-manifest.json
```

The inspector requires exactly one wheel and one sdist. It validates version,
Python policy/classifiers, runtime requirements, MIT license expression and file,
`py.typed`, and package/source byte equality. Explicit payload allowlists exclude
local files, credential filenames, caches and unexpected files; archives reject
unsafe paths, duplicates, and sdist links. This is packaging validation, not a
replacement for source review or secret scanning.

Each artifact is installed separately into a fresh venv, non-editably, with
`--no-index`, lock constraints and (for sdist) `--no-build-isolation` plus the
locked Poetry backend. `pip check`, installed CLI/SQLite smoke, #10's public
inventory and offline behavior, and strict downstream mypy run for each install.
The sdist-built package is compared against the original wheel's package bytes.
The behavioral guard blocks outbound connections/DNS in Python parent/children,
allowing local IPC. Existing compatibility checks add their stronger socket guard.
Dependency retrieval, advisory queries, inventory retrieval and registry
verification are explicitly separate network-enabled phases.

## Protected publishing setup (requires approval)

The committed workflow alone cannot establish protected environments or publisher
bindings. Obtain explicit authorization before any of these external changes:

| Destination | GitHub environment | Allowed deployment ref | Publisher workflow | Registry |
| --- | --- | --- | --- | --- |
| Rehearsal | `testpypi` | branch `release/testpypi` only | `release.yml` | `test.pypi.org` |
| Production | `pypi` | approved stable version tags only | `release.yml` | `pypi.org` |

`release/testpypi` is a reusable, agent-neutral maintenance branch. Its name
describes the destination and stays independent of issue numbers, versions, and
the person or tool preparing the rehearsal. Use it for future rehearsals as well
as the initial issue #11 qualification. For each rehearsal, prepare it from the
newly approved source, obtain approval for a unique prerelease version, and record
the exact immutable source SHA and artifact manifest. Reusing the name does not
reuse a previous approval or authorize branch creation, updates, or uploads.

Validation-only dispatches (`destination=validate`) accept `main` or
`release/testpypi`. TestPyPI dispatches require `release/testpypi`; the workflow,
source validator, and environment deployment restriction must all use that exact
name. Changing it later requires updating all three together, including tests and
runbooks; environment changes still require explicit authorization.

Create the environments **before any upload dispatch**. Require maintainer
reviewers, prevent self-review and administrator bypass where the repository plan
supports it, and configure the deployment ref restrictions above. If the plan
cannot enforce those protections, stop and obtain an approved alternative.
The YAML environment name alone is not an approval barrier: GitHub can create an
unprotected environment on first use.

Before a production approval, review #8's live qualification for the exact candidate
wheel, the accepted #9/#10 evidence, and #11's approved rehearsal evidence. The
offline workflow does not perform or certify that separate live-service gate.

Register a GitHub Trusted Publisher separately on each registry for owner
`jeffshurtliff`, repository `sfdctrust`, workflow filename `release.yml`, and that
destination's exact environment name. TestPyPI accounts/projects/pending publishers
are separate from PyPI. Never register a broad publisher without the environment.
Do not add upload tokens or `PYPI_API_TOKEN` secrets. Review the public immutable
transparency-log notice before enabling attestation publication.

The manual release workflow has `upload=false` and `destination=validate` defaults.
Validation/build jobs have read-only contents permission. Only the two fixed
publishing jobs have `id-token: write`. They download the same-run immutable
artifact ID, recheck the complete file set, source SHA/version and SHA-256/size,
then pass exactly `bundle/dist/` to the official PyPA publishing action. They do
not check out source, install dependencies, or rebuild. The action is pinned to
the official commit inspected during implementation; review and update its pin
deliberately. Per-file attestations are explicitly enabled.

For production, the selected workflow ref must be the stable version tag with no
`v` prefix (the repository's existing tag convention). The tag must resolve to
the exact approved full SHA, metadata must match, and that commit must be an
ancestor of `origin/main`. Prerelease, development, local and post versions are
rejected for production. TestPyPI accepts a canonical alpha/beta/rc version only
from the dedicated rehearsal branch. A rehearsal cannot select a production URL.

## Concrete TestPyPI rehearsal proposal (not authorized)

This proposal is for issue #11's initial qualification. Future rehearsals use the
same `release/testpypi` branch with their own newly approved source, version and
artifact manifest; the example version and commit below are not reusable defaults.

Proposed unique version: **`1.0.0rc2026111301`**. Recheck TestPyPI immediately before
approval because availability can change. This proposal does not edit the current
version or create a tag.

Proposed source: the maintainer-reviewed issue #11 changes based on
`a8be4ed79444450ac8986a96f1a60931f9da2237`, followed by a dedicated rehearsal commit
on `release/testpypi` changing only `[project].version` to that prerelease.
No runtime source, support policy or lock resolution changes are proposed for the
rehearsal. Version is read from installed metadata, so no hard-coded SDK version
file needs editing. Keep main's development version unchanged. Record the actual
reviewed immutable commit SHA before dispatch; an uncommitted tree is not eligible.

Before executing dependent actions, obtain approval for all of:

1. The reviewed implementation source/diff and exact resulting rehearsal SHA,
   the proposed version and rehearsal branch creation/push. Commit/push permission
   has not been granted as part of this task.
2. Creation/protection of `testpypi` and its exact TestPyPI publisher binding;
   any required Read the Docs branch/PR build setup. Production setup is optional
   future preparation and requires its own permission.
3. A dry validation dispatch and the eventual `upload=true` TestPyPI dispatch,
   after reviewing the dry run's artifact hashes and evidence.

Once approved and the workflow is available on the default branch, first dispatch
with `destination=testpypi`, `upload=false`, exact source SHA and version. Inspect
all gates and the `approved-release` artifact's manifest and checksums. For upload,
dispatch the same immutable source with `upload=true`; this new run builds and
validates once and its protected upload job publishes **that run's** checked bytes.
Review that run's manifest before environment approval. It does not implicitly
reuse the dry run's artifacts. If source or bytes differ unexpectedly, withhold
approval and investigate. Never approve an upload using only a previous run's hashes.

After approval, the `verify-registry` job obtains the destination's release JSON,
compares both hosted file names, sizes and SHA-256 digests, downloads those exact
files, and obtains per-file Integrity API provenance. Locked `pypi-attestations`
verifies signatures, transparency proofs and distribution identity; additional
checks constrain publisher repository/workflow/environment and signed certificate
claims for source SHA/ref, workflow URI, manual trigger and run ID. It requires a
publish attestation for each file. TestPyPI uses its own Integrity API, with the
normal production Sigstore trust roots; `--staging` is not a TestPyPI switch.
Hosted files then receive separate clean wheel/sdist offline installs and checks.
Retain raw release JSON, provenance, verified claims, digests and install evidence.

Manual reproduction after an authorized upload:

```sh
# Download the approved-release artifact from that exact run into a fresh directory.
gh run download RUN_ID --repo jeffshurtliff/sfdctrust \
  --name approved-release --dir /tmp/sfdctrust-rehearsal-hosted
poetry run python tools/ci/registry.py --destination testpypi \
  --bundle /tmp/sfdctrust-rehearsal-hosted \
  --ref refs/heads/release/testpypi --run-id RUN_ID
```

Record source SHA, version, workflow run/attempt, environment approval, publisher
identity, both uploaded hashes, both per-file attestations and clean install
results. Verify hosted Read the Docs separately. Keep #11 open until those
approved rehearsal and hosted acceptance results exist.

## Partial uploads, rollback and safe retry

Publishing is not atomic across files. If upload or post-upload verification fails,
stop and inspect both the upload logs and the registry's exact-version JSON and
per-file provenance. Compare existing filenames, digests, sizes and attested
identity against the retained manifest. A verification failure does not mean the
upload failed. Do not rebuild or automatically rerun all jobs after a partial upload.

`skip-existing` is deliberately false. If no files exist, obtain retry approval
and rerun the protected upload job using its retained same-run artifact ID and
checked bytes. If only some files exist and match, prepare a reviewed recovery
upload containing only the missing original files, bound to the same environment
and approved source; any workflow change or upload requires explicit permission.
Do not suppress conflicts or accept an existing filename without comparing its
digest and provenance. An existing file cannot simply acquire an attestation by
re-uploading it. If publisher/digest/provenance is wrong, stop and select a newly
approved rehearsal version rather than attempting overwrite or deletion/reuse.
Retain incomplete evidence and document the diagnosis.

To halt publishing, have the maintainer withhold environment approval or revoke
the publisher binding/disable the publishing workflow with explicit authorization;
keep SDK validation available. Remove obsolete TestPyPI publisher bindings and
unneeded access after a rehearsal, while retaining the exact `release/testpypi`
deployment restriction for future authorized rehearsals. Do not weaken protections
to fix an OIDC error: compare owner/repo/workflow/environment and audience against
the registry binding. PyPI and TestPyPI bindings are distinct.

For a bad production release, coordinate the maintainer's separately authorized
yank and corrected release; do not delete/reuse immutable filenames. Reverting
repository source does not remove a published file. Package support and version
changes require review independently of this CI task.

## Official references

- [PyPA pip-audit CLI and advisory behavior](https://github.com/pypa/pip-audit)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [GitHub OIDC with PyPI](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi)
- [Official PyPA publish action](https://github.com/pypa/gh-action-pypi-publish)
- [Producing per-file attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [Consuming and verifying attestations](https://docs.pypi.org/attestations/consuming-attestations/)
- [PyPI Integrity API](https://docs.pypi.org/api/integrity/)
