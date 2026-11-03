<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logos-dark/sfdctrust-logo-dark-320.png">
    <img src="docs/_static/logos/sfdctrust-logo-320.png" alt="sfdctrust logo" width="200">
  </picture>
</p>

# sfdctrust

An unofficial, community-maintained Python SDK project for the **Salesforce My Trust Center
API**. It is not affiliated with or supported by Salesforce.

The project is in development. The synchronous client lists authorized tenants, retrieves
status snapshots, searches events one page at a time, and returns event timelines and
tenant history through their detail operations.

The API exposes only tenants authorized by the caller's personal access token (PAT);
empty results do not establish Salesforce-wide health.

See the [API contract and implementation decisions](docs/API_CONTRACT.md) for the verified
operation inventory, schema notes, authentication rules, and next implementation steps.

## Quickstart

Install from this checkout with `python -m pip install .` on Python 3.12 or later.
Set `SFDCTRUST_PAT` in the process environment using a PAT from My Trust Center.

```python
from sfdctrust import TrustCenterClient

with TrustCenterClient.from_env() as client:
    page = client.tenants.list()
    for tenant in page.tenants:
        print(tenant.id, tenant.name)
```

If `page.next_page_token is not None`, request the next page with
`client.tenants.list(page_token=page.next_page_token)` inside the same context.
If you supplied `page_size` or `locale` on the first call, repeat those values.
See the [quickstart](docs/getting-started/quickstart.md) and
[tenant reference](docs/reference/tenants.md) for details.

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

See the [status and event reference](docs/reference/events-and-status.md) for signatures and models.

## Development

Requires Python **3.12 or later** and Poetry **2.2 or later, below 3**.
From this checkout:

```sh
poetry install
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry build
```

The SDK uses HTTPX and Pydantic v2. Tests run offline with synthetic PATs.

The [exception hierarchy](docs/reference/exceptions.rst) is available from `sfdctrust`, including
`ConfigurationError`, `AuthenticationError`, and the shared `TrustCenterError` base.
See [authentication](docs/reference/authentication.md) for the implemented boundaries.

The documentation uses Sphinx with the optional `docs` dependency group:

```sh
poetry install --with docs
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

See [Maintain the documentation](docs/maintainers/documentation.md) for details.
