# List authorized tenants

Install the package from a [development checkout](installation.md) and configure
`SFDCTRUST_PAT` in the process environment using a PAT from My Trust Center. See
[Salesforce's PAT setup guide](https://developer.salesforce.com/docs/mytrust-api/get-started.html).

```python
from sfdctrust import TrustCenterClient

with TrustCenterClient.from_env() as client:
    page = client.tenants.list()
    for tenant in page.tenants:
        print(tenant.id, tenant.name)
```

Each call returns one page scoped to the PAT's authorized tenants. An empty page
provides no information about Salesforce-wide health.

If `page.next_page_token` is present, pass it as `page_token` in the next call.
Keep the page size and locale the same across both requests, including any omitted
values. For example:

```python
with TrustCenterClient.from_env() as client:
    page = client.tenants.list(page_size=50, locale="ja-JP")
    if page.next_page_token is not None:
        next_page = client.tenants.list(
            page_size=50, page_token=page.next_page_token, locale="ja-JP"
        )
```

Salesforce can reject a stale or mismatched cursor with HTTP 400. The SDK raises
`APIStatusError` with `status_code == 400` so you can decide whether to start a
new traversal. See the {doc}`../reference/tenants` for model fields and serialization.
