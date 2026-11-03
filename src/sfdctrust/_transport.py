# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._transport
:Synopsis:          Internal synchronous HTTP transport for My Trust Center
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     02 Nov 2026
"""

from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Mapping
from typing import Any, NoReturn, Self
from urllib.parse import unquote

import httpx

from ._auth import PATAuth
from ._constants import DEFAULT_BASE_URL, PACKAGE_NAME
from ._exceptions import (
    APIStatusError,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    TrustCenterError,
)
from ._version import __version__

_BASE = httpx.URL(DEFAULT_BASE_URL)
_RETRY_DELAYS = (0.5, 1.0)
_MAX_JITTER = 0.25  # Both delays and their maximum jitter sum to 2 seconds.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_STATUS_ERRORS = {401: AuthenticationError, 404: NotFoundError, 429: RateLimitError}


def _destination(path: str) -> httpx.URL:
    """Resolve a path under the API base, rejecting ambiguous path syntax."""
    relative = path.removeprefix('/')
    if not relative or '//' in path or ':' in relative.split('/', 1)[0]:
        raise ConfigurationError('An API-relative path is required.')

    segments = [unquote(segment) for segment in relative.split('/')]
    for segment in segments:
        if (
            segment in {'.', '..'}
            or any(char in '/\\%?#;' for char in segment)
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in segment)
        ):
            raise ConfigurationError('The API path contains an unsafe segment.')

    if '/'.join(segments).rstrip('/').lower() == 'pats/refresh':
        raise ConfigurationError('PAT refresh is outside the transport scope.')

    try:
        url = _BASE.copy_with(path=f'{_BASE.path}/{relative}')
    except (httpx.InvalidURL, ValueError):
        pass
    else:
        if (
            (url.scheme, url.host, url.port) == (_BASE.scheme, _BASE.host, _BASE.port)
            and url.path.startswith(f'{_BASE.path}/')
            and not (url.userinfo or url.query or url.fragment)
        ):
            return url
    raise ConfigurationError('The request destination must be under the My Trust Center API base.')


def _can_retry(method: str, path: str) -> bool:
    if method == 'POST':
        return path == '/events/search'
    if method != 'GET':
        return False
    if path in {'/tenants', '/status'}:
        return True
    collection, _, identifier = path[1:].partition('/')
    return collection in {'tenants', 'events'} and bool(identifier) and '/' not in identifier


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError('Nonstandard JSON constant.')


class _Transport:
    """Send synchronous requests using one SDK-owned or trusted injected client.

    The timeout applies to each attempt, including on injected clients. The
    owned client verifies TLS, ignores environment proxies and CA overrides,
    and uses a pool of 20 connections with up to 10 kept idle. An injected
    client controls its own TLS, proxy, pool, hooks, and transport behavior.
    """

    def __init__(self, auth: PATAuth, *, client: httpx.Client | None = None, timeout: httpx.Timeout | None = None) -> None:
        self._auth = auth
        self._timeout = httpx.Timeout(30.0, connect=5.0, pool=5.0) if timeout is None else httpx.Timeout(timeout)
        if any(value is None or not math.isfinite(value) or value <= 0 for value in self._timeout.as_dict().values()):
            raise ConfigurationError('HTTP timeouts must be finite and positive.')
        self._owns_client = client is None
        self._client = (
            httpx.Client(trust_env=False, limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))
            if client is None
            else client
        )

    def close(self) -> None:
        """Close the SDK-owned client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: httpx.QueryParams | Mapping[str, str | int | float | bool | None] | None = None,
        json_body: Any = None,
    ) -> Any:
        """Send an API-relative request and return its decoded JSON."""
        url = _destination(path)
        method = method.upper()
        retryable = _can_retry(method, url.path.removeprefix(_BASE.path))

        for attempt in range(len(_RETRY_DELAYS) + 1):
            request = httpx.Request(
                method,
                url,
                params=params,
                json=json_body,
                headers={'Accept': 'application/json', 'User-Agent': f'{PACKAGE_NAME}/{__version__}'},
                extensions={'timeout': self._timeout.as_dict()},
            )
            try:
                response = self._client.send(request, auth=self._auth, follow_redirects=False, stream=True)
                try:
                    status = response.status_code
                    if response.is_success:
                        return json.loads(response.read().decode('utf-8'), parse_constant=_reject_json_constant)
                    if status in _STATUS_ERRORS:
                        error: TrustCenterError = _STATUS_ERRORS[status]()
                    elif response.is_error:
                        error = APIStatusError(status)
                    else:
                        error = TrustCenterError('My Trust Center API returned an unexpected HTTP status.')
                    transient = status in _RETRY_STATUSES
                finally:
                    response.close()
            except httpx.TimeoutException:
                error = RequestTimeoutError('My Trust Center request timed out.')
                transient = True
            except (ValueError, RecursionError, httpx.DecodingError):
                error = MalformedResponseError('My Trust Center returned an invalid JSON response.')
                transient = False
            except httpx.RequestError as exc:
                error = NetworkError('My Trust Center request could not complete.')
                transient = isinstance(exc, httpx.ConnectError)

            if not retryable or not transient or attempt == len(_RETRY_DELAYS):
                raise error
            # Retry jitter does not require cryptographic randomness
            jitter = random.uniform(0, _MAX_JITTER)  # nosec B311
            time.sleep(_RETRY_DELAYS[attempt] + jitter)

        raise AssertionError('Unreachable retry state.')
