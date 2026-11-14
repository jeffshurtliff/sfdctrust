# Contributing to sfdctrust

`sfdctrust` is an unofficial, community-maintained Python SDK for the Salesforce
**My Trust Center API**. Contributions should keep the SDK predictable, typed,
secure, and useful without Salesforce client libraries or AI frameworks.

Read [AGENTS.md](AGENTS.md) for architecture, API, security, and agent guidance.
The [maintainer documentation](https://sfdctrust.readthedocs.io/en/latest/maintainers/index.html)
contains the detailed qualification and release procedures; its source is in
[`docs/maintainers/`](docs/maintainers/).

## Propose and scope a contribution

1. Open or reference a GitHub issue using the matching template in
   `.github/ISSUE_TEMPLATE/`. Include expected behavior, affected versions, and
   a minimal reproduction with synthetic data. Report sensitive vulnerabilities
   through GitHub's private security reporting when available, rather than a public issue.
2. Discuss public API changes, credential lifecycle changes, support-policy changes,
   and significant new dependencies with the maintainer before implementing them.
3. Start a focused branch from current `main`; use a descriptive category such as
   `feature/`, `fix/`, `docs/`, `test/`, `ci/`, or `security/`, followed by the issue
   number and summary, for example `ci/123-release-validation`. Follow any
   applicable tool-specific prefix requirements for newly created task branches.
   Preserve an existing task branch and all unrelated working-tree changes.
4. Keep code, behavioral tests, relevant documentation, and changelog changes together.
   Avoid unrelated refactors and generated files.

Shared maintenance branches use purpose-based names independent of the
contributor, AI agent, issue number, or release version. The reusable TestPyPI
rehearsal branch is `release/testpypi`, whether prepared by a human, Codex,
Claude Code, or Antigravity/Gemini. Identify each rehearsal by its approved commit
SHA, unique prerelease version, and verified artifact manifest. See the
[publishing runbook](docs/maintainers/ci-and-publishing.md) for the matching
workflow/environment restrictions and separate authorization requirements.

Do not change versions, supported Python policy, tags, repository settings,
publisher registrations, or registry uploads without explicit maintainer direction.
Agents leave work uncommitted unless instructed otherwise. Commit messages use
past tense, mention the file when changing only one file, and reference the issue,
for example `Updated contributor guidance (#123)`.

## Set up the development environment

Python 3.12 is the minimum supported version. The metadata currently advertises
3.12, 3.13, 3.14, and 3.15; CI derives its matrix from those classifiers, with
minimum-version tests on Linux, macOS, and Windows. Do not silently narrow support.
Use Python 3.12 for the complete audit and attestation tooling environment.

```sh
python3.12 -m pip install 'poetry==2.5.1'
poetry env use python3.12
poetry check --lock --strict
poetry install --with docs --no-interaction
```

`pyproject.toml` declares dependencies and `poetry.lock` locks all groups.
Regenerate the lockfile with Poetry when changing dependencies; never edit it by
hand. Audit and attestation tools belong to development tooling, not runtime
requirements. Documentation dependencies are in the optional `docs` group.

Dependency retrieval and advisory queries require networking. Behavioral
qualification is a separate offline phase:

```sh
poetry run python tests/offline/run.py -m pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run bandit -r src -q
poetry run python tools/ci/audit.py --output /tmp/sfdctrust-audit.json
poetry build
poetry run twine check --strict dist/*
poetry run python tools/ci/artifacts.py inspect --manifest /tmp/sfdctrust-release-manifest.json
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

Use a fresh output directory for builds if `dist/` contains older versions. The
artifact inspector deliberately rejects unexpected files. See the
[CI and publishing runbook](docs/maintainers/ci-and-publishing.md) for separate
clean wheel/sdist installations, downstream typing, workflow validation, and
publishing preparation. The
[compatibility runbook](docs/maintainers/compatibility-qualification.md) compares
the published baseline and candidate in isolated, non-editable installations.

## Code, tests, and security

- Follow the existing `src/` layout, resource-oriented sync/async design, Ruff
  configuration, type hints, and reStructuredText docstrings. Document observable
  public behavior, parameters, returns, errors, and edge cases.
- Preserve module headers when editing Python. Use the maintainer's name and the
  actual generating model in `Last Modified`; honor applicable local addenda.
  Do not update unrelated dates or invent authorship.
- Verify changed endpoints against current official My Trust Center documentation.
  Never substitute legacy Trust Status API behavior. Local vendor references, if
  available, supplement the official reference and are not distributable source.
- Use deterministic HTTPX mock transports, synthetic PATs and tenants, and
  disposable stores. Run native permissions and spawned-process tests on their
  supported operating systems. The offline wrapper blocks outbound connections
  and DNS in Python children while permitting loopback/OS IPC.
- Never discover real credentials in `.env` or secret files, contact Salesforce,
  or rotate a real PAT as part of ordinary testing. Live qualification requires
  separate explicit authorization and remains owned by issue #8.
- Preserve tenant-scoped visibility, status-event scopes and duplicates, bounded
  retries/timeouts, and caller-owned HTTP client lifecycle. Never blindly retry
  ambiguous PAT refreshes or disclose PATs in errors, logs, examples, or artifacts.
- Preserve the [accepted compatibility policy](docs/reference/compatibility.md),
  deferred public timeout configuration, single-host SQLite boundary, and
  retirement of migration from legacy unversioned databases.
- Keep runtime dependencies small. Optional integrations must not become core
  requirements. Review both direct and transitive advisory findings; do not
  suppress audit-service failures or add permanent blanket ignores.

## Documentation and pull requests

Use Markdown/MyST for narrative pages, single backticks for inline literals, and
reStructuredText for Sphinx index/reference files and docstrings. Add pages to the
relevant toctree. Strict Sphinx warnings and nitpicky cross-references must pass;
do not hide warnings to make CI green. See
[documentation maintenance](docs/maintainers/documentation.md).

Describe current public behavior in user documentation. Put maintenance changes
and release history in `docs/CHANGELOG.md`. Keep examples copyable and synthetic;
do not describe planned methods as implemented. Respect the MIT license and
check attribution before copying third-party material.

In the PR description, explain the concrete problem, resulting behavior,
compatibility implications, and actual checks run, including skips and platform
limits. Link the issue and any qualification evidence. Use the corresponding
issue/PR labels, including `codex`, `claude`, or `gemini` for agent-assisted work
when available. Do not claim hosted CI, Read the Docs, or registry verification
from local checks alone. Maintainer review is required before merging.

Keep build output, caches, virtual environments, credentials, local vendor
documents, and private data out of commits and distribution archives. Publishing
is a separately authorized maintainer operation with protected environments and
Trusted Publishing; a passing PR never authorizes an upload.
