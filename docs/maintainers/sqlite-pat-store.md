# Qualify the SQLite PAT store

The v0.2.0 store is synchronous and uses one private database on an encrypted
local volume, one host, and one OS account. It reuses the existing refresh protocol.
The tests use synthetic PATs and mock HTTP transports; no Salesforce
credentials are needed.

## Validation

The `SDK validation` GitHub Actions workflow tests macOS, Windows, and Ubuntu
with Python 3.12 and Ubuntu with Python 3.15. It includes native ACL tests,
spawned-process competition, abrupt exits, and an installed-wheel walkthrough.
The separate quality job checks Ruff, Bandit, distribution metadata, and
strict Sphinx output. Windows tests use native Windows APIs and an ordinary
hosted runner; no additional device or architecture matrix is required.

After installing a built wheel, run `python tests/package_smoke.py` from
the checkout to verify its module command, tenant and event reads, explicit
refresh, and reopening. The script rejects editable/source imports.

Record actual platform results before declaring the feature release-ready.
Local macOS success does not establish Windows or Linux qualification.
Do not use a live PAT as part of these checks. Any optional real-account
walkthrough requires separate maintainer authorization. See
{doc}`pat-rotation-qualification` for the installed-wheel procedure.

## Offline recovery rehearsal (issue #9)

`tests/pat_recovery_rehearsal.py` exercises the three operator recovery paths
from {doc}`../reference/authentication` against the installed synchronous
`SQLitePATStore`. It needs only the wheel's runtime dependencies. It refuses
editable/source imports, requires an isolated virtual-environment interpreter,
and compares installed package files with the supplied wheel. Every database
is disposable and seeded with a synthetic PAT through `SQLitePATStore.initialize()`.
The separate `package_smoke.py` walkthrough covers the installed initialization CLI.

The rehearsal installs a Python audit hook that rejects all socket operations,
including DNS, in the parent and each child. It tests the guard deliberately;
any additional blocked attempt fails the run. All HTTP uses `httpx.MockTransport`.
It reads no credential sources and simulates all My Trust Center operator actions.
The guard applies during the rehearsal; dependency installation is a separate
preparation step. No live PAT or Salesforce request is part of issue #9.

### Reproduce from a checkout

Run these commands from the repository root on macOS or Linux with Python 3.12
or later and Poetry available. Use a private local temporary location on an
encrypted volume. Record the initial output before making changes. Dependencies
can be installed from a trusted offline wheelhouse by adding
`--no-index --find-links /path/to/wheelhouse` to the pip install command.

```sh
recovery_repo="$(pwd -P)"
recovery_commit="$(git rev-parse HEAD)"
recovery_branch="$(git branch --show-current)"
git status --short --branch
poetry version --short
recovery_dir="$(mktemp -d "${TMPDIR:-/tmp}/sfdctrust-recovery.XXXXXX")"
poetry build --output "$recovery_dir/dist"
python3.12 -m venv "$recovery_dir/venv"
recovery_python="$recovery_dir/venv/bin/python"
"$recovery_python" -I -m pip install "$recovery_dir"/dist/*.whl
"$recovery_python" -I -m pip check
git status --short --branch
(cd "$recovery_dir" && "$recovery_python" -I "$recovery_repo/tests/package_smoke.py")
(cd "$recovery_dir" && "$recovery_python" -I "$recovery_repo/tests/pat_recovery_rehearsal.py" \
  --wheel "$recovery_dir"/dist/*.whl \
  --source-commit "$recovery_commit" --source-branch "$recovery_branch" \
  --source-state "$(git -C "$recovery_repo" status --short --branch)" \
  > "$recovery_dir/evidence.json")
cat "$recovery_dir/evidence.json"
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry check --lock --strict
poetry run twine check --strict "$recovery_dir"/dist/*
poetry run sphinx-build -W --keep-going -E -a -b html docs "$recovery_dir/html"
```

For a detached checkout, supply its known source branch/ref explicitly. On
Windows create the environment with `py -3.12 -m venv <private-directory>\venv`
and use `<private-directory>\venv\Scripts\python.exe -I` with the same script
arguments; run the commands separately with absolute paths. The CI workflow
selects the appropriate interpreter for each hosted platform and runs the same
rehearsal in a new environment after building the wheel.

The JSON is emitted only after every assertion and subprocess succeeds. A
nonzero exit is a failure, even if shell redirection left an empty evidence file.
Record branch, source commit, initial and final working-tree status, package
version, wheel name/hash, rehearsal hash, interpreter/platform, date, dependency
versions, expected/observed states, and request counts. An uncommitted script
is identified by its hash and working-tree record; a source commit alone does
not identify it. Keep secrets, request objects, payloads, tenant/token identifiers,
and revision/attempt values out of retained evidence.

### Assertions and operator checkpoints

| Case | Expected durable state and operator checkpoint | Refresh POSTs | Recovery HTTP | Fresh-process verification HTTP |
| --- | --- | --- | --- | --- |
| Ambiguous timeout; old probe accepted | Pending survives reopening and blocks clients, reads, and refresh. Simulate quiescence and settlement, recheck old PAT, clear exact match retaining revision. Independently stale revision/attempt writes leave newer state untouched. | 1 | 1 controlled GET | 1 GET |
| Ambiguous timeout; old probe rejected | Preserve original pending marker; no replay or conditional clear. | 1 | 0 | 0 |
| Ambiguous timeout; probe returns 503 or times out (two cases) | Preserve original pending marker; no replay or conditional clear. | 1 each | 0 | 0 |
| Initial claim fails before commit or loses acknowledgment after commit (two cases) | No POST. Old credential remains; marker exists only if claim committed. Reopened committed claim blocks construction. | 0 | 0 | 0 |
| Replacement write fails before commit | Live client retains replacement. Failed retry during storage outage changes nothing. Restore access and retry persistence; replacement and cleared marker survive reopening. | 1 | 0 | 1 GET |
| Replacement commits but acknowledgment is lost | Live client remains blocked until persistence retry confirms committed replacement. Fresh process reads using replacement. | 1 | 0 | 1 GET |
| Different revision or attempt before retry, for each replacement fault (four cases) | Retry refuses newer state without overwriting it. | 1 each | 0 | 0 |
| Process exits after mocked rotation before replacement write | Old credential and pending marker survive exit. Simulate stopping all jobs, issuing a fresh PAT, initializing a new protected path, and changing every job to that same path. Verify a fresh-process read before simulating resume; old store remains blocked. | 1 | 0 | 1 GET |

Initial ambiguous attempts each make one automatic old-PAT probe in addition to
the counts in the recovery column. All persistence recovery counts include
failed retries while storage is inaccessible. The fresh-process read is a
separate verification step, not part of `retry_pat_persistence()`.

Fault injection follows `test_sqlite_pat_store.py`: wrap the real store's public
compare-and-swap boundary and fail immediately before it or after its commit.
The abrupt-exit case follows `test_sqlite_pat_processes.py`, using `os._exit()`
in a child before saving the returned replacement. These are deterministic
test hooks, not operator recovery interfaces or power-loss/storage-device tests.
Operator steps use only public initialization, load, compare-and-swap, client
reads, and persistence retry; no direct SQL edits or new recovery API are needed.

### Local evidence — November 11, 2026

The initial checkout was clean on `test/9-rehearse-sqlite-pat-recovery-runbook`,
commit `d4dde2dc1e753c16ebecb3545a87370ece0acec2`, package `0.2.0`.
The rehearsal and documentation changes are uncommitted; SDK source and public
API are unchanged. The sanitized machine-readable record is available as
{download}`evidence/sqlite-pat-recovery-2026-11-11.json`.
See that record for the exact artifact, interpreter, platform, date, script
hash, and all 13 outcomes. Completed local checks are recorded alongside it in
{doc}`sqlite-pat-recovery-evidence`.

This local result does not establish current hosted macOS, Windows, Linux,
or Python 3.15 results. Run the updated CI matrix after maintainer review and
publication of the changes, then review its results before closing
[issue #9](https://github.com/jeffshurtliff/sfdctrust/issues/9).
The live-service gate in issue #8 remains separate.

## Hosted qualification — historical baseline

All five jobs passed on November 8, 2026 at `7571999` on `main`. Each platform
job ran the offline suite and exercised initialization, tenant and event reads,
one explicit refresh, and reopening from the installed wheel.
[SDK validation run](https://github.com/jeffshurtliff/sfdctrust/actions/runs/42520055761)

| Runner | Python | Offline tests | Installed-wheel walkthrough |
| --- | --- | --- | --- |
| macOS | 3.12 | 597 passed, 15 skipped | Passed |
| Windows | 3.12 | 601 passed, 11 skipped | Passed |
| Ubuntu | 3.12 | 594 passed, 18 skipped | Passed |
| Ubuntu | 3.15 | 594 passed, 18 skipped | Passed |

The Windows run includes the `OWNER RIGHTS` ACL regression and the
two-process refresh test. The quality job passed Ruff, Bandit, distribution
build and metadata checks, and strict Sphinx validation.

### Initial implementation results — 2026-11-06

| Environment/check | Observed result |
| --- | --- |
| Local macOS, Python 3.12 | 597 offline tests passed; 14 Windows-only cases skipped. Includes real macOS ACL checks and spawned-process/crash tests. |
| Fresh macOS Python 3.14 environment | Wheel installed offline with locked runtime dependencies; dependency consistency and the installed-package SQLite walkthrough passed. |
| Local quality/package checks | Ruff lint and formatting, Bandit, strict Poetry/lock checks, wheel/sdist builds, archive content checks, and strict Twine metadata validation passed. |
| Documentation | Strict Sphinx HTML build passed; setup, refresh, and recovery pages reviewed in the browser. |

## Follow-up work

These items are outside this implementation. Keep this list as input to
follow-up GitHub issues after reviewing the completed feature:

- Built-in asynchronous SQLite adapter and cancellation qualification.
- Optional credential encryption/keychain integration in addition to ACLs
  and encrypted-volume requirements.
- An explicit, validated migration command for old example databases.
- Multi-host storage/coordination and automatic refresh scheduling, each
  with its own credential-lifecycle design.
- Broader filesystem/provider checks, complex corporate ACL support,
  advanced crash/power-loss fault injection, and additional platform or
  architecture qualification if demonstrated user needs justify them.

The current store does not claim automated encryption verification,
comprehensive network/sync-folder detection, or secure erasure of backups
and filesystem snapshots. These boundaries are documented in the
{doc}`../reference/authentication` reference.
