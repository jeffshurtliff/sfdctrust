# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_cli_events
:Synopsis:          Offline status and event CLI contracts through real SDK clients
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import json
import os
import sys
from pathlib import Path

import httpx
import pytest

from sfdctrust import SQLitePATStore, TrustCenterClient, _cli
from sfdctrust.models.events import EventDetail, EventSearchResponse
from sfdctrust.models.status import StatusSnapshot

PAT = 'synthetic-cli-event-pat'
PRIVATE = 'synthetic-private-server-\x1b[31m'
CATEGORIES = ('patch', 'incident', 'maintenance', 'informationalMessage')
DATA = {
    'patch': {
        'releaseId': 'synthetic-release',
        'releaseName': 'Synthetic release',
        'releaseVersion': 'future-version',
        'plannedStartTime': '2026-11-01T10:00:00+05:30',
        'plannedEndTime': None,
        'future': None,
    },
    'incident': {'additionalInformation': None, 'rcaLink': None, 'rcaCreatedAt': None, 'future': None},
    'maintenance': {'plannedStartTime': None, 'plannedEndTime': None, 'additionalInformation': None, 'future': None},
    'informationalMessage': {'informationalMessageType': None, 'future': None},
    'future-event': {'futureValue': [None, {'nested': True}], 'unknownTimestamp': 'future-format'},
}
START, END = '2026-11-01T00:00:00+05:45', '2026-11-02T00:00:00-04:00'
SEARCH = ['events', 'search', '--tenant-id', 'realm:one', '--start-time', START, '--end-time', END]
EVENT = {
    'eventId': 'shared-event',
    'eventType': 'patch',
    'status': 'future-status',
    'products': ['one'],
    'services': ['two'],
    'createdAt': '2026-11-01T10:00:00+05:30',
    'title': None,
    'endTime': None,
    'scope': {'tenants': {'realm:one': {'future': None}, 'realm:two': {}}},
    'futureExtra': {'nested': None},
}
DETAIL = {key: value for key, value in EVENT.items() if key != 'scope'}
TIMELINE = {
    'subEventId': 'shared-stage',
    'subEventType': 'patch_release_started',
    'scope': {'tenants': {'realm:one': {'future': None}}},
    'createdAt': '2026-11-01T11:00:00-03:30',
    'message': None,
    'plannedStartTime': None,
    'extra': [None, True],
}
EMPTY = {name: [] for name in CATEGORIES}
SNAPSHOT = {'ongoing': EMPTY, 'upcoming': EMPTY}
OPERATIONS = [(['status', 'snapshot'], SNAPSHOT), (SEARCH, {'events': []}), (['events', 'get', 'shared-event'], DETAIL)]


@pytest.fixture
def api(monkeypatch):
    clients, requests = [], []
    state = {'response': httpx.Response(200, json=SNAPSHOT)}
    original = httpx.Client

    def respond(request):
        requests.append(request)
        response = state['response']
        if isinstance(response, BaseException):
            raise response
        return response

    def client(**kwargs):
        result = original(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(result)
        return result

    monkeypatch.setattr('sfdctrust._transport.httpx.Client', client)
    monkeypatch.setattr('sfdctrust._transport.time.sleep', lambda _: None)
    monkeypatch.setenv('SFDCTRUST_PAT', PAT)
    return state, clients, requests


def invoke(capsys, arguments, expected=0):
    with pytest.raises(SystemExit) as caught:
        _cli.main(arguments)
    assert caught.value.code == expected
    output = capsys.readouterr()
    assert PAT not in output.out + output.err and PRIVATE not in output.out + output.err
    assert 'Traceback' not in output.out + output.err
    if expected:
        assert output.out == ''
        message = {
            1: 'internal or output failure.',
            2: 'error: invalid arguments. Use --help for available options.',
            3: 'credential, configuration, or PAT store failure. Check the selected credential and store state.',
            4: 'My Trust Center request failed.',
            130: 'interrupted.',
        }[expected]
        assert output.err.endswith(f'sfdctrust: {message}\n')
    else:
        assert output.err == ''
    return output.out


@pytest.mark.parametrize('as_json', [False, True])
def test_snapshot_all_buckets_scopes_duplicates_order_and_future_data(api, capsys, as_json):
    state, clients, requests = api
    ongoing = {category: [{**EVENT, 'eventType': category, 'data': DATA[category]}] for category in CATEGORIES}
    # The same patch appears at different stages/scopes, even across groups.
    other = {**EVENT, 'status': 'scheduled', 'scope': {'tenants': {'realm:three': {}}}}
    ongoing['patch'].append(other)
    payload = {'ongoing': {**ongoing, 'futureBucket': [None]}, 'upcoming': {**EMPTY, 'patch': [other]}, 'future': None}
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['status', 'snapshot', '--locale', ' odd locale ', *(['--json'] if as_json else [])])
    if as_json:
        assert output == StatusSnapshot.model_validate(payload).model_dump_json(by_alias=True, exclude_unset=True) + '\n'
        assert json.loads(output) == payload
    else:
        assert 'ongoing:\n' in output and 'upcoming:\n' in output
        assert all(output.count(f'  {category}:\n') == 2 for category in CATEGORIES)
        assert output.count('Event: shared-event') == 6
        assert output.index('future-status') < output.index('scheduled')
        assert 'Affected tenant IDs: ["realm:one", "realm:two"]' in output
        assert output.count('Affected tenant IDs: ["realm:three"]') == 2
        assert 'do not establish Salesforce-wide health' in output
    assert len(requests) == 1 and clients[0].is_closed
    assert requests[0].method == 'GET' and requests[0].url.path.endswith('/status')
    assert dict(requests[0].url.params) == {'locale': ' odd locale '}
    assert not requests[0].content


def test_empty_snapshot_text_has_eight_buckets(api, capsys):
    _, clients, requests = api
    output = invoke(capsys, ['status', 'snapshot'])
    assert output.count('No events returned in this authorized scope.') == 8
    assert 'do not establish Salesforce-wide health' in output
    assert clients[0].is_closed and len(requests) == 1 and not requests[0].url.query


@pytest.mark.parametrize('filters', [None, *[(category,) for category in CATEGORIES], CATEGORIES])
@pytest.mark.parametrize('page_size', [None, 1, 200])
def test_search_request_mapping_defaults_filters_paging_and_preserved_json(api, capsys, filters, page_size):
    state, clients, requests = api
    payload = {'events': [EVENT, {**EVENT, 'scope': {'tenants': {'realm:three': {}}}}], 'nextPageToken': '', 'extra': None}
    state['response'] = httpx.Response(200, json=payload)
    options = ['--tenant-id', 'realm:two', '--tenant-id', 'realm:one', '--locale', '', '--page-token', ' /+=&%?雪 ']
    if filters is not None:
        for category in filters:
            options.extend(['--event-type', category])
    if page_size is not None:
        options.extend(['--page-size', str(page_size)])
    output = invoke(capsys, [*SEARCH, *options, '--json'])
    assert output == EventSearchResponse.model_validate(payload).model_dump_json(by_alias=True, exclude_unset=True) + '\n'
    assert json.loads(output) == payload
    request = requests[0]
    expected = {
        'scopes': [{'type': 'tenant', 'id': name} for name in ('realm:one', 'realm:two', 'realm:one')],
        'startTime': START,
        'endTime': END,
        'pageToken': ' /+=&%?雪 ',
    }
    if page_size is not None:
        expected['pageSize'] = page_size
    if filters is not None:
        expected['eventTypes'] = list(filters)
    assert json.loads(request.content) == expected
    assert request.method == 'POST' and request.url.path.endswith('/events/search')
    assert dict(request.url.params) == {'locale': ''}
    assert request.headers['Authorization'] == f'Bearer {PAT}'
    assert len(requests) == 1 and clients[0].is_closed


@pytest.mark.parametrize(
    ('start', 'end', 'wire_start', 'wire_end'),
    [
        ('2026-11-01t00:00:00z', '2026-11-01T00:00:00.000001Z', '2026-11-01T00:00:00+00:00', '2026-11-01T00:00:00.000001+00:00'),
        ('2026-11-01T23:00:00+05:30', '2026-11-01T20:00:00+00:00', '2026-11-01T23:00:00+05:30', '2026-11-01T20:00:00+00:00'),
    ],
)
def test_search_full_timestamps_compare_instants_and_preserve_offsets(api, capsys, start, end, wire_start, wire_end):
    state, clients, requests = api
    state['response'] = httpx.Response(200, json={'events': []})
    invoke(capsys, [*SEARCH, '--start-time', start, '--end-time', end])
    body = json.loads(requests[0].content)
    assert body['startTime'] == wire_start and body['endTime'] == wire_end
    assert 'eventTypes' not in body and 'pageSize' not in body and 'pageToken' not in body
    assert not requests[0].url.query and clients[0].is_closed


@pytest.mark.parametrize('cursor', [None, '', 'opaque-雪', '雪' * 4096])
def test_search_empty_page_and_continuation_preserves_query(api, capsys, cursor):
    state, clients, requests = api
    payload = {'events': []}
    if cursor is not None:
        payload['nextPageToken'] = cursor
    state['response'] = httpx.Response(200, json=payload)
    arguments = [*SEARCH, '--page-size', '25', '--event-type', 'patch', '--locale', 'ja-JP']
    output = invoke(capsys, arguments)
    assert 'authorized scope' in output and 'does not establish Salesforce-wide health' in output
    assert ('Continuation' in output) == (cursor is not None)
    assert len(requests) == 1
    if cursor is not None:
        assert ('""' if cursor == '' else cursor) in output
        state['response'] = httpx.Response(200, json={'events': [EVENT]})
        output = invoke(capsys, [*arguments, '--page-token', cursor])
        assert 'Event: shared-event' in output and 'Affected tenant IDs:' in output
        before, after = [json.loads(request.content) for request in requests]
        assert after.pop('pageToken') == cursor and before == after
        assert requests[0].url == requests[1].url
    assert all(client.is_closed for client in clients)


def test_search_fifty_scopes_and_json_only_ids_are_not_url_segments(api, capsys):
    state, clients, requests = api
    state['response'] = httpx.Response(200, json={'events': []})
    identifiers = ['realm:one'] + [f' /?雪%#{index}' for index in range(49)]
    options = [argument for name in identifiers[1:] for argument in ('--tenant-id', name)]
    invoke(capsys, [*SEARCH, *options])
    assert [scope['id'] for scope in json.loads(requests[0].content)['scopes']] == identifiers
    assert clients[0].is_closed


@pytest.mark.parametrize('as_json', [False, True])
@pytest.mark.parametrize('category', [*CATEGORIES, 'future-event'])
def test_event_detail_category_metadata_and_scoped_timeline(api, capsys, as_json, category):
    state, clients, requests = api
    subtypes = {
        'patch': 'patch_release_started',
        'incident': 'incident_update',
        'maintenance': 'maintenance_update',
        'informationalMessage': 'im_update_added',
    }
    entry = {**TIMELINE, 'subEventType': subtypes.get(category, 'future-subtype')}
    if category == 'patch':
        entry['contents'] = [{'relatedItem': 'synthetic-change', 'description': 'Supplied patch note', 'future': None}]
    payload = {
        **DETAIL,
        'eventType': category,
        'data': DATA[category],
        'timeline': [entry, {**entry, 'scope': {'tenants': {'realm:other': {}}}}],
        'futureMetadata': None,
    }
    state['response'] = httpx.Response(200, json=payload)
    output = invoke(capsys, ['events', 'get', 'realm:雪 1', '--locale', 'en-US', *(['--json'] if as_json else [])])
    if as_json:
        assert output == EventDetail.model_validate(payload).model_dump_json(by_alias=True, exclude_unset=True) + '\n'
        assert json.loads(output) == payload and 'startTime' not in json.loads(output)
    else:
        assert 'Event metadata:\n' in output and 'Timeline (as supplied):\n' in output
        assert 'title: null' in output and 'futureMetadata: null' in output
        assert output.count('Sub-event: shared-stage') == 2
        assert 'Affected tenant IDs: ["realm:one"]' in output and 'Affected tenant IDs: ["realm:other"]' in output
        assert '+05:30' in output and '-03:30' in output and 'message: null' in output
    assert requests[0].url.path.endswith('/events/realm:雪 1')
    assert dict(requests[0].url.params) == {'locale': 'en-US'}
    assert requests[0].method == 'GET' and len(requests) == 1 and clients[0].is_closed


@pytest.mark.parametrize('supplied', [False, True])
def test_detail_omitted_and_empty_timeline_are_distinct(api, capsys, supplied):
    state, clients, _ = api
    payload = {**DETAIL, **({'timeline': []} if supplied else {})}
    state['response'] = httpx.Response(200, json=payload)
    text = invoke(capsys, ['events', 'get', 'synthetic'])
    assert ('Timeline: omitted from response.' in text) == (not supplied)
    assert ('No timeline entries supplied in this authorized scope' in text) == supplied
    output = json.loads(invoke(capsys, ['events', 'get', 'synthetic', '--json']))
    assert output == payload and all(client.is_closed for client in clients)


@pytest.mark.parametrize('operation', ['status', 'search', 'detail'])
def test_future_response_types_and_terminal_controls(api, capsys, operation):
    state, clients, _ = api
    unsafe = 'unsafe\x1b[31m\n\r\t\x7f\x85\u202e\u2028'
    event = {
        **EVENT,
        'eventId': unsafe,
        'eventType': 'future-type',
        'status': unsafe,
        'title': unsafe,
        'scope': {'tenants': {unsafe: {}}},
    }
    if operation == 'status':
        arguments, payload = ['status', 'snapshot'], {**SNAPSHOT, 'ongoing': {**EMPTY, 'patch': [event]}}
    elif operation == 'search':
        arguments, payload = SEARCH, {'events': [event, event], 'nextPageToken': unsafe}
    else:
        entry = {
            **TIMELINE,
            'subEventId': unsafe,
            'subEventType': 'future-subtype',
            unsafe: unsafe,
            'message': unsafe,
            'scope': {'tenants': {unsafe: {}}},
        }
        arguments = ['events', 'get', 'synthetic']
        payload = {**DETAIL, 'eventType': 'future-type', unsafe: unsafe, 'description': unsafe, 'timeline': [entry]}
    state['response'] = httpx.Response(200, json=payload)
    text = invoke(capsys, arguments)
    assert all(char not in text for char in ('\x1b', '\r', '\t', '\x7f', '\x85', '\u202e', '\u2028'))
    assert '\\x1b' in text
    assert json.loads(invoke(capsys, [*arguments, '--json'])) == payload
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(('arguments', 'payload'), OPERATIONS)
@pytest.mark.parametrize('selector', ['default', 'path', 'alias'])
def test_each_operation_store_selection_ignores_environment(api, monkeypatch, tmp_path, capsys, arguments, payload, selector):
    state, clients, requests = api
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    kwargs = (
        {'path': tmp_path / 'private' / 'pat.sqlite3'}
        if selector == 'path'
        else {'alias': 'monitoring'}
        if selector == 'alias'
        else {}
    )
    SQLitePATStore.initialize(pat='synthetic-event-store', **kwargs)
    original = os.environ.__class__.__getitem__

    def getitem(self, key):
        assert key != 'SFDCTRUST_PAT'
        return original(self, key)

    monkeypatch.setattr(os.environ.__class__, '__getitem__', getitem)
    options = (
        ['--store-path', str(kwargs['path'])]
        if selector == 'path'
        else ['--store-alias', 'monitoring']
        if selector == 'alias'
        else ['--store']
    )
    state['response'] = httpx.Response(200, json=payload)
    invoke(capsys, [*arguments, *options])
    assert len(requests) == 1 and clients[0].is_closed
    assert requests[0].headers['Authorization'] == 'Bearer synthetic-event-store'


@pytest.mark.parametrize(('arguments', 'payload'), OPERATIONS)
def test_missing_credential_and_missing_store_never_fallback(api, monkeypatch, tmp_path, capsys, arguments, payload):
    _, clients, requests = api
    monkeypatch.delenv('SFDCTRUST_PAT')
    invoke(capsys, arguments, 3)
    monkeypatch.setenv('SFDCTRUST_PAT', PAT)
    path = tmp_path / 'missing' / 'pat.sqlite3'
    invoke(capsys, [*arguments, '--store-path', str(path)], 3)
    assert not path.parent.exists() and not clients and not requests


@pytest.mark.parametrize(('arguments', 'payload'), OPERATIONS)
@pytest.mark.parametrize(
    ('response', 'code', 'attempts'),
    [
        (httpx.Response(400, text=PRIVATE), 4, 1),
        (httpx.Response(401, text=PRIVATE), 3, 1),
        (httpx.Response(403, text=PRIVATE), 4, 1),
        (httpx.Response(404, text=PRIVATE), 4, 1),
        (httpx.Response(429, headers={'Retry-After': '0'}, text=PRIVATE), 4, 3),
        (httpx.Response(500, text=PRIVATE), 4, 3),
        (httpx.Response(502, text=PRIVATE), 4, 3),
        (httpx.Response(503, text=PRIVATE), 4, 3),
        (httpx.Response(504, text=PRIVATE), 4, 3),
        (httpx.Response(302, headers={'Location': 'https://example.invalid/' + PAT}), 4, 1),
        (httpx.Response(200, text=PRIVATE), 4, 1),
        (httpx.Response(200, json={}), 4, 1),
        (httpx.ConnectError(PRIVATE), 4, 3),
        (httpx.ReadTimeout(PRIVATE), 4, 3),
        (httpx.ConnectTimeout(PRIVATE), 4, 3),
        (httpx.WriteTimeout(PRIVATE), 4, 3),
        (httpx.PoolTimeout(PRIVATE), 4, 3),
        (httpx.ReadError(PRIVATE), 4, 1),
        (RuntimeError(PRIVATE), 1, 1),
        (KeyboardInterrupt(PRIVATE), 130, 1),
    ],
)
def test_failures_fixed_diagnostics_retries_no_refresh_and_cleanup(api, capsys, arguments, payload, response, code, attempts):
    state, clients, requests = api
    state['response'] = response
    options = ['--page-token', 'stale'] if arguments[0:2] == ['events', 'search'] else []
    invoke(capsys, [*arguments, *options, '--json'], code)
    assert clients[0].is_closed and len(requests) == attempts
    assert all('/pats/' not in request.url.path for request in requests)
    assert all(request.url == requests[0].url and request.content == requests[0].content for request in requests)
    if options:
        assert json.loads(requests[0].content)['pageToken'] == 'stale'


@pytest.mark.parametrize(
    ('arguments', 'payload'),
    [
        (['status', 'snapshot'], {'ongoing': EMPTY}),
        (['status', 'snapshot'], {**SNAPSHOT, 'ongoing': {**EMPTY, 'patch': [{**EVENT, 'scope': None}]}}),
        (SEARCH, {'events': [{**EVENT, 'createdAt': 'invalid'}]}),
        (SEARCH, {'events': [], 'nextPageToken': None}),
        (SEARCH, {'events': [EVENT] * 201}),
        (['events', 'get', 'synthetic'], {**DETAIL, 'timeline': None}),
        (['events', 'get', 'synthetic'], {**DETAIL, 'timeline': [{**TIMELINE, 'subEventType': 'incident_update'}]}),
        (['events', 'get', 'synthetic'], {**DETAIL, 'data': {}}),
    ],
)
def test_malformed_known_models_are_request_failures(api, capsys, arguments, payload):
    state, clients, requests = api
    state['response'] = httpx.Response(200, json=payload)
    invoke(capsys, arguments, 4)
    assert len(requests) == 1 and clients[0].is_closed


@pytest.mark.parametrize(('arguments', 'payload'), OPERATIONS)
@pytest.mark.parametrize('stage', ['render', 'write', 'flush', 'close'])
@pytest.mark.parametrize('interrupted', [False, True])
def test_render_output_close_and_interruption_boundaries(api, monkeypatch, capsys, arguments, payload, stage, interrupted):
    state, clients, _ = api
    state['response'] = httpx.Response(200, json=payload)

    def fail(*args, **kwargs):
        raise KeyboardInterrupt(PRIVATE) if interrupted else OSError(PRIVATE)

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
        _cli.main(arguments)
    assert caught.value.code == (130 if interrupted else 1)
    monkeypatch.undo()
    output = capsys.readouterr()
    assert output.err == ('sfdctrust: interrupted.\n' if interrupted else 'sfdctrust: internal or output failure.\n')
    if stage != 'flush':
        assert not output.out
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(('arguments', 'payload'), OPERATIONS)
def test_json_serialization_is_rendered_before_any_write(api, monkeypatch, capsys, arguments, payload):
    state, clients, _ = api
    state['response'] = httpx.Response(200, json=payload)

    def fail(*args, **kwargs):
        raise ValueError(PRIVATE)

    model = StatusSnapshot if arguments[0] == 'status' else EventSearchResponse if arguments[1] == 'search' else EventDetail
    monkeypatch.setattr(model, 'model_dump_json', fail)
    invoke(capsys, [*arguments, '--json'], 1)
    assert clients[0].is_closed
