# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._async_transport
:Synopsis:          Native asynchronous HTTP transport for My Trust Center
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from typing import Any

import httpx

from ._auth import PATAuth
from ._transport import (
    _BASE,
    _READ_EXCEPTIONS,
    _REFRESH_URL,
    _build_request,
    _can_retry,
    _decode_json,
    _decode_refresh,
    _destination,
    _pool_limits,
    _QueryParams,
    _read_failure,
    _refresh_body,
    _request_timeout,
    _retry_delay,
    _status_failure,
    _validate_max_retries,
)

type _PATResponse = tuple[int | None, dict[str, object] | None]


@asynccontextmanager
async def _closing_response(response: httpx.Response) -> AsyncIterator[httpx.Response]:
    try:
        yield response
    except asyncio.CancelledError:
        with suppress(Exception):
            await response.aclose()
        raise
    except BaseException:
        await response.aclose()
        raise
    else:
        await response.aclose()


class _AsyncTransport:
    def __init__(
        self,
        auth: PATAuth | Callable[[], Awaitable[PATAuth]],
        *,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
    ) -> None:
        self._max_retries = _validate_max_retries(max_retries)
        self._auth = auth
        self._timeout = _request_timeout(None)
        self._owns_client = client is None
        self._client = httpx.AsyncClient(trust_env=False, limits=_pool_limits()) if client is None else client

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _send(self, request: httpx.Request, auth: PATAuth) -> httpx.Response:
        return await self._client.send(request, auth=auth, follow_redirects=False, stream=True)

    def refresh_once(self, auth: PATAuth, days: int | None) -> AbstractAsyncContextManager[_PATResponse]:
        """Expose the decoded response before awaiting any further cleanup."""
        return self._pat_operation('POST', _REFRESH_URL, auth, json_body=_refresh_body(days))

    async def probe_once(self, auth: PATAuth) -> int | None:
        async with self._pat_operation('GET', _destination('/tenants'), auth) as (status, _):
            return status

    @asynccontextmanager
    async def _pat_operation(
        self, method: str, url: httpx.URL, auth: PATAuth, *, json_body: dict[str, int] | None = None
    ) -> AsyncIterator[_PATResponse]:
        response = None
        status = None
        payload = None
        try:
            try:
                response = await self._send(_build_request(method, url, self._timeout, json_body=json_body), auth)
                status = response.status_code
                if method == 'POST' and response.is_success:
                    payload = _decode_refresh(await response.aread())
            except Exception:
                # Hooks and custom transports can raise errors containing credentials.
                payload = None
            yield status, payload
        finally:
            if response is not None:
                with suppress(Exception):
                    await response.aclose()

    async def request(self, method: str, path: str, *, params: _QueryParams | None = None, json_body: Any = None) -> Any:
        url = _destination(path)
        method = method.upper()
        retryable = _can_retry(method, url.path.removeprefix(_BASE.path))

        for attempt in range(self._max_retries + 1):
            request = _build_request(method, url, self._timeout, params=params, json_body=json_body)
            auth = self._auth if isinstance(self._auth, PATAuth) else await self._auth()
            try:
                async with _closing_response(await self._send(request, auth)) as response:
                    if response.is_success:
                        return _decode_json(await response.aread())
                    error, transient, retry_after = _status_failure(response)
            except _READ_EXCEPTIONS as exc:
                error, transient = _read_failure(exc)
                retry_after = None

            if not retryable or not transient or attempt == self._max_retries:
                raise error
            await asyncio.sleep(_retry_delay(attempt, retry_after))

        raise AssertionError('Unreachable retry state.')
