# Tenants

Call `client.tenants.list()` to retrieve one page of tenants visible to your
PAT. Empty results provide no information about Salesforce-wide health.

| Keyword argument | Behavior |
| --- | --- |
| `page_size` | Integer from 1 through 200. Omission uses Salesforce's default of 100. |
| `page_token` | Opaque string of at most 4096 characters. Pass the preceding page's `next_page_token` unchanged. |
| `locale` | BCP 47 locale string. Salesforce defaults to `en-US` and applies that fallback for unsupported or malformed values. |

An omitted argument or `None` leaves that query parameter out. Repeat the
original page size and locale when requesting the next page. An invalid local
argument raises `ConfigurationError` before I/O. Salesforce's HTTP 400 for
an invalid, stale, or mismatched cursor surfaces as `APIStatusError` without
restarting the traversal. Invalid JSON or response fields raise
`MalformedResponseError`. See the {doc}`exception reference <exceptions>` for
other request failures.

(tenant-traversal)=
## Traverse tenants

```python
from collections.abc import Iterator

from sfdctrust import PaginationError
from sfdctrust.models.tenants import Tenant

client.tenants.iter_all(
    *,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
    max_pages: int = 1000,
) -> Iterator[Tenant]
client.tenants.list_all(
    *,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
    max_pages: int = 1000,
) -> list[Tenant]
```

`iter_all()` fetches the first page when advanced and fetches the next page
only after yielding the current page's items. `list_all()` consumes that
iterator and propagates any failure. Both preserve server order and repeated
entries. They start at the supplied cursor and forward each continuation
unchanged, preserving all other arguments and omissions. Only an absent
cursor ends traversal. An empty page with a cursor continues, and an
empty-string cursor is a supplied value.

`max_pages` must be a positive integer. Booleans raise `ConfigurationError`.
Each successfully fetched page counts, including the initial page and empty
pages. Retries do not count. A terminal page at the limit succeeds. If another
page would exceed the limit or reuse a cursor, including the starting cursor,
the SDK raises `PaginationError` before requesting that page. A lazy iterator
may have yielded items by then.

## Response models

Import `Tenant` and `TenantListResponse` from `sfdctrust.models.tenants`.

- `TenantListResponse.tenants` is a list of up to 200 `Tenant` objects and may
  be empty. An absent `next_page_token` marks the final page.
- `Tenant` has string fields `id`, `cloud`, and `name`. The SDK treats IDs
  and cloud values as opaque strings. The optional fields `environment` and
  `my_domain` are strings when present.
- Both models validate known field types strictly and preserve unknown fields.
  Optional fields read as `None` when omitted. Explicit JSON null is invalid
  for those fields. Use `model_fields_set` to inspect which fields were present.

Use Pydantic's wire aliases and omit unset fields when serializing a page to a
JSON-compatible dictionary:

```python
data = page.model_dump(mode="json", by_alias=True, exclude_unset=True)
```

The aliases are `myDomain` and `nextPageToken`.

## Tenant detail

```python
client.tenants.get(tenant_id: str, *, locale: str | None = None) -> TenantDetail
```

Import `TenantDetail` and `TenantLocation` from `sfdctrust.models.tenants`.
`TenantDetail` extends `Tenant` with required `events`, a list of
`EventSummary` objects scoped to the requested tenant. Salesforce includes
events whose lifecycle overlaps the 365 days before or after the request
time. Informational messages cover the preceding 365 days. A patch can
appear once per lifecycle, so the SDK preserves repeated IDs and order.

Optional `region`, `version`, and `maintenance_window` (`maintenanceWindow`)
are nullable strings. Optional `location` is a non-null `TenantLocation`
when present. It requires the string fields `city`, `state_name`
(`stateName`), `state_code` (`stateCode`), `country_name` (`countryName`),
and `country_code` (`countryCode`). Salesforce uses empty strings when
location components are unavailable. Use `model_fields_set` and
`model_dump(mode="json", by_alias=True, exclude_unset=True)` to retain
the distinction between omitted fields and explicit null.

Supply the opaque `tenant_id` from a tenant response. The SDK rejects
empty, unsafe, or unrepresentable path segments with `ConfigurationError`
before I/O. A detail HTTP 404 raises `NotFoundError` for a nonexistent or
unauthorized tenant. Locale works as in listing. See
{doc}`events-and-status` for the event fields and timeline.
