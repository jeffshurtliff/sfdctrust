# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources._requests
:Synopsis:          Shared resource request validation and pagination
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from .._async_transport import _AsyncTransport
from .._exceptions import ConfigurationError, MalformedResponseError, PaginationError
from .._transport import _Transport


def _locale_params(locale: str | None) -> dict[str, str]:
    if locale is None:
        return {}
    if not isinstance(locale, str):
        raise ConfigurationError('locale must be a string.')
    return {'locale': locale}


def _page_params(page_size: int | None, page_token: str | None) -> dict[str, str | int]:
    params: dict[str, str | int] = {}
    if page_size is not None:
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 200:
            raise ConfigurationError('page_size must be an integer from 1 through 200.')
        params['pageSize'] = page_size
    if page_token is not None:
        if not isinstance(page_token, str) or len(page_token) > 4096:
            raise ConfigurationError('page_token must be a string of at most 4096 characters.')
        params['pageToken'] = page_token
    return params


def _id_segment(identifier: str) -> str:
    if not isinstance(identifier, str) or not identifier:
        raise ConfigurationError('A nonempty string ID is required.')
    try:
        # The transport also checks the decoded segment for ambiguous syntax.
        return quote(identifier, safe='')
    except UnicodeEncodeError:
        pass
    raise ConfigurationError('The resource ID could not be encoded in a request URL.')


@dataclass(frozen=True, slots=True)
class _ModelRequest[Model: BaseModel]:
    method: str
    path: str
    model: type[Model]
    params: Mapping[str, str | int]
    response_error: str
    encoding_error: str = 'Request arguments could not be encoded.'
    json_body: dict[str, object] | None = None

    def send(self, transport: _Transport) -> Model:
        try:
            payload = transport.request(self.method, self.path, params=self.params, json_body=self.json_body)
        except (UnicodeEncodeError, httpx.InvalidURL):
            pass
        else:
            return self._validate(payload)
        raise ConfigurationError(self.encoding_error)

    async def send_async(self, transport: _AsyncTransport) -> Model:
        try:
            payload = await transport.request(self.method, self.path, params=self.params, json_body=self.json_body)
        except (UnicodeEncodeError, httpx.InvalidURL):
            pass
        else:
            return self._validate(payload)
        raise ConfigurationError(self.encoding_error)

    def _validate(self, payload: object) -> Model:
        try:
            return self.model.model_validate(payload)
        except ValidationError:
            pass
        raise MalformedResponseError(self.response_error)


def _validate_max_pages(max_pages: int) -> None:
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ConfigurationError('max_pages must be a positive integer.')


def _check_cursor(next_token: str, seen: set[str]) -> None:
    if next_token in seen:
        raise PaginationError('My Trust Center pagination repeated a cursor.')


def _iterate_pages[Item](
    fetch: Callable[[str | None], tuple[list[Item], str | None]], page_token: str | None, max_pages: int
) -> Iterator[Item]:
    _validate_max_pages(max_pages)
    seen: set[str] = set()
    for _ in range(max_pages):
        items, next_token = fetch(page_token)
        if page_token is not None:
            seen.add(page_token)
        yield from items
        if next_token is None:
            return
        _check_cursor(next_token, seen)
        page_token = next_token
    raise PaginationError('My Trust Center pagination exceeded max_pages.')


async def _iterate_pages_async[Item](
    fetch: Callable[[str | None], Awaitable[tuple[list[Item], str | None]]], page_token: str | None, max_pages: int
) -> AsyncIterator[Item]:
    _validate_max_pages(max_pages)
    seen: set[str] = set()
    for _ in range(max_pages):
        items, next_token = await fetch(page_token)
        if page_token is not None:
            seen.add(page_token)
        for item in items:
            yield item
        if next_token is None:
            return
        _check_cursor(next_token, seen)
        page_token = next_token
    raise PaginationError('My Trust Center pagination exceeded max_pages.')
