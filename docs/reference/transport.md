# Internal HTTP transport

Each transport reuses one HTTPX client and performs no network I/O during construction.
The synchronous transport uses `httpx.Client`, and the asyncio transport uses
`httpx.AsyncClient` with awaitable backoff. Requests take an API-relative path with an optional leading slash.
Pass query parameters and the optional JSON body separately. The transport validates the
destination under the fixed production HTTPS API base before applying PAT authentication.
It sends `Accept: application/json` and `sfdctrust/<version>` as the user agent, with
redirect following disabled per request.

## Client ownership and settings

- The SDK closes an internally created client on explicit close or context exit.
  It verifies TLS using HTTPX's default trust store, ignores environment proxy and
  CA overrides, and allows up to 20 total and 10 idle connections.
- An injected client is caller-owned. The caller controls its pool, TLS, proxy policy,
  hooks, and underlying transport. Inject only a trusted client because it handles
  authenticated requests. HTTPX diagnostics and injected hooks can expose request data.
- Each attempt uses the transport's timeout configuration, including with injected
  clients. The defaults are 5 seconds each for connect and pool and 30 seconds each
  for read and write. Custom `httpx.Timeout` values must be positive and finite in
  all four phases in the private transport. Public phase-timeout configuration
  was deferred for 1.0 by maintainer decision; injected HTTPX timeout settings
  do not override SDK limits. These are HTTPX phase timeouts, not a total deadline.
  See {doc}`compatibility`.

## Responses and retries

The transport inspects the status before reading the response body. It maps 401,
404, and 429 to their specialized exceptions and other 4xx and 5xx statuses to
`APIStatusError`. Unexpected statuses such as redirects raise `TrustCenterError`.
Successful responses must contain valid UTF-8 JSON. Empty or invalid JSON raises
`MalformedResponseError`. Resources validate decoded JSON against their response models. Exceptions omit server messages, requests, responses, and URLs.
Request-ID capture remains deferred.

The retry allowlist covers `GET /tenants`, `GET /tenants/{tenantId}`, `GET /status`,
`GET /events/{eventId}`, and read-only `POST /events/search`. HTTPX connection
establishment errors and timeouts, along with HTTP 429, 500, 502, 503, and 504,
are retryable. HTTP 400, 401, 404, redirects, and malformed successful responses
fail immediately.

All credential entry points accept keyword-only `max_retries: int = 2`. The count
is additional SDK attempts per request. It accepts integers from 0 through 5,
excluding booleans. Zero disables SDK retries. An injected HTTPX client may
implement its own transport retries.

When another attempt is available, the SDK honors a valid `Retry-After` on
HTTP 429 or 503. The header accepts nonnegative integer seconds or an HTTP date.
Zero and past dates produce zero delay. The SDK caps the header-directed wait
at 30 seconds and adds no jitter to it. This cap can cause a retry sooner than
the server requested. See [RFC 9110, section 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

Without a valid applicable header, the SDK waits 0.5 seconds before the first
retry, doubling the base for each additional retry, plus up to 0.25 seconds of
jitter each time. The local Salesforce specification documents plain-text 429
responses without `Retry-After` for all five reads. The response closes before
the wait, and retries preserve the request, including any cursor and search
body. Exhaustion surfaces the final translated error without another wait.

Cancelling an async request or retry wait propagates
`asyncio.CancelledError`. The SDK closes any response it is handling and
the cancelled traversal issues no further retries or page requests.

The generic request path rejects PAT refresh before authentication. The dedicated
store-backed refresh path sends one `POST /pats/refresh` to the same fixed
production HTTPS destination with the same phase timeouts and redirect policy.
It omits the body for the default lifetime or sends only `expiresInDays`.
It decodes a response body only on success (documented as HTTP 200). A plain-text refresh 429 is a
known rejection and is never retried by the SDK. After an ambiguous outcome,
one status-only `GET /tenants` probes the old PAT without read retries.
`max_retries` affects neither request.

An injected client's transport, proxies, and hooks must avoid replaying the
POST. Keep HTTP diagnostics and response hooks from disclosing credentials.
See the {doc}`authentication` reference for persistence and recovery.
