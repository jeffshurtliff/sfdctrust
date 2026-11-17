# Changelog

This project uses a curated changelog to highlight notable changes by release.
Detailed commit history remains available in GitHub.

The format is based on the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) guidelines,
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
(relnotes-unreleased)=
## [Unreleased]

(unreleased-added)=
### Added

- None yet.

(unreleased-changed)=
### Changed

- None yet.

(unreleased-fixed)=
### Fixed

- None yet.

(unreleased-security)=
### Security

- None yet.

(relnotes-1-1-0)=
## [1.1.0] - 2026-11-17

This release adds a read-only command-line interface for Salesforce My Trust
Center. It requires Python 3.12 or later and preserves the supported Python SDK
interfaces and versioned SQLite PAT stores from 1.0.0.

(release-1-1-0-added)=
### Added

- Installed `sfdctrust` and `python -m sfdctrust` launchers with five read commands:
  `tenants list`, `tenants get`, `status snapshot`, `events search`, and `events get`.
  Root, group, and command help and root `--version` work without credentials or
  network access.
- Reads use `SFDCTRUST_PAT` by default or an explicitly selected existing SQLite
  store. Store selection supports the default path, an explicit path, or an alias.
  The CLI validates arguments before accessing credentials and reports errors
  with sanitized diagnostics and documented exit codes.
- Tenant listing and event search return one page, including the continuation
  token when supplied by Salesforce. Search accepts 1–50 tenant IDs, an aware
  start and end time, and optional event-type filters. Text output summarizes
  results, and `--json` preserves the full SDK response, including field presence,
  affected scopes, and repeated scoped events.
- Static Open Graph previews for documentation links (#13).

(release-1-1-0-changed)=
### Changed

- Artifact validation checks the declared console entry point and exercises both
  installed launchers. Compatibility checks compare against published 0.2.0 and
  1.0.0 wheels and verify ready and pending SQLite stores and downstream typing.

(release-1-1-0-fixed)=
### Fixed

- A closed CLI output stream reports exit 1 without a Python shutdown traceback,
  including when opening the null device reuses the stdout descriptor.

(relnotes-1-0-0)=
## [1.0.0] - 2026-11-15

This release establishes the accepted public compatibility contract for the 1.x
series. It requires Python 3.12 or later and preserves the synchronous and
asynchronous API and supported versioned SQLite stores from 0.2.0.

(release-1-0-0-added)=
### Added

- Locked runtime dependency advisory audits, metadata-derived Python CI coverage,
  strict documentation checks for every PR, and gated Trusted Publishing preparation
  with separate wheel/sdist qualification and verified artifact transfer.
- Contributor guidance and maintainer CI/publishing runbooks.
- Public 1.x compatibility inventory and versioning/SQLite upgrade policy, with
  an offline published-wheel comparison and an installed-package downstream mypy CI gate.
- Repeatable offline installed-wheel SQLite PAT recovery rehearsal for pending
  attempts, retained replacements, and replacement loss across process exit.

(release-1-0-0-changed)=
### Changed

- Runtime Pydantic is pinned to `2.14.3`; HTTPX remains `>=0.28.1,<1.0.0`.
- Ruff no longer fails lint checks for line length (`E501`); the formatter still targets 130 characters.
- PAT recovery instructions show conditional reconciliation through public store
  operations and fresh-store verification before jobs resume, including backup retirement.

(release-1-0-0-fixed)=
### Fixed

- Sync and async tenant collectors now expose `list[Tenant]` correctly to
  downstream type checkers despite the resource method named `list`.
- Windows recovery rehearsal evidence reporting no longer requests the local
  hostname through Python's platform helpers while the socket guard is active.
- Source distributions exclude nested pytest, mypy, and Ruff caches; artifact
  inspection rejects those generated directories.

(release-1-0-0-security)=
### Security

- None yet.

(relnotes-0-2-0)=
## [0.2.0] - 2026-11-08

This release adds a built-in SQLite PAT store for synchronous clients. It
requires Python 3.12 or later.

(release-0-2-0-added)=
### Added

- Built-in synchronous `SQLitePATStore` for durable single-host PAT refresh,
  with private file protection on macOS, Windows, and Linux, versioned storage,
  and support for the existing persistence-only recovery API.
- Installed-package initialization command, `python -m sfdctrust.pat_store init`,
  with hidden input, optional environment input, custom paths, and named aliases.
- Offline SQLite process and crash tests, with hosted tests and installed-wheel
  checks on macOS, Windows, and Ubuntu.

(release-0-2-0-changed)=
### Changed

- Getting Started uses the built-in SQLite store and shows how to reopen it
  with the default location, a custom path, or an alias. The authentication
  reference documents the transition from an example database to a fresh store.

(release-0-2-0-fixed)=
### Fixed

- `SQLitePATStore` can open and initialize stores under Windows directories
  whose ACL grants `OWNER RIGHTS` to a verified owner, including Python's
  private temporary directories.

(release-0-2-0-security)=
### Security

- SQLite stores enforce ownership and private permissions/ACLs, check file
  identities, and reject unsafe linked paths. PATs remain plaintext in SQLite;
  a private encrypted local volume is required.

(relnotes-0-1-0)=
## [0.1.0] - 2026-11-04

First stable release of the unofficial Python SDK for the Salesforce My Trust
Center API. Requires Python 3.12 or later.

(release-0-1-0-added)=
### Added

- Synchronous `TrustCenterClient` and native asyncio `AsyncTrustCenterClient`
  for listing authorized tenants, retrieving status snapshots, searching
  events, and reading event timelines and tenant history.
- Typed responses that preserve tenant scopes, repeated event IDs, timestamp
  offsets, and unknown response fields.
- Single-page, lazy, and collecting methods for tenant lists and event search,
  with page limits and cursor-cycle detection.
- Bounded timeouts and configurable retries for documented read operations,
  with bounded `Retry-After` handling for HTTP 429 and 503.
- Explicit PAT authentication or opt-in loading from `SFDCTRUST_PAT`, plus
  explicit refresh for compatible sync and async stores. A successful refresh
  immediately revokes the old PAT. The clients can retry persistence of a
  retained replacement without making another refresh request.
- Public exceptions for configuration, authentication, network, rate-limit,
  pagination, and API response failures.
- Installation, authentication, and usage guides, with a public API reference.

(release-0-1-0-changed)=
### Changed

- For users of earlier development builds, use `sfdctrust.__version__` in place
  of the removed `sfdctrust.version` module. The version is read from installed
  metadata or from `pyproject.toml` in a source checkout.
- The direct runtime dependencies are HTTPX and Pydantic v2.

[Unreleased]: https://github.com/jeffshurtliff/sfdctrust/compare/1.1.0...main
[1.1.0]: https://github.com/jeffshurtliff/sfdctrust/compare/1.0.0...1.1.0
[1.0.0]: https://github.com/jeffshurtliff/sfdctrust/compare/0.2.0...1.0.0
[0.2.0]: https://github.com/jeffshurtliff/sfdctrust/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/jeffshurtliff/sfdctrust/tree/0.1.0
