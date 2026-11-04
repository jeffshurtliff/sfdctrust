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

No unreleased additions at this time.

(unreleased-changed)=
### Changed

No unreleased changes at this time.

(unreleased-security)=
### Security

No unreleased security updates at this time.

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

[Unreleased]: https://github.com/jeffshurtliff/sfdctrust/compare/0.1.0...main
[0.1.0]: https://github.com/jeffshurtliff/sfdctrust/tree/0.1.0
