# Qualify public compatibility, CLI and MCP installations

The {doc}`../reference/compatibility` policy defines the 1.x public surface.
Compare the candidate with the published `1.1.0` SDK and CLI. Continue the
historical SDK and SQLite compatibility campaigns against `0.2.0` and `1.0.0`.
Use the reviewed Python inventory in `tests/compatibility/public-api.json`
for all three baselines. The general-purpose CLI first shipped in `1.1.0`.

All behavioral qualification uses synthetic credentials, disposable stores,
HTTPX mocks, and outbound blocking. Live-service and final stable-artifact
qualification are separately authorized release gates. A passing local dirty-tree
campaign is not exact-commit hosted evidence or permission to publish.

## Preparation and isolated installations

Use Python 3.12 and the locked development tools. Choose fresh directories and
record HEAD, branch, dirty state, full source/diff hashes, dependency freezes,
artifact digests, commands and results. An uncommitted candidate is HEAD plus its
reviewed working diff. Use the artifact digests to identify the exact bytes.
These POSIX examples run from the repository root. Windows environments use
`Scripts/python.exe` instead of `bin/python`.

Retrieve dependencies separately from behavioral qualification. The artifact
preparer pins active locked runtime dependencies, the build backend and checker.
Published baseline wheels are retrieved from PyPI, not rebuilt from tags. Multiple
versions of one distribution require **separate pip download invocations**:

```sh
poetry check --lock --strict
poetry install --extras mcp --no-interaction
poetry build --output /tmp/sfdctrust-cli-dist
poetry run python tools/ci/qualify.py prepare --dist /tmp/sfdctrust-cli-dist \
  --wheelhouse /tmp/sfdctrust-cli-compat/wheels --work /tmp/sfdctrust-cli-compat/retrieval
for baseline in 0.2.0 1.0.0 1.1.0; do
  poetry run python -m pip download --only-binary=:all: --no-deps \
    --dest /tmp/sfdctrust-cli-compat/wheels "sfdctrust==$baseline"
done
```

The following phase installs exclusively from the prepared wheelhouse. Keep
baseline and candidate environments, seed stores and evidence separate for each
campaign. Do not use editable installs or add the checkout to module search paths.

```sh
compat_root=/tmp/sfdctrust-cli-compat
candidate_version="$(poetry version --short)"
candidate_wheel="/tmp/sfdctrust-cli-dist/sfdctrust-$candidate_version-py3-none-any.whl"
checker_version="$(poetry run python -c 'from importlib.metadata import version; print(version("mypy"))')"
for baseline in 0.2.0 1.0.0 1.1.0; do
  campaign="$compat_root/$baseline"
  mkdir -p "$campaign/evidence"
  poetry run python -m venv "$campaign/baseline"
  poetry run python -m venv "$campaign/candidate"
  "$campaign/baseline/bin/python" -I -m pip install --no-index --find-links "$compat_root/wheels" \
    --constraint "$compat_root/wheels/locked-active.txt" \
    "$compat_root/wheels/sfdctrust-$baseline-py3-none-any.whl"
  "$campaign/candidate/bin/python" -I -m pip install --no-index --find-links "$compat_root/wheels" \
    --constraint "$compat_root/wheels/locked-active.txt" "$candidate_wheel" "mypy==$checker_version"
  for role in baseline candidate; do
    "$campaign/$role/bin/python" -I -m pip check
    "$campaign/$role/bin/python" -I -m pip freeze > "$campaign/evidence/$role-freeze.txt"
  done
done
```

## Behavioral comparison and store upgrade

`check_wheel.py` requires `-I`, rejects optimized/editable imports, verifies
installed package bytes against the specified wheel, and checks `py.typed`.
Its socket/DNS audit guard is installed before SDK imports. An event loop is
created first for Windows wakeup IPC; no SDK behavior precedes the guard. Two
deliberate guard probes are counted separately; other networking fails.

The reviewed inventory contains exports, signatures/defaults, call/await
semantics, model fields/aliases, exception inheritance and probe values. It
normalizes only the private omission sentinel and equivalent `builtins.list`
spelling. Normal runs and CI never use `--record-inventory`; do not regenerate a
snapshot to make failures pass. Approved future public additions require a
separate reviewed candidate inventory while preserving the historical snapshot.

```sh
for baseline in 0.2.0 1.0.0 1.1.0; do
  campaign="$compat_root/$baseline"
  if [ "$baseline" = "1.1.0" ]; then
    "$campaign/baseline/bin/python" -I tests/offline/run.py tests/package_smoke.py
  fi
  "$campaign/baseline/bin/python" -I tests/compatibility/check_wheel.py \
    --wheel "$compat_root/wheels/sfdctrust-$baseline-py3-none-any.whl" --expected-version "$baseline" \
    --snapshot tests/compatibility/public-api.json --evidence "$campaign/evidence/baseline.json"
  "$campaign/candidate/bin/python" -I tests/compatibility/check_wheel.py \
    --wheel "$candidate_wheel" --expected-version "$candidate_version" \
    --snapshot tests/compatibility/public-api.json --evidence "$campaign/evidence/candidate.json"
  "$campaign/baseline/bin/python" -I tests/compatibility/check_wheel.py \
    --wheel "$compat_root/wheels/sfdctrust-$baseline-py3-none-any.whl" --expected-version "$baseline" \
    --snapshot tests/compatibility/public-api.json --mode seed --store-directory "$campaign/stores" \
    --evidence "$campaign/evidence/seed.json"
  "$campaign/candidate/bin/python" -I tests/compatibility/check_wheel.py \
    --wheel "$candidate_wheel" --expected-version "$candidate_version" \
    --snapshot tests/compatibility/public-api.json --mode upgrade --store-directory "$campaign/stores" \
    --evidence "$campaign/evidence/upgrade.json"
  "$campaign/candidate/bin/python" -I tests/offline/run.py -m mypy \
    --config-file tests/compatibility/mypy.ini --no-incremental tests/compatibility/downstream.py
done
```

Each baseline and candidate exercises all five Python reads in sync/async form,
serialization/aliases, omission/null, offsets, unknown values, scoped duplicates,
lazy iteration, continuation/failure, HTTP errors, ownership, fixed timeouts,
bounded retries, cancellation and the existing PAT-store initialization module.
Seed mode uses the baseline's public initializer for ready and pending stores.
Upgrade mode reopens those stores with the candidate, retains revisions/attempt
markers, refuses stale compare-and-swap, blocks a pending client, and refuses
initializer overwrite. It performs no refresh, migration, or recovery automation.
The completed operator-recovery evidence remains in
[issue #9](https://github.com/jeffshurtliff/sfdctrust/issues/9#issuecomment-6810823647).

Strict downstream mypy uses only public paths, inferred-type assertions and the
installed PEP 561 package. It never executes the fixture and uses no SDK stubs,
`MYPYPATH`, missing-import suppression or Pydantic plugin. CI obtains the checker
version from locked tooling. Published `0.2.0` has two known `assert-type`
diagnostics for `tenants.list_all()` because `list` shadows its annotation;
`1.0.0` contains the correction. The installed candidate must pass. This does not
claim that all SDK internals pass strict mypy.

## Candidate CLI and MCP artifact checks

```sh
poetry run python tools/ci/qualify.py qualify --dist /tmp/sfdctrust-cli-dist \
  --wheelhouse /tmp/sfdctrust-cli-compat/wheels --work /tmp/sfdctrust-cli-installs
```

The qualifier installs wheel and sdist separately, non-editably and offline,
then verifies MCP is absent and runs package smoke, compatibility and strict downstream typing.
Each installation then adds the same artifact with its `mcp` extra and runs the
real client/server protocol checks with a mocked Salesforce transport. Real console
and module launchers run outside the checkout with a test-only bootstrap that
blocks outbound traffic **before SDK imports**. Tests use synthetic environment
PATs/disposable stores, and retain bytecode-cache protection when rewriting
bootstraps. No production test switches are provided.

The installed checks cover all five documented read examples, help/version,
preflight without credential/store access, all store selectors, no environment
lookup or fallback for explicit stores, missing environment credentials despite
a ready default store, pending/unseeded/missing failures, one-page cursors and
stale errors, aliases/presence/extras/offsets, scopes/order/duplicates/history/
timelines, safe streams/exit codes/redaction, bounded retries/interruption and
cleanup. They exercise leading-dash argparse forms, real closed output pipes and
closed stdout descriptors, including interpreter shutdown without tracebacks.
Source-level regressions additionally cover unsafe and changing store revisions,
render/write/close errors and complete validation boundaries.

CI's metadata-derived matrix retains Python 3.12–3.15 on Linux and the minimum
minor on macOS/Windows, including native SQLite permissions/spawned processes
and real installed wheel launchers. The quality job separately qualifies both
artifacts. The existing compatibility job runs both baseline campaigns on
Linux/Python 3.12 and retains separate evidence/freeze files even on failures.
Required job names, permissions and release protection remain unchanged.

Run the full outbound-blocked suite, Ruff lint/format, Bandit, strict Poetry/lock,
private CLI typing, fresh build/strict Twine, artifact/source/entry-point/digest
inspection, actionlint and strict Sphinx; see {doc}`ci-and-publishing` for commands.
Dependency/advisory/intersphinx networking is separate from behavioral tests.
Record actual failures, retries, skips and host limits. Verify hosted matrix and
docs against the exact release commit after authorized delivery. Follow
{doc}`stable-release` for final artifact qualification and publishing.

## Historical 0.2.0 qualification — 2026-11-11

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
