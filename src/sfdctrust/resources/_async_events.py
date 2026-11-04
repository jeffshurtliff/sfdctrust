# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources._async_events
:Synopsis:          Asynchronous event search and detail
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from .._async_transport import _AsyncTransport
from ..models.events import EventDetail, EventSearchResponse, EventSearchResult, EventSearchScope, EventType
from ._requests import _iterate_pages_async
from .events import _event_detail_request, _event_search_request


class AsyncEventsResource:
    """Search and retrieve events visible to the client's PAT."""

    def __init__(self, transport: _AsyncTransport) -> None:
        self._transport = transport

    async def search(
        self,
        *,
        scopes: Sequence[EventSearchScope],
        start_time: datetime,
        end_time: datetime,
        event_types: Sequence[EventType] | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
    ) -> EventSearchResponse:
        """Search one page of events across the supplied tenant scopes.

        :param scopes: One through 50 tenant scopes. Salesforce removes duplicates.
        :param start_time: Inclusive start as an aware datetime.
        :param end_time: Exclusive end as an aware datetime later than the start.
        :param event_types: Optional nonempty sequence of distinct event types.
        :param page_size: Optional maximum results per page, from 1 through 200.
        :param page_token: Opaque cursor. Keep all other arguments the same.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: One typed page, which may contain zero results.
        :raises ConfigurationError: If a supplied argument is invalid.
        :raises APIStatusError: If Salesforce rejects the request or cursor.
        """
        return await _event_search_request(
            scopes=scopes,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            page_size=page_size,
            page_token=page_token,
            locale=locale,
        ).send_async(self._transport)

    def iter_search(
        self,
        *,
        scopes: Sequence[EventSearchScope],
        start_time: datetime,
        end_time: datetime,
        event_types: Sequence[EventType] | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
        max_pages: int = 1000,
    ) -> AsyncIterator[EventSearchResult]:
        """Yield search results in server order, fetching pages on demand.

        Search arguments match :meth:`search`. The scope and event type
        sequences are copied when the iterator is created.

        :param scopes: One through 50 tenant scopes. Salesforce removes duplicates.
        :param start_time: Inclusive start as an aware datetime.
        :param end_time: Exclusive end as an aware datetime later than the start.
        :param event_types: Optional nonempty sequence of distinct event types.
        :param page_size: Optional maximum results per page, from 1 through 200.
        :param page_token: Optional opaque cursor from which to start the traversal.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :param max_pages: Positive maximum number of fetched pages.
        :raises PaginationError: If a cursor repeats or a further page exceeds the limit.
                                 Earlier items may already have been yielded.
        """
        # Keep invalid sequence types intact for the shared search validation.
        if isinstance(scopes, Sequence) and not isinstance(scopes, str):
            scopes = tuple(scopes)
        if isinstance(event_types, Sequence) and not isinstance(event_types, str):
            event_types = tuple(event_types)

        async def fetch(token: str | None) -> tuple[list[EventSearchResult], str | None]:
            page = await self.search(
                scopes=scopes,
                start_time=start_time,
                end_time=end_time,
                event_types=event_types,
                page_size=page_size,
                page_token=token,
                locale=locale,
            )
            return page.events, page.next_page_token

        return _iterate_pages_async(fetch, page_token, max_pages)

    async def search_all(
        self,
        *,
        scopes: Sequence[EventSearchScope],
        start_time: datetime,
        end_time: datetime,
        event_types: Sequence[EventType] | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
        max_pages: int = 1000,
    ) -> list[EventSearchResult]:
        """Collect :meth:`iter_search` results, propagating any traversal error.

        :param scopes: One through 50 tenant scopes. Salesforce removes duplicates.
        :param start_time: Inclusive start as an aware datetime.
        :param end_time: Exclusive end as an aware datetime later than the start.
        :param event_types: Optional nonempty sequence of distinct event types.
        :param page_size: Optional maximum results per page, from 1 through 200.
        :param page_token: Optional opaque cursor from which to start the traversal.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :param max_pages: Positive maximum number of fetched pages.
        """
        return [
            event
            async for event in self.iter_search(
                scopes=scopes,
                start_time=start_time,
                end_time=end_time,
                event_types=event_types,
                page_size=page_size,
                page_token=page_token,
                locale=locale,
                max_pages=max_pages,
            )
        ]

    async def get(self, event_id: str, *, locale: str | None = None) -> EventDetail:
        """Retrieve an event and its embedded timeline, when available.

        :param event_id: Opaque event identifier.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: The event detail and its optional timeline.
        :raises NotFoundError: If the event is nonexistent or unauthorized.
        """
        return await _event_detail_request(event_id, locale=locale).send_async(self._transport)
