# Issue #11 local validation evidence

Validation date: **2026-11-13**. **Issue #11 remains incomplete.** The changed
source has not been committed or pushed, its hosted CI/Read the Docs runs do not
exist, and no TestPyPI rehearsal has been authorized or performed.

The [machine-readable evidence](evidence/ci-publishing-2026-11-13.json) contains the
audit report, artifact/payload hashes, installed compatibility reports, original
implementation file hashes, local results, historical hosted references and
outstanding actions. The branch-policy follow-up below records the subsequent
changes separately. Each implementation snapshot identifies the base commit plus
changed/new files; this derived evidence page and JSON report are excluded from
those fingerprints to avoid a circular hash. See {doc}`ci-and-publishing` for the
reviewable workflow and complete setup, approval, publishing and rollback runbook.

## Source and scope

| Field | Verified value |
| --- | --- |
| Starting branch | `ci/close-ci-and-pypi-publishing-gaps` |
| Starting and final HEAD | `a8be4ed79444450ac8986a96f1a60931f9da2237` |
| Package version | `1.0.0.dev0`, unchanged |
| Starting working tree | Clean |
| Final working tree | Uncommitted issue #11 implementation and documentation |
| Latest published release | GitHub release `0.2.0`, verified read-only |
| Python policy | `>=3.12`, classifiers 3.12–3.15, unchanged |
| Runtime requirements and locked runtime versions | Unchanged |

No SDK runtime files, public API, timeout configuration, SQLite schema or storage
boundary changed. No commits, pushes, tags, GitHub issue updates, settings changes,
publisher registrations or uploads were made. No Salesforce credentials were read
or Salesforce requests attempted. #8 live qualification and #9's dedicated
operator recovery gate were not rerun; their existing evidence was reused.

## Executed local checks

| Interpreter on macOS arm64 | Unit/integration suite | Additional checks |
| --- | --- | --- |
| Python 3.12.7 | **630 passed, 15 skipped** | Controlled real pip-audit CLI fixture, publisher verification orchestration, installed wheel and sdist compatibility/strict typing |
| Python 3.13.18 | **627 passed, 18 skipped** | Separate isolated installed-wheel smoke passed |
| Python 3.14.10 | **627 passed, 18 skipped** | Separate isolated installed-wheel smoke passed |
| Python 3.15.2 | **627 passed, 18 skipped** | Separate isolated installed-wheel smoke passed |

All runs used synthetic data and disposable stores with an inherited outbound
socket/DNS guard. The 15 platform skips are native Windows cases on macOS. The
three extra skips on 3.13–3.15 are the pip-audit CLI fixture and two attestation-tool
tests: those tools are intentionally installed only for Python 3.12. Native Linux
and Windows behavior for this changed source still requires hosted CI.

Poetry lock validation, Ruff lint/format, Bandit, wheel/sdist builds, strict Twine,
archive metadata/payload inspection, separate clean non-editable installations,
`pip check`, installed CLI/SQLite smoke, the accepted public inventory and offline
behavior checker, and strict downstream mypy 1.20.2 all passed. The sdist produced
an identical wheel (same SHA-256 below). Both compatibility reports recorded zero
unexpected network attempts. A copy of the artifacts passed file-set/size/SHA-256
transfer verification. Regression tests also execute both publishing jobs' actual
inline checksum verifiers and prove altered bytes are rejected.

The current-source release preflight was deliberately exercised and **rejected
the uncommitted tree**, as required. This local artifact qualification does not
authorize publishing from a dirty checkout.

Strict Sphinx 9.1.1 passed with `-W --keep-going -E -a`, nitpicky references, and
the normal online Python intersphinx inventory. No warnings were suppressed.
Actionlint **1.7.12** passed both workflows after correction of an invalid job-level
`runner.temp` expression. The official macOS arm64 validator archive was verified
against its published checksum:
`aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f`.
Static workflow tests verify docs-only/code/dependency PR trigger coverage and
read-only fork behavior; actual new hosted PR runs remain outstanding.

The online **pip-audit 2.10.1** scan covered all **11** locked main-group packages,
including transitive/marker variants, with **no known vulnerabilities and no
exceptions**. The real CLI's deterministic mocked advisory fixture reported
`CVE-2024-35195` for `requests==2.31.0`, identified fixed `2.32.0`, and exited 1
without installing that package or using networking.

Local environment preparation initially tried the source-checkout fallback test
against a non-editable wheel on 3.13/3.14; that context mismatch failed as expected.
The final source unit suites used `PYTHONPATH=src`, and the installed-wheel smoke
remained a separate `-I` invocation. No tests were suppressed or runtime source
changed. Python 3.15 lacked a locked PyYAML macOS wheel; its hash-verified source
distribution built successfully before offline testing.

## Original development artifacts

The files are retained locally under
`/private/tmp/sfdctrust-issue11-reviewed/dist/`. These are development artifacts
from the original uncommitted qualification snapshot, before the branch-policy
follow-up below. They are not current-source or approved rehearsal/release artifacts.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sfdctrust-1.0.0.dev0-py3-none-any.whl` | 55757 | `ceeda06eee10041b9abb3b49829187da5e06950646530fc06b105db549e0815e` |
| `sfdctrust-1.0.0.dev0.tar.gz` | 203572 | `bc6c5c3bba3b7a9a1a7567b803e4b1fec4562a2e92abe31d7cda5cd205c82941` |

The exact local manifest, `SHA256SUMS`, per-artifact compatibility reports, freeze
outputs and clean environments are under
`/private/tmp/sfdctrust-issue11-reviewed/evidence/`. The qualification log is
`/private/tmp/sfdctrust-issue11-reviewed-qualification.log`. Local scratch files
are disposable; durable results and payload hashes are retained in the linked JSON.

## Reproduction commands

The final build and verification used these commands from the repository root;
choose fresh output/work directories when repeating them:

```sh
poetry check --lock --strict
poetry install --with docs --no-interaction
poetry run python tests/offline/run.py -m pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry run python tools/ci/audit.py --output /private/tmp/sfdctrust-issue11-audit.json
/private/tmp/sfdctrust-issue11-actionlint/actionlint .github/workflows/ci.yml .github/workflows/release.yml
poetry run sphinx-build -W --keep-going -E -a -b html docs /private/tmp/sfdctrust-issue11-docs
poetry build --output /private/tmp/sfdctrust-issue11-reviewed/dist
poetry run twine check --strict /private/tmp/sfdctrust-issue11-reviewed/dist/*
poetry run python tools/ci/artifacts.py inspect \
  --dist /private/tmp/sfdctrust-issue11-reviewed/dist \
  --manifest /private/tmp/sfdctrust-issue11-reviewed/evidence/release-manifest.json
# Dependency retrieval was done separately against the preceding identical wheel:
poetry run python tools/ci/qualify.py prepare \
  --dist /private/tmp/sfdctrust-issue11-build/dist \
  --wheelhouse /private/tmp/sfdctrust-issue11-build/wheels \
  --work /private/tmp/sfdctrust-issue11-build/evidence/installs
poetry run python tools/ci/qualify.py qualify \
  --dist /private/tmp/sfdctrust-issue11-reviewed/dist \
  --wheelhouse /private/tmp/sfdctrust-issue11-build/wheels \
  --work /private/tmp/sfdctrust-issue11-reviewed/evidence/installs
mkdir /private/tmp/sfdctrust-issue11-reviewed/transfer
cp /private/tmp/sfdctrust-issue11-reviewed/dist/* /private/tmp/sfdctrust-issue11-reviewed/transfer/
poetry run python tools/ci/artifacts.py transfer \
  --dist /private/tmp/sfdctrust-issue11-reviewed/transfer \
  --manifest /private/tmp/sfdctrust-issue11-reviewed/evidence/release-manifest.json
```

For the additional local interpreters, generate test/runtime requirements from
the lock without installing audit/attestation tooling on unsupported tooling minors:

```sh
python3 - <<'PY'
import tomllib
from pathlib import Path
lock = tomllib.loads(Path('poetry.lock').read_text())
selected = {'pytest', 'pytest-asyncio', 'pyyaml', 'packaging', 'pluggy', 'iniconfig', 'pygments'}
packages = [p for p in lock['package'] if 'main' in p['groups'] or p['name'] in selected]
assert len(packages) == len({p['name'] for p in packages})
Path('/private/tmp/sfdctrust-issue11-tests-requirements.txt').write_text(''.join(
    p['name'] + '==' + p['version'] + ' ' + ' '.join('--hash=' + f['hash'] for f in p['files']) + '\n'
    for p in packages
))
PY
```

Repeat the following for `3.13`, `3.14`, and `3.15` (the recorded executable
locations are Homebrew installations):

```sh
test_minor=3.13
/opt/homebrew/bin/python${test_minor} -m venv /private/tmp/sfdctrust-issue11-python${test_minor}
test_python=/private/tmp/sfdctrust-issue11-python${test_minor}/bin/python
"$test_python" -m pip install --require-hashes -r /private/tmp/sfdctrust-issue11-tests-requirements.txt
"$test_python" -m pip install --no-deps --no-index \
  /private/tmp/sfdctrust-issue11-reviewed/dist/sfdctrust-1.0.0.dev0-py3-none-any.whl
"$test_python" -I -m pip check
PYTHONPATH="$PWD/src" "$test_python" tests/offline/run.py -m pytest -q
"$test_python" -I tests/offline/run.py tests/package_smoke.py
```

## Hosted evidence and required next actions

Existing [GitHub Actions run 43319593708](https://github.com/jeffshurtliff/sfdctrust/actions/runs/43319593708)
and [Read the Docs build 35852450](https://app.readthedocs.org/projects/sfdctrust/builds/35852450/)
succeeded at starting commit `a8be4ed79444450ac8986a96f1a60931f9da2237`.
They do not validate the changed workflows or Poetry 2.5.1 Read the Docs setup.
The existing [#9](https://github.com/jeffshurtliff/sfdctrust/issues/9#issuecomment-6810823647)
and [#10](https://github.com/jeffshurtliff/sfdctrust/issues/10#issuecomment-6856289949)
acceptance records remain the governing completed gates.

No branch protection, rulesets or publishing environments were present when
inspected. Before issue #11 can close, the maintainer must review/commit/push the
changes with separate authorization, obtain successful hosted CI and docs evidence,
approve the concrete rehearsal source/version/configuration/upload proposal, and
configure the protected `testpypi` environment and exact publisher binding.

Proposed rehearsal version **`1.0.0rc2026111301`** returned HTTP 404 from TestPyPI
on the validation date. Recheck availability before approval. The reviewed
implementation plus a version-only commit on `release/testpypi` is the
proposed source; its actual immutable SHA must be recorded after authorized commit
and push. Neither that source change nor environment/publisher setup nor upload
is authorized here. Review the dry run and the upload run's own manifest before
environment approval. After an approved upload, retain matching hosted digests,
Trusted Publishing identity, cryptographically verified per-file provenance and
clean hosted-wheel installation evidence. These results are currently **pending**.

## Reusable branch policy follow-up

The maintainer requested an agent-neutral, reusable rehearsal branch after the
original qualification above. The current branch policy is **`release/testpypi`**,
independent of agent, issue number or package version. The runbook, contributor
guide, workflow upload condition, source validator, proposal metadata and tests
now agree on that exact branch. Validation-only dispatches accept `main` or
`release/testpypi`, removing the temporary implementation-branch exception.
Source SHA/version approval and all publishing permissions remain required.

Original audit, multi-version, clean-install and artifact reports above retain
their original snapshot and digests. The JSON's `branch_policy_follow_up` records
the current source fingerprint, focused verification and rebuilt artifact hashes
separately. No branch or external settings were created or changed for this update.
