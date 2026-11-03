# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_tenants
:Synopsis:          Offline tests of the public tenant-list operation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     02 Nov 2026
"""

import traceback
from collections.abc import Iterator

import httpx
import pytest

from sfdctrust import (
    APIStatusError,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    TrustCenterClient,
    TrustCenterError,
)
from sfdctrust.models.tenants import Tenant, TenantListResponse

_URL = 'https://api.salesforce.com/platform/mytrust/v1/tenants'
_PAT = 'synthetic-tenant-pat'
_TENANT = {'id': 'realm:001', 'cloud': 'future-cloud', 'name': 'Example tenant'}
_TOKEN = ' /+=&%?雪 '


@pytest.fixture
def mock_api() -> Iterator[tuple[httpx.Client, list[httpx.Request], list[httpx.Response]]]:
    requests: list[httpx.Request] = []
    responses: list[httpx.Response] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        yield http_client, requests, responses


def test_explicit_pat_and_default_query(mock_api, monkeypatch: pytest.MonkeyPatch) -> None:
    http_client, requests, responses = mock_api
    monkeypatch.setenv('SFDCTRUST_PAT', 'different-synthetic-pat')
    responses.append(httpx.Response(200, json={'tenants': [_TENANT]}))
    with TrustCenterClient(_PAT, http_client=http_client) as client:
        assert not requests
        page = client.tenants.list(page_size=None, page_token=None, locale=None)

    assert not http_client.is_closed
    (request,) = requests
    assert request.method == 'GET'
    assert str(request.url) == _URL
    assert request.headers['Authorization'] == f'Bearer {_PAT}'
    assert isinstance(page, TenantListResponse)
    (tenant,) = page.tenants
    assert isinstance(tenant, Tenant)
    assert (tenant.id, tenant.cloud, tenant.name) == tuple(_TENANT.values())
    assert tenant.environment is tenant.my_domain is page.next_page_token is None
    assert tenant.model_fields_set == {'id', 'cloud', 'name'}
    assert page.model_fields_set == {'tenants'}


def test_constructor_requires_explicit_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SFDCTRUST_PAT', _PAT)
    with pytest.raises(TypeError):
        TrustCenterClient()


@pytest.mark.parametrize('use_override', [False, True])
def test_env_selection(mock_api, monkeypatch: pytest.MonkeyPatch, use_override: bool) -> None:
    http_client, requests, responses = mock_api
    env_pat = 'synthetic-env-pat'
    monkeypatch.setenv('SFDCTRUST_PAT', env_pat)
    responses.append(httpx.Response(200, json={'tenants': []}))
    kwargs = {'pat': _PAT} if use_override else {}
    with TrustCenterClient.from_env(http_client=http_client, **kwargs) as client:
        assert not requests
        assert client.tenants.list().tenants == []
    assert requests[0].headers['Authorization'] == f'Bearer {_PAT if use_override else env_pat}'


@pytest.mark.parametrize('pat', [None, '', ' ', 123])
def test_invalid_override_never_falls_back(mock_api, monkeypatch: pytest.MonkeyPatch, pat: object) -> None:
    http_client, requests, _ = mock_api
    monkeypatch.setenv('SFDCTRUST_PAT', _PAT)
    with pytest.raises(ConfigurationError):
        TrustCenterClient.from_env(pat=pat, http_client=http_client)
    assert not requests


def test_missing_env_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SFDCTRUST_PAT', raising=False)
    with pytest.raises(ConfigurationError):
        TrustCenterClient.from_env()


@pytest.mark.parametrize('use_context', [True, False])
def test_sdk_owned_client_closes(mock_api, monkeypatch: pytest.MonkeyPatch, use_context: bool) -> None:
    http_client, requests, _ = mock_api
    monkeypatch.setattr('sfdctrust._transport.httpx.Client', lambda **kwargs: http_client)
    client = TrustCenterClient(_PAT)
    if use_context:
        with client as entered:
            assert entered is client
            assert not http_client.is_closed
    else:
        client.close()
    assert http_client.is_closed
    assert not requests


@pytest.mark.parametrize(('page_size', 'page_token'), [(1, ''), (200, 'x' * 4096)])
def test_query_boundaries(mock_api, page_size: int, page_token: str) -> None:
    http_client, requests, responses = mock_api
    responses.append(httpx.Response(200, json={'tenants': [_TENANT] * page_size}))
    with TrustCenterClient(_PAT, http_client=http_client) as client:
        assert (
            len(client.tenants.list(page_size=page_size, page_token=page_token, locale='not a BCP 47 tag').tenants) == page_size
        )
    assert dict(requests[0].url.params) == {
        'pageSize': str(page_size),
        'pageToken': page_token,
        'locale': 'not a BCP 47 tag',
    }


@pytest.mark.parametrize(
    ('argument', 'value'),
    [
        ('page_size', 0),
        ('page_size', 201),
        ('page_size', True),
        ('page_size', 1.0),
        ('page_size', '1'),
        ('page_token', 123),
        ('page_token', 'x' * 4097),
        ('locale', ['en-US']),
    ],
)
def test_invalid_query_fails_before_io(mock_api, argument: str, value: object) -> None:
    http_client, requests, _ = mock_api
    with TrustCenterClient(_PAT, http_client=http_client) as client, pytest.raises(ConfigurationError, match=argument):
        client.tenants.list(**{argument: value})
    assert not requests


def test_caller_driven_pages_and_wire_serialization(mock_api) -> None:
    http_client, requests, responses = mock_api
    tenant = {**_TENANT, 'environment': 'Production', 'myDomain': 'example', 'futureField': {'value': 1}}
    first = {'tenants': [tenant], 'nextPageToken': _TOKEN, 'futureMetadata': True}
    second = {'tenants': []}
    responses.extend(httpx.Response(200, json=page) for page in (first, second))
    with TrustCenterClient(_PAT, http_client=http_client) as client:
        page = client.tenants.list(page_size=1, locale='ja-JP')
        assert len(requests) == 1
        assert page.tenants[0].my_domain == 'example'
        assert page.next_page_token == _TOKEN
        assert page.model_dump(mode='json', by_alias=True, exclude_unset=True) == first
        page = client.tenants.list(page_size=1, page_token=page.next_page_token, locale='ja-JP')
        assert page.next_page_token is None
        assert page.model_dump(mode='json', by_alias=True, exclude_unset=True) == second

    first_request, second_request = requests
    assert dict(first_request.url.params) == {'pageSize': '1', 'locale': 'ja-JP'}
    assert dict(second_request.url.params) == {'pageSize': '1', 'locale': 'ja-JP', 'pageToken': _TOKEN}
    assert b'%2F%2B%3D%26%25%3F%E9%9B%AA' in second_request.url.query


def _assert_safe(error: TrustCenterError) -> None:
    assert error.__cause__ is error.__context__ is None
    displayed = ''.join(traceback.format_exception(error))
    for sensitive in (_PAT, _URL, 'private-server-detail', 'ValidationError'):
        assert sensitive not in displayed


@pytest.mark.parametrize(('status', 'error_type'), [(400, APIStatusError), (401, AuthenticationError)])
def test_server_errors_surface_without_retry_or_restart(mock_api, status: int, error_type: type[APIStatusError]) -> None:
    http_client, requests, responses = mock_api
    responses.append(httpx.Response(status, json={'message': 'private-server-detail'}))
    with TrustCenterClient(_PAT, http_client=http_client) as client, pytest.raises(error_type) as exc:
        client.tenants.list(page_token=_TOKEN)
    assert exc.value.status_code == status
    assert len(requests) == 1
    _assert_safe(exc.value)


@pytest.mark.parametrize(
    'payload',
    [
        {},
        [],
        {'tenants': None},
        {'tenants': {}},
        {'tenants': [{}]},
        {'tenants': [{key: value for key, value in _TENANT.items() if key != 'name'}]},
        {'tenants': [{**_TENANT, 'id': 123}]},
        {'tenants': [{**_TENANT, 'cloud': ['core']}]},
        {'tenants': [{**_TENANT, 'name': True}]},
        {'tenants': [{**_TENANT, 'environment': None}]},
        {'tenants': [{**_TENANT, 'environment': 1}]},
        {'tenants': [{**_TENANT, 'myDomain': None}]},
        {'tenants': [{**_TENANT, 'myDomain': []}]},
        {'tenants': [], 'nextPageToken': None},
        {'tenants': [], 'nextPageToken': 123},
        {'tenants': [_TENANT] * 201},
        {'tenants': 'private-server-detail'},
    ],
)
def test_malformed_schema_is_sanitized(mock_api, payload: object) -> None:
    http_client, requests, responses = mock_api
    responses.append(httpx.Response(200, json=payload))
    with TrustCenterClient(_PAT, http_client=http_client) as client, pytest.raises(MalformedResponseError) as exc:
        client.tenants.list()
    assert str(exc.value) == 'My Trust Center returned an invalid tenant page.'
    assert len(requests) == 1
    _assert_safe(exc.value)


def test_malformed_json_preserves_transport_error(mock_api) -> None:
    http_client, requests, responses = mock_api
    responses.append(httpx.Response(200, content=b'{"tenants": private-server-detail}'))
    with TrustCenterClient(_PAT, http_client=http_client) as client, pytest.raises(MalformedResponseError) as exc:
        client.tenants.list()
    assert str(exc.value) == 'My Trust Center returned an invalid JSON response.'
    assert len(requests) == 1
    _assert_safe(exc.value)


@pytest.mark.parametrize('kwargs', [{'page_token': '\ud800'}, {'locale': 'x' * 70000}])
def test_query_encoding_failure_is_safe(mock_api, kwargs: dict[str, str]) -> None:
    http_client, requests, _ = mock_api
    with TrustCenterClient(_PAT, http_client=http_client) as client, pytest.raises(ConfigurationError) as exc:
        client.tenants.list(**kwargs)
    assert not requests
    _assert_safe(exc.value)
