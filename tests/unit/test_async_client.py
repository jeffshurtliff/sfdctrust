# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_async_client
:Synopsis:          Offline async read parity, ownership, and cancellation tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sfdctrust import (
    APIStatusError,
    AsyncTrustCenterClient,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    PaginationError,
    RequestTimeoutError,
    TrustCenterClient,
    TrustCenterError,
)
from sfdctrust.models.events import EventSearchScope

pytestmark = pytest.mark.asyncio
PAT = 'synthetic-async-read-pat'
BASE = 'https://api.salesforce.com/platform/mytrust/v1'
TENANT = {'id': 'synthetic tenant:雪', 'name': 'Synthetic tenant', 'cloud': 'Core'}
EVENT = {
    'eventId': 'synthetic event:雪',
    'eventType': 'patch',
    'status': 'active',
    'products': [],
    'services': [],
    'createdAt': '2026-11-01T09:00:00+05:30',
}
SUMMARY = {**EVENT, 'scope': {'tenants': {TENANT['id']: {}}}}
OTHER_SUMMARY = {**EVENT, 'status': 'confirmed', 'scope': {'tenants': {'another': {}}}}
BUCKETS = {'incident': [], 'maintenance': [], 'informationalMessage': [], 'patch': [SUMMARY, OTHER_SUMMARY]}
START = datetime(2026, 11, 1, tzinfo=UTC)
END = START + timedelta(days=1)
CURSOR = 'opaque /?+雪'


def search_args() -> dict:
    return {'scopes': [EventSearchScope(id=TENANT['id'])], 'start_time': START, 'end_time': END}


@pytest.mark.parametrize(
    ('resource', 'operation', 'args', 'kwargs', 'method', 'path', 'payload'),
    [
        ('tenants', 'list', (), {'page_token': ''}, 'GET', '/tenants', {'tenants': [TENANT], 'nextPageToken': CURSOR}),
        ('tenants', 'get', (TENANT['id'],), {}, 'GET', f'/tenants/{TENANT["id"]}', {**TENANT, 'events': [SUMMARY]}),
        ('status', 'snapshot', (), {}, 'GET', '/status', {'ongoing': BUCKETS, 'upcoming': BUCKETS}),
        ('events', 'search', (), search_args(), 'POST', '/events/search', {'events': [SUMMARY, OTHER_SUMMARY]}),
        (
            'events',
            'get',
            (EVENT['eventId'],),
            {},
            'GET',
            f'/events/{EVENT["eventId"]}',
            {
                **EVENT,
                'timeline': [
                    {
                        'subEventId': 'synthetic-entry',
                        'subEventType': 'patch_release_started',
                        'createdAt': EVENT['createdAt'],
                        'scope': SUMMARY['scope'],
                    }
                ],
            },
        ),
    ],
)
async def test_reads_match_sync_wire_and_models(resource, operation, args, kwargs, method, path, payload) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as sync_http:
        sync = TrustCenterClient(PAT, http_client=sync_http)
        expected = getattr(getattr(sync, resource), operation)(*args, **kwargs, locale='fr-CA')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as async_http:
        async with AsyncTrustCenterClient(PAT, http_client=async_http) as client:
            call = getattr(getattr(client, resource), operation)(*args, **kwargs, locale='fr-CA')
            assert len(requests) == 1
            actual = await call

    assert type(actual) is type(expected)
    assert actual.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload
    sync_request, async_request = requests
    assert (async_request.method, async_request.url.path) == (method, f'/platform/mytrust/v1{path}')
    assert str(async_request.url).startswith(f'{BASE}/')
    assert async_request.url == sync_request.url
    assert dict(async_request.headers) == dict(sync_request.headers)
    assert async_request.headers['Authorization'] == f'Bearer {PAT}'
    assert async_request.url.params['locale'] == 'fr-CA'
    assert async_request.content == sync_request.content
    assert async_request.extensions['timeout'] == {'connect': 5.0, 'read': 30.0, 'write': 30.0, 'pool': 5.0}


@pytest.mark.parametrize('mode', ['explicit', 'env', 'override'])
async def test_construction_precedence_static_refresh_and_injected_ownership(monkeypatch, mode) -> None:
    env_pat = PAT if mode == 'env' else 'synthetic-unused-environment-pat'
    monkeypatch.setenv('SFDCTRUST_PAT', env_pat)
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(401, content=PAT.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        if mode == 'explicit':
            client = AsyncTrustCenterClient(PAT, http_client=http)
        elif mode == 'env':
            client = AsyncTrustCenterClient.from_env(http_client=http)
        else:
            client = AsyncTrustCenterClient.from_env(pat=PAT, http_client=http)
        assert not attempts
        with pytest.raises(ConfigurationError):
            AsyncTrustCenterClient.from_env(pat=None, http_client=http)
        async with client:
            with pytest.raises(ConfigurationError):
                await client.refresh_pat()
            with pytest.raises(ConfigurationError):
                await client.retry_pat_persistence()
            assert not attempts
            with pytest.raises(AuthenticationError) as exc:
                await client.tenants.list()
        await client.aclose()
        assert not http.is_closed

    assert len(attempts) == 1
    assert attempts[0].headers['Authorization'] == f'Bearer {PAT}'
    assert PAT not in str(exc.value)


async def test_sdk_owned_client_has_safe_defaults_and_closes(monkeypatch) -> None:
    real_client = httpx.AsyncClient
    created = []

    def create(**kwargs):
        assert kwargs['trust_env'] is False
        assert kwargs['limits'] == httpx.Limits(max_connections=20, max_keepalive_connections=10)
        http = real_client(**kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'tenants': []})))
        created.append(http)
        return http

    monkeypatch.setattr('sfdctrust._async_transport.httpx.AsyncClient', create)
    client = AsyncTrustCenterClient(PAT)
    assert len(created) == 1 and not created[0].is_closed
    async with client as entered:
        assert entered is client
        assert await client.tenants.list_all() == []
    assert created[0].is_closed
    await client.aclose()


@pytest.mark.parametrize('value', [True, -1, 6, 1.0, '2', None])
async def test_invalid_retry_limits(value) -> None:
    with pytest.raises(ConfigurationError, match='max_retries'):
        AsyncTrustCenterClient(PAT, max_retries=value)


@pytest.mark.parametrize('resource', ['tenants', 'events'])
@pytest.mark.parametrize('collect', [False, True])
async def test_pagination_is_lazy_and_preserves_opaque_cursors_and_duplicates(resource, collect) -> None:
    items = [TENANT, TENANT] if resource == 'tenants' else [SUMMARY, OTHER_SUMMARY]
    requests = []
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = len(requests)
        if resource == 'tenants':
            params = dict(request.url.params)
            assert request.content == b''
            assert params.pop('pageSize') == '2'
            assert params.pop('locale') == 'fr'
            cursor = params.get('pageToken')
        else:
            assert dict(request.url.params) == {'locale': 'fr'}
            body = json.loads(request.content)
            cursor = body.pop('pageToken', None)
            bodies.append(body)
        assert cursor == [None, '', CURSOR][page - 1]
        payload = {resource: [] if page == 2 else items}
        if page < 3:
            payload['nextPageToken'] = ['', CURSOR][page - 1]
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http)
        kwargs = {'page_size': 2, 'locale': 'fr'}
        if resource == 'tenants':
            call = client.tenants.list_all(**kwargs) if collect else client.tenants.iter_all(**kwargs)
        else:
            args = search_args()
            filters = ['patch']
            kwargs.update(args, event_types=filters)
            call = client.events.search_all(**kwargs) if collect else client.events.iter_search(**kwargs)
            if not collect:
                args['scopes'].clear()
                filters.clear()
        assert not requests
        result = await call if collect else [item async for item in call]

    assert len(requests) == 3
    assert [item.model_dump(mode='json', by_alias=True, exclude_unset=True) for item in result] == items * 2
    if bodies:
        expected = {
            'scopes': [{'type': 'tenant', 'id': TENANT['id']}],
            'eventTypes': ['patch'],
            'pageSize': 2,
            'startTime': START.isoformat(),
            'endTime': END.isoformat(),
        }
        assert bodies == [expected] * 3


@pytest.mark.parametrize('resource', ['tenants', 'events'])
@pytest.mark.parametrize(
    ('start', 'tokens', 'limit', 'error', 'match', 'expected_calls'),
    [
        ('', [''], 2, PaginationError, 'repeated', 1),
        (None, ['next', 'next'], 2, PaginationError, 'repeated', 2),
        (None, ['next'], 1, PaginationError, 'max_pages', 1),
        (None, ['next', 400], 3, APIStatusError, '400', 2),
        (None, [], False, ConfigurationError, 'max_pages', 0),
        ([], [], 2, ConfigurationError, 'page_token', 0),
    ],
)
async def test_pagination_failure_parity(resource, start, tokens, limit, error, match, expected_calls) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        token = tokens[calls]
        calls += 1
        if token == 400:
            return httpx.Response(400, content=PAT.encode())
        return httpx.Response(200, json={resource: [], 'nextPageToken': token})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http)
        kwargs = {'page_token': start, 'max_pages': limit}
        with pytest.raises(error, match=match):
            if resource == 'tenants':
                await client.tenants.list_all(**kwargs)
            else:
                await client.events.search_all(**search_args(), **kwargs)
    assert calls == expected_calls


async def test_iterator_stops_without_prefetching() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': CURSOR})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http)
        async for tenant in client.tenants.iter_all():
            assert tenant.id == TENANT['id']
            break
    assert len(requests) == 1


async def test_retry_waits_match_sync_for_read_post(monkeypatch) -> None:
    sync_delays = []
    async_delays = []
    monkeypatch.setattr('sfdctrust._transport.time.sleep', sync_delays.append)
    monkeypatch.setattr('sfdctrust._transport.time.time', lambda: START.timestamp())
    monkeypatch.setattr('sfdctrust._transport.random.uniform', lambda *_: 0.125)

    async def sleep(delay):
        async_delays.append(delay)

    monkeypatch.setattr('sfdctrust._async_transport.asyncio.sleep', sleep)

    def run_sequence():
        responses = iter(
            [
                httpx.Response(429, headers={'Retry-After': '99999'}),
                httpx.Response(503, headers={'Retry-After': 'Sun, 01 Nov 2026 00:00:09 GMT'}),
                httpx.Response(502, headers={'Retry-After': '0'}),
                httpx.Response(429, headers={'Retry-After': 'invalid'}),
                httpx.Response(200, json={'events': []}),
            ]
        )
        bodies = []

        def handler(request):
            assert request.method == 'POST'
            bodies.append(request.content)
            return next(responses)

        return handler, bodies

    sync_handler, sync_bodies = run_sequence()
    async_handler, async_bodies = run_sequence()
    with httpx.Client(transport=httpx.MockTransport(sync_handler)) as http:
        sync = TrustCenterClient(PAT, http_client=http, max_retries=4)
        assert sync.events.search(**search_args(), page_token=CURSOR).events == []
    async with httpx.AsyncClient(transport=httpx.MockTransport(async_handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http, max_retries=4)
        assert (await client.events.search(**search_args(), page_token=CURSOR)).events == []
    assert async_delays == sync_delays == [30, 9, 2.125, 4.125]
    assert async_bodies == sync_bodies == [sync_bodies[0]] * 5


@pytest.mark.parametrize(
    ('failure', 'error', 'retries'),
    [
        (httpx.ConnectError, NetworkError, 2),
        (httpx.ReadTimeout, RequestTimeoutError, 2),
        (httpx.ReadError, NetworkError, 0),
        (httpx.DecodingError, MalformedResponseError, 0),
        (None, NetworkError, 0),
    ],
)
async def test_network_failure_retry_limits_and_safe_errors(monkeypatch, failure, error, retries) -> None:
    requests = []
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr('sfdctrust._async_transport.asyncio.sleep', sleep)

    def handler(request):
        requests.append(request)
        raise (failure or httpx.ConnectError)(f'{BASE} {PAT}', request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http, max_retries=0 if failure is None else 2)
        with pytest.raises(error) as exc:
            await client.tenants.list(page_token=CURSOR)
    assert len(requests) == retries + 1
    assert len(delays) == retries
    assert exc.value.__context__ is exc.value.__cause__ is None
    assert PAT not in ''.join(traceback.format_exception(exc.value))


@pytest.mark.parametrize(
    ('status', 'content', 'error'),
    [
        (302, b'ignored', TrustCenterError),
        (200, b'{"tenants": [NaN]}', MalformedResponseError),
        (200, b'\xff', MalformedResponseError),
        (200, b'{"tenants": ["synthetic-async-read-pat"]}', MalformedResponseError),
    ],
)
async def test_redirects_and_malformed_responses_fail_closed(status, content, error) -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, content=content, headers={'Location': 'https://example.invalid/'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http)
        with pytest.raises(error) as exc:
            await client.tenants.list()
    assert len(requests) == 1
    assert exc.value.__context__ is exc.value.__cause__ is None
    assert PAT not in ''.join(traceback.format_exception(exc.value))


@pytest.mark.parametrize('boundary', ['request', 'body', 'backoff', 'next_page'])
async def test_cancellation_stops_reads_and_closes_streams(monkeypatch, boundary) -> None:
    blocked = asyncio.Event()
    closed = asyncio.Event()
    requests = []

    async def pause():
        blocked.set()
        await asyncio.Future()

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            assert boundary == 'body'
            await pause()
            yield b''

        async def aclose(self):
            closed.set()
            if boundary == 'body':
                raise httpx.ReadError('synthetic close error after cancellation')

    async def handler(request):
        requests.append(request)
        if boundary == 'next_page' and len(requests) == 1:
            return httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': CURSOR})
        if boundary in {'request', 'next_page'}:
            await pause()
        return httpx.Response(503 if boundary == 'backoff' else 200, stream=Body())

    async def sleep(_):
        assert closed.is_set()
        await pause()

    monkeypatch.setattr('sfdctrust._async_transport.asyncio.sleep', sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncTrustCenterClient(PAT, http_client=http)
        task = asyncio.create_task(client.tenants.list_all())
        await asyncio.wait_for(blocked.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(requests) == (2 if boundary == 'next_page' else 1)
    if boundary in {'body', 'backoff'}:
        assert closed.is_set()
