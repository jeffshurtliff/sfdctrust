# Read My Trust Center from the command line

This guide describes the **unreleased 1.1 development version**. Install a
reviewed development wheel or checkout as described in {doc}`installation`.
The published 1.0.0 release does not provide the general read CLI.

## Available commands

```sh
sfdctrust --version
sfdctrust --help
sfdctrust tenants --help
sfdctrust tenants list --help
sfdctrust tenants get --help
sfdctrust status --help
sfdctrust status snapshot --help
sfdctrust events --help
sfdctrust events search --help
sfdctrust events get --help
sfdctrust tenants list --page-size 25 --json
sfdctrust tenants get synthetic-tenant --locale en-US --json
sfdctrust status snapshot --locale en-US --json
sfdctrust events search --tenant-id synthetic-tenant --start-time 2026-11-01T00:00:00Z --end-time 2026-11-02T00:00:00Z --event-type incident --json
sfdctrust events get synthetic-event --store-alias monitoring
```

`python -m sfdctrust` is equivalent to the installed `sfdctrust` command.
Read options follow the action (`list`, `get`, `snapshot`, or `search`); spell
long options in full. Tenant listing and event search accept `--page-size N`
and `--page-token TOKEN`. All five operations accept
`--locale LOCALE`, `--json`, and one optional store selector. Tenant detail
includes its supplied event history; it does not make additional event requests.

Status snapshot retrieves the `ongoing` and `upcoming` groups, each with `patch`,
`incident`, `maintenance`, and `informationalMessage` buckets. Each scoped event
is retained separately, even when its ID appears in another scope or stage.
Event detail includes its supplied timeline without additional requests.

## Event search inputs

Search requires `--tenant-id TENANT_ID` repeated for **1–50 tenant scopes**,
`--start-time TIMESTAMP` (inclusive), and `--end-time TIMESTAMP` (exclusive).
Use full timezone-aware timestamps such as `2026-11-01T00:00:00Z` or
`2026-11-01T05:45:00+05:45`. Date-only, naive, space-separated, or incomplete
timestamps are invalid. Start must precede end when compared as instants,
including when their offsets differ. Offsets use whole minutes.

Optional `--event-type` may be repeated with distinct values from `patch`,
`incident`, `maintenance`, and `informationalMessage`. Omit it to include all
types. Response types may include future values; those do not automatically
become valid request filters. Tenant IDs and filters retain supplied order;
duplicate tenant scopes are forwarded for Salesforce to handle.

```sh
sfdctrust events search --tenant-id synthetic-one --tenant-id synthetic-two --start-time 2026-11-01T00:00:00Z --end-time 2026-11-02T00:00:00Z --event-type patch --event-type maintenance --page-size 25 --locale en-US --json
```

## Credentials and stores

Without a store selector, reads call `TrustCenterClient.from_env()` and use
`SFDCTRUST_PAT`. Set the PAT through your trusted secret-management workflow;
never pass it as a command argument. The CLI does not read `.env` files,
prompt, discover stores, or refresh credentials. See {doc}`setup` for obtaining
and storing a PAT.

Select an **existing, seeded** SQLite store explicitly:

```sh
sfdctrust tenants list --store --json
sfdctrust tenants list --store-path /private/local/path/pat.sqlite3 --json
sfdctrust tenants get synthetic-tenant --store-alias monitoring
```

| Selector | Location |
| --- | --- |
| `--store` | `~/.sfdctrust/pat.sqlite3` |
| `--store-path PATH` | The supplied existing local database |
| `--store-alias ALIAS` | `~/.sfdctrust/ALIAS.sqlite3` |

These selectors are mutually exclusive. Explicit store selection ignores
`SFDCTRUST_PAT`, including when opening/loading the store fails. There is no
fallback. An absent environment PAT does not trigger store discovery either.
Aliases follow the SDK's ASCII letters/digits/underscore/hyphen and reserved-name
rules. Invalid selector syntax fails as invalid arguments before credential I/O.

The SDK's private ownership/permissions, supported format, seeded record,
pending-rotation, and changed-revision checks remain enforced. Missing, unsafe,
unseeded, pending, or changed stores fail with exit 3; the CLI does not initialize,
repair, reseed, or rotate them. Use one shared store for one PAT lineage under
one OS account on a trusted encrypted local volume, outside network/synced folders.
Store connections close per operation and the SDK client closes after every read,
including failure. See {doc}`../reference/authentication` for storage and recovery.
The separate `python -m sfdctrust.pat_store init` workflow is unchanged.

## Paging and locale

Tenant listing and event search retrieve **one page only**, even if it is empty
and has a continuation.
`--page-size` accepts 1–200. Omission keeps SDK/API defaults. `--page-token`
is opaque, has a 4,096-character limit, and may be an empty string. Repeat the
same page size and locale when continuing; for search, also keep all tenant
scopes, time bounds, and event filters unchanged. The CLI does not persist these inputs.
Use the returned `nextPageToken` verbatim, including an empty cursor:

```sh
sfdctrust tenants list --page-size 25 --locale en-US --json
sfdctrust tenants list --page-size 25 --locale en-US --page-token="" --json
sfdctrust events search --tenant-id synthetic-tenant --start-time 2026-11-01T00:00:00Z --end-time 2026-11-02T00:00:00Z --page-size 25 --locale en-US --page-token="" --json
```

An example with `--page-token=""` is appropriate only when the preceding response actually
returned `"nextPageToken": ""`. An omitted token means no continuation. A stale
cursor surfaces as an API error; the CLI never silently restarts or fetches all
pages. Normal bounded SDK read retries retain the same query inputs/cursor.
`--locale` is forwarded unchanged; Salesforce controls locale fallback.

Values beginning with `-` can look like options to argparse. For option values,
use the equals form, for example `--page-token=-opaque-cursor` or
`--tenant-id=-synthetic-scope`. For positional detail IDs, put options before
`--`, then supply the ID:

```sh
sfdctrust tenants list --page-token=-opaque-cursor --json
sfdctrust tenants get --json -- -synthetic-tenant
sfdctrust events get --json -- -synthetic-event
```

Use these cursors only when returned by the preceding matching query; quoting
alone does not stop argparse interpreting a leading dash as an option.

Detail IDs must be nonempty and safe in a single SDK URL segment. Search scope
IDs are nonempty strings encoded in the JSON request body. Paging, timestamps,
scopes, filters, model inputs, ID/path safety, URL/JSON encoding, and selector arguments are checked before credential
resolution. Help/version and invalid arguments need no credential, store,
prompt, or network access.

## Output and exit codes

`--json` writes exactly one SDK response using
`model_dump_json(by_alias=True, exclude_unset=True)` followed by a newline.
There is no CLI envelope or added timestamp. Unknown fields, explicit nullable
values, omission, array order, tenant scopes, repeated scoped events, and timestamp
offsets are preserved. Original timestamp lexemes/precision, whitespace, and key
ordering are not promised. JSON retains the complete response; handle it as
untrusted service data when displaying it in a terminal or another application.

Default text lists tenant ID, name, cloud, and environment as concise rows.
Tenant detail labels known tenant fields and supplied event history, including
affected tenant IDs. Status text shows all eight group/category buckets,
including empty buckets. Status/search rows show event ID, type, status, title,
and affected tenant IDs, retaining every scoped occurrence in server order.
Event detail labels metadata and each supplied timeline entry with its tenant
IDs. An omitted timeline is labeled separately from a supplied empty list.
Text preserves history/timeline order and repeated events and escapes
nonprinting characters in displayed fields, including terminal controls. A continuation is labeled
`nextPageToken`; an empty cursor is shown as `""`. Text is a human view and may
omit response fields, scope metadata, or top-level extras; use JSON for complete
data and automation. Text/help/diagnostic wording and layout can change.

Empty pages, buckets, histories, or timelines are successful observations of authorized tenant scope;
they do not establish Salesforce-wide health. No freshness timestamp is added.

Responses are fully rendered and connections closed before writing stdout.
Request and validation failures leave stdout empty. Diagnostics go to stderr
without supplied values, raw request/response data, exception chains, or
tracebacks. An output device can fail after a partial write, so always check the
exit status before consuming output.

| Code | Meaning |
| --- | --- |
| 0 | Success, including empty results, help, or version |
| 1 | Unexpected internal or output failure |
| 2 | Invalid arguments |
| 3 | Credential/configuration/store failure, including HTTP 401 |
| 4 | Other API/network/timeout/malformed-response failure |
| 130 | Interruption |

HTTP 401 does not automatically refresh or distinguish revoked, expired, and
invalid PATs. HTTP 404 does not distinguish an absent tenant/event from an unauthorized
one. Use exit codes, not diagnostic text, in scripts. The separate initialization
CLI retains its own existing exit-code contract.
