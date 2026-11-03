# Tenant listing

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
