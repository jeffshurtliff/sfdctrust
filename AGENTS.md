# AGENTS.md — sfdctrust

This is the canonical, tool-agnostic guidance for coding agents (including Codex) working on **sfdctrust**. 
Apply it alongside the maintainer's current task, repository documentation, local-only instructions
(e.g. `AGENTS.local.md` or `local/AGENTS.md`), and any more specific instructions in nested directories. 
Keep any tool-specific and/or local companion files short and consistent with this file.

**Repository:** https://github.com/jeffshurtliff/sfdctrust  
**Distribution/import name:** `sfdctrust`  
**Project status:** Under development; the repository is initially private and is intended to become public 
when ready. Do not change repository visibility or publish releases without explicit maintainer authorization.

## Purpose and product boundaries

`sfdctrust` is a standalone Python SDK for the **Salesforce My Trust Center API**. Its purpose is to make 
authorized Salesforce tenant status and event data easy to retrieve, understand, and integrate into Python 
applications, scheduled monitoring, ITSM systems, and AI agents.

- Target the *My Trust Center API*, **not** the legacy Salesforce Trust Status API. Do not copy legacy API 
  endpoints, authentication assumptions, or response fields into this SDK.
- The SDK covers data visible to the caller's authorized tenants, not every Salesforce instance, product, 
  or service. Never infer global Salesforce health from an empty or partial response.
- The core package must be useful independently of Salesforce client libraries, CLI frameworks, 
  AI frameworks, and MCP.
- Primary qualities: predictable API, clear documentation, strong typing, secure authentication, dependable 
  network behavior, testability, and minimal unnecessary complexity.
- Treat API operations and capabilities described below as **design goals**, not proof that the methods or 
  files are already implemented. Inspect the repository before modifying it.

## Sources of truth

Read the relevant official Salesforce documentation before implementing or changing endpoint behavior:

- API overview: https://developer.salesforce.com/docs/mytrust-api/overview.html
- Getting started, pagination, and status snapshot behavior: https://developer.salesforce.com/docs/mytrust-api/get-started.html
- PAT authentication and refresh: https://developer.salesforce.com/docs/mytrust-api/authentication.html
- API reference: https://developer.salesforce.com/docs/mytrust-api/api-reference

Confirm HTTP methods, URL paths, query parameters, field names, pagination tokens, accepted values, 
error bodies, and authentication requirements against the **current** official reference. Do not invent 
endpoints, enums, request arguments, or response structures based on the proposed SDK interface. If 
documentation is unavailable, isolate assumptions and say what remains unverified rather than presenting 
guesses as facts.

For tooling conventions, treat the repository's actual `pyproject.toml`, dependency lockfile, CI 
configuration, and `CONTRIBUTING.md` as authoritative. This file expresses architectural intent; 
it is not permission to replace working repository decisions or broaden a task.

## Agent workflow and scope

1. Read this file, inspect `git status`, and examine the relevant source, tests, configuration, and 
   documentation before making changes. Preserve existing work and uncommitted user changes.
2. Determine the smallest implementation that fulfills the maintainer's request; identify affected public 
   contracts, security implications, and relevant tests.
3. Reuse existing patterns when reasonable. Prefer a focused change over reorganizing unrelated modules. 
   Explain and justify material architecture or dependency changes.
4. Make implementation and regression tests together. Update public documentation and changelog when 
   behavior changes.
5. Run applicable local checks. Report **what actually ran**, results, skipped checks, known limitations, 
   and remaining decisions. Do not claim CI passed unless its run is verified.
6. Leave edits uncommitted unless explicitly asked to commit. Do not push, merge, tag, release, upload 
   to PyPI, change GitHub settings, or make the repository public without explicit authorization.

Do not treat speculative feature ideas or example interfaces as completed work. Where a task is 
underspecified, make a conservative, reversible choice when safe; seek a maintainer decision for public 
API breaking changes, credential lifecycle automation, new major dependencies, or externally visible 
changes to behavior.

## Architectural direction

**Use a lightweight, resource-oriented, object-oriented SDK**, not a collection of unrelated HTTP helper 
functions and not a large inheritance-driven framework.

Preferred public experience (illustrative; validate names before implementing):

```python
from sfdctrust import TrustCenterClient

with TrustCenterClient.from_env() as client:
    tenants = client.tenants.list_all()
    status = client.status.snapshot()
    events = client.events.search(event_type="incident")
```

- Provide a clear synchronous `TrustCenterClient` as the primary entry point. It owns configuration, authentication 
  integration, the HTTP connection lifecycle, and access to resource objects.
- Group domain operations behind discoverable resources such as `client.tenants`, `client.status`, and `client.events`, 
  where supported by the actual API.
- Prefer descriptive, typed methods (`list`, `list_all`, `snapshot`, `search`, `get`, etc.) to forcing consumers to 
  construct endpoint strings or raw query parameters. Names and signatures must match real endpoint semantics.
- Support context management and explicit `close()` behavior; avoid I/O during ordinary import or object construction 
  unless the contract explicitly requires it.
- Centralize request transport, error translation, timeouts, retry rules, response decoding, and authentication 
  handling. Avoid duplicating these in each resource.
- Allow injection of a configured HTTP client/transport for offline tests and advanced integrations. Carefully 
  define ownership so the SDK does not unexpectedly close caller-owned clients.
- Prefer HTTPX for its synchronous and asynchronous support and connection pooling, subject to existing 
  dependency decisions.
- Plan for `AsyncTrustCenterClient` with a comparable public interface, but 
  **do not delay a correct, well-tested synchronous MVP** merely to provide async parity. Share pure logic and 
  models rather than forcing an overly complex class hierarchy.
- Favor composition and narrow modules. Do not introduce frameworks, registries, factories, or abstract base 
  classes without a demonstrated use case.

### Proposed organization (adapt to the existing repository)

```text
src/sfdctrust/
    __init__.py
    _client.py
    _async_client.py       # When async support is implemented
    _transport.py
    _auth.py
    _constants.py
    _exceptions.py
    _version.py
    models/
        __init__.py
        tenants.py
        events.py
        status.py
    resources/
        __init__.py
        tenants.py
        events.py
        status.py
    integrations/          # Optional adapters only
        __init__.py
    py.typed
tests/
    integration/           # Opt-in for live API access
        __init__.py
    unit/
        __init__.py
    __init__.py
    conftest.py
examples/
docs/
    _build/
    _static/
    _templates/
    getting-started/
        index.rst
        installation.md
        overview.md
        quickstart.md
    guides/
        index.rst
    maintainers/
        index.rst
    reference/
        client.rst
        exceptions.rst
        index.rst
    CHANGELOG.md
    conf.py
    index.md
```

This is a **target layout**, not a mandate to create all files. Avoid empty scaffolding, unused classes, 
and speculative abstractions. Keep public imports intentional and stable; underscore-prefixed modules are 
implementation details.

## Data models and public contracts

- Prefer Pydantic v2 models for public API response types when implementing typed responses. Align model field 
  aliases, optionality, and nested structures with real Salesforce payloads, and document any normalization.
- Use explicit type hints on public classes, functions, parameters, and returns. Include `py.typed` when shipping 
  a typed package.
- Expose predictable model attribute access and JSON-compatible serialization (`model_dump(mode="json")` for 
  Pydantic). Use timezone-aware UTC datetimes internally where normalization is appropriate; do not silently 
  discard Salesforce's original timezone information.
- Handle additional unknown Salesforce response fields without silently corrupting known fields. Decide 
  deliberately whether to preserve extras and cover that choice with tests.
- Avoid unpredictable public return unions such as `dict | httpx.Response | Model` controlled by multiple boolean 
  flags. If raw responses are necessary, provide an intentional, separately documented mechanism.
- Define and document a small exception hierarchy for configuration errors, authentication failures, rate limits, 
  network/timeouts, malformed responses, and other API failures. Preserve useful non-sensitive context such as 
  status code and request ID when available.
- Keep a single default response contract. Avoid returning `None`, an empty list, or an empty dictionary 
  interchangeably to represent errors.
- Treat backwards compatibility seriously once a version is released. Any proposed breaking change requires 
  explicit attention and release/documentation planning.

## API semantics that must be preserved

- Tenant listing is paginated. Honor `nextPageToken` and use the documented `pageToken` query parameter for 
  subsequent pages. Provide a way to retrieve an individual page and, when appropriate, a lazy iterator 
  or `list_all()` convenience method.
- Preserve the My Trust Center status snapshot's `ongoing` and `upcoming` grouping and its documented event 
  categories. A higher-level convenience view may be added without discarding the original structure.
- **Never blindly deduplicate status events by `eventId`.** A patch release may appear more than once for 
  different affected tenant scopes or stages.
- Retain event-to-tenant scope, event update timelines, and distinctions between ongoing, upcoming, past, 
  and informational events.
- Preserve documented locale behavior (BCP 47 locale values) and let callers opt into localization.
- A missing event, empty status bucket, or absent tenant does **not** establish that all Salesforce services 
  are healthy. Access is limited by the PAT's tenant permissions and by the My Trust Center product coverage.
- For monitoring outputs, consider an explicit `retrieved_at` UTC timestamp so consumers and AI tools can 
  distinguish observed/cached data from current status. Do not claim fresh status when serving cached results.

## Authentication, token lifecycle, and security

The My Trust Center API uses a **personal access token (PAT)** as a Bearer credential; it is not an ordinary 
Salesforce org OAuth flow. PATs are secrets.

- Support an explicitly supplied PAT and a documented, opt-in environment-based configuration path 
  (proposed name: `SFDCTRUST_PAT`). If an existing project configuration convention exists, reconcile it before 
  fixing a public environment variable name. Document precedence and fail clearly when no credential is supplied.
- Never log, print, serialize, include in exceptions, commit, or expose PAT values, Authorization headers, full 
  credential-bearing URLs, or token-refresh response secrets.
- Do not read local `.env` files, private secrets, or credential files to discover real credentials without 
  explicit permission. `.env.example` may contain placeholders only. Avoid copying personal tenant IDs or incident 
  data into tests and public examples when synthetic data will work.
- Do not disable TLS verification as a default. Explicit insecure test behavior, if ever supported, must be visibly 
  opt-in.
- Do not silently refresh a PAT on every `401`, and do not automatically create/revoke tokens in My Trust Center. 
  A `401` may indicate a revoked, expired, or otherwise invalid PAT.
- Salesforce allows only one active PAT. UI-issued PAT lifetimes are 7, 15, or 30 days; refreshed PATs have their 
  own documented lifetime rules, and the complete token lineage is limited to 365 days. Consult the official 
  documentation for current rules.
- **PAT refresh is non-idempotent.** On success the previous PAT is immediately revoked and the replacement secret 
  is returned once. Implement refresh only with a clearly specified persistence/coordination strategy; never assume 
  that storing the new PAT in the current process's environment updates a parent process or secret manager.
- Never blindly retry refresh after a timeout or ambiguous server failure. Follow Salesforce's documented recovery 
  procedure (including checking whether the old PAT still works with a harmless read before considering another 
  refresh). Account for concurrent processes that share one PAT.
- Rate-limit handling must be endpoint-specific. In particular, do not assume PAT refresh `429` responses 
  include `Retry-After` or JSON: use the behavior documented for that endpoint and bounded exponential backoff 
  with jitter where appropriate.
- Use bounded timeouts and bounded retries for transient read requests. Retry only operations known to be safe, 
  and never use a generic retry policy for side-effecting calls.
- Keep all agent-accessible operations read-only by default. Do not expose PAT secrets, credential rotation, 
  or other sensitive lifecycle operations as tools.

## Integration and AI-agent readiness

**Build a high-quality Python SDK first.** AI and automation interfaces should wrap the same public SDK rather 
than fork endpoint logic.

- Public methods should have discoverable names, well-defined arguments, type annotations, and concise descriptions 
  suitable for IDEs and tool-schema generation.
- Prefer structured, serializable outputs and clear error types over human-formatted strings as the only result.
- Keep MCP and other agent frameworks as optional dependencies/extras (for example, `sfdctrust[mcp]`). Core imports 
  and installation must not require an AI framework.
- When MCP is implemented, verify the supported version of the official Python MCP SDK and its current APIs; do 
  not assume that older `FastMCP` code remains valid. Prefer the supported `MCPServer` interface for MCP v2 
  where applicable.
- Expose focused, read-only tools (for example: listing authorized tenants, retrieving tenant status, searching 
  events, and reading event timelines). Validate inputs and enforce reasonable response-size limits.
- Keep transport/server setup, agent-specific descriptions, and agent policy decisions inside the adapter. 
  The SDK must remain useful without MCP.
- Return trustworthy provenance and freshness information where practical; avoid inventing incident impact, 
  resolution, current availability, or tenant coverage.
- Do not send Salesforce data or PATs to external AI services as an automatic side effect of an SDK call.

## Development environment and coding conventions

- Inspect `pyproject.toml` and CI before assuming Python versions, packaging backend, or exact commands. 
  Do not narrow or expand supported Python versions without a deliberate maintainer decision.
- Prefer a `src/` package layout, standardized `[project]` metadata in `pyproject.toml`, and Poetry for 
  development/dependency management if consistent with the repository. Maintain one authoritative dependency 
  declaration and regenerate any lockfile using its package manager; never hand-edit generated lockfiles.
- Prefer pytest for testing and Ruff for formatting/linting, respecting existing repository configuration rather 
  than imposing an unrelated style. For new setup, use straightforward PEP 8 conventions and modern type syntax 
  compatible with the project's minimum Python version.
- Maintain clear, narrowly scoped functions. Avoid unnecessary abstractions, global state, import-time network 
  operations, and mutable shared configuration.
- Use PEP 257 docstrings. Prefer Sphinx-compatible reStructuredText field lists (`:param name:`, `:returns:`, 
  `:raises ExceptionType:`) for public methods, consistent with the maintainer's other Python projects. Describe 
  observable behavior, edge cases, and exceptions; avoid repeating obvious type hints.
- Respect existing module header conventions, if present. Do not invent authorship, model identifiers, or edit 
  unrelated modification dates.
- Do not reformat unrelated modules. Keep generated `dist/`, `*.egg-info/`, caches, coverage reports, and built 
  documentation out of tracked source changes.
- Justify new runtime dependencies in terms of user value, maintainability, security, and compatibility. Use 
  optional extras for integrations that not every SDK user needs.

Once the relevant dependencies are configured, typical local checks are:

```sh
poetry install
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry build
```

These commands are **illustrative** until the repository's actual toolchain is verified. If tools are absent, 
report that fact; do not install or reconfigure substantial tooling as part of an unrelated task.

## Testing and validation

- Add focused unit tests with every behavior change and regression tests for bug fixes. Unit tests must be 
  deterministic, offline, and never require real PATs or live Salesforce tenants.
- Use HTTPX mock transports or an equivalent transport-boundary mock to verify request methods, URLs, headers 
  (without exposing credentials), query parameters, retry behavior, pagination, and response handling.
- Use sanitized, synthetic fixtures that represent documented payload variations. Cover missing/extra fields, 
  invalid data, timezone handling, pagination termination, zero results, localization, error responses, 
  and status snapshot duplicates.
- Specifically test authentication expiration/errors, PAT refresh success and persistence boundaries, ambiguous 
  refresh failures, refresh `429`, and concurrent refresh situations **when** token refresh is implemented.
- Verify sync and async feature parity for operations implemented in both clients, including closing behavior 
  and cancellation when relevant.
- Keep live integration tests separate and opt-in. Never run tests against a real My Trust Center account, rotate   
  a real PAT, or make live API requests without explicit maintainer authorization and appropriate test credentials.
- Check packaging/imports in a clean environment when changing packaging or public exports. Run applicable static 
  checks and documentation builds if configured.
- Tests should validate behavior, not merely assert that methods exist or mocks were called.

## Documentation, examples, and release readiness

- Maintain a concise README with installation, authentication setup (using placeholders), a minimal working example, 
  supported Python versions, and an explicit unofficial/community-maintained disclaimer unless approved otherwise.
- Document each public resource operation and model, including return types, pagination, relevant errors, 
  and the fact that status visibility is tenant-scoped.
- Keep examples copyable and low-friction. Do not document planned methods as available. Update README, API docs, 
  and changelog when public behavior changes.
- If the repository uses Sphinx, maintain Sphinx-compatible docstrings and existing documentation structure; 
  do not add a second documentation stack without a reason.
- Document AI/MCP installation and launch separately from ordinary SDK setup. Never require agent tooling to use 
  the base Python library.
- Check licenses and attribution before copying code from other SDKs. Architectural inspiration is fine; 
  wholesale copying is not.
- Repository publication, PyPI releases, tags, version changes, and visibility changes require explicit 
  maintainer direction.

## Code review rules

When reviewing code in this repository, flag issues with a concrete risk and suggested safe alternative, especially:

- Incorrect My Trust Center endpoints or silently reused legacy Trust Status API behavior.
- Leaked PATs, insecure credential defaults, unsafe PAT refresh retries, or missing refresh persistence/coordination.
- Lost tenant/event scopes, accidental patch-event deduplication, or unsupported claims of Salesforce-wide health.
- Missing timeouts, unbounded pagination/retries, unexpected network calls, or unclosed HTTP connections.
- Publicly exposed private implementation details, unstable return shapes, missing tests for contract changes, 
  or incorrect model assumptions.
- Hard runtime dependencies on agent frameworks, unnecessary breaking changes, and examples that claim 
  unimplemented functionality.

Prioritize correctness and security over minor style issues already enforced by formatting/CI.

## Completion handoff

At the end of each task, summarize: what changed; user-visible/API implications; tests, lint, build, and docs 
checks run (with results); anything intentionally not run; unresolved assumptions or risks; and whether changes 
are uncommitted. Never claim a release, GitHub update, or live Salesforce verification without evidence.
