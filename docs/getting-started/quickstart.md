# Read tenant status and events

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

## Read status, search events, and inspect details

Use IDs from the tenant list, snapshot, or search results. Tenant detail
includes Salesforce's event history window. Event detail includes the
timeline when entries are available.

```python
from datetime import UTC, datetime, timedelta

from sfdctrust import TrustCenterClient
from sfdctrust.models.events import EventSearchScope

with TrustCenterClient.from_env() as client:
    snapshot = client.status.snapshot(locale="en-US")
    for incident in snapshot.ongoing.incident:
        print(incident.event_id, incident.title, list(incident.scope.tenants))

    tenants = client.tenants.list()
    if tenants.tenants:
        tenant_id = tenants.tenants[0].id
        end = datetime.now(UTC)
        options = dict(
            scopes=[EventSearchScope(id=tenant_id)],
            start_time=end - timedelta(days=30),
            end_time=end,
            event_types=["incident"],
            page_size=50,
            locale="en-US",
        )
        page = client.events.search(**options)
        results = list(page.events)
        if page.next_page_token is not None:
            next_page = client.events.search(**options, page_token=page.next_page_token)
            results.extend(next_page.events)

        if results:
            event = client.events.get(results[0].event_id, locale="en-US")
            for entry in event.timeline or []:
                print(entry.created_at, entry.sub_event_type, entry.message)

        tenant = client.tenants.get(tenant_id, locale="en-US")
        for event in tenant.events:
            print(event.event_id, event.status)
```

The search includes the start instant and excludes the end instant. Each
continuation repeats the original parameters and uses the token from the
preceding page. Salesforce's tenant history covers lifecycle overlap
within 365 days before or after the request time. Informational messages
cover the preceding 365 days. The PAT determines which tenants and events
are visible. An empty snapshot bucket, search page, or history establishes
no Salesforce-wide health claim.

See {doc}`../reference/events-and-status` and {doc}`../reference/tenants` for
public signatures, model fields, and error handling.
