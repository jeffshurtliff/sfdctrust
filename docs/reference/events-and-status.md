# Status, event search, and event detail

Import `TrustCenterClient` from `sfdctrust`. Its synchronous resources share
the same authenticated connection pool.

```python
client.status.snapshot(*, locale: str | None = None) -> StatusSnapshot
client.events.search(
    *,
    scopes: Sequence[EventSearchScope],
    start_time: datetime,
    end_time: datetime,
    event_types: Sequence[EventType] | None = None,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
) -> EventSearchResponse
client.events.iter_search(
    *,
    scopes: Sequence[EventSearchScope],
    start_time: datetime,
    end_time: datetime,
    event_types: Sequence[EventType] | None = None,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
    max_pages: int = 1000,
) -> Iterator[EventSearchResult]
client.events.search_all(
    *,
    scopes: Sequence[EventSearchScope],
    start_time: datetime,
    end_time: datetime,
    event_types: Sequence[EventType] | None = None,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
    max_pages: int = 1000,
) -> list[EventSearchResult]
client.events.get(event_id: str, *, locale: str | None = None) -> EventDetail
```

`Iterator` and `Sequence` are from `collections.abc` and `datetime` is from `datetime`.
Import `StatusSnapshot` and `EventTypeBuckets` from `sfdctrust.models.status`.
Import the other types on this page from `sfdctrust.models.events`.

## Status snapshot

`StatusSnapshot.ongoing` and `StatusSnapshot.upcoming` are `EventTypeBuckets`.
Both have four required arrays of `EventSummary` objects, even when empty.
The Python attributes are `patch`, `incident`, `maintenance`, and
`informational_message` (wire alias `informationalMessage`). Response order
and repeated IDs are preserved, including patch entries with different
tenant scopes or lifecycle stages.

## Event search

Construct each scope with `EventSearchScope(id="opaque-tenant-id")`. Its
`type` defaults to `"tenant"`, the sole supported type. Pass 1 to 50 scopes
with nonempty, case-sensitive IDs. Salesforce removes duplicate tenants and
ignores tenants outside the PAT's authorization. The SDK sends scopes in
the order supplied, including duplicates.

The start is inclusive and the end is exclusive. Supply aware datetimes
with offsets representable as `±HH:MM`. The SDK compares instants and sends
full ISO 8601 timestamps with the supplied offsets. The optional
`event_types` must contain distinct values from `patch`, `incident`,
`maintenance`, and `informationalMessage`. Omit it to search all types.
An explicit `page_size` must be an integer from 1 through 200. Salesforce
defaults to 100. A supplied `page_token` is an opaque string of at most
4096 characters.

`EventSearchResponse.events` contains up to 200 `EventSearchResult` objects.
The page may be empty, including when zero requested tenants are authorized.
If `next_page_token` (alias `nextPageToken`) is present, pass it as
`page_token` with the same scopes, timestamps, filters, page size, and locale.
A stale or mismatched token surfaces as HTTP 400 `APIStatusError`. The caller
decides whether to restart. Entries can share an ID and differ in tenant
scope, status, start time, end time, or duration.

## Traverse search results

`iter_search()` copies the scope and event type sequences when created. It
fetches the first page when advanced and fetches subsequent pages as needed.
`search_all()` consumes the iterator and propagates any failure. Both preserve
server order, repeated event IDs, tenant scopes, and lifecycle values.

Search uses the same {ref}`cursor and page-limit rules as tenant traversal <tenant-traversal>`.
It puts the cursor in the search body and preserves the original arguments
and omissions. Import `PaginationError` from `sfdctrust`. An iterator may
have yielded items before an error surfaces.

## Event detail and shared fields

`EventSummary` and `EventSearchResult` include a required `scope` of type
`SubEventScope`. Its `tenants` maps opaque IDs to objects. Membership is
represented by key presence. `EventDetail` can include a `timeline` of
`TimelineItem` objects. Each entry has its own scope.

| Python event field | Wire name | Contract |
| --- | --- | --- |
| `event_id`, `event_type` | `eventId`, `eventType` | Required strings |
| `status`, `products`, `services` | Same | Required string and two string arrays |
| `created_at` | `createdAt` | Required aware datetime |
| `start_time`, `end_time` | `startTime`, `endTime` | Optional nullable aware datetimes |
| `title`, `description`, `duration` | Same | Optional nullable strings |
| `display_duration` | `displayDuration` | Optional nullable presentation text |
| `data` | Same | Optional non-null object selected by event type |

`duration` retains the ISO 8601 duration string. `display_duration`
contains localized text for display. The fields within a known `data`
object are required, including those that accept null.

| Event type | Data model | Python fields with wire aliases |
| --- | --- | --- |
| `patch` | `PatchEventData` | `release_id` (`releaseId`), `release_name` (`releaseName`), `release_version` (`releaseVersion`), `planned_start_time` (`plannedStartTime`), `planned_end_time` (`plannedEndTime`) |
| `incident` | `IncidentEventData` | `additional_information` (`additionalInformation`), `rca_link` (`rcaLink`), `rca_created_at` (`rcaCreatedAt`) |
| `maintenance` | `MaintenanceEventData` | `planned_start_time` (`plannedStartTime`), `planned_end_time` (`plannedEndTime`), `additional_information` (`additionalInformation`) |
| `informationalMessage` | `InformationalMessageEventData` | `informational_message_type` (`informationalMessageType`) |

Timeline entries have required `sub_event_id` (`subEventId`),
`sub_event_type` (`subEventType`), `scope`, and `created_at` (`createdAt`).
The optional `message` and `updated_at` (`updatedAt`) accept null.
Known subtypes select `PatchTimelineItem`, `IncidentTimelineItem`,
`MaintenanceTimelineItem`, or `InformationalMessageTimelineItem`.
Patch and maintenance entries can include nullable `planned_start_time`
and `planned_end_time`. Patch entries can also include nullable
`publication_date` (`publicationDate`) and a non-null `contents` array of
`PatchNote` objects. Each note has optional non-null `related_item`
(`relatedItem`) and `description` strings.

## Validation and forward compatibility

The models preserve extra fields and unknown response enum strings.
An unknown event type keeps its `data` as a dictionary. An unknown
timeline subtype keeps the common typed fields and preserves the rest as
extras. A malformed known variant raises `MalformedResponseError`.
A known timeline subtype on a different known parent event type also fails
validation. Wire timestamps must be full ISO 8601 strings with offsets.
The models parse them to aware datetimes and preserve their UTC offsets.

Omitted optional fields read as `None`. Check `model_fields_set` to tell
omission from explicit null on nullable fields. For example:

```python
if "end_time" in event.model_fields_set and event.end_time is None:
    print("Salesforce returned a null endTime")
wire_data = event.model_dump(mode="json", by_alias=True, exclude_unset=True)
```

Every method forwards a supplied string `locale` as a query parameter.
Salesforce handles BCP 47 fallback to `en-US`. Invalid local arguments
raise `ConfigurationError` before I/O. Detail IDs must fit safely in one
URL segment, and detail HTTP 404 raises `NotFoundError` for either missing
or unauthorized resources. Malformed responses raise a sanitized
`MalformedResponseError`. See the {doc}`exception reference <exceptions>`.

All results are tenant-scoped. Empty results establish no Salesforce-wide
health claim. See the {doc}`../getting-started/quickstart` for examples.
