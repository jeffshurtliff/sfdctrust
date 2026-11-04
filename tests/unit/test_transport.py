# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_transport
:Synopsis:          Offline tests of the synchronous transport boundary
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

import json
import traceback
from collections.abc import Callable, Iterator

import httpx
import pytest

from sfdctrust import (
    APIStatusError,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    TrustCenterError,
    __version__,
)
from sfdctrust._auth import PATAuth
from sfdctrust._constants import DEFAULT_BASE_URL
from sfdctrust._transport import _Transport

_PAT = 'synthetic-transport-pat'
_SENSITIVE = f'{DEFAULT_BASE_URL}/tenants?token={_PAT}'


@pytest.fixture
def delays(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr('sfdctrust._transport.time.sleep', sleeps.append)
    monkeypatch.setattr('sfdctrust._transport.random.uniform', lambda low, high: high)
    return sleeps


@pytest.fixture
def mock_client() -> Iterator[Callable[..., httpx.Client]]:
    clients: list[httpx.Client] = []

    def create(handler: Callable[[httpx.Request], httpx.Response], **kwargs: object) -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    yield create
    for client in clients:
        client.close()


def _assert_safe(error: TrustCenterError) -> None:
    assert error.__cause__ is None
    assert error.__context__ is None
    displayed = ''.join(traceback.format_exception(error))
    for secret in (_PAT, DEFAULT_BASE_URL, 'private-server-message'):
        assert secret not in displayed


def test_authenticated_request_arguments_and_json(mock_client: Callable[..., httpx.Client]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == 'POST'
        assert str(request.url) == f'{DEFAULT_BASE_URL}/events/search?locale=ja-JP'
        assert request.headers['Authorization'] == f'Bearer {_PAT}'
        assert request.headers['Accept'] == 'application/json'
        assert request.headers['User-Agent'] == f'sfdctrust/{__version__}'
        assert json.loads(request.content) == {'scopes': [{'type': 'tenant', 'id': 'synthetic-tenant'}]}
        assert request.extensions['timeout'] == {'connect': 5.0, 'pool': 5.0, 'read': 30.0, 'write': 30.0}
        return httpx.Response(200, json={'events': []})

    client = mock_client(handler, base_url='https://example.invalid', auth=('user', 'unused'), timeout=None)
    with _Transport(PATAuth(_PAT), client=client) as transport:
        assert transport.request(
            'post',
            '/events/search',
            params={'locale': 'ja-JP'},
            json_body={'scopes': [{'type': 'tenant', 'id': 'synthetic-tenant'}]},
        ) == {'events': []}
    assert not client.is_closed


@pytest.mark.parametrize(
    'path',
    [
        '',
        '/',
        'https://example.invalid/tenants',
        f'{DEFAULT_BASE_URL}/tenants',
        '//example.invalid/tenants',
        '../tenants',
        '/tenants/../../status',
        '/tenants/%2e%2E/status',
        '/tenants/%252e%252e/status',
        '/tenants/%2f..%2fstatus',
        '/tenants/%5C..%5cstatus',
        '/tenants?token=synthetic',
        '/tenants#fragment',
        '/pats/refresh',
        '/pats/%72efresh/',
        '/pats//refresh',
    ],
)
def test_rejects_unsafe_paths_and_refresh_before_authentication(
    mock_client: Callable[..., httpx.Client], monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    def forbidden(*_: object) -> None:
        pytest.fail('Invalid path reached authentication or network')

    monkeypatch.setattr(PATAuth, 'auth_flow', forbidden)
    transport = _Transport(PATAuth(_PAT), client=mock_client(forbidden))
    with pytest.raises(ConfigurationError) as caught:
        transport.request('POST', path)
    _assert_safe(caught.value)


@pytest.mark.parametrize(
    ('status', 'error_type'),
    [(400, APIStatusError), (401, AuthenticationError), (404, NotFoundError), (418, APIStatusError), (429, RateLimitError)],
)
@pytest.mark.parametrize('json_error', [False, True])
def test_status_mapping_precedes_body_decoding(
    mock_client: Callable[..., httpx.Client], delays: list[float], status: int, error_type: type[APIStatusError], json_error: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['Authorization'] == f'Bearer {_PAT}'
        message = f'private-server-message {_SENSITIVE}'
        return httpx.Response(status, json={'message': message}) if json_error else httpx.Response(status, text=message)

    transport = _Transport(PATAuth(_PAT), client=mock_client(handler))
    with pytest.raises(error_type) as caught:
        transport.request('GET', 'tenants')
    assert type(caught.value) is error_type
    assert caught.value.status_code == status
    assert vars(caught.value) == {'status_code': status}
    _assert_safe(caught.value)
    assert delays == ([0.75, 1.25] if status == 429 else [])


@pytest.mark.parametrize('body', [b'', b' ', b'{broken', b'{}{}', b'NaN', b'[Infinity]', b'-Infinity', b'"\xff"'])
def test_malformed_success_fails_immediately(mock_client: Callable[..., httpx.Client], delays: list[float], body: bytes) -> None:
    transport = _Transport(PATAuth(_PAT), client=mock_client(lambda _: httpx.Response(200, content=body)))
    with pytest.raises(MalformedResponseError) as caught:
        transport.request('GET', '/status')
    _assert_safe(caught.value)
    assert delays == []


@pytest.mark.parametrize('body', [None, False, 0, 'text', [1, None]])
def test_valid_json_scalars_and_arrays_pass_through(mock_client: Callable[..., httpx.Client], body: object) -> None:
    transport = _Transport(PATAuth(_PAT), client=mock_client(lambda _: httpx.Response(200, content=json.dumps(body).encode())))
    assert transport.request('GET', '/status') == body


@pytest.mark.parametrize('location', ['https://example.invalid/other', f'{DEFAULT_BASE_URL}/status'])
def test_redirects_are_blocked_even_with_injected_client(
    mock_client: Callable[..., httpx.Client], delays: list[float], location: str
) -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(302, headers={'Location': location})

    transport = _Transport(PATAuth(_PAT), client=mock_client(handler, follow_redirects=True))
    with pytest.raises(TrustCenterError, match='unexpected HTTP status') as caught:
        transport.request('GET', '/tenants')
    _assert_safe(caught.value)
    assert paths == ['/platform/mytrust/v1/tenants']
    assert delays == []


@pytest.mark.parametrize('status', [101, 304, 600])
def test_other_unexpected_statuses(mock_client: Callable[..., httpx.Client], status: int) -> None:
    transport = _Transport(PATAuth(_PAT), client=mock_client(lambda _: httpx.Response(status)))
    with pytest.raises(TrustCenterError, match='unexpected HTTP status'):
        transport.request('GET', '/status')


def test_custom_timeout_overrides_injected_client_default(mock_client: Callable[..., httpx.Client]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions['timeout'] == {'connect': 1, 'read': 2, 'write': 3, 'pool': 4}
        return httpx.Response(200, json={})

    timeout = httpx.Timeout(connect=1, read=2, write=3, pool=4)
    client = mock_client(handler, timeout=99)
    assert _Transport(PATAuth(_PAT), client=client, timeout=timeout).request('GET', '/status') == {}


@pytest.mark.parametrize('timeout', [None, float('inf'), float('nan'), 0, -1])
def test_rejects_unbounded_or_invalid_timeout(timeout: float | None) -> None:
    with pytest.raises(ConfigurationError, match='finite and positive'):
        _Transport(PATAuth(_PAT), timeout=httpx.Timeout(timeout))


@pytest.mark.parametrize(
    ('method', 'path', 'retries'),
    [
        ('GET', '/tenants', True),
        ('GET', '/tenants/synthetic%20tenant', True),
        ('GET', '/status', True),
        ('GET', '/events/synthetic-event', True),
        ('POST', '/events/search', True),
        ('POST', '/events/other', False),
        ('GET', '/unknown', False),
        ('GET', '/tenants/extra/segment', False),
        ('PUT', '/tenants', False),
    ],
)
def test_retry_allowlist_and_exhaustion(
    mock_client: Callable[..., httpx.Client], delays: list[float], method: str, path: str, retries: bool
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500 if attempts == 1 else 503)

    transport = _Transport(PATAuth(_PAT), client=mock_client(handler))
    with pytest.raises(APIStatusError) as caught:
        transport.request(method, path)
    assert caught.value.status_code == (503 if retries else 500)
    assert attempts == (3 if retries else 1)
    assert delays == ([0.75, 1.25] if retries else [])


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_retry_can_recover(mock_client: Callable[..., httpx.Client], delays: list[float], status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['Authorization'] == f'Bearer {_PAT}'
        assert request.url.params['locale'] == 'en-US'
        assert json.loads(request.content) == {'scopes': []}
        if not delays:
            return httpx.Response(status, text='local_rate_limited', headers={'Retry-After': '120'})
        return httpx.Response(200, json={'events': []})

    transport = _Transport(PATAuth(_PAT), client=mock_client(handler))
    assert transport.request('POST', '/events/search', params={'locale': 'en-US'}, json_body={'scopes': []}) == {'events': []}
    assert delays == [30 if status in {429, 503} else 0.75]


@pytest.mark.parametrize(
    ('failure', 'error_type', 'retries'),
    [
        (httpx.ConnectError, NetworkError, True),
        (httpx.ConnectTimeout, RequestTimeoutError, True),
        (httpx.ReadTimeout, RequestTimeoutError, True),
        (httpx.WriteTimeout, RequestTimeoutError, True),
        (httpx.PoolTimeout, RequestTimeoutError, True),
        (httpx.ReadError, NetworkError, False),
        (httpx.RemoteProtocolError, NetworkError, False),
    ],
)
@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_network_translation_and_retry_scope(
    mock_client: Callable[..., httpx.Client],
    delays: list[float],
    failure: type[httpx.RequestError],
    error_type: type[NetworkError],
    retries: bool,
    method: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure(_SENSITIVE, request=request)

    transport = _Transport(PATAuth(_PAT), client=mock_client(handler))
    with pytest.raises(error_type) as caught:
        transport.request(method, '/tenants')
    assert type(caught.value) is error_type
    _assert_safe(caught.value)
    assert delays == ([0.75, 1.25] if retries and method == 'GET' else [])


@pytest.mark.parametrize('use_context', [True, False])
def test_owned_client_is_reused_and_closed(monkeypatch: pytest.MonkeyPatch, use_context: bool) -> None:
    real_client = httpx.Client
    clients: list[httpx.Client] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'tenants': []})

    def create(*, trust_env: bool, limits: httpx.Limits) -> httpx.Client:
        assert trust_env is False
        assert limits.max_connections == 20
        assert limits.max_keepalive_connections == 10
        client = real_client(transport=httpx.MockTransport(handler), trust_env=trust_env, limits=limits)
        clients.append(client)
        return client

    monkeypatch.setattr('sfdctrust._transport.httpx.Client', create)
    transport = _Transport(PATAuth(_PAT))
    assert requests == []
    if use_context:
        with transport:
            transport.request('GET', 'tenants')
            transport.request('GET', 'tenants')
    else:
        transport.request('GET', 'tenants')
        transport.request('GET', 'tenants')
        transport.close()
    assert len(requests) == 2
    assert len(clients) == 1
    assert clients[0].is_closed


@pytest.mark.parametrize('status', [200, 401])
def test_response_stream_closes_and_only_success_is_read(mock_client: Callable[..., httpx.Client], status: int) -> None:
    class Body(httpx.SyncByteStream):
        closed = False

        def __iter__(self) -> Iterator[bytes]:
            assert status == 200, 'Error body was read'
            yield b'{"tenants": []}'

        def close(self) -> None:
            self.closed = True

    body = Body()
    transport = _Transport(PATAuth(_PAT), client=mock_client(lambda _: httpx.Response(status, stream=body)))
    if status == 200:
        assert transport.request('GET', '/tenants') == {'tenants': []}
    else:
        with pytest.raises(AuthenticationError):
            transport.request('GET', '/tenants')
    assert body.closed
