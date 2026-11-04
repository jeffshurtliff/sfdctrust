# Quickstart

Follow {doc}`setup` first and keep the interactive Python session open.
The examples use the `client` you created there. The read steps work with
either setup option. Refresh requires the store from Option B. When pasting
a loop or an `if` block into a basic Python prompt, enter a blank line
after the block to run it.

## Verify access and list tenants

A tenant is a separate Salesforce data space, such as a Salesforce org
or Marketing Cloud Engagement business unit. The API returns only tenants
you can access in My Trust Center.

```python
page = client.tenants.list()
print("Tenants on this page:", len(page.tenants))
for tenant in page.tenants:
    print(tenant.id, tenant.name)

```

This call verifies that Salesforce accepts the PAT. If the list is empty,
check that your account can see tenants in My Trust Center. To get all
tenants, use `client.tenants.list_all()`. Salesforce can split the list into
pages, and this method follows those pages for you. See {doc}`../reference/tenants`
for manual paging.

## See current and upcoming events

A status snapshot groups events by timing and by kind. For example, print
current incidents and upcoming maintenance affecting your tenants.

```python
snapshot = client.status.snapshot()
print("Ongoing incidents:", len(snapshot.ongoing.incident))
for incident in snapshot.ongoing.incident:
    print(incident.event_id, incident.title)

print("Upcoming maintenance:", len(snapshot.upcoming.maintenance))
for maintenance in snapshot.upcoming.maintenance:
    print(maintenance.event_id, maintenance.title)

```

An empty group means this request returned no matching events for your
authorized tenants. It provides no information about Salesforce-wide health.

## Search for events and read a timeline

The example below searches the first tenant from your list for events
in the last 30 days. `EventSearchScope` tells Salesforce which tenant to search.
Leave the event type unspecified to search across event types.

```python
from datetime import UTC, datetime, timedelta

from sfdctrust.models.events import EventSearchScope

if page.tenants:
    tenant_id = page.tenants[0].id
    end = datetime.now(UTC)
    results = client.events.search_all(
        scopes=[EventSearchScope(id=tenant_id)],
        start_time=end - timedelta(days=30),
        end_time=end,
    )
else:
    results = []

print("Matching events:", len(results))
for event in results:
    print(event.event_id, event.title, event.status)

```

If the search returned events, use the first event's ID to request its
details and print any timeline entries.

```python
if results:
    event = client.events.get(results[0].event_id)
    print(event.title)
    for entry in event.timeline or []:
        print(entry.created_at, entry.message)

```

If there are no results, try a different authorized tenant or a different
time window. You can also use an event ID from the status snapshot. To
read a tenant's event history directly, call `client.tenants.get(tenant_id)`
with an ID from your tenant list. For search filters, paging, and field
descriptions, see {doc}`../reference/events-and-status` and
{doc}`../reference/tenants`.

## Use asyncio for the same reads

With `SFDCTRUST_PAT` configured, save this as a Python script and run it with
Python 3.12 or later.

```python
import asyncio

from sfdctrust import AsyncTrustCenterClient


async def main():
    async with AsyncTrustCenterClient.from_env() as client:
        page = await client.tenants.list(page_size=5)
        print("Tenants on this page", len(page.tenants))

        snapshot = await client.status.snapshot()
        print("Upcoming maintenance", len(snapshot.upcoming.maintenance))

        async for tenant in client.tenants.iter_all(page_size=50):
            print(tenant.id, tenant.name)


if __name__ == "__main__":
    asyncio.run(main())
```

Use `await client.tenants.list_all()` to collect pages into a list. Event
search supports both `await client.events.search_all(...)` and
`async for` over `client.events.iter_search(...)` with the search arguments
above. The context closes the SDK-owned HTTP client on exit.
See {doc}`../reference/package` for the async interface and
{doc}`../reference/authentication` for async rotation.

## Rotate a PAT from a store

Use the client from {doc}`setup`, Option B. Make sure the tenant listing
above works before continuing. Refresh replaces the active PAT and
immediately revokes the old one, so pause other users of the same PAT
before testing.

1. In the same Python session, call refresh once. Seven days is an example
   lifetime. Use an integer from 1 to 30, or omit the argument for Salesforce's
   default of 30 days.

   ```python
   result = client.refresh_pat(expires_in_days=7)
   ```

2. If the call returns, the replacement is already saved and this client is
   using it. Verify with a read. `metadata_valid=False` means the replacement
   was saved but some accompanying Salesforce fields did not match the
   expected format.

   ```python
   print("Response details matched the expected format:", result.metadata_valid)
   print("Tenants on this page:", len(client.tenants.list().tenants))
   ```

3. Verify the token survives reopening. Run `client.close()`, then `exit()`,
   and start `python` again from the directory containing `local_pat_store.py`.
   Run the following. If you selected a custom directory during setup,
   use the same directory again.

   ```python
   from local_pat_store import LocalPATStore
   from sfdctrust import TrustCenterClient

   with TrustCenterClient.from_store(LocalPATStore()) as client:
       print("Tenants on this page:", len(client.tenants.list().tenants))

   ```

   Recreate other store-backed clients using this store before resuming
   their reads. An environment-based client keeps the token it was given.

### If a step fails

| What you see | What to check |
| --- | --- |
| `ConfigurationError` when creating the client | For Option A, check that you set `SFDCTRUST_PAT` in this Python session. For Option B, check that seeding succeeded and the client uses the same directory. |
| `AuthenticationError` on a read | Salesforce rejected the PAT. Check for an expired or revoked token and verify that you used My Trust Center's PAT. |
| `RateLimitError` during refresh | Salesforce rejected this attempt before replacing the PAT. Wait before making a later deliberate attempt. See the recovery runbook for backoff. |
| `PATPersistenceError` reporting that durable storage of the replacement could not be confirmed | Keep this Python session and client open. Restore access to the store, then call `client.retry_pat_persistence()`. After it succeeds, verify with `client.tenants.list()`. |
| `PATRefreshAmbiguousError`, `PATRefreshPendingError`, or a marker-write error | Stop and follow the recovery runbook before another refresh. The store can retain a marker to block another attempt while the outcome is uncertain. |

If a replacement was lost and the runbook calls for a new PAT, close all
clients using the test store. Revoke the active token in My Trust Center
if present and create a new one. Seed a **new** private directory with
`python local_pat_store.py seed --directory "path/to/new-private-folder"`.
Use that directory when opening `LocalPATStore` in Python. After you
confirm access with the new store, remove the old test store. For the full
recovery procedure, see {doc}`../reference/authentication`.

When you finish, call `client.close()` on any client you opened outside a
`with` block and exit Python. If the PAT was created solely for testing,
revoke it in My Trust Center before removing the test store.
