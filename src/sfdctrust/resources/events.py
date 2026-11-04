# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.events
:Synopsis:          Synchronous event search and detail
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import get_args

from .._exceptions import ConfigurationError
from .._transport import _Transport
from ..models._wire import _parse_timestamp
from ..models.events import EventDetail, EventSearchResponse, EventSearchResult, EventSearchScope, EventType
from ._requests import _id_segment, _iterate_pages, _locale_params, _ModelRequest, _page_params

_EVENT_TYPES = frozenset(get_args(EventType))


def _search_window(start_time: datetime, end_time: datetime) -> tuple[str, str]:
    if isinstance(start_time, datetime) and isinstance(end_time, datetime):
        try:
            start, end = start_time.isoformat(), end_time.isoformat()
            # Comparing fixed-offset values also handles folds in a shared zone.
            if _parse_timestamp(start) < _parse_timestamp(end):
                return start, end
        except (ValueError, TypeError, OverflowError):
            pass
    raise ConfigurationError(
        'Search requires aware start_time and end_time with minute-aligned offsets and start_time before end_time.'
    )


def _event_search_request(
    *,
    scopes: Sequence[EventSearchScope],
    start_time: datetime,
    end_time: datetime,
    event_types: Sequence[EventType] | None = None,
    page_size: int | None = None,
    page_token: str | None = None,
    locale: str | None = None,
) -> _ModelRequest[EventSearchResponse]:
    if not isinstance(scopes, Sequence) or not 1 <= len(scopes) <= 50:
        raise ConfigurationError('scopes must contain one through 50 tenant scopes.')
    scope_body = []
    for scope in scopes:
        if not isinstance(scope, EventSearchScope) or scope.type != 'tenant' or not isinstance(scope.id, str) or not scope.id:
            raise ConfigurationError('Each scope must be an EventSearchScope with type tenant and a nonempty string ID.')
        scope_body.append({'type': 'tenant', 'id': scope.id})

    start, end = _search_window(start_time, end_time)
    body: dict[str, object] = {
        'scopes': scope_body,
        'startTime': start,
        'endTime': end,
        **_page_params(page_size, page_token),
    }
    if event_types is not None:
        if not isinstance(event_types, Sequence) or isinstance(event_types, str):
            raise ConfigurationError('event_types must be a nonempty sequence of distinct supported event types.')
        filters = list(event_types)
        if (
            not filters
            or any(not isinstance(value, str) or value not in _EVENT_TYPES for value in filters)
            or len(set(filters)) != len(filters)
        ):
            raise ConfigurationError('event_types must be a nonempty sequence of distinct supported event types.')
        body['eventTypes'] = filters

    return _ModelRequest(
        'POST',
        '/events/search',
        EventSearchResponse,
        params=_locale_params(locale),
        json_body=body,
        response_error='My Trust Center returned an invalid event search page.',
    )


def _event_detail_request(event_id: str, *, locale: str | None = None) -> _ModelRequest[EventDetail]:
    return _ModelRequest(
        'GET',
        f'/events/{_id_segment(event_id)}',
        EventDetail,
        params=_locale_params(locale),
        response_error='My Trust Center returned invalid event detail.',
    )


class EventsResource:
    """Search and retrieve events visible to the client's PAT."""

    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def search(
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
        return _event_search_request(
            scopes=scopes,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            page_size=page_size,
            page_token=page_token,
            locale=locale,
        ).send(self._transport)

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
    ) -> Iterator[EventSearchResult]:
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

        def fetch(token: str | None) -> tuple[list[EventSearchResult], str | None]:
            page = self.search(
                scopes=scopes,
                start_time=start_time,
                end_time=end_time,
                event_types=event_types,
                page_size=page_size,
                page_token=token,
                locale=locale,
            )
            return page.events, page.next_page_token

        return _iterate_pages(fetch, page_token, max_pages)

    def search_all(
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
        return list(
            self.iter_search(
                scopes=scopes,
                start_time=start_time,
                end_time=end_time,
                event_types=event_types,
                page_size=page_size,
                page_token=page_token,
                locale=locale,
                max_pages=max_pages,
            )
        )

    def get(self, event_id: str, *, locale: str | None = None) -> EventDetail:
        """Retrieve an event and its embedded timeline, when available.

        :param event_id: Opaque event identifier.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: The event detail and its optional timeline.
        :raises NotFoundError: If the event is nonexistent or unauthorized.
        """
        return _event_detail_request(event_id, locale=locale).send(self._transport)
