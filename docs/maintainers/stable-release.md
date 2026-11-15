# Release sfdctrust 1.0.0

[#12](https://github.com/jeffshurtliff/sfdctrust/issues/12) owns release progress,
approvals and final evidence. Preparation does not authorize publication. Keep
the tracker open until the maintainer explicitly approves closure. The proposed
changelog date is **2026-11-15**, America/Denver; review it before merging if the
release date changes. Do not select a next development version during this release.

## Source, validation and frozen artifacts

The previous reachable stable tag is `0.2.0`; the intended annotated tag is
`1.0.0`, without a `v` prefix. The distribution and import name are `sfdctrust`.
Python remains `>=3.12`, advertising 3.12–3.15. Preserve #10's accepted policy,
fixed phase timeouts, single-host SQLite boundary and retired legacy migration.
Runtime requirements remain HTTPX `>=0.28.1,<1.0.0` and Pydantic `==2.14.3`.

Leave preparation edits uncommitted for review. Commits, pushes, PR creation and
merge require separate authorization. After review/merge, require a clean main
checkout equal to remote main. Record the full final commit SHA; the preparation
branch's base SHA plus dirty files is not a release source identity.

Follow {doc}`ci-and-publishing` for lock validation, offline tests, Ruff, Bandit,
online locked-runtime auditing, strict Sphinx, strict Twine, artifact inspection,
separate non-editable wheel/sdist checks and downstream typing. Also run the
`python-stable-release` skill's artifact inspector and Actionlint on both workflows.
Keep retrieval/advisory requests separate from outbound-blocked behavior checks.
Never inspect credentials or contact Salesforce during preparation.

Require exact-final-commit hosted `SDK validation`: policy, audit, packaging/docs,
public compatibility/typing, Linux 3.12/3.13/3.14/3.15 and macOS/Windows 3.12.
Verify native SQLite permissions and spawned-process steps, actual skips and all
job conclusions. Historical #9/#10/#11 evidence supports their completed gates;
it does not qualify new stable artifacts. Verify Read the Docs separately.

Build and inspect again from the clean final main commit. Preserve these local
artifacts as comparison evidence, with their source SHA, sizes and digests. Then
prepare the following **validation-only** dispatch; obtain dispatch approval
before execution. `release_sha` must be the verified final main SHA, not a base
commit, placeholder, PR head or merge preview.

```sh
release_sha='REPLACE_WITH_VERIFIED_FINAL_MAIN_40_CHARACTER_SHA'
test "$(git rev-parse HEAD)" = "$release_sha"
test "$(git rev-parse origin/main)" = "$release_sha"
test -z "$(git status --porcelain --untracked-files=all)"
poetry check --lock --strict
poetry run python tools/ci/artifacts.py source --destination validate \
  --sha "$release_sha" --version 1.0.0 --ref refs/heads/main
# Only after explicit dispatch authorization:
gh workflow run release.yml --repo jeffshurtliff/sfdctrust --ref main \
  -f destination=validate -f source_sha="$release_sha" -f version=1.0.0 -f upload=false
```

Record the returned run's URL/ID, attempt, head SHA and inputs. Download its
`approved-release` artifact to a fresh permanent release-evidence directory:

```sh
release_run='REPLACE_WITH_SUCCESSFUL_VALIDATION_RUN_ID'
release_bundle='/absolute/path/to/new/frozen-1.0.0-bundle'
gh run download "$release_run" --repo jeffshurtliff/sfdctrust \
  --name approved-release --dir "$release_bundle"
poetry run python tools/ci/artifacts.py transfer --dist "$release_bundle/dist" \
  --manifest "$release_bundle/evidence/release-manifest.json"
```

Independently inspect the bundle manifest's version, clean source state, exact
SHA, two filenames, sizes and hashes. Reconcile it with the final local build;
investigate any mismatch. Freeze and retain the reviewed hosted wheel, sdist,
`evidence/SHA256SUMS`, manifest and qualification evidence beyond GitHub's 30-day
artifact retention. Record both file identities in #12. No subsequent build
implicitly replaces this frozen set.

## Exact-wheel qualification owned by #8

[#8](https://github.com/jeffshurtliff/sfdctrust/issues/8) requires both live phases
on the frozen stable wheel. Ask separately before updating that issue. Prior
0.2.0 results and the distinct TestPyPI rehearsal are not stable qualification.
The maintainer supplies credentials privately and runs the live commands.

Install the frozen wheel without rebuilding it. The following setup is offline
after retrieving active locked dependencies with `tools/ci/qualify.py prepare`.
Set `release_wheels` to that reviewed wheelhouse. Its constraints pin active
runtime dependencies; this setup never retrieves or discovers Salesforce secrets.

```sh
qual_repo="$(pwd -P)"
qual_wheel="$release_bundle/dist/sfdctrust-1.0.0-py3-none-any.whl"
release_wheels='/absolute/path/to/reviewed/locked-wheelhouse'
qual_dir="$(mktemp -d "${TMPDIR:-/tmp}/sfdctrust-1.0.0-live.XXXXXX")"
python3.12 -m venv "$qual_dir/venv"
qual_py="$qual_dir/venv/bin/python"
"$qual_py" -I -m pip install --no-cache-dir --no-index --find-links "$release_wheels" \
  --constraint "$release_wheels/locked-active.txt" "$qual_wheel"
"$qual_py" -I -m pip check
"$qual_py" -I - "$qual_wheel" "$release_bundle/evidence/release-manifest.json" <<'PY'
from datetime import datetime, UTC
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import sysconfig
import sfdctrust

wheel = Path(sys.argv[1])
manifest = json.loads(Path(sys.argv[2]).read_text())
record = manifest['files'][wheel.name]
assert manifest['version'] == version('sfdctrust') == sfdctrust.__version__ == '1.0.0'
assert manifest['source_status'] == ''
assert wheel.stat().st_size == record['size']
assert sha256(wheel.read_bytes()).hexdigest() == record['sha256']
assert Path(sfdctrust.__file__).resolve().is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
print('Source', manifest['source_commit'], 'Wheel', wheel.name)
print('Bytes', record['size'], 'SHA-256', record['sha256'])
print('SDK', version('sfdctrust'), 'Import', sfdctrust.__file__)
print('Python', platform.python_version(), 'Platform', platform.system(), platform.machine())
print('UTC', datetime.now(UTC).isoformat())
PY
"$qual_py" -I "$qual_repo/tests/offline/run.py" "$qual_repo/tests/package_smoke.py"
```

**Phase A, only after separate read-only authorization:** run the hidden-prompt
command from {doc}`installed-wheel-qualification` in this environment:

```sh
(cd "$qual_dir" && "$qual_py" -I "$qual_repo/tests/live_read_smoke.py" --live)
```

It checks both clients' five reads, continuation where available, status grouping,
event/tenant scope, history and timelines. Record each outcome and explicit
maintainer dispositions for data-dependent skips; exit 0 alone is insufficient.

**Phase B, only after separate rotation authorization:** follow the exact seed,
one-refresh, persistence, replacement-read, old-PAT-401 and fresh-process-reopen
commands in {doc}`pat-rotation-qualification`, using the same `qual_py` and a new
private store for a dedicated non-production lineage. Quiesce other users of the
lineage. Never blindly retry an ambiguous refresh; keep the original process
alive for persistence-only recovery when required.

Record only sanitized results, exact wheel/hash, source SHA, SDK/Python/platform,
date, phase authorizations and skip dispositions. Link accepted #8 evidence into
#12. Any artifact-affecting source change requires a new manifest and an explicit
requalification decision.

## Production setup, tag and draft

Read-only inspection on 2026-11-15 found main unprotected, no rulesets, and only
the `testpypi` environment. A protected production `pypi` environment is required
before any production upload dispatch. Propose required maintainer reviewers,
prevent self-review and disable administrator bypass; restrict deployments to the
approved **tag** `1.0.0`, excluding branches. If unavailable under the repository
plan or solo-maintainer arrangement, stop for an explicit production alternative.
Do not inherit the rehearsal's self-approval exception.

The separate PyPI Trusted Publisher must bind owner `jeffshurtliff`, repository
`sfdctrust`, workflow `release.yml`, environment `pypi`. Verify it in the project's
PyPI publishing settings; the public package API cannot establish current private
publisher settings. Review public per-file attestation/transparency publication.
Settings changes and publisher registration each need approval. Use GitHub OIDC.

Prepare an annotated `1.0.0` tag on the verified final main SHA. Creating the local
tag, pushing that tag, and creating a draft GitHub Release each require separate
authorization. Recheck tag/version availability before these actions. Prepare
reviewed notes without MyST labels and attach exactly the frozen wheel, sdist and
`SHA256SUMS`. Verify draft=true, prerelease=false and the tag's peeled target SHA.
Never let release creation implicitly create a tag or substitute a branch head.

Prepare these commands for individual approvals; execute only the specifically
authorized step. `release_notes` is the reviewed local Markdown notes file.

```sh
# Separate authorization: create local tag.
git tag -a 1.0.0 "$release_sha" -m 'sfdctrust 1.0.0'
test "$(git rev-parse '1.0.0^{commit}')" = "$release_sha"
# Separate authorization: push that tag.
git push origin refs/tags/1.0.0
# Separate authorization: create a draft, after verifying the remote tag.
release_notes='/absolute/path/to/reviewed/RELEASE_NOTES.md'
gh release create 1.0.0 --repo jeffshurtliff/sfdctrust --verify-tag --draft \
  --title 'sfdctrust 1.0.0' --notes-file "$release_notes" \
  "$release_bundle/dist/sfdctrust-1.0.0-py3-none-any.whl" \
  "$release_bundle/dist/sfdctrust-1.0.0.tar.gz" "$release_bundle/evidence/SHA256SUMS"
```

## Maintainer-executed upload and mandatory hash comparison

Only after the preceding gates and dispatch authorization, the maintainer runs:

```sh
gh workflow run release.yml --repo jeffshurtliff/sfdctrust --ref 1.0.0 \
  -f destination=pypi -f source_sha="$release_sha" -f version=1.0.0 -f upload=true
```

This **new run rebuilds** during validation/build. Its protected publishing job
downloads the same-run immutable artifact ID, rechecks its bytes and uploads
without rebuilding. Before environment approval, download that new run's
`approved-release` bundle into a different directory. Verify its run/ref/source
and all gates, then compare **both** files against the frozen #8-qualified set:

```sh
upload_bundle='/absolute/path/to/new/upload-run-bundle'
poetry run python tools/ci/artifacts.py transfer --dist "$upload_bundle/dist" \
  --manifest "$release_bundle/evidence/release-manifest.json"
poetry run python - "$release_bundle" "$upload_bundle" <<'PY'
import json
from pathlib import Path
import sys
frozen, upload = [json.loads((Path(p) / 'evidence/release-manifest.json').read_text()) for p in sys.argv[1:]]
for key in ('version', 'source_commit', 'source_status', 'files'):
    assert frozen[key] == upload[key], f'Mismatch: {key}'
assert upload['version'] == '1.0.0' and upload['source_status'] == ''
print('PASS both artifact identities match the frozen manifest')
PY
```

Stop on either mismatch. Investigate source/tool/build differences and obtain an
explicit requalification decision; successful CI does not qualify new live bytes.
Only after a successful comparison may the maintainer separately approve the
protected deployment for that exact run. This guide does not grant approval.

## Verify production and finish

After the maintainer's upload, inspect the exact run and its `registry-verification`
artifact. For independent read-only reproduction from the final source, using a
fresh upload bundle without an existing `evidence/registry` directory:

```sh
upload_run='REPLACE_WITH_APPROVED_PRODUCTION_RUN_ID'
poetry run python tools/ci/registry.py --destination pypi --bundle "$upload_bundle" \
  --ref refs/tags/1.0.0 --run-id "$upload_run"
```

This compares both hosted names/sizes/hashes, downloads the hosted bytes, verifies
per-file signatures/transparency and repository/workflow/environment/ref/SHA/run
claims, then separately installs the hosted wheel and sdist with offline smoke,
compatibility and typing checks. Review the retained `release.json` metadata too:
version, Python requirement/classifiers, MIT license/file, Markdown description,
runtime requirements and all project URLs must match the approved source.
Check description rendering on PyPI. Require exact-source successful Read the
Docs build evidence and served stable version `1.0.0`; local Sphinx or an older
`latest` page is insufficient. Obtain approval for any documentation settings change.

Only after production verification and separate explicit approval, publish the
existing GitHub draft and mark it latest. Verify peeled tag/source, reviewed
notes, three asset bytes/digests, stable status and latest designation. Record
final evidence in #12, then request explicit closure approval when every
acceptance criterion is supported.

```sh
# Only after PyPI verification and separate publish/latest authorization:
gh release edit 1.0.0 --repo jeffshurtliff/sfdctrust --draft=false --prerelease=false --latest
```

For partial uploads, preserve the run and bytes and inspect exact-version JSON,
logs and each file's provenance before retrying anything. If no file exists,
seek approval to retry only the protected upload job with its retained same-run
artifact. If a matching subset exists, prepare separately approved recovery of
only missing original files. Never rebuild an accepted filename, move a public
tag, reuse a published version, or use `--skip-existing`. A verification failure
does not prove upload failed. For a bad production release, seek approval for a
yank and corrected version. See {doc}`ci-and-publishing` for the full recovery
procedure; withholding approval halts an unstarted deployment.
