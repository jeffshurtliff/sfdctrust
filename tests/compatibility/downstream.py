# -*- coding: utf-8 -*-
"""
:Module:            tests.compatibility.downstream
:Synopsis:          Strict typed consumer of the installed public package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     11 Nov 2026
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, assert_type
from uuid import UUID

import httpx

from sfdctrust import (
    APIStatusError,
    AsyncPATStore,
    AsyncTrustCenterClient,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    PaginationError,
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    PATRefreshResult,
    PATStore,
    PATStoreRecord,
    RateLimitError,
    RequestTimeoutError,
    SQLitePATStore,
    TrustCenterClient,
    TrustCenterError,
    __version__,
)
from sfdctrust.models.events import EventDetail, EventSearchResponse, EventSearchResult, EventSearchScope, EventType
from sfdctrust.models.status import StatusSnapshot
from sfdctrust.models.tenants import Tenant, TenantDetail, TenantListResponse


class CustomStore:
    """Signature fixture only; production adapters require durable atomic storage."""

    def load(self) -> PATStoreRecord | None:
        raise NotImplementedError

    def compare_and_swap(self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord) -> bool:
        raise NotImplementedError


class CustomAsyncStore:
    async def load(self) -> PATStoreRecord | None:
        raise NotImplementedError

    async def compare_and_swap(
        self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord
    ) -> bool:
        raise NotImplementedError


# Assignments verify structural conformance without inheriting either protocol.
sync_store: PATStore = CustomStore()
async_store: AsyncPATStore = CustomAsyncStore()
assert_type(__version__, str)
assert_type(APIStatusError(400).status_code, int)
assert_type(PATRefreshAmbiguousError(PATProbeResult.INCONCLUSIVE).probe, PATProbeResult)
errors: tuple[type[TrustCenterError], ...] = (
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    PaginationError,
    PATPersistenceError,
    PATRefreshPendingError,
    RateLimitError,
    RequestTimeoutError,
)
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 2, tzinfo=UTC)
SCOPES = [EventSearchScope(id='synthetic-tenant')]
TYPES: list[EventType] = ['incident']


def synchronous(http: httpx.Client) -> None:
    with TrustCenterClient('synthetic-pat', http_client=http, max_retries=0) as client:
        assert_type(client, TrustCenterClient)
        assert_type(client.tenants.list(page_size=1, page_token='', locale='en-US'), TenantListResponse)
        assert_type(client.tenants.get('tenant'), TenantDetail)
        assert_type(client.tenants.iter_all(max_pages=2), Iterator[Tenant])
        assert_type(client.tenants.list_all(), list[Tenant])
        assert_type(client.status.snapshot(), StatusSnapshot)
        assert_type(client.events.search(scopes=SCOPES, start_time=START, end_time=END, event_types=TYPES), EventSearchResponse)
        assert_type(client.events.get('event'), EventDetail)
        assert_type(client.events.iter_search(scopes=SCOPES, start_time=START, end_time=END), Iterator[EventSearchResult])
        assert_type(client.events.search_all(scopes=SCOPES, start_time=START, end_time=END), list[EventSearchResult])
        tenant = client.tenants.list().tenants[0]
        assert_type(tenant.my_domain, str | None)
        event = client.events.get('event')
        assert_type(event.created_at, datetime)
        assert_type(event.end_time, datetime | None)
        assert_type(event.model_dump(mode='json', by_alias=True, exclude_unset=True), dict[str, Any])
        client.close()
    assert_type(TrustCenterClient.from_env(pat='synthetic-pat'), TrustCenterClient)
    with TrustCenterClient.from_store(sync_store) as stored:
        result = stored.refresh_pat(expires_in_days=7)
        assert_type(result, PATRefreshResult)
        assert_type(result.metadata_valid, bool)
        assert_type(stored.retry_pat_persistence(), PATRefreshResult)
    builtin: PATStore = SQLitePATStore.initialize(pat='synthetic-pat', path='unused-fixture.sqlite3')
    record = builtin.load()
    if record is not None:
        assert_type(record.revision, UUID)
        assert_type(record.pending_attempt, UUID | None)
        assert_type(record.get_pat(), str)


async def asynchronous(http: httpx.AsyncClient) -> None:
    async with AsyncTrustCenterClient('synthetic-pat', http_client=http, max_retries=0) as client:
        assert_type(client, AsyncTrustCenterClient)
        assert_type(await client.tenants.list(), TenantListResponse)
        assert_type(await client.tenants.get('tenant'), TenantDetail)
        assert_type(client.tenants.iter_all(max_pages=2), AsyncIterator[Tenant])
        async for tenant in client.tenants.iter_all():
            assert_type(tenant, Tenant)
        assert_type(await client.tenants.list_all(), list[Tenant])
        assert_type(await client.status.snapshot(), StatusSnapshot)
        assert_type(await client.events.search(scopes=SCOPES, start_time=START, end_time=END), EventSearchResponse)
        assert_type(await client.events.get('event'), EventDetail)
        assert_type(client.events.iter_search(scopes=SCOPES, start_time=START, end_time=END), AsyncIterator[EventSearchResult])
        async for event in client.events.iter_search(scopes=SCOPES, start_time=START, end_time=END):
            assert_type(event, EventSearchResult)
        assert_type(await client.events.search_all(scopes=SCOPES, start_time=START, end_time=END), list[EventSearchResult])
        await client.aclose()
    assert_type(AsyncTrustCenterClient.from_env(pat='synthetic-pat'), AsyncTrustCenterClient)
    async with await AsyncTrustCenterClient.from_store(async_store) as stored:
        assert_type(await stored.refresh_pat(), PATRefreshResult)
        assert_type(await stored.retry_pat_persistence(), PATRefreshResult)
