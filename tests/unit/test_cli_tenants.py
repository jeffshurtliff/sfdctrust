# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_cli_tenants
:Synopsis:          Offline CLI tenant reads with real clients and disposable stores
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from sfdctrust import PATStoreRecord, SQLitePATStore, TrustCenterClient, _cli
from sfdctrust.models.tenants import TenantDetail

PAT = 'synthetic-cli-pat'
PRIVATE = 'private-server-detail-\x1b[31m'
TENANT = {'id': 'realm:001', 'name': 'Synthetic tenant', 'cloud': 'future-cloud'}
EVENT = {
    'eventId': 'shared-event',
    'eventType': 'future-event',
    'status': 'future-status',
    'products': ['one'],
    'services': ['two'],
    'createdAt': '2026-11-01T10:00:00+05:30',
    'title': None,
    'scope': {'tenants': {'realm:001': {'future': None}, 'other': {}}},
    'futureExtra': {'nested': None},
}


@pytest.fixture
def api(monkeypatch):
    """Replace only HTTP construction; SDK credentials, resources and close are real."""
    clients, requests = [], []
    state = {'response': httpx.Response(200, json={'tenants': [TENANT]})}
    client_type = httpx.Client

    def handler(request):
        requests.append(request)
        response = state['response']
        if isinstance(response, BaseException):
            raise response
        return response

    def factory(**kwargs):
        client = client_type(**kwargs, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    monkeypatch.setattr('sfdctrust._transport.httpx.Client', factory)
    monkeypatch.setattr('sfdctrust._transport.time.sleep', lambda _: None)
    monkeypatch.setenv('SFDCTRUST_PAT', PAT)
    return state, clients, requests


def invoke(capsys, arguments, expected=0):
    with pytest.raises(SystemExit) as caught:
        _cli.main(arguments)
    assert caught.value.code == expected
    output = capsys.readouterr()
    assert PAT not in output.out + output.err
    assert PRIVATE not in output.out + output.err
    assert 'Traceback' not in output.out + output.err
    assert (output.err == '') == (expected == 0)
    if expected:
        assert output.out == ''
    return output.out


@pytest.mark.parametrize(
    'arguments', [[], ['--page-size', '1'], ['--page-size', '200', '--page-token', '', '--locale', ' odd locale ']]
)
def test_environment_and_page_inputs(api, capsys, arguments):
    state, clients, requests = api
    payload = {'tenants': [{**TENANT, 'unknown': None}], 'nextPageToken': '', 'future': [None]}
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['tenants', 'list', *arguments, '--json'])
    assert json.loads(output) == payload and output.endswith('\n') and output.count('\n') == 1
    assert len(requests) == 1 and clients[0].is_closed
    request = requests[0]
    assert request.method == 'GET' and request.url.path.endswith('/tenants')
    assert request.headers['Authorization'] == f'Bearer {PAT}'
    if not arguments:
        assert not request.url.query
    elif arguments == ['--page-size', '1']:
        assert dict(request.url.params) == {'pageSize': '1'}
    else:
        assert dict(request.url.params) == {'pageSize': '200', 'pageToken': '', 'locale': ' odd locale '}


@pytest.mark.parametrize('cursor', [None, '', ' /+=&%?雪 '])
def test_empty_page_cursor_and_text(api, capsys, cursor):
    state, clients, requests = api
    payload = {'tenants': []}
    if cursor is not None:
        payload['nextPageToken'] = cursor
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['tenants', 'list'])
    assert 'authorized scope' in output and 'does not establish Salesforce-wide health' in output
    assert ('Continuation' in output) == (cursor is not None)
    if cursor is not None:
        assert (cursor if cursor else '""') in output
    assert len(requests) == 1 and clients[0].is_closed


def test_continuation_is_caller_driven_and_preserves_inputs(api, capsys):
    state, clients, requests = api
    token = ' /+=&%?雪 '
    state['response'] = httpx.Response(200, json={'tenants': [], 'nextPageToken': token})
    first = json.loads(invoke(capsys, ['tenants', 'list', '--page-size', '25', '--locale', 'ja-JP', '--json']))
    assert len(requests) == 1
    state['response'] = httpx.Response(200, json={'tenants': [TENANT]})
    invoke(capsys, ['tenants', 'list', '--page-size', '25', '--locale', 'ja-JP', '--page-token', first['nextPageToken']])
    assert dict(requests[1].url.params) == {'pageSize': '25', 'locale': 'ja-JP', 'pageToken': token}
    assert len(requests) == 2 and all(client.is_closed for client in clients)


@pytest.mark.parametrize('as_json', [False, True])
def test_detail_history_presence_offsets_extras_and_scoped_duplicates(api, capsys, as_json):
    state, clients, requests = api
    payload = {**TENANT, 'region': None, 'futureTenant': True, 'events': [EVENT, {**EVENT, 'scope': {'tenants': {'third': {}}}}]}
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['tenants', 'get', TENANT['id'], '--locale', 'en-US', *(['--json'] if as_json else [])])
    if as_json:
        assert json.loads(output) == payload
        assert output == TenantDetail.model_validate(payload).model_dump_json(by_alias=True, exclude_unset=True) + '\n'
        assert 'environment' not in json.loads(output)
    else:
        assert output.count('Event: shared-event') == 2
        assert 'History (as supplied):' in output and '+05:30' in output
        assert 'Affected tenant IDs: ["realm:001", "other"]' in output
        assert 'Affected tenant IDs: ["third"]' in output
        assert 'region: null' in output and 'futureExtra' in output
    assert requests[0].url.path.endswith('/tenants/realm:001')
    assert dict(requests[0].url.params) == {'locale': 'en-US'}
    assert clients[0].is_closed


@pytest.mark.parametrize('as_json', [False, True])
def test_terminal_controls_in_rows_history_keys_scopes_and_cursor(api, capsys, as_json):
    state, _, _ = api
    value = 'unsafe\x1b[31m\n\r\t\x7f\x85\u202e\u2028'
    event = {**EVENT, 'description': value, value: value, 'scope': {'tenants': {value: {}}}}
    payload = {**TENANT, 'name': value, 'events': [event]}
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['tenants', 'get', TENANT['id'], *(['--json'] if as_json else [])])
    if as_json:
        assert json.loads(output) == payload
    else:
        assert all(char not in output for char in ('\x1b', '\r', '\t', '\x7f', '\x85', '\u202e', '\u2028'))
        assert '\\x1b' in output
    state['response'] = httpx.Response(200, json={'tenants': [{**TENANT, 'name': value}], 'nextPageToken': value})
    output = invoke(capsys, ['tenants', 'list'])
    assert value not in output and '\\x1b' in output


@pytest.mark.parametrize('selector', ['default', 'path', 'alias'])
@pytest.mark.parametrize('action', ['list', 'get'])
def test_explicit_stores_ignore_environment_without_fallback(api, monkeypatch, tmp_path, capsys, selector, action):
    state, clients, requests = api
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    kwargs = (
        {'path': tmp_path / 'private' / 'pat.sqlite3'}
        if selector == 'path'
        else {'alias': 'monitoring'}
        if selector == 'alias'
        else {}
    )
    SQLitePATStore.initialize(pat='synthetic-store-pat', **kwargs)
    original = os.environ.__class__.__getitem__

    def getitem(self, key):
        assert key != 'SFDCTRUST_PAT', 'An explicit store must ignore the ambient PAT.'
        return original(self, key)

    monkeypatch.setattr(os.environ.__class__, '__getitem__', getitem)
    options = (
        ['--store-path', str(kwargs['path'])]
        if selector == 'path'
        else ['--store-alias', 'monitoring']
        if selector == 'alias'
        else ['--store']
    )
    if action == 'get':
        state['response'] = httpx.Response(200, json={**TENANT, 'events': []})
    invoke(capsys, ['tenants', action, *([TENANT['id']] if action == 'get' else []), *options])
    assert requests[0].headers['Authorization'] == 'Bearer synthetic-store-pat'
    assert len(requests) == 1 and clients[0].is_closed


@pytest.mark.parametrize(
    'state_name', ['missing', 'empty-file', 'unseeded', 'pending', 'unsafe', 'changed', 'pending-after-load']
)
@pytest.mark.parametrize(
    'arguments',
    [
        ['tenants', 'list'],
        ['tenants', 'get', 'synthetic'],
        ['status', 'snapshot'],
        ['events', 'get', 'synthetic'],
        [
            'events',
            'search',
            '--tenant-id',
            'synthetic',
            '--start-time',
            '2026-11-01T00:00:00Z',
            '--end-time',
            '2026-11-02T00:00:00Z',
        ],
    ],
)
def test_store_failures_no_fallback_no_requests(api, monkeypatch, tmp_path, capsys, state_name, arguments):
    _, clients, requests = api
    path = tmp_path / 'private' / 'pat.sqlite3'
    if state_name == 'empty-file':
        path.parent.mkdir(mode=0o700)
        path.touch(mode=0o600)
    elif state_name != 'missing':
        store = SQLitePATStore.initialize(pat='synthetic-store-pat', path=path)
        if state_name == 'unseeded':
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM credential')
        elif state_name == 'pending':
            record = store.load()
            assert store.compare_and_swap(
                expected_revision=record.revision,
                expected_attempt=None,
                replacement=PATStoreRecord(record.revision, record.get_pat(), uuid4()),
            )
        elif state_name == 'unsafe':
            if sys.platform == 'win32':
                pytest.skip('POSIX mode check; native Windows ACL tests are separate.')
            path.chmod(0o644)
        elif state_name in {'changed', 'pending-after-load'}:
            original = _cli._client

            def client(args):
                result = original(args)
                record = store.load()
                replacement = (
                    PATStoreRecord(uuid4(), 'synthetic-replacement')
                    if state_name == 'changed'
                    else PATStoreRecord(record.revision, record.get_pat(), uuid4())
                )
                assert store.compare_and_swap(expected_revision=record.revision, expected_attempt=None, replacement=replacement)
                return result

            monkeypatch.setattr(_cli, '_client', client)
    invoke(capsys, [*arguments, '--store-path', str(path)], 3)
    assert not requests
    assert all(client.is_closed for client in clients)
    if state_name == 'missing':
        assert not path.exists() and not path.parent.exists()


def test_missing_environment_does_not_discover_default_store(api, monkeypatch, tmp_path, capsys):
    _, clients, requests = api
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    SQLitePATStore.initialize(pat='synthetic-store-pat')
    monkeypatch.delenv('SFDCTRUST_PAT')
    invoke(capsys, ['tenants', 'list'], 3)
    assert not requests and not clients


@pytest.mark.parametrize(
    ('response', 'code'),
    [
        (httpx.Response(401, text=PRIVATE), 3),
        (httpx.Response(400, text=PRIVATE), 4),
        (httpx.Response(403, text=PRIVATE), 4),
        (httpx.Response(404, text=PRIVATE), 4),
        (httpx.Response(429, text=PRIVATE), 4),
        (httpx.Response(503, text=PRIVATE), 4),
        (httpx.Response(302, headers={'Location': 'https://example.invalid/' + PAT}), 4),
        (httpx.Response(200, text=PRIVATE), 4),
        (httpx.Response(200, json={'tenants': [{'id': PRIVATE}]}), 4),
        (httpx.ReadTimeout(PRIVATE), 4),
        (httpx.ConnectError(PRIVATE), 4),
        (RuntimeError(PRIVATE), 1),
        (KeyboardInterrupt(PRIVATE), 130),
    ],
)
def test_failures_streams_redaction_and_cleanup(api, capsys, response, code):
    state, clients, requests = api
    state['response'] = response
    invoke(capsys, ['tenants', 'list', '--page-token', 'stale-synthetic', '--json'], code)
    assert clients[0].is_closed
    assert all(request.url.params['pageToken'] == 'stale-synthetic' for request in requests)
    if isinstance(response, httpx.Response) and response.status_code == 400:
        assert len(requests) == 1  # Never restart a stale cursor.


@pytest.mark.parametrize('stage', ['render', 'write', 'flush', 'close'])
@pytest.mark.parametrize('interrupted', [False, True])
def test_internal_output_and_interruption_failures(api, monkeypatch, capsys, stage, interrupted):
    _, clients, _ = api

    def fail(*args, **kwargs):
        raise KeyboardInterrupt(PRIVATE) if interrupted else RuntimeError(PRIVATE)

    if stage == 'render':
        monkeypatch.setattr(_cli, '_render', fail)
    elif stage == 'close':
        original = TrustCenterClient.close

        def close(self):
            original(self)
            fail()

        monkeypatch.setattr(TrustCenterClient, 'close', close)
    else:
        monkeypatch.setattr(sys.stdout, stage, fail)
    with pytest.raises(SystemExit) as caught:
        _cli.main(['tenants', 'list'])
    assert caught.value.code == (130 if interrupted else 1)
    # Restore broken stream methods before asking pytest to read its capture.
    monkeypatch.undo()
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err and 'Traceback' not in output.err
    if stage != 'flush':
        assert output.out == ''
    assert all(client.is_closed for client in clients)


def test_failed_diagnostic_does_not_mask_error_or_leak(api, monkeypatch):
    state, clients, _ = api
    state['response'] = httpx.Response(401, text=PRIVATE)

    def fail(*args):
        raise OSError(PRIVATE)

    monkeypatch.setattr(sys.stderr, 'write', fail)
    with pytest.raises(SystemExit) as caught:
        _cli.main(['tenants', 'list'])
    assert caught.value.code == 3 and clients[0].is_closed


def test_maximum_cursor_and_unicode_id(api, capsys):
    state, clients, requests = api
    invoke(capsys, ['tenants', 'list', '--page-token', '雪' * 4096, '--page-size', '200', '--locale', ''])
    assert dict(requests[0].url.params) == {'pageToken': '雪' * 4096, 'pageSize': '200', 'locale': ''}
    identifier = 'realm:雪 1'
    state['response'] = httpx.Response(200, json={**TENANT, 'id': identifier, 'events': []})
    invoke(capsys, ['tenants', 'get', identifier])
    assert requests[1].url.path.endswith('/tenants/' + identifier)
    assert all(client.is_closed for client in clients)


def test_credential_interruption_is_safe(api, monkeypatch, capsys):
    _, clients, requests = api

    def interrupted():
        raise KeyboardInterrupt(PRIVATE)

    monkeypatch.setattr(TrustCenterClient, 'from_env', interrupted)
    invoke(capsys, ['tenants', 'list'], 130)
    assert not clients and not requests
