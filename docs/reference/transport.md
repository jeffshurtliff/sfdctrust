# Internal HTTP transport

The private synchronous transport reuses one HTTPX client and performs no network I/O
during construction. Requests take an API-relative path with an optional leading slash.
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
  all four phases. These are HTTPX phase timeouts.

## Responses and retries

The transport inspects the status before reading the response body. It maps 401,
404, and 429 to their specialized exceptions and other 4xx and 5xx statuses to
`APIStatusError`. Unexpected statuses such as redirects raise `TrustCenterError`.
Successful responses must contain valid UTF-8 JSON. Empty or invalid JSON raises
`MalformedResponseError`. Valid JSON values pass through for future resources to
validate. Exceptions omit server messages, requests, responses, and URLs.
Request-ID capture remains deferred.

The retry allowlist covers `GET /tenants`, `GET /tenants/{tenantId}`, `GET /status`,
`GET /events/{eventId}`, and read-only `POST /events/search`. HTTPX connection
establishment errors and timeouts, along with HTTP 429, 500, 502, 503, and 504,
allow up to two retries. The waits are 0.5 and 1.0 seconds plus up to 0.25 seconds
of jitter each, for at most 2 seconds of scheduled sleep. A plain-text 429 follows
the same policy. The transport uses its own delays independently of `Retry-After`
and surfaces the final translated error if attempts are exhausted.

PAT refresh is rejected before authentication. The public client, resource methods,
response models, pagination, and async support are outside this milestone.
