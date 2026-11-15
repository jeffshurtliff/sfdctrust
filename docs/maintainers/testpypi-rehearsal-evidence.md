# TestPyPI rehearsal evidence

The separately authorized issue #11 rehearsal passed on **2026-11-14**. This
qualifies the CI/publishing workflow on TestPyPI. Production release execution and
issue #8's exact-release live-service qualification remain separate gates.

The [sanitized evidence](evidence/testpypi-rehearsal-2026-11-14.json) retains exact
source, artifact hashes, workflow/job results, signed certificate claims, installed
compatibility results, audit disposition and reproduction commands. This report
was written after qualification; it is not part of the uploaded source snapshot.

## Source and authorization

- Reviewed main: `6b9b89f7ce94199a4c83c67734ff97555053c0ae`, version `1.0.0.dev0`.
- Rehearsal branch: `release/testpypi`.
- Rehearsal commit: `b004853c90ddb72cebd1f1d01eaea4508e255037`.
- Rehearsal version: **`1.0.0rc2026111401`**. The commit changed only
  `[project].version` in `pyproject.toml`; main's version and source are unchanged.
- The maintainer explicitly approved preparation, the TestPyPI publisher binding,
  the protected environment, rehearsal documentation activation, and then the
  exact source/version/file hashes plus environment approval for upload.

The `testpypi` environment requires reviewer `jeffshurtliff`, restricts deployments
to the exact `release/testpypi` branch, and disables administrator bypass. The
maintainer explicitly allowed self-approval for this TestPyPI environment. That
decision does not configure or authorize a production environment.

## Hosted workflow and documentation

[Release run 43632216296, attempt 1](https://github.com/jeffshurtliff/sfdctrust/actions/runs/43632216296)
passed **13 jobs**; the production PyPI job was **skipped**. The manual dispatch
used `destination=testpypi`, `upload=true`, and the exact rehearsal SHA/version.
The environment gate was approved only after downloading this run's artifact and
independently matching both files to the maintainer-approved dry-run manifest.

| Runner / Python | Offline suite |
| --- | --- |
| macOS / 3.12 | 630 passed, 15 skipped |
| Windows / 3.12 | 634 passed, 11 skipped |
| Ubuntu / 3.12 | 627 passed, 18 skipped |
| Ubuntu / 3.13, 3.14, 3.15, each | 624 passed, 21 skipped |

The existing native permission/process and installed-wheel checks, public
compatibility/downstream typing, Ruff lint/format, Bandit, strict Twine and strict
Sphinx all passed. The locked runtime audit covered 11 packages, with no known
vulnerabilities and no exceptions. Platform/tooling skips remain explicit.

[Read the Docs build 35895397](https://app.readthedocs.org/projects/sfdctrust/builds/35895397/)
passed at the same exact rehearsal SHA. The
[served rehearsal documentation](https://sfdctrust.readthedocs.io/en/release-testpypi/)
was checked for the expected version. The default/stable documentation versions
were not changed.

## Published files and verified provenance

The [TestPyPI prerelease](https://test.pypi.org/project/sfdctrust/1.0.0rc2026111401/)
contains exactly these two files; neither is yanked:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sfdctrust-1.0.0rc2026111401-py3-none-any.whl` | 55824 | `dd6cf52e1553793c94824ba80b7321dbcf8e1c154d7e7668d2a85f167c229245` |
| `sfdctrust-1.0.0rc2026111401.tar.gz` | 201130 | `bd23438f6844e9dba080479ece2766810fa2cb2d37a414f3028730a1ce288b5e` |

The approved dry run, upload-run artifact, downloaded hosted bytes and fresh
TestPyPI release JSON all matched these hashes and sizes. The publishing job
downloaded the same-run immutable artifact ID, rechecked its manifest, and
uploaded the exact bytes without rebuilding.

Both files have a cryptographically verified PyPI publish attestation
(`https://docs.pypi.org/attestations/publish/v1`). Locked `pypi-attestations`
verified signatures, transparency proofs and distribution identity. The report
also verified the publisher repository, `release.yml`, environment `testpypi`,
signed source SHA/ref, manual trigger and exact run/attempt. The signed issuer
was GitHub Actions. Authentication used OIDC Trusted Publishing without a
long-lived upload token.

The original pending publisher became the project's normal Trusted Publisher
through the first approved upload. No production publisher was registered.

## Clean installation and retained artifacts

Hosted wheel and sdist were installed separately in fresh non-editable Python
3.12 environments on Ubuntu. Both passed `pip check`, installed CLI/SQLite smoke,
the accepted public inventory/behavior checker, and strict downstream mypy 1.20.2.
Each behavioral phase used synthetic credentials, mocked HTTP, disposable stores,
and a socket/DNS guard; both compatibility reports recorded **zero unexpected
network attempts**. The sdist-built wheel matched the published wheel's SHA-256.
Dependency retrieval and registry/provenance requests were separate online steps.

The workflow retains these artifacts:

| Artifact | ID | Archive SHA-256 |
| --- | --- | --- |
| `approved-release` | 14128337940 | `8c5118ec240c0e2b594ec20c36651272e6e020fe687a204a839b9c429e149787` |
| `registry-verification` | 14127939366 | `91f9b06640b3e782adf36ff3b4b7da922c728d7ca335542d7dd268d39ae6f216` |

The downloaded archives matched GitHub's artifact digests. Local extracted
evidence is under `/private/tmp/sfdctrust-testpypi-upload-43632216296/`; scratch
files and hosted artifact retention are temporary. The linked JSON durably
records the verified results and provenance claims. Public per-file provenance
remains available through TestPyPI's Integrity API.

To repeat the verification against the same published files, run from a checkout
of the recorded rehearsal source with the locked Python 3.12 development tools,
using a fresh directory:

```sh
gh run download 43632216296 --repo jeffshurtliff/sfdctrust \
  --name approved-release --dir /tmp/sfdctrust-rehearsal-final
poetry run python tools/ci/registry.py --destination testpypi \
  --bundle /tmp/sfdctrust-rehearsal-final \
  --ref refs/heads/release/testpypi --run-id 43632216296
```

The command performs online digest/provenance verification and dependency
retrieval, followed by network-blocked behavioral checks. Do not repeat the upload
to reproduce verification.

No live Salesforce qualification, independent operator-recovery gate, stable
version/tag, production upload or main-branch merge was performed. Accepted #9/#10
evidence remains in effect; #8 still requires both separately authorized live
phases for the exact wheel intended for stable 1.0.0.
