<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jeffshurtliff/sfdctrust/main/docs/_static/logos-dark/sfdctrust-logo-dark-320.png">
    <img src="https://raw.githubusercontent.com/jeffshurtliff/sfdctrust/main/docs/_static/logos/sfdctrust-logo-320.png" alt="sfdctrust logo" width="200">
  </picture>
</p>

# sfdctrust

An unofficial, community-maintained Python SDK project for the **Salesforce My Trust Center
API**. It is not affiliated with or supported by Salesforce.

The synchronous and asynchronous clients list authorized tenants, retrieve
status snapshots, search events, and return event timelines and tenant history
through their detail operations.

The API exposes only tenants authorized by the caller's personal access token (PAT);
empty results do not establish Salesforce-wide health.

See the [API contract and implementation decisions](https://sfdctrust.readthedocs.io/en/latest/API_CONTRACT.html) for the verified
operation inventory, schema notes, and authentication rules.

## Quickstart

Install from PyPI with `python -m pip install sfdctrust` on Python 3.12 or later.
Set `SFDCTRUST_PAT` in the process environment using a PAT from My Trust Center.
For installation in a virtual environment, see [Installation](https://sfdctrust.readthedocs.io/en/latest/getting-started/installation.html).
For creating a PAT and entering it at a hidden prompt, see
[Prepare to use sfdctrust](https://sfdctrust.readthedocs.io/en/latest/getting-started/setup.html).

```python
from sfdctrust import TrustCenterClient

with TrustCenterClient.from_env() as client:
    for tenant in client.tenants.iter_all(page_size=50):
        print(tenant.id, tenant.name)
```

If you use `client.tenants.list()` to fetch a single page and `page.next_page_token`
is set, request the next page with
`client.tenants.list(page_token=page.next_page_token)` inside the same context.
If you supplied `page_size` or `locale` on the first call, repeat those values.
See the [quickstart](https://sfdctrust.readthedocs.io/en/latest/getting-started/quickstart.html) and
[tenant reference](https://sfdctrust.readthedocs.io/en/latest/reference/tenants.html) for details.

## Use the asynchronous client

```python
import asyncio

from sfdctrust import AsyncTrustCenterClient


async def main():
    async with AsyncTrustCenterClient.from_env() as client:
        snapshot = await client.status.snapshot()
        print('Ongoing incidents', len(snapshot.ongoing.incident))
        async for tenant in client.tenants.iter_all(page_size=50):
            print(tenant.id, tenant.name)


if __name__ == '__main__':
    asyncio.run(main())
```

Await single-page methods and the `list_all()` and `search_all()` collectors.
Consume `iter_all()` and `iter_search()` directly with `async for`.
Both clients use the same arguments, response models, and retry rules.
[Package reference](https://sfdctrust.readthedocs.io/en/latest/reference/package.html)

## Read status, search events, and inspect details

Use IDs from the tenant list, snapshot, or search results. Tenant detail
includes Salesforce's event history window. Event detail includes the
timeline when entries are available.

```python
from datetime import UTC, datetime, timedelta

from sfdctrust import TrustCenterClient
from sfdctrust.models.events import EventSearchScope

with TrustCenterClient.from_env() as client:
    snapshot = client.status.snapshot(locale='en-US')
    for incident in snapshot.ongoing.incident:
        print(incident.event_id, incident.title, list(incident.scope.tenants))

    tenants = client.tenants.list()
    if tenants.tenants:
        tenant_id = tenants.tenants[0].id
        end = datetime.now(UTC)
        results = client.events.search_all(
            scopes=[EventSearchScope(id=tenant_id)],
            start_time=end - timedelta(days=30),
            end_time=end,
            event_types=['incident'],
            page_size=50,
            locale='en-US',
        )

        if results:
            event = client.events.get(results[0].event_id, locale='en-US')
            for entry in event.timeline or []:
                print(entry.created_at, entry.sub_event_type, entry.message)

        tenant = client.tenants.get(tenant_id, locale='en-US')
        for event in tenant.events:
            print(event.event_id, event.status)
```

Use `client.tenants.list_all(page_size=50)` to collect tenants, or use
`client.events.iter_search(...)` with the same search arguments to consume
events lazily. Both traversals preserve order and duplicates. An empty page
continues when a cursor is present, including an empty string. A repeated cursor
or a required page beyond `max_pages` (default 1000) raises `PaginationError`
from `sfdctrust`. Iterators can yield items before a failure. Stale cursors raise
HTTP 400 `APIStatusError` without a restart.

All credential entry points default to two additional attempts per eligible read.
Set `max_retries=0` to disable SDK retries or choose an integer up to 5.

The search includes the start instant and excludes the end instant. Each
continuation repeats the original parameters and uses the token from the
preceding page. Salesforce's tenant history covers lifecycle overlap
within 365 days before or after the request time. Informational messages
cover the preceding 365 days. The PAT determines which tenants and events
are visible. An empty snapshot bucket, search page, or history establishes
no Salesforce-wide health claim.

See the [status and event reference](https://sfdctrust.readthedocs.io/en/latest/reference/events-and-status.html) for signatures and models.

## Rotate a PAT explicitly

For rotation, use `TrustCenterClient.from_store(store)` with a seeded,
caller-supplied adapter that provides durable atomic updates shared by all
rotators of the PAT. Call `client.refresh_pat(expires_in_days=7)` to save and
activate a replacement. It sends one POST and returns a secret-free
`PATRefreshResult`. The constructor and `from_env()` remain static credential
modes. See the [authentication reference](https://sfdctrust.readthedocs.io/en/latest/reference/authentication.html)
for the adapter contract and recovery runbook. To create and seed a working
local test store, follow [Prepare to use sfdctrust](https://sfdctrust.readthedocs.io/en/latest/getting-started/setup.html).

For asyncio, use `await AsyncTrustCenterClient.from_store(store)` with an
`AsyncPATStore`, then await rotation and any persistence recovery.
[Async adapter contract and cancellation recovery](https://sfdctrust.readthedocs.io/en/latest/reference/authentication.html#async-store-backed-clients)

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

The [exception hierarchy](https://sfdctrust.readthedocs.io/en/latest/reference/exceptions.html) is available from `sfdctrust`, including
`ConfigurationError`, `AuthenticationError`, and the shared `TrustCenterError` base.
See [authentication](https://sfdctrust.readthedocs.io/en/latest/reference/authentication.html) for the implemented boundaries.

The documentation uses Sphinx with the optional `docs` dependency group:

```sh
poetry install --with docs
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

See [Maintain the documentation](https://sfdctrust.readthedocs.io/en/latest/maintainers/documentation.html) for details.
