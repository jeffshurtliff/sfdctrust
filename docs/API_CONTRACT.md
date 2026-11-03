# My Trust Center API contract

Reviewed on **2026-11-01**. This is an implementation inventory, not an SDK reference:
no API client or resource operations are implemented yet.

## Sources and verification boundary

- [Salesforce overview](https://developer.salesforce.com/docs/mytrust-api/overview.html)
- [Getting started](https://developer.salesforce.com/docs/mytrust-api/get-started.html)
- [PAT authentication and recovery](https://developer.salesforce.com/docs/mytrust-api/authentication.html)
- [Rendered API reference](https://developer.salesforce.com/docs/mytrust-api/api-reference)
- Local vendor specification: `local/vendor_docs/mytrust-api.yaml`, OpenAPI 3.0.0,
  API version `v1.0` (27 named schemas).

The local specification supplies the detailed field inventory below. The current rendered
reference was checked for all six operations, request constraints, pagination, error behavior,
and the top-level tenant-list and event-detail response schemas; these agree with the local copy.
The reference's linked YAML download returned HTTP 404, so a byte-for-byte comparison and
independent verification of every nested schema were unavailable. No live API calls were made.
The vendor file remains local and is not redistributed by this package.

## Shared contract

Base URL: `https://api.salesforce.com/platform/mytrust/v1`.
Every operation requires `Authorization: Bearer <PAT>`; this is not org OAuth.
Successful responses are JSON. All data is limited to the PAT's authorized tenants.
Empty results never establish Salesforce-wide health.

All five read operations declare an optional `locale` query string: BCP 47, default `en-US`;
unsupported or malformed values fall back to `en-US`. The shared parameter description says
it applies to every endpoint, but refresh does not declare it. Do not add a refresh locale
argument without clarification. Tenant IDs are opaque strings, not necessarily Core org IDs.

## Operations

All paths below are relative to the base URL. Every success is HTTP 200.

| Method and path | Operation ID | Inputs | Success schema | Documented errors |
| --- | --- | --- | --- | --- |
| `GET /tenants` | `getTenants` | Optional query `locale`, `pageSize`, `pageToken` | `TenantListResponse` | 400, 401, 429, 500 |
| `GET /tenants/{tenantId}` | `getTenant` | Required string path `tenantId`; optional query `locale` | `TenantDetail` | 401, 404, 429, 500 |
| `GET /status` | `getFleetStatus` | Optional query `locale` | `StatusSnapshot` | 401, 429, 500 |
| `POST /events/search` | `searchEvents` | Optional query `locale`; required JSON `EventSearchRequest` | `EventSearchResponse` | 400, 401, 429, 500 |
| `GET /events/{eventId}` | `getEvent` | Required string path `eventId`; optional query `locale` | `EventDetail` | 401, 404, 429, 500 |
| `POST /pats/refresh` | `refreshPat` | Optional JSON `PatRefreshRequest` | `PatCredential` | 401, 429, 500 |

Search is a read operation despite its HTTP method. There is no separate timeline or
tenant-history endpoint: event detail supplies timelines, and tenant detail embeds history.
Refresh is inventoried for completeness and remains outside the initial implementation.

### Pagination and search inputs

- Tenant listing: query `pageSize` is an integer from 1 to 200, default 100. Query
  `pageToken` is an opaque string of at most 4096 characters. Results are ordered by tenant
  ID and cloud. Send `nextPageToken` back as `pageToken`, preserving all other parameters.
  An absent token marks the final page. Invalid, stale, or mismatched tokens return 400.
- `EventSearchScope`: required `type` (only `tenant`) and `id` (nonempty string).
- `EventSearchRequest`: required `scopes` (1–50 scope objects; duplicate tenants removed),
  `startTime` (inclusive), and `endTime` (exclusive and later than start).
  Timestamps must be full ISO 8601 with `Z` or `±HH:MM`; date-only, year-only, and
  space-separated values fail with 400.
- Optional body `eventTypes`: nonempty array of unique `EventType` values. Omit it for all
  types. Optional body `pageSize` and `pageToken` have the same limits as tenant listing.
  Search returns a stable order; repeat the unchanged body with the new token, also preserving
  locale. Changed matching results can invalidate the cursor with 400. Surface the error so
  the caller can restart deliberately; silently restarting could duplicate prior results.
- `EventSearchResponse`: required `events` (at most 200 `EventSearchResult` items) and
  optional `nextPageToken`, absent on the final page. Unauthorized tenant IDs are ignored;
  zero authorized matches can return `{"events": []}` with 200.
- Snapshot, event detail, and tenant detail declare no pagination controls. Tenant detail
  covers lifecycle overlap within 365 days before/after request time; informational messages
  cover the preceding 365 days. Do not add arbitrary history-window arguments to that endpoint.

## Schema inventory

Names and field casing below are Salesforce wire names. Required and nullable are separate:
a required nullable field must still be present. Unless identified as nullable, an optional
field may be omitted but is not declared to accept JSON null. Date-time fields are ISO 8601
strings on the wire. Most response objects disallow additional properties in the vendor
schema; `Tenant` leaves them unspecified. The SDK's proposed forward-compatible extra-field
policy is described separately below.

### Tenants and status (5 schemas)

| Schema | Required fields | Optional fields and structure |
| --- | --- | --- |
| `Tenant` | `id`, `cloud`, `name`: strings | `environment`, `myDomain`: strings; My Domain only for applicable Core tenants |
| `TenantListResponse` | `tenants`: array of `Tenant`, max 200 | `nextPageToken`: string |
| `TenantDetail` | Inherits `Tenant`; `events`: array of `EventSummary` | `region`, `version`, `maintenanceWindow`: nullable strings; `location`: object |
| `EventTypeBuckets` | `patch`, `incident`, `maintenance`, `informationalMessage`: arrays of `EventSummary` | Preserve each category, including empty arrays |
| `StatusSnapshot` | `ongoing`, `upcoming`: `EventTypeBuckets` | No flattening or automatic deduplication |

`TenantDetail.location`, when present, requires string `city`, `stateName`, `stateCode`,
`countryName`, and `countryCode` (empty strings when unavailable). Instance fields describe
the primary instance and are omitted when instance information is unavailable.

### Events, scopes, and enums (7 schemas)

| Schema | Contract |
| --- | --- |
| `Event` | Requires string `eventId`, `eventType`, `status`, string arrays `products`/`services`, and date-time `createdAt`. Optional nullable strings: `title`, `description`, `duration`, `displayDuration`; optional nullable date-times: `startTime`, `endTime`. Optional `data`, `timeline`, and `scope` depend on endpoint. |
| `EventDetail` | `Event` without a top-level `scope`. Optional `timeline` is an array of `TimelineItem`; can be absent when there are no entries. |
| `EventSummary` | `Event` with required `scope: SubEventScope` and no `timeline`. Used in snapshot and tenant history. |
| `EventSearchResult` | Inherits `EventSummary`. Lifecycle values reflect the matched tenant scope. |
| `SubEventScope` | Required `tenants`: map of tenant ID to object (documented as empty). Key presence identifies membership. |
| `EventType` | `patch`, `incident`, `maintenance`, `informationalMessage` |
| `EventStatus` | `active`, `resolved`, `confirmed`, `canceled`; canceled applies only to maintenance. |

`data` is a `oneOf` the four event-data shapes below; the schema has no discriminator.
`duration` is an ISO 8601 duration string, including elapsed time for ongoing events;
`displayDuration` is localized presentation text. Do not parse localized text for calculations.
An empty `products` array can mean a platform-wide informational message, and an empty
`services` array can mean impact information is unavailable.

Preserve duplicates and scope: snapshot patches may repeat across tenant lifecycles and both
buckets; tenant history patches may repeat per lifecycle. Search can return an event once per
matched tenant, with different status/times/duration for each result. Neither event ID alone
nor a set keyed by it is a safe lossless representation.

### Type-specific event data (4 schemas)

All listed fields are required; `?` here means the value may be null.

| Schema | Fields |
| --- | --- |
| `PatchEventData` | String `releaseId`, `releaseName`, `releaseVersion`; date-time `plannedStartTime?`, `plannedEndTime?` |
| `IncidentEventData` | String `additionalInformation?`, `rcaLink?`; date-time `rcaCreatedAt?` |
| `MaintenanceEventData` | Date-time `plannedStartTime?`, `plannedEndTime?`; string `additionalInformation?` |
| `InformationalMessageEventData` | String `informationalMessageType?`; documented categories `informationalMessage` / `productSpecific`, not a schema enum |

### Timeline (5 schemas)

`TimelineItem` is an `anyOf` the following four shapes. Each requires string `subEventId`,
string `subEventType`, `scope: SubEventScope`, and date-time `createdAt`. Each allows optional
nullable string `message` and nullable date-time `updatedAt`.

| Schema | `subEventType` values | Other optional fields |
| --- | --- | --- |
| `PatchTimelineItem` | `patch_release_scheduled`, `patch_release_started`, `patch_release_ended`, `patch_release_notes` | Nullable date-times `publicationDate`, `plannedStartTime`, `plannedEndTime`; `contents`: array of objects with optional string `relatedItem` and `description` |
| `IncidentTimelineItem` | `incident_started`, `incident_update`, `incident_resolved` | None |
| `MaintenanceTimelineItem` | `maintenance_scheduled`, `maintenance_update`, `maintenance_started`, `maintenance_completed`, `maintenance_canceled` | Nullable date-times `plannedStartTime`, `plannedEndTime` |
| `InformationalMessageTimelineItem` | `im_created`, `im_update_added` | None |

Do not assume every timeline entry has scheduling fields, a message, or an update time.

### Search, PAT, and errors (6 schemas)

The four search schemas (`EventSearchScope`, `EventSearchRequest`, `EventSearchResult`,
`EventSearchResponse`) are detailed above; `EventSearchResult` is counted in the event group.
The remaining schemas are:

- `PatRefreshRequest`: optional body; optional integer `expiresInDays`, 1–30, default 30.
  Additional fields are forbidden.
- `PatCredential`: required `tokenId` (UUID string), `secret` and `label` (strings),
  `createdAt` and `expiresAt` (date-times). `secret` is returned once and must never enter
  ordinary response logging, exception context, or serialization used by agent tools.
- `Error`: required string `error`, enum `badRequest`, `unauthorized`, `notFound`,
  `internalError`; optional string `message`, omitted for unauthorized responses.

Across the groups, all **27 distinct schema names** are covered (the search-result alias
belongs to both discussions but is counted once).

## Errors and PAT lifecycle

400 means invalid arguments/cursor where declared. A detail 404 can mean nonexistent or
unauthorized; do not distinguish these without evidence. All operations document JSON
401/500 errors. All six reference the gateway's 429 response: **plain text**
`local_rate_limited`, without `Retry-After`; authentication docs also exclude `RateLimit-*`
headers for refresh. Do not assume that every failure body is JSON or has `message`.

The authentication guide documents one active PAT, UI lifetimes of 7/15/30 days,
refresh lifetimes of 1–30 days, and a 365-day maximum lineage. Refresh immediately revokes
the old PAT; it is non-idempotent. Invalid refresh lifetime is reported as the same 401 as
an invalid PAT. A refresh 429 leaves the old PAT active; retry can use backoff and jitter.
A refresh timeout/500 has an ambiguous result: first test the old token with a harmless read.
If it succeeds, a later refresh may be retried; a 401 requires manual recovery in My Trust
Center. Never apply generic automatic refresh retries or refresh automatically after 401.
See [Salesforce's recovery instructions](https://developer.salesforce.com/docs/mytrust-api/authentication.html).

## Foundation changes and implementation decisions

Runtime dependencies are now only `httpx>=0.28.1,<1` and `pydantic>=2.14.2,<3`.
The Pydantic lower bound is retained from this repository. Use HTTPX's pool, explicit timeouts,
and `MockTransport`; use Pydantic v2 validation/serialization directly. Let those packages
manage their own `pydantic-core`, `typing-extensions`, and concurrency dependencies.
Existing pytest, coverage, Ruff, Bandit, Twine, and optional Sphinx tooling are retained.
RESPX, pytest-asyncio, JWT, dotenv, retry frameworks, and AI dependencies are unnecessary now.
Add a type checker with a defined configuration when the first typed operation is introduced.
See [HTTPX](https://www.python-httpx.org/) and
[Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).

Removed the unused copied `_models`, `_types`, `_compat`, and `_utils` cluster: it contained
unchecked model construction, Pydantic compatibility machinery, async conversion, generic
transformers, proxies, multipart/streaming-related types, and dangling helper imports.
No code outside that cluster imported it. Removed unrelated org-ID/YAML validation constants,
Stainless response flags, audio queue sizing, and oversized HTTP defaults. Retained the
package identity, verified base URL/default locale, empty resource/model/integration namespaces,
`py.typed`, and existing base exception. Removed the redundant public `version.py` module;
use `sfdctrust.__version__` for the package version.
Fixed the checkout version fallback (it previously looked one directory above the repository)
and exposed package `__version__`. The PEP 621 version remains authoritative and unchanged.

The following SDK policies are distinct from Salesforce requirements. The credential and
exception decisions are now implemented as described below; the remaining policies are
proposals to resolve when implementing their respective slices:

| Area | Recommended initial decision |
| --- | --- |
| Credentials | Explicit required `pat` for construction; opt-in `from_env()` reads only `SFDCTRUST_PAT`. An explicit override takes precedence; empty overrides fail rather than silently fall back. No `.env` loading, JWT parsing, provider framework, or refresh. Hide the PAT from repr/logs/errors. |
| Ownership | Internally created `httpx.Client` is SDK-owned and closed by `close()`/context exit; caller-supplied client remains caller-owned. No network I/O at construction. |
| Network defaults | Propose connect/pool 5 seconds, read/write 30 seconds, 20 total/10 idle connections, at most 2 retries after the initial attempt, capped exponential backoff with jitter and a total retry-wait budget. Set concrete backoff bounds with transport tests before implementation. |
| Safe retry classification | Allowlist GET reads and read-only `POST /events/search`; never infer safety from all POSTs or retry refresh. Propose retrying connection/timeouts and 429/500/502/503/504 within limits. Fail immediately on 400/401/404 and malformed successful responses. |
| Credential destination | Fixed production HTTPS origin initially; redirects off. Decide any custom-base-URL/proxy policy before exposing it publicly so the PAT cannot be redirected to an unintended host. |
| Models | Python snake_case attributes with explicit camelCase aliases; deliberate JSON serialization with `by_alias=True`. Validate known field types/requiredness; preserve response extras with `extra='allow'` even where vendor schemas are closed. Strict request validation. |
| Optionality/time | Preserve omitted versus explicit-null via Pydantic field-set information and `exclude_unset`. Reject null on optional non-nullable wire fields. Require aware input timestamps; preserve response offsets, with explicit UTC conversion when needed. Keep ISO durations lossless as strings initially. |
| Event evolution | Validate outgoing enum filters; preserve unknown response enum strings/data. Dispatch known `data` shapes using `eventType`, rather than an untagged permissive union that could select the wrong shape. Design this before event models. |
| Pagination | First expose one explicit page. Later add lazy iteration with repeated-token detection and a finite page bound; never silently restart stale cursors. Choose the bound and error before publishing iterator methods. |
| Errors | Retain `TrustCenterError`; add a small hierarchy for configuration, network/timeout, API status, authentication, rate limiting, not found, and malformed responses. Preserve status and a verified safe request ID when available; do not retain raw credential-bearing requests or unsanitized server messages. Header name for request IDs is not specified by this API. |
| Freshness | No caching initially. Defer an SDK `retrieved_at` envelope until its return-shape implications are decided; do not add it to Salesforce's wire schema. |

### Authentication and exceptions implemented (2026-11-02)

`_auth.PATAuth` is an internal HTTPX auth component with required explicit `pat` construction
and opt-in `from_env()` reading only `SFDCTRUST_PAT`. An explicit override wins without an
environment read; empty, blank, non-string, and explicit `None` overrides fail rather than
fall back. PAT values are opaque visible-ASCII strings: whitespace/control characters are
rejected without trimming, and JWT parsing is not performed. Construction performs no I/O.
Pydantic `SecretStr` protects ordinary representations; pickling is disabled. Only the fixed
production HTTPS origin without URL user information may receive the Bearer header.
The auth flow sends once and passes 401 responses through unchanged, without parsing,
retrying, or refreshing. Redirects must be disabled by the future transport.

The public exception hierarchy is exported from `sfdctrust`: `TrustCenterError`,
`ConfigurationError`, `NetworkError` / `RequestTimeoutError`, `APIStatusError` /
`AuthenticationError` (401), `RateLimitError` (429), `NotFoundError` (404), and
`MalformedResponseError`. Status errors retain only a validated integer `status_code`
and an SDK-authored message, with no raw request, response, or server message.
Request-ID capture is deferred because no safe header source has been verified.
Other exception messages must likewise be SDK-authored and secret-free.

The current [Salesforce authentication guide](https://developer.salesforce.com/docs/mytrust-api/authentication.html)
was rechecked for Bearer authentication and 401 semantics. HTTPX's custom auth protocol was
checked against its official documentation. Tests use synthetic credentials and mock requests;
no live API calls or real credential discovery occurred. See the
[authentication boundaries](reference/authentication.md) and
[exception reference](reference/exceptions.rst). No transport, client, or refresh is implemented.

Recommended sequence:

1. **Complete:** `_auth.py` input/environment validation and safe secret handling, plus the small
   `_exceptions.py` hierarchy and offline tests for missing/blank inputs, precedence, redaction,
   destination restrictions, and unchanged 401 behavior.
2. Implement `_transport.py` with ownership, HTTPS/redirect rules, finite timeouts, bounded
   retries, status translation before JSON parsing, and strict successful-response decoding.
   Use offline `httpx.MockTransport` tests for URLs, auth headers, JSON/plain-text errors,
   timeout/retry exhaustion, and caller-owned client closing behavior.
3. Add `Tenant`/`TenantListResponse`, `resources/tenants.py`, and a minimal synchronous
   `TrustCenterClient`. Proposed first method: `client.tenants.list(*, page_size=None,
   page_token=None, locale=None) -> TenantListResponse`; translate names explicitly, omit
   unspecified query values, and let Salesforce supply defaults. Test 1/200 boundaries,
   invalid booleans/floats/page sizes, 4096-character tokens, extra fields, absent versus null,
   zero tenants, localization, and multiple pages before adding convenience iteration.

There is no CONTRIBUTING file or CI workflow. Sphinx configuration and documentation tooling
have since been added, and offline version/authentication/exception tests are available.
Python `>=3.12` and the existing classifiers are preserved; a tested Python
matrix (including the existing 3.15 classifier) remains a release-readiness decision.
No client, resource methods, async functionality, MCP, PAT refresh, version bump, or release
is introduced by this foundation task.

## Validation of the original foundation

On Python 3.12, the eight offline version tests, Ruff lint, formatting of changed Python
files, Bandit, Poetry configuration checks, wheel/sdist builds, and Twine metadata checks
passed. A clean wheel installation imported every retained module and passed `pip check`;
an uninstalled source checkout also imported successfully. The wheel includes `py.typed`
and declares exactly two runtime dependencies. The sdist includes this contract and the
tests, and excludes local vendor/private files and virtual environments. All 68 local
OpenAPI references resolve and all 27 schema names are covered in this inventory; this
is a structural check, not full OpenAPI semantic validation or live-response verification.

Repository-wide `ruff format --check .` still flags four unchanged files: `AGENTS.md`
and the `models`, `resources`, and `integrations` namespace
`__init__.py` files. Their existing formatting was left intact. No hosted CI, Python-version
matrix, live Salesforce, or Sphinx build was run; Sphinx has no configuration in this checkout.
