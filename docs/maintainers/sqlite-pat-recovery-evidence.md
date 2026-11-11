# SQLite PAT recovery rehearsal evidence — November 11, 2026

This records local work for [issue #9](https://github.com/jeffshurtliff/sfdctrust/issues/9).
The initial working tree was clean on `test/9-rehearse-sqlite-pat-recovery-runbook`
at `d4dde2dc1e753c16ebecb3545a87370ece0acec2`, package version `0.2.0`.
The final changes are uncommitted. No SDK source, public API, dependency, or
version change was required. No GitHub issue was changed and nothing was pushed
or published.

The {download}`sanitized JSON record <evidence/sqlite-pat-recovery-2026-11-11.json>`
identifies the wheel and script by SHA-256, with interpreter/platform, UTC date,
runtime dependency versions, source state, expected and observed states, and
per-case request counts. It contains no credentials, headers, raw payloads, or
tenant/token/revision/attempt identifiers. All 13 cases passed using a new venv,
synthetic credentials, real disposable databases, mock HTTP, and a socket/DNS
guard in every process. The tested package files match the wheel byte for byte.

## Exact local reproduction commands

Run from the repository root. The offline wheelhouse below was already available
on the qualification workstation; other machines can prepare an equivalent
wheelhouse with the dependency versions in the JSON. Use a new environment path
for each independent qualification. Installation below used no package index.
The portable preparation procedure is in {doc}`sqlite-pat-store`.

```sh
poetry build --output /private/tmp/sfdctrust-issue9-dist
poetry run python -m venv /private/tmp/sfdctrust-issue9-final-venv
/private/tmp/sfdctrust-issue9-final-venv/bin/python -I -m pip install --no-index \
  --find-links /private/tmp/sfdctrust-0.2.0-release.qTLpEA/wheelhouse \
  /private/tmp/sfdctrust-issue9-dist/sfdctrust-0.2.0-py3-none-any.whl
/private/tmp/sfdctrust-issue9-final-venv/bin/python -I -m pip check
/private/tmp/sfdctrust-issue9-final-venv/bin/python -I tests/package_smoke.py
/private/tmp/sfdctrust-issue9-final-venv/bin/python -I tests/pat_recovery_rehearsal.py \
  --wheel /private/tmp/sfdctrust-issue9-dist/sfdctrust-0.2.0-py3-none-any.whl \
  --source-commit d4dde2dc1e753c16ebecb3545a87370ece0acec2 \
  --source-branch test/9-rehearse-sqlite-pat-recovery-runbook \
  --source-state "$(git status --short --branch)" \
  > /private/tmp/sfdctrust-issue9-evidence.json
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry check --lock --strict
poetry run twine check --strict /private/tmp/sfdctrust-issue9-dist/*
poetry run sphinx-build -W --keep-going -E -a -b html \
  docs /private/tmp/sfdctrust-issue9-html
```

## Local verification

- Offline repository suite: **603 passed, 15 skipped** on macOS, Python 3.12.7.
  Skips are platform-specific Windows cases; no live-service tests were run.
- Clean, non-editable wheel installation, dependency consistency check, existing
  installed-package CLI smoke walkthrough, and all 13 recovery cases passed.
- Ruff lint/format, Bandit, strict Poetry/lock validation, wheel/sdist build,
  and strict Twine metadata checks passed.
- The standard strict Sphinx build failed solely because sandbox DNS could not
  resolve `docs.python.org` to retrieve the Python intersphinx inventory. A strict
  full rebuild with a previously cached Python inventory passed without warnings;
  no warnings were suppressed and repository Sphinx settings were unchanged.

The exact offline documentation fallback was:

```sh
poetry run python - <<'PY'
from sphinx.application import Sphinx
app = Sphinx(
    srcdir='docs', confdir='docs',
    outdir='/private/tmp/sfdctrust-issue9-html-offline',
    doctreedir='/private/tmp/sfdctrust-issue9-doctrees-offline',
    buildername='html',
    confoverrides={'intersphinx_mapping': {'python': (
        'https://docs.python.org/3',
        '/private/tmp/sfdctrust-0.2.0-release.qTLpEA/python_objects.inv',
    )}},
    warningiserror=True, freshenv=True, keep_going=True,
)
app.build(force_all=True)
raise SystemExit(app.statuscode)
PY
```

## Remaining qualification

The workflow now runs this rehearsal in a clean wheel environment in each
existing hosted matrix job. Those updated hosted jobs have not run as part of
this local task. Maintainer review, committing/pushing the changes, verifying
hosted results, and updating/closing issue #9 remain. Issue #8's live-service
qualification is separate and was intentionally not run.

Faults were injected at the public store boundary before commit or after a
successful commit; abrupt process exit was real. This does not qualify physical
power loss, device durability, encrypted-volume configuration, or secure erasure.
No SDK defect was found and no new recovery API is proposed. Entire's Brain
brief lookup was unavailable because its lock location was outside the writable
sandbox; source inspection and executed checks supplied the evidence instead.
