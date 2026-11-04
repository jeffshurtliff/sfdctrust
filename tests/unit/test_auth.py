# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_auth
:Synopsis:          Offline PAT validation, redaction, and authentication coverage
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import socket
from pathlib import Path

import httpx
import pytest

from sfdctrust import ConfigurationError
from sfdctrust._auth import PATAuth
from sfdctrust._constants import DEFAULT_BASE_URL


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests never read a real PAT from the process environment."""
    monkeypatch.delenv('SFDCTRUST_PAT', raising=False)


@pytest.mark.parametrize(
    'pat',
    [
        None,
        '',
        ' ',
        '\t\r\n',
        b'synthetic-pat',
        123,
        False,
        [],
        {},
        ' padded',
        'padded ',
        'two words',
        'Bearer synthetic-pat',
        'injected\r\nX-Header:value',
        'nul\x00value',
        'del\x7fvalue',
        'non-ascii-\u00e9',
        '\u00a0',
    ],
)
def test_invalid_pat_is_rejected_without_echoing_input(pat: object) -> None:
    """Reject missing, mistyped, and unsafe header values without interpolation."""
    with pytest.raises(ConfigurationError) as caught:
        PATAuth(pat)
    assert str(caught.value) == 'PAT must be a nonempty string of visible ASCII characters without whitespace.'
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_explicit_pat_is_required() -> None:
    """Omitting the constructor argument never discovers credentials implicitly."""
    with pytest.raises(TypeError):
        PATAuth()


def test_construction_does_not_read_environment_or_perform_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation neither opens files nor connects to a service."""

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Unexpected I/O or environment lookup')

    with monkeypatch.context() as patch:
        patch.setattr('builtins.open', forbidden)
        patch.setattr(Path, 'open', forbidden)
        patch.setattr(socket, 'create_connection', forbidden)
        patch.setattr('os.environ.get', forbidden)
        auth = PATAuth('synthetic-explicit-pat')
        overridden = PATAuth.from_env(pat='synthetic-override-pat')
    assert '**********' in repr(auth)
    assert '**********' in repr(overridden)


def test_from_env_reads_only_the_documented_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The opt-in path reads one variable without loading files or changing it."""
    reads: list[str] = []

    def read(key: str) -> str:
        reads.append(key)
        return 'synthetic-env-pat'

    with monkeypatch.context() as patch:
        patch.setattr('os.environ.get', read)
        auth = PATAuth.from_env()
    assert reads == ['SFDCTRUST_PAT']
    request = next(auth.auth_flow(httpx.Request('GET', f'{DEFAULT_BASE_URL}/tenants')))
    assert request.headers['Authorization'] == 'Bearer synthetic-env-pat'


@pytest.mark.parametrize('value', [None, '', ' ', 'bad\npat'])
def test_missing_or_invalid_environment_fails(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Missing and invalid environment configuration fails clearly."""
    if value is not None:
        monkeypatch.setenv('SFDCTRUST_PAT', value)
    with pytest.raises(ConfigurationError):
        PATAuth.from_env()


@pytest.mark.parametrize('override', [None, '', ' ', 'bad\rpat', b'bytes-pat', False])
def test_invalid_override_never_falls_back(monkeypatch: pytest.MonkeyPatch, override: object) -> None:
    """Even a valid environment PAT cannot rescue an explicit invalid override."""
    monkeypatch.setenv('SFDCTRUST_PAT', 'synthetic-env-pat')
    with pytest.raises(ConfigurationError):
        PATAuth.from_env(pat=override)


def test_explicit_override_wins_and_environment_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selection preserves both the supplied value and the original environment."""
    monkeypatch.setenv('SFDCTRUST_PAT', 'synthetic-env-pat')
    auth = PATAuth.from_env(pat='synthetic.override+/=._-')
    request = next(auth.auth_flow(httpx.Request('GET', f'{DEFAULT_BASE_URL}/tenants')))
    assert request.headers['Authorization'] == 'Bearer synthetic.override+/=._-'
    assert os.environ['SFDCTRUST_PAT'] == 'synthetic-env-pat'


def test_secrets_are_redacted_from_representations_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Common formatting and diagnostic dictionaries show no raw credential."""
    pat = 'synthetic-private-pat'
    auth = PATAuth(pat)
    with caplog.at_level(logging.INFO):
        logging.getLogger(__name__).info('auth=%s repr=%r state=%s', auth, auth, vars(auth))
    for rendered in (str(auth), repr(auth), repr(vars(auth)), json.dumps(vars(auth), default=str), caplog.text):
        assert pat not in rendered
        assert '**********' in rendered


def test_credential_object_cannot_be_serialized() -> None:
    """Do not accidentally export the credential through JSON or pickle."""
    auth = PATAuth('synthetic-private-pat')
    with pytest.raises(TypeError, match='cannot be serialized'):
        pickle.dumps(auth)
    with pytest.raises(TypeError):
        json.dumps(auth)


@pytest.mark.parametrize('url', [DEFAULT_BASE_URL + '/tenants', 'https://api.salesforce.com:443/platform/mytrust/v1/status'])
def test_bearer_header_replaces_existing_auth(url: str) -> None:
    """Send exactly the chosen opaque PAT using the documented Bearer scheme."""
    auth = PATAuth('synthetic-not-a-jwt')
    request = httpx.Request('GET', url, headers={'Authorization': 'Bearer old-synthetic-pat'})
    authenticated = next(auth.auth_flow(request))
    assert authenticated is request
    assert authenticated.headers['Authorization'] == 'Bearer synthetic-not-a-jwt'


@pytest.mark.parametrize(
    'url',
    [
        'http://api.salesforce.com/platform/mytrust/v1/tenants',
        'https://example.invalid/tenants',
        'https://api.salesforce.com.example.invalid/tenants',
        'https://api.salesforce.com:8443/platform/mytrust/v1/tenants',
        'https://synthetic-user:synthetic-password@api.salesforce.com/platform/mytrust/v1/tenants',
    ],
)
def test_unsafe_destinations_fail_before_credential_attachment(url: str) -> None:
    """Never attach the PAT to an unintended destination or echo its URL."""
    request = httpx.Request('GET', url)
    with pytest.raises(ConfigurationError) as caught:
        next(PATAuth('synthetic-private-pat').auth_flow(request))
    assert 'Authorization' not in request.headers
    assert url not in str(caught.value)
    assert 'synthetic' not in str(caught.value)


@pytest.mark.parametrize('body', [b'{"error":"unauthorized"}', b'not-json'])
def test_401_does_not_retry_refresh_or_parse_the_response(body: bytes) -> None:
    """A rejected PAT results in exactly one offline request and an unchanged 401."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers['Authorization'] == 'Bearer synthetic-rejected-pat'
        return httpx.Response(401, content=body)

    with httpx.Client(auth=PATAuth('synthetic-rejected-pat'), transport=httpx.MockTransport(handler)) as client:
        response = client.get(f'{DEFAULT_BASE_URL}/tenants')
    assert paths == ['/platform/mytrust/v1/tenants']
    assert response.status_code == 401
    assert response.content == body
