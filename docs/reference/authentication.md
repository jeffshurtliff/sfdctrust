# Authentication and PAT rotation

Both `TrustCenterClient` and `AsyncTrustCenterClient` use the same internal HTTPX
Bearer authentication component.

For step-by-step PAT creation and built-in SQLite store initialization,
start with {doc}`../getting-started/setup`.

## Credential selection

- Construction requires an explicit `pat`; it never reads the environment.
- Opt-in `from_env()` reads only `SFDCTRUST_PAT`.
- `from_env(pat=...)` uses the override without reading the environment. An explicit
  empty, blank, or `None` override raises `sfdctrust.ConfigurationError`, even when the
  environment contains a valid PAT.
- `from_store(store, ...)` loads a seeded, caller-supplied store. Await this call for the async client.
  That store is the sole credential source for the client.
- The SDK changes no environment variables and opens no `.env`, shell profile,
  credential file, or service configuration on its own.

A PAT must be a nonempty string containing only visible ASCII characters, with no whitespace
or control characters. The value is preserved exactly; it is never trimmed or parsed as JWT.
Supply the token alone, without `Bearer `; the auth component adds that prefix.
This validates header safety, not the token's validity, expiration, or tenant permissions.

## Secret handling and request behavior

Ordinary string representations, diagnostic dictionary representations, and formatting of
the credential object redact its PAT. Pickling is disabled, and there is no JSON export.
The private secret container uses Pydantic `SecretStr`. Redaction prevents accidental output;
it is not encryption or protection against code deliberately inspecting private state.

Authentication attaches the PAT only to `https://api.salesforce.com` on the default HTTPS
port, without URL user information. It replaces any existing Authorization header and
yields exactly one request. Construction and validation make no network requests.

The auth flow yields a 401 response unchanged. The private transport maps it to
`AuthenticationError` and fails immediately. The transport disables redirects on every request. 
A read returning 401 never triggers refresh.

Authenticated request objects necessarily contain the Authorization header. Do not log or
serialize those objects or manually expose the secret. The transport uses SDK-authored errors 
when translating HTTPX failures.

(sqlite-pat-store)=
## Built-in SQLite store

`SQLitePATStore` is a synchronous, standard-library implementation of `PATStore`
for one PAT lineage on one host. Import it explicitly from `sfdctrust`.
It works with `TrustCenterClient.from_store()`; the async client still requires
a custom `AsyncPATStore`.

```python
from sfdctrust import SQLitePATStore, TrustCenterClient

store = SQLitePATStore()  # Existing ~/.sfdctrust/pat.sqlite3
with TrustCenterClient.from_store(store) as client:
    tenants = client.tenants.list_all()
```

### Paths and first-time initialization

`SQLitePATStore(path=None, *, alias=None)` opens and validates an existing
database without creating one. A path can be a string or `pathlib.Path`;
relative paths are relative to the working directory when the adapter is
constructed, and `~` is expanded. Later working-directory changes do not
change the selected store. Omitting both arguments selects
`~/.sfdctrust/pat.sqlite3`. An alias selects `~/.sfdctrust/<alias>.sqlite3`.
Path and alias are mutually exclusive. Aliases must match `[A-Za-z0-9_-]+`;
Windows device names such as `CON`, `NUL`, `COM1`, and `LPT1` are rejected
on every platform. Separate aliases are for separate PAT lineages.

`SQLitePATStore.initialize(*, pat, path=None, alias=None)` creates and seeds
a new database and returns its adapter. Prefer the command below for
interactive setup; trusted integration code can supply `pat` through its
existing secret input path. Initialization validates the PAT before creating
files, creates only the final private directory if needed, and refuses every
existing destination. It never changes existing permissions. A failed
initialization can leave a protected file that requires inspection; no
automatic cleanup discards a potentially committed write.

```sh
python -m sfdctrust.pat_store init
python -m sfdctrust.pat_store init --alias secondary
python -m sfdctrust.pat_store init --path "/private/location/pat.sqlite3"
python -m sfdctrust.pat_store init --from-env
python -m sfdctrust.pat_store init --from-env=SFDCTRUST_PAT_ALT
```

The default is a hidden prompt that fails if input cannot be hidden.
`--from-env` selects `SFDCTRUST_PAT`; supplying a name selects only that
variable. Missing or invalid environment values fail without prompt fallback.
The command neither refreshes a token nor changes environment variables.
It has no PAT argument, overwrite option, or recovery shortcut.

### Protection and supported storage

Use the same database for every process that can refresh a lineage, under
the same OS account. The store directory must have trusted containing
directories that other unprivileged users cannot substitute or change.
Every operation rechecks protection and the directory/database identities.
Linked store directories, symlinks, reparse points, non-regular database
files, and hard-linked databases are rejected. These checks do not isolate
the PAT from malicious code running as you or from privileged administrators.

| Platform | Enforced protection |
| --- | --- |
| macOS and Linux | Current-user ownership, no group/other mode permissions on the directory or files; newly created directories use `0700`, files `0600`. macOS extended allow ACLs are conservatively rejected, including on containing directories. Deny-only ACLs are permitted. |
| Windows | A local filesystem with persistent ACL support, current-user ownership of the store directory and database, and protected DACLs. Allow entries may name only the current user, SYSTEM, or Administrators. SQLite journals may have a trusted privileged owner and inherited restricted ACLs. Unsupported ACE types, broad grants, and null DACLs are rejected. No administrator elevation is requested. |

Plain SQLite does not encrypt the PAT. The operator must select a private,
encrypted local volume (for example, FileVault or BitLocker). Encryption
protects a locked volume; it does not prevent access by authorized accounts
or their programs while unlocked. The SDK does not verify encryption,
identify every network mount, or detect all sync providers.

Network filesystems, shared/synchronized folders, and independent database
copies are outside the support boundary. Windows remote drives are rejected;
on all platforms the operator remains responsible for placement. See
[SQLite's network filesystem guidance](https://www.sqlite.org/useovernet.html).
Keep the database, journal files, backups, and snapshots private and on
encrypted storage. Copying a store does not establish coordinated rotation.
Do not restore a stale backup as an active credential source or run jobs
against multiple copies. Backups, filesystem snapshots, and deleted blocks
may retain older credential bytes; the SDK does not promise secure erasure.

### Format, transactions, and errors

The built-in format uses SQLite `application_id=0x53464454` and
`user_version=1`, with one `credential` table containing `slot` (fixed to 1),
`revision`, `pat`, and nullable `pending_attempt`. UUIDs are stored as
canonical text. This is an internal, versioned format, not a general database
editing API. Unknown versions, unexpected schema objects, malformed records,
and the old unversioned example format are rejected. There is no automatic
migration or in-place reseeding.

Connections last only for an operation, so the adapter needs no `close()`.
Each connection uses an existing-file URI, a five-second lock timeout,
rollback `DELETE` journaling, `synchronous=EXTRA`, and macOS `fullfsync=ON`.
Required durability settings are verified. Conditional writes compare
revision and attempt together inside an immediate transaction. The complete
replacement and marker removal commit together before success is returned.
No SQLite transaction spans an HTTP request. Durability depends on the local
filesystem and device honoring synchronization, as described in
[SQLite's atomic commit documentation](https://www.sqlite.org/atomiccommit.html).

Opening, loading, or initializing an unsuitable store raises
`ConfigurationError`. A conditional write that cannot be safely confirmed
raises `PATPersistenceError`; only a comparison mismatch returns `False`.
Error messages do not include SQLite diagnostics, paths, SQL parameters,
or the PAT. A lock or disk failure is an error, not a credential mismatch.
After a failed replacement commit, retain the original client, restore
storage access, and call `retry_pat_persistence()` as described below.

### Transition from the downloadable example

The old `LocalPATStore` database is unversioned and is not opened or silently
converted by `SQLitePATStore`. Stop every job using that lineage and resolve
any pending refresh first. Recover through My Trust Center if needed, then
initialize a fresh built-in store, using a new path or alias if the old
database occupies the default location. Supply the currently valid PAT
through a trusted input path; if it cannot be recovered, revoke the active
PAT if present and create a fresh one in My Trust Center. Update every job
to use the new store and verify reads before restarting jobs. Retire the
old database and backups securely. Never run old and new stores as independent
rotators of the same lineage.

## Store-backed API

Import `TrustCenterClient`, `PATStore`, `PATStoreRecord`, `PATRefreshResult`,
and the PAT exceptions from `sfdctrust`.

```python
TrustCenterClient.from_store(
    store: PATStore, *, http_client: httpx.Client | None = None, max_retries: int = 2
) -> TrustCenterClient
client.refresh_pat(*, expires_in_days: int | None = None) -> PATRefreshResult
client.retry_pat_persistence() -> PATRefreshResult
```

Construction loads and validates the seeded credential. A missing or unreadable
store, an unseeded lineage, or an invalid record raises `ConfigurationError`.
A pending marker raises `PATRefreshPendingError`. Before each ordinary HTTP
attempt the SDK checks the store again for pending state and revision changes.
A changed revision raises `ConfigurationError`. Recreate other running clients
with `from_store` or restart their processes to load the replacement. Reads
that passed the check before a concurrent rotation began can finish with the
old PAT and receive 401. For a coordinated rollout, pause readers before rotation.

A refresh reads the latest credential, claims it with a conditional pending
write, then sends one POST. Use `None` for the server default of 30 days or
choose a whole number from 1 through 30. Booleans are rejected. Static clients
reject refresh before I/O. A successful refresh immediately revokes the old
PAT. The current client switches only after the replacement is saved durably.
`PATRefreshResult(metadata_valid: bool)` reports whether `tokenId`, `label`,
`createdAt`, and `expiresAt` matched the documented response schema. If metadata
is missing or malformed but the response contains a usable replacement, the
SDK saves it and returns `metadata_valid=False`. The result contains no
server-supplied values.

### Adapter contract

An adapter instance addresses one PAT lineage. Every process that can rotate
that lineage must use the same underlying record and atomic coordination.
The SDK checks the interface at runtime. Durability and coordination are
responsibilities of the adapter and its backing system.

- `PATStoreRecord(revision: UUID, pat: str, pending_attempt: UUID | None = None)`
  holds one version of the credential and its optional pending marker.
  Generate a fresh UUID for every new credential, including reseeds. Never
  reuse a revision for a different PAT. `record.get_pat() -> str` is for
  trusted adapter I/O and explicit operator recovery.
- `load() -> PATStoreRecord | None` returns the latest committed record from a
  strongly consistent read, or `None` when unseeded. Preserve pending state
  when reading or reconstructing the record. Raise on access or decoding failures.
- `compare_and_swap(*, expected_revision: UUID, expected_attempt: UUID | None,
  replacement: PATStoreRecord) -> bool` compares both fields and atomically
  replaces the entire record across processes. Return `True` only after a
  durable commit. Return `False` only if the comparison failed and no write
  occurred. Raise if the write or its acknowledgment cannot be confirmed.
  A new credential and removal of its marker must commit in the same transaction.
- Pending markers must survive crashes, restarts, and lease expiry. A process
  that loses its lease must still leave the durable marker in place. Use one
  consistent, secure record, or a transactional scheme with equivalent atomic
  visibility. A cache, eventually consistent replica, or process-local mutex
  alone is unsuitable.
- The adapter owns access control, encryption at rest and in transit, seeding,
  operator reconciliation, and secret-safe observability. Provision distinct
  storage identities for distinct lineages. Secure the initial PAT through the
  adapter's administrative path and create a fresh revision with no marker.
  Treat stale environment PATs and external copies as separate credentials to
  manage through their existing processes.

For storage systems other than the built-in SQLite option, implement the
same adapter contract. In the example below,
`my_service.trust_store` is your integration module and `store` is an instance
of your own implementation of the contract above. Seed it through its
administrative path before running this code. Run it in an interactive
session so the client remains available for persistence recovery if needed.

```python
from my_service.trust_store import store  # Your seeded, durable PATStore adapter.
from sfdctrust import TrustCenterClient

client = TrustCenterClient.from_store(store)
result = client.refresh_pat(expires_in_days=7)
print('Response metadata validated:', result.metadata_valid)
print('Authorized tenants:', len(client.tenants.list().tenants))
```

The SDK keeps raw credentials, response bodies, headers, request URLs, and
underlying errors out of its refresh result and errors. Store records redact
the PAT in their repr and reject pickling. The adapter and HTTP client see
plaintext where needed. Configure hooks, proxies, HTTPX and HTTP-core logging,
store telemetry, and error reporting so they do not record request or response
content, URLs, credentials, or locals. Redaction does not protect against
code deliberately inspecting process memory or private state. Call `client.close()`
after use and any persistence recovery.

(async-store-backed-clients)=
### Async store-backed clients

Implement `AsyncPATStore` with awaitable `load()` and `compare_and_swap()`
using the same arguments, records, return values, and cross-process
guarantees as `PATStore`. Use asynchronous backing I/O and propagate
`asyncio.CancelledError` from the adapter. A cancelled or failed write can
have committed before the caller receives confirmation. Subsequent loads
must reflect the latest committed record, including any pending marker.
Each CAS must still compare both the revision and attempt at the time of
the atomic write.

The integration below assumes `my_service.trust_store` exports your seeded,
durable `AsyncPATStore` instance as `async_store`. Use `python -m asyncio`
for an interactive session that keeps the client available for recovery.

```python
from my_service.trust_store import async_store
from sfdctrust import AsyncTrustCenterClient

client = await AsyncTrustCenterClient.from_store(async_store)
result = await client.refresh_pat(expires_in_days=7)
print('Response metadata validated', result.metadata_valid)
print('Authorized tenants', len((await client.tenants.list()).tenants))
```

If the replacement commit was interrupted or unconfirmed, keep the same
client and restore access to the store. Reconcile the write in a running task.

```python
result = await client.retry_pat_persistence()
print('Response metadata validated', result.metadata_valid)
```

Call `await client.aclose()` after use and any persistence recovery. As with
the sync API, store-backed reads check the current revision and pending
marker before each HTTP attempt. Recreate clients whose loaded revision has
changed. Explicit refresh loads the current credential before claiming it.

#### Cancellation during rotation

| Cancellation point | Durable state and recovery |
| --- | --- |
| Pending-marker write before acknowledgment | The SDK sends no POST. The marker may have committed. Inspect the store through its administrative path and reconcile the exact marker after establishing that the write has settled. |
| Refresh POST or old-PAT probe | The marker remains unresolved. Cancellation can arrive before Salesforce's outcome is known. Quiesce rotators and follow the ambiguous-outcome runbook below. |
| Replacement commit or response cleanup after decoding a usable replacement | The client retains the replacement privately before the next await. Use `await client.retry_pat_persistence()` to confirm a committed replacement or conditionally finish the matching attempt with store I/O alone. |
| Marker clear after a known rejection | The clear may have committed. Inspect the exact revision and marker through the store's administrative path. |

Cancellation propagates to the caller in each case. An unresolved marker
blocks new store-backed clients and ordinary reads. If the original
client or process is lost, a committed replacement can be loaded by a
new client. If the marker remains and the replacement was lost, establish
whether the old PAT is still usable after the original operation settles.
If it is unusable, recover in My Trust Center and reseed through the
administrative path described below.

### Recovery runbook

| Outcome | Operator action |
| --- | --- |
| `AuthenticationError` (401) | Check the configured lineage, token validity, and lifetime limits. A 401 does not identify the cause. Recover the PAT in My Trust Center if necessary. |
| `RateLimitError` (429) | Salesforce rejected refresh before rotating. The old PAT stays active. Before a later explicit attempt, wait a few seconds plus random jitter. For repeated 429s, double the base delay up to an operator-defined cap and limit the number of attempts. The response is plain text without retry headers. |
| `PATRefreshAmbiguousError`, `probe == PATProbeResult.OLD_PAT_ACCEPTED` | The old PAT worked when the SDK probed it. Keep the marker until the original request has settled. Quiesce rotators, wait, and recheck the old PAT with a harmless tenant listing before conditionally clearing the exact marker. Only then consider a later explicit refresh. |
| `PATRefreshAmbiguousError`, `probe == PATProbeResult.OLD_PAT_REJECTED` | Salesforce may have rotated without delivering the replacement. Quiesce rotators. If the replacement is unavailable, revoke the active PAT if present in My Trust Center, create one, and reseed the store. |
| `PATRefreshAmbiguousError`, `probe == PATProbeResult.INCONCLUSIVE` | Preserve the marker. After the original request has settled, establish whether the old PAT still works or recover through My Trust Center. |
| `PATPersistenceError` while saving the replacement | Keep the original client alive and restore store access. Call `client.retry_pat_persistence()` to reconcile a lost acknowledgment or repeat the conditional write. It sends no HTTP requests and never overwrites a different revision or attempt. |
| `PATPersistenceError` while setting or clearing the marker | Inspect the store through its administrative path. An unacknowledged marker creation sends no POST. An unacknowledged marker clear after known rejection can leave the marker in place. Reconcile the exact stored revision and attempt before proceeding. |
| `PATRefreshPendingError` | A rotation may still be in flight or a process may have stopped mid-rotation. Verify ownership and outcome before taking administrative action. |

After an ambiguous outcome the SDK makes one status-only `GET /tenants` using
the old PAT. It preserves the marker for all probe results, including 200,
because an interrupted POST may still be settling. A 401 indicates rejection
of the old PAT and other statuses or request failures are inconclusive.
The SDK never follows a probe with another refresh.

While a replacement write remains unresolved, the initiating client blocks
reads and refresh. Other store-backed clients block on the pending marker
or reject a changed revision. If the commit actually succeeded and only its
acknowledgment was lost, a newly constructed client can load the committed
replacement. A process crash before durable commit can lose the only copy
of the replacement. If the store still has a pending attempt and the PAT is
unrecoverable, use My Trust Center to create a fresh PAT after revoking the
active one if present.

For administrative reconciliation, stop all rotators and check for in-flight
requests before clearing or replacing the marker. Use a controlled read with
the old PAT only to determine whether it still works. Conditionally clear the
matching marker while retaining the revision only when you have established
that the old credential is still usable and no refresh can still be in flight.
If reseeding, conditionally replace the observed revision and marker with a
fresh revision and the new PAT in one durable write. Restart or recreate
clients afterward and verify tenant listing. A PAT and all its replacements
can last up to 365 days in total. See the
[Salesforce authentication and recovery guide](https://developer.salesforce.com/docs/mytrust-api/authentication.html).
