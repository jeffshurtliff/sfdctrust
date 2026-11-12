# Qualify the public compatibility baseline

The {doc}`../reference/compatibility` policy defines the 1.x public surface.
This gate compares the latest published pre-1.0 wheel (`0.2.0` at this handoff)
with a locally built candidate, without editable installs, real credentials,
or Salesforce requests. It complements the existing offline suite rather than
reimplementing every behavior test.

Live-service qualification remains owned by
[issue #8](https://github.com/jeffshurtliff/sfdctrust/issues/8).
Operator recovery is complete under
[issue #9's closing evidence](https://github.com/jeffshurtliff/sfdctrust/issues/9#issuecomment-6810823647),
including successful macOS/Windows/Ubuntu hosted rehearsals at
`3b7438ecf9f0ad8c9c922982c8afe1d101b55fbc`. Do not rerun those gates to satisfy
issue #10. The upgrade check here only reopens baseline-created ready/pending
stores and verifies public compare-and-swap protection; it performs no refresh
or operator recovery rehearsal.

## Preparation and isolated installations

Run from the repository root with Python 3.12 (the inventory/checker interpreter) and the locked development tools.
Choose a fresh work directory for each run. The commands below are the local
POSIX commands used for this qualification. On Windows, use each venv's
`Scripts/python.exe` instead of `bin/python`. The new compatibility job uses
Ubuntu/Python 3.12; the existing matrix continues to validate native storage
and the rest of the SDK on all configured runners.

Package retrieval is an explicit network-enabled preparation step. Record the
release source, versions and hashes; the published wheel is not rebuilt from
a tag. Keep dependency versions equivalent between the two environments for
this comparison. Retain `pip freeze` outputs with evidence if the resolver
selects different dependency versions on another date.

```sh
git branch --show-current
git rev-parse HEAD
git status --short --branch
poetry check --lock --strict
poetry install --with docs
poetry build
mkdir -p /private/tmp/sfdctrust-compat/wheels
poetry run python -m pip download --only-binary=:all: \
  --dest /private/tmp/sfdctrust-compat/wheels 'sfdctrust==0.2.0' 'mypy==1.20.2'
poetry run python -m venv /private/tmp/sfdctrust-compat/baseline
poetry run python -m venv /private/tmp/sfdctrust-compat/candidate
/private/tmp/sfdctrust-compat/baseline/bin/python -I -m pip install --no-index \
  --find-links /private/tmp/sfdctrust-compat/wheels \
  /private/tmp/sfdctrust-compat/wheels/sfdctrust-0.2.0-py3-none-any.whl 'mypy==1.20.2'
/private/tmp/sfdctrust-compat/candidate/bin/python -I -m pip install --no-index \
  --find-links /private/tmp/sfdctrust-compat/wheels \
  dist/sfdctrust-1.0.0.dev0-py3-none-any.whl 'mypy==1.20.2'
/private/tmp/sfdctrust-compat/baseline/bin/python -I -m pip check
/private/tmp/sfdctrust-compat/candidate/bin/python -I -m pip check
/private/tmp/sfdctrust-compat/baseline/bin/python -I -m pip freeze
/private/tmp/sfdctrust-compat/candidate/bin/python -I -m pip freeze
```

Mypy is the single checker and a development dependency only. CI obtains its
version from the Poetry lock installation and installs that version in the
candidate venv. It is not included in runtime metadata. The strict fixture
imports only public paths, checks model/results, both clients, lazy async
iteration, and structural conformance of custom sync/async PAT stores. It is
checked, never executed. No `MYPYPATH`, missing-import suppression, SDK stubs,
Pydantic plugin, editable installation, or skipped SDK imports are used. The
checker discovers the installed PEP 561 package in its own interpreter, per
[mypy's installed-package guidance](https://mypy.readthedocs.io/en/stable/installed_packages.html).
Assertions of inferred types prevent an `Any` return from disguising a broken
public annotation. This does not claim that all SDK internals pass strict mypy.

## Behavioral comparison and store upgrade

Each invocation below requires `-I`, rejects optimized execution and editable
imports, verifies package bytes against its specified wheel, and confirms the
shipped `py.typed` marker. A socket/DNS audit guard is installed before importing
the SDK or executing behavior. The event loop is initialized first because
Windows may need a socket pair for its internal wakeup mechanism. Qualification
cannot open any sockets after that point. The two deliberate guard self-tests
are counted separately; any other socket/DNS attempt fails qualification.

The checked inventory contains supported exports, method parameter kinds,
keyword-only defaults, return types, call/await invocation, model fields/aliases,
exception inheritance and probe values. It normalizes the private environment
omission sentinel and the equivalent `builtins.list` spelling. It does not
freeze an incidental import or the version string. No module search path is
added by the harness. Its CLI test executes the real installed module inside
the same guarded interpreter with an explicitly named synthetic environment
variable; it does not discover credentials.

```sh
/private/tmp/sfdctrust-compat/baseline/bin/python -I tests/compatibility/check_wheel.py \
  --wheel /private/tmp/sfdctrust-compat/wheels/sfdctrust-0.2.0-py3-none-any.whl \
  --expected-version 0.2.0 --snapshot tests/compatibility/public-api.json \
  --evidence /private/tmp/sfdctrust-compat/baseline.json
/private/tmp/sfdctrust-compat/candidate/bin/python -I tests/compatibility/check_wheel.py \
  --wheel dist/sfdctrust-1.0.0.dev0-py3-none-any.whl \
  --expected-version 1.0.0.dev0 --snapshot tests/compatibility/public-api.json \
  --evidence /private/tmp/sfdctrust-compat/candidate.json
/private/tmp/sfdctrust-compat/baseline/bin/python -I tests/compatibility/check_wheel.py \
  --wheel /private/tmp/sfdctrust-compat/wheels/sfdctrust-0.2.0-py3-none-any.whl \
  --expected-version 0.2.0 --snapshot tests/compatibility/public-api.json \
  --mode seed --store-directory /private/tmp/sfdctrust-compat/stores-final \
  --evidence /private/tmp/sfdctrust-compat/seed.json
/private/tmp/sfdctrust-compat/candidate/bin/python -I tests/compatibility/check_wheel.py \
  --wheel dist/sfdctrust-1.0.0.dev0-py3-none-any.whl \
  --expected-version 1.0.0.dev0 --snapshot tests/compatibility/public-api.json \
  --mode upgrade --store-directory /private/tmp/sfdctrust-compat/stores-final \
  --evidence /private/tmp/sfdctrust-compat/upgrade.json
```

The first baseline inventory was recorded with the explicit developer option
`--record-inventory`, then reviewed. Normal qualification and CI never use that
option. Do not regenerate the snapshot merely to make a break pass. When future
approved additions cause the baseline and candidate surfaces to diverge, retain
the historical baseline snapshot separately and review candidate changes under
the versioning policy; do not demand that old wheels implement new additions.
The current versions share the same normalized inventory.

Both wheels exercise all five reads in sync/async form, serialization/aliases,
omission/null rules, offsets, unknown values, status duplicates and scopes,
lazy iteration, continuation and partial failure, HTTP errors versus pagination
guards, connection ownership, timeout overrides, bounded retries, cancellation
and installed CLI initialization. Detailed read/search/pagination, retries,
exception sanitization, async refresh/cancellation and SQLite unsupported-format
cases remain in the existing unit suite.

## Downstream typing and other checks

```sh
/private/tmp/sfdctrust-compat/baseline/bin/python -I -m mypy --version
/private/tmp/sfdctrust-compat/baseline/bin/python -I -m mypy \
  --config-file tests/compatibility/mypy.ini --no-incremental tests/compatibility/downstream.py
/private/tmp/sfdctrust-compat/candidate/bin/python -I -m mypy --version
/private/tmp/sfdctrust-compat/candidate/bin/python -I -m mypy \
  --config-file tests/compatibility/mypy.ini --no-incremental tests/compatibility/downstream.py
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry check --lock --strict
poetry build
poetry run twine check --strict dist/sfdctrust-1.0.0.dev0*
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

The baseline mypy command intentionally exits **1** with exactly two
`assert-type` diagnostics: sync and async `tenants.list_all()` resolve to
`list?[Tenant]` because the method `list` shadows the built-in annotation name.
Run it separately from shell sequences that stop on the first failure. The
candidate qualifies `builtins.list[Tenant]` and must exit **0** with no errors.
This is a typing correction, not a runtime incompatibility or migration.
CI enforces the candidate's success; the published baseline's known typing
failure is recorded here and in local evidence, not required to pass.

## Local results and closure boundaries

Qualification date: **2026-11-11 America/Denver** (UTC timestamps fall on
2026-11-12). Initial source: clean `main` at
`3b7438ecf9f0ad8c9c922982c8afe1d101b55fbc`, package `1.0.0.dev0`.
All changes remain uncommitted. See the
{download}`sanitized evidence <evidence/compatibility-2026-11-11.json>` for wheel
and harness hashes, installed paths, Python/platform, dependencies, checker
version, source state and outcomes.

| Gate | Local outcome |
| --- | --- |
| Published 0.2.0 vs candidate normalized public inventory | Equal |
| Non-editable installations and wheel byte identity | Passed in separate clean venvs |
| `py.typed` in archive and installation | Passed for both |
| Offline sync/async behavior, CLI, serialization and pagination/errors | Passed for both; zero unexpected network attempts |
| Reopen baseline-created ready and pending SQLite stores | Passed; revisions/markers retained and stale CAS refused |
| Strict downstream mypy 1.20.2 | Baseline: two known annotation diagnostics; candidate: passed |
| Existing offline suite | 605 passed, 15 platform-specific skips on macOS/Python 3.12.7 |
| Ruff lint and format, Bandit, Poetry lock, wheel/sdist build, packaging contents, strict Twine and Sphinx | Passed |

The maintainer approved deferring public phase-timeout configuration on
2026-11-11. No intentional runtime incompatibility was found; no version bump,
new runtime dependency or storage migration was introduced. No real credentials
were read, no Salesforce call was made, and GitHub was not modified.

Before issue #10 can close, the maintainer must approve the inventory/versioning
and upgrade policy and review the typing correction, and the updated workflow
must pass in hosted CI. The local machine does not verify the new Ubuntu job or
a new Windows run. Prior issue #9 hosted evidence covers that recovery gate
only. Qualification of the exact stable release artifact and live service stays
with the release process/#8. Nothing here claims those remaining gates passed.
