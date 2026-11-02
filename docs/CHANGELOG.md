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

- Documented the My Trust Center operation, parameter, schema, authentication, and pagination contract,
  including verification limits and proposed implementation decisions.
- Exposed the package version as `sfdctrust.__version__` and added version regression tests.
- Added Sphinx documentation using the PyData theme (dark mode by default), MyST Markdown pages,
  autodoc reference pages, sphinx-favicon, and a Read the Docs configuration that installs from
  `poetry.lock`. Logos and favicons are enabled automatically once their files are added.

(unreleased-changed)=
### Changed

- Removed the redundant `sfdctrust.version` module; use `sfdctrust.__version__` instead.
- Corrected package metadata and README to target the My Trust Center API.
- Reduced direct runtime dependencies to HTTPX and Pydantic v2.
- Removed unused copied compatibility, model-construction, transformation, proxy, and async utilities,
  and unrelated constants; retained only package identity and API defaults.
- Fixed source-checkout version lookup to use the repository's `pyproject.toml`.

(unreleased-security)=
### Security

No unreleased security updates at this time.
