# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._transport
:Synopsis:          Internal synchronous HTTP transport for My Trust Center
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
_REFRESH_URL = _BASE.copy_with(path=f'{_BASE.path}/pats/refresh')
_MAX_JITTER = 0.25
_MAX_RETRY_AFTER = 30
# HTTP-date allows IMF-fixdate and the two obsolete HTTP date formats.
_DAY = r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)'
_LONG_DAY = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
_CLOCK = r'[0-9]{2}:[0-9]{2}:[0-9]{2}'
_HTTP_DATE = re.compile(
    rf'{_DAY}, [0-9]{{2}} [A-Z][a-z]{{2}} [0-9]{{4}} {_CLOCK} GMT'
    rf'|{_LONG_DAY}, [0-9]{{2}}-[A-Z][a-z]{{2}}-(?P<short_year>[0-9]{{2}}) {_CLOCK} GMT'
    rf'|{_DAY} [A-Z][a-z]{{2}} (?: [0-9]|[0-9]{{2}}) {_CLOCK} [0-9]{{4}}'
)
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
        raise ConfigurationError('PAT refresh requires the dedicated transport path.')

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


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip(' \t')
    if value.isascii() and value.isdecimal():
        digits = value.lstrip('0')
        # Avoid converting an unbounded integer from an untrusted header.
        return _MAX_RETRY_AFTER if len(digits) > 2 else min(_MAX_RETRY_AFTER, int(digits or '0'))
    match = _HTTP_DATE.fullmatch(value)
    if match is None:
        return None
    try:
        now = time.time()
        if match['short_year'] is not None:
            # RFC 9110 interprets a two-digit year relative to the current date.
            current = datetime.fromtimestamp(now, UTC)
            upper_year = current.year + 50
            year = upper_year - (upper_year - int(match['short_year'])) % 100
            start, end = match.span('short_year')
            date = parsedate_to_datetime(f'{value[:start]}{year:04d}{value[end:]}')
            if year == upper_year and date.timetuple()[1:6] > current.timetuple()[1:6]:
                date = date.replace(year=year - 100)
        else:
            date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=UTC)
        return min(_MAX_RETRY_AFTER, max(0.0, date.timestamp() - now))
    except (ValueError, OverflowError, OSError):
        return None


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError('Nonstandard JSON constant.')


def _refresh_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Invalidate duplicate fields without discarding an unambiguous secret."""
    fields: dict[str, object] = {}
    for key, value in pairs:
        fields[key] = None if key in fields else value
    return fields


class _Transport:
    """Send synchronous requests using one SDK-owned or trusted injected client.

    The timeout applies to each attempt, including on injected clients. The
    owned client verifies TLS, ignores environment proxies and CA overrides,
    and uses a pool of 20 connections with up to 10 kept idle. An injected
    client controls its own TLS, proxy, pool, hooks, and transport behavior.
    """

    def __init__(
        self,
        auth: PATAuth | Callable[[], PATAuth],
        *,
        client: httpx.Client | None = None,
        timeout: httpx.Timeout | None = None,
        max_retries: int = 2,
    ) -> None:
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or not 0 <= max_retries <= 5:
            raise ConfigurationError('max_retries must be an integer from 0 through 5.')
        self._max_retries = max_retries
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

    def _build_request(
        self,
        method: str,
        url: httpx.URL,
        *,
        params: httpx.QueryParams | Mapping[str, str | int | float | bool | None] | None = None,
        json_body: Any = None,
    ) -> httpx.Request:
        return httpx.Request(
            method,
            url,
            params=params,
            json=json_body,
            headers={'Accept': 'application/json', 'User-Agent': f'{PACKAGE_NAME}/{__version__}'},
            extensions={'timeout': self._timeout.as_dict()},
        )

    def _send(self, request: httpx.Request, auth: PATAuth) -> httpx.Response:
        return self._client.send(request, auth=auth, follow_redirects=False, stream=True)

    def refresh_once(self, auth: PATAuth, days: int | None) -> tuple[int | None, dict[str, object] | None]:
        """Use the fixed refresh destination exactly once, decoding only success."""
        body = None if days is None else {'expiresInDays': days}
        return self._send_pat_operation('POST', _REFRESH_URL, auth, json_body=body)

    def probe_once(self, auth: PATAuth) -> int | None:
        """Check the old PAT with one status-only tenants request."""
        status, _ = self._send_pat_operation('GET', _destination('/tenants'), auth)
        return status

    def _send_pat_operation(
        self, method: str, url: httpx.URL, auth: PATAuth, *, json_body: dict[str, int] | None = None
    ) -> tuple[int | None, dict[str, object] | None]:
        status = None
        try:
            response = self._send(self._build_request(method, url, json_body=json_body), auth)
        except Exception:
            # Hooks and custom transports can raise arbitrary exceptions containing secrets.
            return None, None
        try:
            status = response.status_code
            if method == 'POST' and response.is_success:
                payload = json.loads(
                    response.read().decode('utf-8'),
                    parse_constant=_reject_json_constant,
                    # Refresh fields are strings. Invalid numeric metadata must not lose the secret.
                    parse_int=lambda _: None,
                    parse_float=lambda _: None,
                    object_pairs_hook=_refresh_fields,
                )
                if isinstance(payload, dict):
                    return status, payload
        except Exception:
            return status, None
        finally:
            # A failed close cannot invalidate an already received replacement or status.
            with suppress(Exception):
                response.close()
        return status, None

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

        for attempt in range(self._max_retries + 1):
            retry_after = None
            request = self._build_request(method, url, params=params, json_body=json_body)
            auth = self._auth if isinstance(self._auth, PATAuth) else self._auth()
            try:
                response = self._send(request, auth)
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
                    if retryable and attempt < self._max_retries and status in {429, 503}:
                        retry_after = response.headers.get('Retry-After')
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

            if not retryable or not transient or attempt == self._max_retries:
                raise error
            delay = _retry_after(retry_after)
            if delay is None:
                jitter = random.uniform(0, _MAX_JITTER)  # nosec B311
                delay = 0.5 * 2**attempt + jitter
            time.sleep(delay)

        raise AssertionError('Unreachable retry state.')
