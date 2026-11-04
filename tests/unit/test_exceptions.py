# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_exceptions
:Synopsis:          Offline exception hierarchy and safe status-context coverage
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import pytest

import sfdctrust
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
    _exceptions,
)


@pytest.mark.parametrize(
    'error',
    [
        ConfigurationError('Invalid SDK configuration.'),
        NetworkError('Request could not complete.'),
        RequestTimeoutError('Request timed out.'),
        APIStatusError(400),
        AuthenticationError(),
        RateLimitError(),
        NotFoundError(),
        APIStatusError(500),
        MalformedResponseError('Response could not be decoded.'),
    ],
)
def test_all_sdk_errors_can_be_caught_at_the_package_root(error: TrustCenterError) -> None:
    """Consumers catch specific failures or the shared base through stable imports."""
    assert getattr(sfdctrust, type(error).__name__) is type(error)
    assert getattr(_exceptions, type(error).__name__) is type(error)
    with pytest.raises(TrustCenterError) as caught:
        raise error
    assert caught.value is error


def test_timeout_can_be_caught_as_a_network_failure() -> None:
    """Timeout handling can share the network-failure recovery path."""
    with pytest.raises(NetworkError):
        raise RequestTimeoutError('Request timed out.')


@pytest.mark.parametrize(
    ('error', 'status'),
    [
        (AuthenticationError(), 401),
        (RateLimitError(), 429),
        (NotFoundError(), 404),
        (APIStatusError(400), 400),
        (APIStatusError(503), 503),
    ],
)
def test_api_status_context_is_safe_and_predictable(error: APIStatusError, status: int) -> None:
    """Retain status without raw requests, responses, bodies, headers, or guessed IDs."""
    with pytest.raises(APIStatusError) as caught:
        raise error
    assert caught.value.status_code == status
    assert vars(error) == {'status_code': status}
    assert error.args == (f'My Trust Center API returned HTTP {status}.',)
    assert str(error) == f'My Trust Center API returned HTTP {status}.'


@pytest.mark.parametrize('status', [None, True, False, '401', 401.0, 200, 399, 600, -1])
def test_invalid_status_does_not_echo_untrusted_input(status: object) -> None:
    """Reject invalid status metadata with a constant error message."""
    with pytest.raises(ValueError, match='^status_code must be an integer from 400 through 599$'):
        APIStatusError(status)


@pytest.mark.parametrize('error_type', [AuthenticationError, RateLimitError, NotFoundError])
def test_fixed_status_errors_cannot_accept_server_messages(error_type: type[APIStatusError]) -> None:
    """There is no response-message input through which to retain echoed credentials."""
    with pytest.raises(TypeError):
        error_type(message='synthetic-server-message')


def test_base_exception_preserves_existing_message_behavior() -> None:
    """The existing base remains compatible with ordinary Exception construction."""
    error = TrustCenterError('Safe SDK-authored message.')
    assert str(error) == 'Safe SDK-authored message.'


def test_malformed_response_is_distinct_from_an_http_status_failure() -> None:
    """Invalid successful content is not misclassified as a failed HTTP status."""
    error = MalformedResponseError('Response could not be decoded.')
    assert isinstance(error, TrustCenterError)
    assert not isinstance(error, APIStatusError)
