# Public compatibility for the 1.x series

This is the proposed 1.0 public baseline, verified locally against published
`0.2.0` and the `1.0.0.dev0` candidate. It becomes the compatibility promise
with the stable 1.0 release. The package remains at its development version;
this document does not announce a release. Maintainer review of the inventory
and policy remains a release gate. See the
{doc}`qualification procedure and evidence <../maintainers/compatibility-qualification>`.

## Supported imports

The following names are supported from `sfdctrust`:

```text
__version__
TrustCenterClient  AsyncTrustCenterClient
TrustCenterError  ConfigurationError  NetworkError  RequestTimeoutError
APIStatusError  AuthenticationError  RateLimitError  NotFoundError
MalformedResponseError  PaginationError
PATStore  AsyncPATStore  PATStoreRecord  SQLitePATStore  PATRefreshResult
PATProbeResult  PATRefreshPendingError  PATRefreshAmbiguousError  PATPersistenceError
```

`__version__` is the installed version string. Import response and request
models from these paths, rather than from the otherwise empty `models` package:

| Module | Supported names |
| --- | --- |
| `sfdctrust.models.tenants` | `Tenant`, `TenantDetail`, `TenantListResponse`, `TenantLocation` |
| `sfdctrust.models.status` | `StatusSnapshot`, `EventTypeBuckets` |
| `sfdctrust.models.events` | `EventType`, `EventSearchScope`, `EventSearchResponse`, `EventSearchResult`, `EventDetail`, `EventSummary`, `SubEventScope`, `PatchEventData`, `IncidentEventData`, `MaintenanceEventData`, `InformationalMessageEventData`, `TimelineItem`, `PatchTimelineItem`, `IncidentTimelineItem`, `MaintenanceTimelineItem`, `InformationalMessageTimelineItem`, `PatchNote` |

`EventType` is the request literal union `patch | incident | maintenance |
informationalMessage` (string values). `TimelineItem` is a response union,
including a common-field fallback for unknown subtypes; callers must not import
its private fallback class. Access resources through the client attributes
`tenants`, `status`, and `events`. Their operations and return types are public;
resource constructors and direct resource-class imports are not promised.

Underscore-prefixed modules, helper classes, validators, transport objects,
constants, incidental imports, `__dict__` layout, and private attributes are
internal. An import being possible does not make it supported. Third-party
Pydantic/HTTPX APIs retain their own compatibility policies. The SDK promises
the model access and serialization behavior below, not every inherited helper.
The module CLI is public; Python functions inside `sfdctrust.pat_store` are not.

## Construction, credentials, and lifecycle

Signatures below omit `self`/`cls`. `*` marks keyword-only parameters. `Self`
means the client class being constructed. No public timeout parameter exists.
The omission marker in `from_env` is descriptive, not an importable value.

```python
TrustCenterClient(pat: str, *, http_client: httpx.Client | None = None,
                  max_retries: int = 2) -> None
TrustCenterClient.from_env(*, pat: str | None = <omitted>,
                           http_client: httpx.Client | None = None,
                           max_retries: int = 2) -> Self
TrustCenterClient.from_store(store: PATStore, *,
                             http_client: httpx.Client | None = None,
                             max_retries: int = 2) -> Self
client.refresh_pat(*, expires_in_days: int | None = None) -> PATRefreshResult
client.retry_pat_persistence() -> PATRefreshResult
client.close() -> None
client.__enter__() -> Self
client.__exit__(*_ : object) -> None
```

`AsyncTrustCenterClient` has the same constructor and factory defaults, with
`httpx.AsyncClient` and `AsyncPATStore` in place of their synchronous types.
Construction and `from_env()` are ordinary calls; `from_store()` must be
awaited. Await `refresh_pat()` and `retry_pat_persistence()` with the same
arguments/results. Use `async with` (`await __aenter__() -> Self`,
`await __aexit__(*_ : object) -> None`) or `await aclose() -> None`.
There is no async `close()` or synchronous context protocol. Use each async
client and adapter on one event loop.

The constructor uses only its explicit PAT. `from_env()` reads only
`SFDCTRUST_PAT` when `pat` is omitted. A supplied override wins, including an
invalid value: explicit `None` fails instead of falling back. Whitespace,
empty strings, and Bearer-prefixed credentials are rejected. No entry point
automatically reads `.env`, discovers a store, or refreshes on HTTP 401.
`from_store()` loads the selected adapter and rejects unseeded or pending state;
it never falls back to an environment credential. Store-backed reads reload
the durable record. See {doc}`authentication` for the full credential contract.

Ordinary construction and `from_env()` perform no network I/O; `from_store()`
performs store I/O, not HTTP. The SDK closes its internally created HTTPX
client on context exit/explicit close; closing it again is harmless. Closing
a client is not a way to reopen it for later use. Injected HTTPX clients remain
caller-owned and open on SDK context exit/close. The caller controls their
pool, TLS, proxies, hooks, and underlying transport; inject only a trusted
client. Those components can see secrets or implement additional retries.
The SDK still fixes the production destination, authentication, redirect
policy, phase timeouts, and error translation. Default clients verify TLS,
ignore environment proxy/CA overrides, and use 20 total/10 idle connections.

### Timeout decision and retries

**Maintainer decision, 2026-11-11:** defer public phase-timeout configuration
beyond 1.0. The fixed per-attempt limits are connect 5 s, pool 5 s, read 30 s,
and write 30 s, including when the injected HTTPX client specifies different
limits. A timeout override on an injected client is not a workaround.
These are HTTPX phase limits, not a total-operation deadline; retries,
backoff, multiple reads and streamed data can extend elapsed time. A future
public configuration option requires its own approved change and tests.
Private transport timeout arguments are outside this promise.

`max_retries=2` permits two additional SDK attempts per eligible read; integers
0 through 5 are accepted, booleans are not. The five operations below are the
retry allowlist, including read-only event-search POST. Connection-establishment
errors and HTTPX timeouts, plus HTTP 429/500/502/503/504 are eligible. Other failures,
including HTTP 400/401/404, redirects and malformed successful responses, fail
immediately. Exhaustion raises the final translated error. The same arguments,
body and cursor are preserved across retries.

A valid `Retry-After` on 429/503 supplies nonnegative seconds or an HTTP date,
capped at 30 s without jitter (possibly earlier than the server requested).
Otherwise delay is 0.5 s doubled per retry plus up to 0.25 s jitter. Each
response closes before waiting. See {doc}`transport`. Cancellation propagates
`asyncio.CancelledError`, closes the response being handled and stops further
SDK retries/pages in that traversal. Cancelling refresh can leave a durable
pending marker or an unconfirmed replacement; see the recovery contract below.

## Five reads and pagination

These signatures apply to both clients. Async calls are awaited, except the
two lazy iterator factories, which are called directly and consumed with
`async for`. `Iterator` becomes `AsyncIterator` for those factories only.
All other return types are the same after awaiting.

```python
client.tenants.list(*, page_size: int | None = None,
                    page_token: str | None = None,
                    locale: str | None = None) -> TenantListResponse
client.tenants.get(tenant_id: str, *, locale: str | None = None) -> TenantDetail
client.status.snapshot(*, locale: str | None = None) -> StatusSnapshot
client.events.search(*, scopes: Sequence[EventSearchScope],
                     start_time: datetime, end_time: datetime,
                     event_types: Sequence[EventType] | None = None,
                     page_size: int | None = None, page_token: str | None = None,
                     locale: str | None = None) -> EventSearchResponse
client.events.get(event_id: str, *, locale: str | None = None) -> EventDetail
client.tenants.iter_all(*, page_size: int | None = None,
                        page_token: str | None = None, locale: str | None = None,
                        max_pages: int = 1000) -> Iterator[Tenant]
client.tenants.list_all(*, page_size: int | None = None,
                        page_token: str | None = None, locale: str | None = None,
                        max_pages: int = 1000) -> list[Tenant]
client.events.iter_search(*, scopes: Sequence[EventSearchScope],
                          start_time: datetime, end_time: datetime,
                          event_types: Sequence[EventType] | None = None,
                          page_size: int | None = None, page_token: str | None = None,
                          locale: str | None = None,
                          max_pages: int = 1000) -> Iterator[EventSearchResult]
client.events.search_all(*, scopes: Sequence[EventSearchScope],
                         start_time: datetime, end_time: datetime,
                         event_types: Sequence[EventType] | None = None,
                         page_size: int | None = None, page_token: str | None = None,
                         locale: str | None = None,
                         max_pages: int = 1000) -> list[EventSearchResult]
```

`Sequence`/`Iterator`/`AsyncIterator` are from `collections.abc`; `datetime`
is from `datetime`. `None` omits the optional request value. Explicit page
sizes are 1–200; page tokens are opaque strings up to 4096 characters.
Search accepts 1–50 tenant scopes, aware start/end datetimes with minute-aligned
offsets and start before end, and optional distinct known event types.
IDs must be nonempty and safe in one URL segment. Locale is a forwarded string;
Salesforce controls BCP 47 fallback. See {doc}`tenants` and
{doc}`events-and-status` for detailed validation and wire placement.

Iteration fetches on advancement, preserves server order, duplicates, scopes,
and omissions, and continues from the supplied token. Search factories copy
scope/filter sequences at creation. No absent cursor is synthesized from an
empty page: only an omitted `nextPageToken` terminates traversal; `""` is still
a cursor. Keep all other arguments unchanged when continuing manually. The SDK
does not sort, restart, deduplicate, or promise a stable service-side snapshot
across pages. Salesforce controls cursor validity, lifetime and result order.

`max_pages` is a positive integer, excluding bool, counts fetched pages
including empty/initial pages, and excludes retries. A terminal page at the
limit succeeds. A repeated cursor (including the starting cursor) or a required
page beyond the limit raises `PaginationError` before requesting that page.
Current-page items may already have been yielded. HTTP 400 for an invalid or
stale API cursor raises `APIStatusError(status_code=400)`, not `PaginationError`.
Local invalid arguments raise `ConfigurationError` before the affected request;
validation in a lazy traversal may wait until advancement. Collectors propagate
errors without returning a partial list; iterators may have delivered a partial
sequence. Callers must handle partial side effects in their own consumers.

## Models and serialization

The attribute, alias, required/optional and nullable contracts in
{doc}`tenants` and {doc}`events-and-status` are part of this baseline, including
all four event-data models, timeline variants and patch notes. The checked
inventory in `tests/compatibility/public-api.json` also records every public
model's field types, aliases and defaults. It is a regression artifact; private
class names appearing in union representations do not become public imports.

Known fields validate strictly; malformed successful API payloads become
`MalformedResponseError`. Direct `Model.model_validate(payload)` instead raises
Pydantic's `ValidationError`. Missing required fields and explicit null in
non-null fields fail. Optional omitted fields read as `None`, but this does not
mean they accept explicit null. In particular tenant optional `environment` and
`my_domain`, page cursors, tenant `location`, event `data`/`timeline`, patch
`contents`, and patch-note strings reject null when supplied. Nullable event
fields and nullable required event-data fields retain explicit null.

Use `model_fields_set` (Python field names) to distinguish omission from null.
Use `model_dump(mode='json', by_alias=True, exclude_unset=True)` for a
JSON-compatible dictionary retaining wire aliases and presence, or
`model_dump_json(by_alias=True, exclude_unset=True)` for JSON text. Plain
`model_dump()` uses Python names/types and includes defaults; without
`exclude_unset=True`, omitted optional fields can serialize as null. Do not
promise byte-for-byte JSON, whitespace, key order, or timestamp lexemes.

Wire timestamps require full ISO 8601 strings with explicit offsets. Parsed
values are aware `datetime` objects retaining the supplied UTC offset, not
silently converted to UTC or made naive. Python datetime precision is
microseconds; original lexical spelling and finer precision are not retained.
Unknown extras remain in JSON-compatible dumps; unknown timestamp-like extras
are not automatically parsed. IDs, clouds, statuses, products, services,
durations and response event/subevent strings are Salesforce-controlled values.
Unknown response enum strings and extra fields are preserved. Unknown event
`data` remains a dictionary; unknown timeline subtypes retain common attributes
and extra fields. Known data variants still validate their required fields;
summaries reject `timeline`, detail rejects top-level `scope`, and known
mismatched parent/timeline categories fail. Forward compatibility does not
mean accepting arbitrary corruption of known shapes.

Request validation is intentionally narrower: `EventSearchScope` is frozen,
forbids extras and supports only `type='tenant'` (default), with nonempty `id`;
`EventType` restricts request filters to the four supported categories. A new
response value is not automatically an accepted request value.

All results are PAT-authorized tenant observations. Preserve `ongoing` and
`upcoming`, each with `patch`, `incident`, `maintenance`, and
`informational_message` (`informationalMessage`) arrays. Repeated event IDs,
including patch lifecycle/tenant variants, are preserved in lists and timelines.
Never infer Salesforce-wide health, missing tenant impact, or a guaranteed
retrieval time from empty results. No freshness timestamp is added by the SDK;
record observation time in the consuming application if needed.

## Exceptions and safe machine-readable context

```text
Exception
  TrustCenterError
    ConfigurationError
    NetworkError
      RequestTimeoutError
    APIStatusError
      AuthenticationError
      RateLimitError
      NotFoundError
    MalformedResponseError
    PaginationError
    PATRefreshPendingError
    PATRefreshAmbiguousError
    PATPersistenceError
```

`APIStatusError(status_code: int)` exposes `status_code: int` (400–599,
excluding bool); specialized zero-argument errors expose 401, 429 and 404.
`PATRefreshAmbiguousError(probe: PATProbeResult)` exposes `probe: PATProbeResult`.
`PATProbeResult` is a string enum with `OLD_PAT_ACCEPTED='old_pat_accepted'`,
`OLD_PAT_REJECTED='old_pat_rejected'`, and `INCONCLUSIVE='inconclusive'`.
Other SDK errors have no additional promised machine-readable fields. Use
classes/fields, not message text; exact messages are not stable. Requests,
responses, URLs, server messages, validation diagnostics, secrets, and request
IDs are not retained as public error context. HTTP 401 does not distinguish
expired/revoked/invalid PATs; 404 does not distinguish nonexistent/unauthorized
resources. See {doc}`exceptions`.

## PAT adapters, refresh and recovery

```python
PATStoreRecord(revision: UUID, pat: InitVar[str],
               pending_attempt: UUID | None = None) -> None
record.get_pat() -> str
PATRefreshResult(metadata_valid: bool) -> None
store.load() -> PATStoreRecord | None
store.compare_and_swap(*, expected_revision: UUID,
                       expected_attempt: UUID | None,
                       replacement: PATStoreRecord) -> bool
SQLitePATStore(path: str | Path | None = None, *, alias: str | None = None) -> None
SQLitePATStore.initialize(*, pat: str, path: str | Path | None = None,
                          alias: str | None = None) -> Self
```

`UUID` is from `uuid`, `Path` from `pathlib`, and `InitVar` from `dataclasses`.
The two store methods define structural, runtime-checkable `PATStore`;
`AsyncPATStore` defines their awaited equivalents with identical arguments and
results. Production adapters must provide strongly consistent loads and durable,
atomic cross-process compare-and-swap. Inheritance is not required. The built-in
SQLite adapter conforms to `PATStore` only; async callers supply their own adapter.
A type check verifies shape, not durability or concurrency correctness.

A record is a frozen snapshot with UUID `revision` and optional UUID
`pending_attempt`. `pat` is constructor input, not a public secret attribute.
`get_pat()` is for trusted adapter I/O only. Repr hides the secret; record
serialization/pickling is refused. Do not rely on value equality, hashing or
private storage layout. `load()` returns `None` only for an unseeded lineage.
Compare both revision **and** attempt, including expected `None`; write the whole
replacement atomically. `True` means durable commit, `False` means comparison
mismatch with no write, and an exception means failure or an unconfirmed outcome.
Revision identifies the credential and stays stable during pending-marker changes;
a replacement credential receives a new revision. Attempt IDs distinguish claims
for the same credential revision. Pending state survives process/lease loss.

Explicit refresh requires a store-backed client. It claims pending state durably
before one `POST /pats/refresh`; `expires_in_days` is None (omit body) or an integer
1–30, excluding bool. No SDK retry, including on 429; `max_retries` does not apply.
After ambiguous outcomes a single status-only old-PAT probe does not automatically
authorize another refresh. Unresolved pending state blocks reads and rotations;
store operations remain available for coordinated operator recovery. Never bypass
pending protection with an unconditional write or independent database copy.

Success activates the replacement only after confirmed persistence and returns a
frozen, secret-free `PATRefreshResult` with `metadata_valid: bool`. False means
metadata did not validate, not that persistence failed; no response secret or
server metadata is returned. If a received replacement's commit is unconfirmed,
retain that original client and call `retry_pat_persistence()` (await async).
It only reconciles/retries store I/O, does not contact Salesforce or rotate again,
and preserves competing revisions/attempts. It cannot recover a replacement lost
with the process. `PATPersistenceError`, `PATRefreshPendingError`, and
`PATRefreshAmbiguousError.probe` drive recovery; they do not disclose secrets.
Async cancellation propagates, may interrupt an already committed write, and must
not discard a client holding an unconfirmed replacement. Full operator procedures
and the accepted #9 recovery evidence are linked from {doc}`authentication` and
{doc}`../maintainers/compatibility-qualification`.

### Versioned SQLite stores and operators

The supported versioned SQLite format introduced by 0.2.0 must reopen in 1.0
without losing the credential, revision, or pending state. Throughout 1.x,
upgrades must continue to support those stores, either directly or through a
documented, explicit upgrade procedure preserving those invariants. A future
format change must describe supported source versions, quiescence, protection,
backup handling, failure recovery and whether downgrade is possible before it
ships. Do not infer that an older SDK can read a newer format.

The SQL schema, PRAGMA identifiers, table/column names and journal settings are
private implementation details. Direct SQL edits are unsupported. Unknown,
newer, malformed and unversioned legacy formats fail closed with
`ConfigurationError` on open/load rather than being overwritten or interpreted
as a new store. Unconfirmed conditional writes raise `PATPersistenceError`.
Initialization exclusively creates a new destination; it never reseeds or
migrates an existing database. Migration of the unused unversioned example
remains retired and is outside upgrade support.

The single-host boundary remains: all jobs for one PAT share one store under
one OS account on a trusted private encrypted local volume. Network/synced
folders, independent copies and distributed coordination are unsupported.
Before upgrading, quiesce every reader/rotator, resolve pending operations using
the recovery runbook, preserve private permissions/ACLs, install the selected
wheel in the application environment, reopen the same store and verify reads
before resuming. Never restore stale backups as an active lineage or run mixed
uncoordinated versions/copies. Protect/retire backups as credentials. The SDK
checks file protection but cannot verify encryption or every sync provider.
No migration or live rotation is needed for the verified 0.2.0-to-candidate reopen.

### Initialization CLI

```sh
python -m sfdctrust.pat_store init [--path PATH | --alias ALIAS] [--from-env [NAME]]
```

No location option uses `~/.sfdctrust/pat.sqlite3`; `--alias` selects an alternative
basename there. `--path` and `--alias` are mutually exclusive. Only the final
private directory may be created; its parent must exist. Aliases use ASCII
letters/digits/underscore/hyphen and exclude reserved platform names. There is
no overwrite option or PAT argument. Default input is a hidden terminal prompt;
`--from-env` reads `SFDCTRUST_PAT`, and `--from-env NAME` selects that environment
variable. `-h`/`--help` is supported. Exit status is 0 for success/help, 2 for
invalid command arguments and 1 for input/storage failure or cancellation.
Diagnostics and success text can change; credentials must not be echoed.

## Versioning, deprecation, and upgrade guidance

Semantic Versioning applies to this supported surface starting at 1.0.0.
Compatible fixes ship in patches; additive operations, optional keyword
arguments with preserving defaults, supported request values, and new model
attributes may ship in minor versions. Existing response shapes, Python types,
aliases, presence/null rules, exception inheritance/fields, ownership, iterator
semantics and persistence guarantees must remain compatible. Service-provided
new extras/enum values can arrive independently of SDK releases; applications
must tolerate them. Dependencies are not frozen, but their updates must preserve
the documented SDK contracts and supported Python floor (currently 3.12).

Deprecations require a documented replacement, changelog notice and upgrade
instructions before removal in a major release; no deprecated supported API is
removed during 1.x. An incompatible signature/import/return/serialization/error
or storage change requires a major release and explicit maintainer review.
Security fixes that must reject previously accepted unsafe input must explain
the affected cases, risk and operator action in release notes. Do not silently
turn a behavior change into a compatibility exception.

Every upgrade requiring caller/operator action must identify affected versions,
before/after usage, handling of stored data and secrets, deployment order,
rollback constraints and validation steps. Python/runtime support changes need
explicit review and equivalent guidance. Private refactors are free to change
only while preserving this public behavior. Pre-1.0 releases are not a promise
to freeze every incidental behavior: intentional incompatibilities discovered
before 1.0 must be recorded with explicit maintainer disposition and user-facing
upgrade notes before closing this gate.

The comparison found no intentional runtime incompatibility. The candidate
repairs the annotation of sync/async `tenants.list_all()` so a downstream checker
can resolve `list[Tenant]` despite the resource's `list()` method. This is a typing
correction with no calling or runtime return change; no application migration is
required. Published 0.2.0 fails those two strict type assertions; the candidate
must pass all assertions. General inventory/policy approval and hosted CI
verification remain separate from the already approved timeout decision.
