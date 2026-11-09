# Qualify an installed wheel against My Trust Center

This is the read-only phase of the
[v1.0.0 qualification gate](https://github.com/jeffshurtliff/sfdctrust/issues/8).
Use a maintainer-authorized test account and record each result against the
specific wheel tested. Follow {doc}`pat-rotation-qualification` separately
when authorized to rotate a dedicated test PAT.

## Build and verify the candidate

From the checkout, record the source commit and working-tree state. The
commands below use a fresh directory and Python 3.12. If qualifying a
previously built candidate, set `qual_wheel` to that exact wheel and record
its source commit instead of building a replacement.

```sh
qual_repo="$(pwd -P)"
git rev-parse HEAD
git status --short --branch
qual_dir="$(mktemp -d "${TMPDIR:-/tmp}/sfdctrust-qualification.XXXXXX")"
poetry build --format wheel --output "$qual_dir"
qual_wheel="$(find "$qual_dir" -maxdepth 1 -name 'sfdctrust-*.whl' -print)"
python3.12 -m venv "$qual_dir/venv"
qual_py="$qual_dir/venv/bin/python"
"$qual_py" -I -m pip install "$qual_wheel"
"$qual_py" -I -m pip check
(
  cd "$qual_dir" &&
  "$qual_py" -I - "$qual_wheel" <<'PY'
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
import platform
import sys
import sysconfig
from datetime import date

import sfdctrust

wheel = Path(sys.argv[1])
purelib = Path(sysconfig.get_path('purelib')).resolve()
if not Path(sfdctrust.__file__).resolve().is_relative_to(purelib):
    raise SystemExit('FAIL installation: SDK import is outside the candidate environment.')
with wheel.open('rb') as stream:
    print('SHA-256', file_digest(stream, 'sha256').hexdigest())
print('Wheel', wheel.name)
print('Installed sfdctrust', version('sfdctrust'))
print('Python', platform.python_version(), 'Platform', platform.system(), platform.machine())
print('Local run date', date.today().isoformat())
print('PASS installed wheel import')
PY
)
(cd "$qual_dir" && "$qual_py" -I "$qual_repo/tests/package_smoke.py")
```

The last command reuses the offline installed-wheel check with synthetic PATs
and mock HTTP. The read-only procedure below is a separate opt-in command.
On Windows use the candidate environment's `venv\Scripts\python.exe` and the
same script arguments.

## Run the read-only check

In an interactive terminal, run the following and enter the approved PAT at
the hidden prompt.

```sh
(cd "$qual_dir" && "$qual_py" -I "$qual_repo/tests/live_read_smoke.py" --live)
```

If a trusted launcher has already injected the PAT into a specific
environment variable, pass only the variable's **name**.

```sh
(cd "$qual_dir" && "$qual_py" -I "$qual_repo/tests/live_read_smoke.py" --live --from-env QUALIFICATION_PAT)
```

Both clients sample tenant listing with page size 1 and follow one
continuation when available. The script retrieves detail and embedded history
for the first sampled tenant, validates both status buckets, and searches for
all event types across the sampled tenant IDs in the preceding 90 days.
Both clients use the same minute-aligned UTC search window and `en-US` locale.
Search uses page size 1 and follows one continuation with the original
arguments intact. It uses the first search result for event detail, falling
back to tenant history or the status snapshot when needed. A timeline is
validated when present. SDK models validate the response structures and
tenant scopes. Counts include repeated scoped events.

Each client reports its own outcomes. An empty successful read passes with
a zero count. A missing continuation, missing ID in sampled data, or empty
history or timeline can skip coverage. A skip caused by a failed prerequisite
is identified in its reason. A cursor rejected by the API or repeated by the
server fails the continuation check. The script disables SDK retries and
never restarts pagination. Exit 0 means the attempted reads passed, possibly
with skips. Exit 1 indicates failure, and exit 2 indicates invalid invocation.

Record only the output outcomes, counts, and fixed reasons. If an observed
status or schema differs from {doc}`../API_CONTRACT`, record the operation and
sanitized discrepancy. For example, report a schema validation failure by
operation name. Keep PATs, headers, cursors, IDs, URLs with request parameters,
raw responses, private incident information, and store contents out of the
record. Results describe only the PAT's authorized scope.

## Evidence record

Live qualification is pending until the maintainer records the results.
Review and disposition data-dependent skips before marking the release gate
complete. Repeat this procedure for the final release candidate.

```text
Commit / working-tree state:
Wheel filename / SHA-256:
Installed SDK / Python / platform / local date:
Phase A sync — PASS / FAIL / SKIP by operation:
Phase A async — PASS / FAIL / SKIP by operation:
Skipped coverage and reason / contract discrepancies:
Phase B (separate run) — baseline / refresh / metadata / replacement read /
  old PAT rejected (401) / fresh-process read:
Overall phase A / phase B — PASS / FAIL / pending:
```
