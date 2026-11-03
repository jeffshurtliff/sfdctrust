# Authentication foundation

The internal `sfdctrust._auth.PATAuth` component implements HTTPX Bearer authentication.
It is an implementation detail for the future SDK client, rather than a stable public
credential interface. The private transport uses it for each request.

## Credential selection

- Construction requires an explicit `pat`; it never reads the environment.
- Opt-in `PATAuth.from_env()` reads only `SFDCTRUST_PAT`.
- `PATAuth.from_env(pat=...)` uses the override without reading the environment. An explicit
  empty, blank, or `None` override raises `sfdctrust.ConfigurationError`, even when the
  environment contains a valid PAT.
- No `.env`, credential files, or secret providers are read. The environment is never changed.

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
`AuthenticationError` and fails immediately. The transport also disables redirects per
request because HTTPX handles redirects outside the auth flow. PAT refresh and token
persistence remain deferred.

Authenticated request objects necessarily contain the Authorization header. Do not log or
serialize those objects or manually expose the secret. The transport uses SDK-authored errors when translating HTTPX failures.
