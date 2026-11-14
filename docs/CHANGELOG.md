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

- Locked runtime dependency advisory audits, metadata-derived Python CI coverage,
  strict documentation checks for every PR, and gated Trusted Publishing preparation
  with separate wheel/sdist qualification and verified artifact transfer.
- Contributor guidance and maintainer CI/publishing runbooks.
- Public 1.x compatibility inventory and versioning/SQLite upgrade policy, with
  an offline published-wheel comparison and an installed-package downstream mypy CI gate.
- Repeatable offline installed-wheel SQLite PAT recovery rehearsal for pending
  attempts, retained replacements, and replacement loss across process exit.

(unreleased-changed)=
### Changed

- Ruff no longer fails lint checks for line length (`E501`); the formatter still targets 130 characters.
- PAT recovery instructions show conditional reconciliation through public store
  operations and fresh-store verification before jobs resume, including backup retirement.

(unreleased-fixed)=
### Fixed

- Sync and async tenant collectors now expose `list[Tenant]` correctly to
  downstream type checkers despite the resource method named `list`.
- Windows recovery rehearsal evidence reporting no longer requests the local
  hostname through Python's platform helpers while the socket guard is active.

(unreleased-security)=
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

[Unreleased]: https://github.com/jeffshurtliff/sfdctrust/compare/0.2.0...main
[0.2.0]: https://github.com/jeffshurtliff/sfdctrust/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/jeffshurtliff/sfdctrust/tree/0.1.0
