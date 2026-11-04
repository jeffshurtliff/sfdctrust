# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_client_retries
:Synopsis:          Offline public-client retry policy tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

import traceback
from datetime import UTC, datetime

import httpx
import pytest

from sfdctrust import ConfigurationError, NetworkError, RateLimitError, RequestTimeoutError, TrustCenterClient

_PAT = 'synthetic-retry-secret'
_CURSOR = 'private-retry-cursor'
_NOW = datetime(2026, 11, 3, tzinfo=UTC).timestamp()


@pytest.mark.parametrize(
    ('status', 'header', 'delay'),
    [
        (429, None, 0.75),
        (503, '7', 7),
        (429, '0000', 0),
        (503, 'Tue, 03 Nov 2026 00:00:08 GMT', 8),
        (503, 'Tuesday, 03-Nov-26 00:00:08 GMT', 8),
        (503, 'Sunday, 03-Nov-69 00:00:08 GMT', 30),
        (503, 'Wut, 03 Nov 2026 00:00:08 GMT', 0.75),
        (429, 'Tue Nov  3 00:00:08 2026', 8),
        (503, 'Mon, 02 Nov 2026 00:00:00 GMT', 0),
        (429, 'Tue, 03 Nov 2026 00:05:00 GMT', 30),
        (503, '9' * 5000, 30),
        (429, '+2', 0.75),
        (503, '-1', 0.75),
        (503, '1.5', 0.75),
        (429, 'Tue, 03 Nov 2026 00:00:08 GMT, 2', 0.75),
        (429, 'Tue, 32 Nov 2026 00:00:08 GMT', 0.75),
        (500, '10', 0.75),
    ],
)
def test_retry_after_and_response_closure(monkeypatch: pytest.MonkeyPatch, status, header, delay) -> None:
    delays = []
    responses = []

    def sleep(seconds: float) -> None:
        assert responses[-1].is_closed
        delays.append(seconds)

    def respond(_: httpx.Request) -> httpx.Response:
        if not responses:
            response = httpx.Response(
                status,
                stream=httpx.ByteStream(b'local_rate_limited'),
                headers={} if header is None else {'Retry-After': header},
            )
        else:
            response = httpx.Response(200, json={'tenants': []})
        responses.append(response)
        return response

    monkeypatch.setattr('sfdctrust._transport.time.time', lambda: _NOW)
    monkeypatch.setattr('sfdctrust._transport.time.sleep', sleep)
    monkeypatch.setattr('sfdctrust._transport.random.uniform', lambda *_: 0.25)
    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http_client,
        TrustCenterClient(_PAT, http_client=http_client, max_retries=1) as client,
    ):
        assert client.tenants.list().tenants == []
    assert delays == [delay]
    assert len(responses) == 2
    assert all(response.is_closed for response in responses)


@pytest.mark.parametrize('factory', [TrustCenterClient, TrustCenterClient.from_env])
@pytest.mark.parametrize('options', [{}, {'max_retries': 0}, {'max_retries': 5}])
def test_retry_limit_exhaustion_is_safe(monkeypatch: pytest.MonkeyPatch, factory, options) -> None:
    monkeypatch.setattr('sfdctrust._transport.random.uniform', lambda *_: 0.125)
    delays = []
    requests = []
    monkeypatch.setattr('sfdctrust._transport.time.sleep', delays.append)

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, text='private-response', headers={'Retry-After': 'private-header'})

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http_client,
        factory(pat=_PAT, http_client=http_client, **options) as client,
        pytest.raises(RateLimitError) as exc,
    ):
        client.tenants.list(page_token=_CURSOR)

    retries = options.get('max_retries', 2)
    assert len(requests) == retries + 1
    assert all(request.url == requests[0].url for request in requests)
    assert delays == [0.5 * 2**index + 0.125 for index in range(retries)]
    assert exc.value.status_code == 429
    _assert_safe(exc.value)


@pytest.mark.parametrize('value', [-1, 6, False, True, 2.0, '2', None])
@pytest.mark.parametrize('factory', [TrustCenterClient, TrustCenterClient.from_env])
def test_invalid_retry_configuration(value, factory) -> None:
    with pytest.raises(ConfigurationError, match='max_retries must be an integer from 0 through 5'):
        factory(pat=_PAT, max_retries=value)


def _assert_safe(error: Exception) -> None:
    assert error.__cause__ is error.__context__ is None
    displayed = ''.join(traceback.format_exception(error))
    for secret in (_PAT, _CURSOR, 'private-response', 'private-header', 'api.salesforce.com', 'private-exception'):
        assert secret not in displayed


@pytest.mark.parametrize(
    ('failure', 'error', 'retries'),
    [
        (httpx.ConnectError, NetworkError, 1),
        (httpx.ReadTimeout, RequestTimeoutError, 1),
        (httpx.ReadError, NetworkError, 0),
    ],
)
def test_network_failures_are_retried_only_when_eligible(monkeypatch: pytest.MonkeyPatch, failure, error, retries) -> None:
    requests = []
    delays = []
    monkeypatch.setattr('sfdctrust._transport.time.sleep', delays.append)

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise failure('private-exception', request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http_client,
        TrustCenterClient(_PAT, http_client=http_client, max_retries=1) as client,
        pytest.raises(error) as exc,
    ):
        client.tenants.list(page_token=_CURSOR)
    assert len(requests) == retries + 1
    assert len(delays) == retries
    _assert_safe(exc.value)
