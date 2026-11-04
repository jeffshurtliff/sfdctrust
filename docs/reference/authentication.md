# Authentication and PAT rotation

The synchronous `TrustCenterClient` uses an internal HTTPX Bearer authentication
component for each request.

For step-by-step PAT creation and a downloadable local test store with a
seeding command, start with {doc}`../getting-started/setup`.

## Credential selection

- Construction requires an explicit `pat`; it never reads the environment.
- Opt-in `TrustCenterClient.from_env()` reads only `SFDCTRUST_PAT`.
- `TrustCenterClient.from_env(pat=...)` uses the override without reading the environment. An explicit
  empty, blank, or `None` override raises `sfdctrust.ConfigurationError`, even when the
  environment contains a valid PAT.
- `TrustCenterClient.from_store(store, ...)` loads a seeded, caller-supplied store.
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
`AuthenticationError` and fails immediately. The transport disables redirects on every request. A read returning 401
never triggers refresh.

Authenticated request objects necessarily contain the Authorization header. Do not log or
serialize those objects or manually expose the secret. The transport uses SDK-authored errors when translating HTTPX failures.

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

The SDK does not bundle a production adapter. In the example below,
`my_service.trust_store` is your integration module and `store` is an instance
of your own implementation of the contract above. Seed it through its
administrative path before running this code. Run it in an interactive
session so the client remains available for persistence recovery if needed.

```python
from my_service.trust_store import store  # Your seeded, durable PATStore adapter.
from sfdctrust import TrustCenterClient

client = TrustCenterClient.from_store(store)
result = client.refresh_pat(expires_in_days=7)
print("Response metadata validated:", result.metadata_valid)
print("Authorized tenants:", len(client.tenants.list().tenants))
```

The SDK keeps raw credentials, response bodies, headers, request URLs, and
underlying errors out of its refresh result and errors. Store records redact
the PAT in their repr and reject pickling. The adapter and HTTP client see
plaintext where needed. Configure hooks, proxies, HTTPX and HTTP-core logging,
store telemetry, and error reporting so they do not record request or response
content, URLs, credentials, or locals. Redaction does not protect against
code deliberately inspecting process memory or private state. Call `client.close()`
after use and any persistence recovery.

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
