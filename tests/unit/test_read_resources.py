# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_read_resources
:Synopsis:          Offline public-client tests for status, events, and tenant detail
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo

import httpx
import pytest

from sfdctrust import (
    APIStatusError,
    ConfigurationError,
    MalformedResponseError,
    NotFoundError,
    PaginationError,
    TrustCenterClient,
)
from sfdctrust.models.events import (
    EventDetail,
    EventSearchResponse,
    EventSearchResult,
    EventSearchScope,
    IncidentEventData,
    IncidentTimelineItem,
    InformationalMessageEventData,
    InformationalMessageTimelineItem,
    MaintenanceEventData,
    MaintenanceTimelineItem,
    PatchEventData,
    PatchTimelineItem,
)
from sfdctrust.models.status import StatusSnapshot
from sfdctrust.models.tenants import TenantDetail

_PAT = 'synthetic-read-pat'
_BASE = 'https://api.salesforce.com/platform/mytrust/v1'
_TIME = '2026-09-01T00:00:00.123456+05:45'
_START = datetime.fromisoformat(_TIME)
_END = datetime(2026, 9, 2, tzinfo=UTC)
_TOKEN = 'private-cursor /+=?雪'
_TENANT = {'id': 'realm:雪 1', 'cloud': 'future-cloud', 'name': 'Synthetic tenant'}
_EVENT = {
    'eventId': 'evt.雪 1',
    'eventType': 'incident',
    'status': 'active',
    'products': [],
    'services': [],
    'createdAt': _TIME,
}
_SCOPE = {'tenants': {_TENANT['id']: {'futureScopeField': 1}}}
_ITEM = {'subEventId': 'entry', 'scope': _SCOPE, 'createdAt': _TIME}
_BUCKETS = {'patch': [], 'incident': [], 'maintenance': [], 'informationalMessage': []}
_SEARCH = {'scopes': [EventSearchScope(id=_TENANT['id'])], 'start_time': _START, 'end_time': _END}
_INCIDENT_DATA = {'additionalInformation': None, 'rcaLink': None, 'rcaCreatedAt': None}
_PATCH_DATA = {
    'releaseId': 'release',
    'releaseName': 'Patch',
    'releaseVersion': '1',
    'plannedStartTime': _TIME,
    'plannedEndTime': None,
}


@pytest.fixture
def api() -> Iterator[tuple[TrustCenterClient, list[httpx.Request], list[httpx.Response]]]:
    requests = []
    responses = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers['Authorization'] == f'Bearer {_PAT}'
        assert request.url.scheme == 'https'
        assert request.url.host == 'api.salesforce.com'
        assert not request.url.fragment
        requests.append(request)
        return responses.pop(0)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http_client,
        TrustCenterClient(_PAT, http_client=http_client) as client,
    ):
        yield client, requests, responses


def _safe_error(error: Exception) -> None:
    assert error.__context__ is error.__cause__ is None
    displayed = ''.join(traceback.format_exception(error))
    for private in (_PAT, _BASE, _TOKEN, 'private-payload', 'ValidationError'):
        assert private not in displayed


def test_snapshot_preserves_buckets_order_scope_and_duplicates(api) -> None:
    client, requests, responses = api
    first = {**_EVENT, 'eventType': 'patch', 'scope': _SCOPE}
    second = {**first, 'status': 'confirmed', 'scope': {'tenants': {'another': {}}}}
    payload = {'ongoing': {**_BUCKETS, 'patch': [first, second]}, 'upcoming': {**_BUCKETS, 'patch': [second]}}
    responses.append(httpx.Response(200, json=payload))

    snapshot = client.status.snapshot(locale='not a supported locale')

    assert isinstance(snapshot, StatusSnapshot)
    assert [(entry.event_id, entry.status) for entry in snapshot.ongoing.patch] == [
        (_EVENT['eventId'], 'active'),
        (_EVENT['eventId'], 'confirmed'),
    ]
    assert snapshot.ongoing.patch[0].scope.tenants == _SCOPE['tenants']
    assert snapshot.upcoming.patch[0].scope.tenants == {'another': {}}
    assert snapshot.ongoing.informational_message == []
    assert snapshot.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload
    (request,) = requests
    assert request.method == 'GET'
    assert str(request.url.copy_with(query=None)) == f'{_BASE}/status'
    assert dict(request.url.params) == {'locale': 'not a supported locale'}
    assert request.content == b''


def test_search_caller_driven_pages_and_retry(api, monkeypatch: pytest.MonkeyPatch) -> None:
    client, requests, responses = api
    delays = []
    monkeypatch.setattr('sfdctrust._transport.time.sleep', delays.append)
    result = {**_EVENT, 'scope': _SCOPE, 'duration': 'PT4H', 'displayDuration': '4 hours'}
    second = {**result, 'scope': {'tenants': {'second': {}}}, 'status': 'resolved', 'duration': 'PT1H'}
    responses.extend(
        [
            httpx.Response(503),
            httpx.Response(200, json={'events': [result, second], 'nextPageToken': _TOKEN}),
            httpx.Response(200, json={'events': []}),
            httpx.Response(400, json={'message': 'private-payload'}),
        ]
    )
    scopes = [EventSearchScope(id=_TENANT['id'])] * 49 + [EventSearchScope(id='second')]
    filters = ['incident', 'maintenance']
    options = {**_SEARCH, 'scopes': scopes, 'event_types': filters, 'locale': 'ja-JP', 'page_size': 200}

    page = client.events.search(**options)
    assert isinstance(page, EventSearchResponse)
    assert len(delays) == 1
    assert len(requests) == 2
    assert page.next_page_token == _TOKEN
    assert isinstance(page.events[0], EventSearchResult)
    assert [event.event_id for event in page.events] == [_EVENT['eventId']] * 2
    assert [event.duration for event in page.events] == ['PT4H', 'PT1H']
    assert [event.scope.tenants for event in page.events] == [_SCOPE['tenants'], {'second': {}}]
    assert page.events[0].display_duration == '4 hours'
    assert page.events[0].created_at.utcoffset() == timedelta(hours=5, minutes=45)
    final = client.events.search(**options, page_token=page.next_page_token)
    assert final.events == []
    assert final.model_fields_set == {'events'}
    with pytest.raises(APIStatusError) as exc:
        client.events.search(**options, page_token=_TOKEN)
    assert exc.value.status_code == 400
    _safe_error(exc.value)
    assert len(requests) == 4
    assert scopes == [EventSearchScope(id=_TENANT['id'])] * 49 + [EventSearchScope(id='second')]
    assert filters == ['incident', 'maintenance']
    body = {
        'scopes': [{'type': 'tenant', 'id': scope.id} for scope in scopes],
        'startTime': _TIME,
        'endTime': '2026-09-02T00:00:00+00:00',
        'eventTypes': filters,
        'pageSize': 200,
    }
    for index, request in enumerate(requests):
        assert request.method == 'POST'
        assert str(request.url) == f'{_BASE}/events/search?locale=ja-JP'
        assert request.headers['Content-Type'] == 'application/json'
        assert json.loads(request.content) == (body if index < 2 else {**body, 'pageToken': _TOKEN})


def test_search_defaults_and_minimal_bounds(api) -> None:
    client, requests, responses = api
    responses.extend([httpx.Response(200, json={'events': []}) for _ in range(3)])
    for options in ({}, {'page_size': 1, 'page_token': ''}, {'page_token': 'x' * 4096}):
        assert client.events.search(**_SEARCH, **options).events == []
    first, second, third = (json.loads(request.content) for request in requests)
    assert first == {'scopes': [{'id': _TENANT['id'], 'type': 'tenant'}], 'startTime': _TIME, 'endTime': _END.isoformat()}
    assert second == {**first, 'pageSize': 1, 'pageToken': ''}
    assert third == {**first, 'pageToken': 'x' * 4096}
    assert all(not request.url.query for request in requests)


@pytest.mark.parametrize(
    ('argument', 'value'),
    [
        ('scopes', []),
        ('scopes', _SEARCH['scopes'] * 51),
        ('scopes', [{'type': 'tenant', 'id': 'id'}]),
        ('scopes', [EventSearchScope.model_construct(id='')]),
        ('scopes', [EventSearchScope.model_construct(id='id', type='org')]),
        ('scopes', [EventSearchScope.model_construct(id='\ud800')]),
        ('start_time', '2026-09-01T00:00:00Z'),
        ('start_time', datetime(2026, 9, 1)),
        ('start_time', _END),
        ('start_time', _END + timedelta(days=1)),
        ('end_time', datetime(2026, 9, 1, tzinfo=timezone(timedelta(seconds=10)))),
        ('end_time', _START.astimezone(UTC)),
        ('event_types', []),
        ('event_types', ['future-type']),
        ('event_types', ['incident'] * 2),
        ('event_types', 'incident'),
        ('event_types', [{}]),
        ('page_size', 0),
        ('page_size', 201),
        ('page_size', True),
        ('page_size', 1.0),
        ('page_size', '1'),
        ('page_token', 1),
        ('page_token', 'x' * 4097),
        ('page_token', '\ud800'),
        ('locale', 1),
        ('locale', '\ud800'),
    ],
)
def test_search_rejects_invalid_input_before_io(api, argument: str, value: object) -> None:
    client, requests, _ = api
    with pytest.raises(ConfigurationError) as exc:
        client.events.search(**{**_SEARCH, argument: value})
    assert not requests
    _safe_error(exc.value)


def test_search_orders_instants_across_shared_timezone_fold(api) -> None:
    class FoldZone(tzinfo):
        def utcoffset(self, dt: datetime | None) -> timedelta:
            return timedelta(hours=-7 if dt is not None and dt.fold else -6)

    client, requests, responses = api
    responses.append(httpx.Response(200, json={'events': []}))
    zone = FoldZone()
    client.events.search(
        scopes=_SEARCH['scopes'],
        start_time=datetime(2026, 11, 1, 1, 45, tzinfo=zone),
        end_time=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1),
    )
    body = json.loads(requests[0].content)
    assert body['startTime'] == '2026-11-01T01:45:00-06:00'
    assert body['endTime'] == '2026-11-01T01:15:00-07:00'


@pytest.mark.parametrize(
    ('kind', 'data', 'data_class', 'entry', 'entry_class'),
    [
        (
            'patch',
            _PATCH_DATA,
            PatchEventData,
            {'subEventType': 'patch_release_notes', 'publicationDate': _TIME, 'contents': [{'relatedItem': 'note'}, {}]},
            PatchTimelineItem,
        ),
        ('incident', _INCIDENT_DATA, IncidentEventData, {'subEventType': 'incident_update'}, IncidentTimelineItem),
        (
            'maintenance',
            {'plannedStartTime': _TIME, 'plannedEndTime': None, 'additionalInformation': None},
            MaintenanceEventData,
            {'subEventType': 'maintenance_started', 'plannedStartTime': _TIME},
            MaintenanceTimelineItem,
        ),
        (
            'informationalMessage',
            {'informationalMessageType': 'future-category'},
            InformationalMessageEventData,
            {'subEventType': 'im_update_added'},
            InformationalMessageTimelineItem,
        ),
    ],
)
def test_event_detail_typed_variants_and_wire_aliases(api, kind, data, data_class, entry, entry_class) -> None:
    client, requests, responses = api
    payload = {
        **_EVENT,
        'eventType': kind,
        'status': 'future-status',
        'endTime': None,
        'data': {**data, 'futureData': True},
        'timeline': [{**_ITEM, **entry, 'updatedAt': None}, {**_ITEM, 'subEventType': 'future-item', 'futureItem': 42}],
        'futureEvent': [1],
    }
    responses.append(httpx.Response(200, json=payload))
    event = client.events.get(_EVENT['eventId'], locale='ja-JP')
    assert isinstance(event, EventDetail)
    assert isinstance(event.data, data_class)
    assert isinstance(event.timeline[0], entry_class)
    assert event.timeline[0].sub_event_id == _ITEM['subEventId']
    assert event.timeline[1].sub_event_type == 'future-item'
    assert event.timeline[1].model_extra == {'futureItem': 42}
    assert event.end_time is event.start_time is None
    assert 'end_time' in event.model_fields_set and 'start_time' not in event.model_fields_set
    assert event.created_at.isoformat() == _TIME
    assert event.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload
    (request,) = requests
    assert request.method == 'GET'
    assert str(request.url) == f'{_BASE}/events/evt.%E9%9B%AA%201?locale=ja-JP'
    assert request.content == b''


def test_unknown_event_type_and_missing_timeline(api) -> None:
    client, _, responses = api
    payload = {**_EVENT, 'eventType': 'future-event', 'data': {'freeForm': [None]}}
    responses.append(httpx.Response(200, json=payload))
    event = client.events.get('id')
    assert event.event_type == 'future-event'
    assert event.data == {'freeForm': [None]}
    assert event.timeline is None and 'timeline' not in event.model_fields_set
    assert event.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload


def test_tenant_detail_embeds_history_and_location(api) -> None:
    client, requests, responses = api
    patch = {**_EVENT, 'eventType': 'patch', 'scope': _SCOPE}
    location = {'city': '', 'stateName': '', 'stateCode': '', 'countryName': 'Example', 'countryCode': 'EX'}
    payload = {**_TENANT, 'maintenanceWindow': None, 'location': location, 'events': [patch, {**patch, 'status': 'confirmed'}]}
    responses.append(httpx.Response(200, json=payload))
    tenant = client.tenants.get(_TENANT['id'], locale='en-US')
    assert isinstance(tenant, TenantDetail)
    assert tenant.location.country_code == 'EX'
    assert [event.event_id for event in tenant.events] == [_EVENT['eventId']] * 2
    assert [event.status for event in tenant.events] == ['active', 'confirmed']
    assert tenant.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload
    (request,) = requests
    assert request.method == 'GET'
    assert str(request.url) == f'{_BASE}/tenants/realm%3A%E9%9B%AA%201?locale=en-US'
    assert request.content == b''


@pytest.mark.parametrize('resource', ['tenants', 'events'])
@pytest.mark.parametrize(
    'identifier',
    [
        '',
        None,
        12,
        '.',
        '..',
        '../status',
        '//example.invalid',
        'a\\b',
        'a?x',
        'a#x',
        'a;x',
        'a%2fb',
        '%252e%252e',
        'a\n',
        'a\x7f',
        '\ud800',
    ],
)
def test_detail_id_safety(api, resource: str, identifier: object) -> None:
    client, requests, _ = api
    with pytest.raises(ConfigurationError) as exc:
        getattr(client, resource).get(identifier)
    assert not requests
    _safe_error(exc.value)


@pytest.mark.parametrize('resource', ['tenants', 'events'])
def test_detail_404_keeps_ambiguous_translation(api, resource: str) -> None:
    client, requests, responses = api
    responses.append(httpx.Response(404, json={'message': 'private-payload'}))
    with pytest.raises(NotFoundError) as exc:
        getattr(client, resource).get('safe-id')
    assert exc.value.status_code == 404
    assert len(requests) == 1
    assert not requests[0].url.query
    _safe_error(exc.value)


@pytest.mark.parametrize(
    ('operation', 'payload'),
    [
        ('snapshot', {'ongoing': _BUCKETS}),
        ('snapshot', {'ongoing': {'patch': [], 'incident': [], 'maintenance': []}, 'upcoming': _BUCKETS}),
        ('snapshot', {'ongoing': {**_BUCKETS, 'incident': [_EVENT]}, 'upcoming': _BUCKETS}),
        ('search', {'events': [], 'nextPageToken': None}),
        ('search', {'events': [{**_EVENT, 'scope': _SCOPE}] * 201}),
        ('search', {'events': [{**_EVENT, 'scope': {'tenants': {'id': None}}}]}),
        ('search', {'events': [{**_EVENT, 'scope': _SCOPE, 'timeline': []}]}),
        ('tenant', {**_TENANT, 'events': [], 'location': None}),
        ('tenant', {**_TENANT, 'events': [], 'location': {'countryCode': 'EX'}}),
        ('tenant', {**_TENANT, 'events': [], 'myDomain': None}),
        ('tenant', _TENANT),
        ('event', {**_EVENT, 'scope': _SCOPE}),
        ('event', {**_EVENT, 'timeline': None}),
        ('event', {**_EVENT, 'data': None}),
        ('event', {**_EVENT, 'eventType': 'patch', 'data': _INCIDENT_DATA}),
        ('event', {**_EVENT, 'data': {'additionalInformation': None, 'rcaLink': None}}),
        ('event', {**_EVENT, 'data': {**_INCIDENT_DATA, 'rcaCreatedAt': 123}}),
        ('event', {**_EVENT, 'timeline': [{**_ITEM, 'subEventType': 'future', 'updatedAt': 'private-payload'}]}),
        ('event', {**_EVENT, 'timeline': [{**_ITEM, 'subEventType': 'maintenance_update'}]}),
        (
            'event',
            {**_EVENT, 'eventType': 'patch', 'timeline': [{**_ITEM, 'subEventType': 'patch_release_notes', 'contents': None}]},
        ),
        (
            'event',
            {
                **_EVENT,
                'eventType': 'patch',
                'timeline': [{**_ITEM, 'subEventType': 'patch_release_notes', 'contents': [{'relatedItem': None}]}],
            },
        ),
        ('event', {**_EVENT, 'eventType': False}),
        ('event', {**_EVENT, 'products': [1]}),
        *[
            ('event', {**_EVENT, 'createdAt': value})
            for value in (
                None,
                1,
                '2026-09-01',
                '2026-09-01T00:00:00',
                '2026-09-01 00:00:00Z',
                '2026-09-01T00:00:00+02:60',
                '2026-02-30T00:00:00Z',
                'private-payload',
            )
        ],
    ],
)
def test_nested_response_validation_is_sanitized(api, operation: str, payload: dict) -> None:
    client, requests, responses = api
    responses.append(httpx.Response(200, json=payload))
    calls = {
        'snapshot': client.status.snapshot,
        'search': lambda: client.events.search(**_SEARCH),
        'event': lambda: client.events.get('id'),
        'tenant': lambda: client.tenants.get('id'),
    }
    with pytest.raises(MalformedResponseError) as exc:
        calls[operation]()
    assert len(requests) == 1
    _safe_error(exc.value)


@pytest.mark.parametrize('resource', ['tenants', 'events'])
def test_lazy_traversal_snapshots_inputs_and_preserves_order(api, resource: str, monkeypatch: pytest.MonkeyPatch) -> None:
    client, requests, responses = api
    monkeypatch.setattr('sfdctrust._transport.time.sleep', lambda _: None)
    scopes = [EventSearchScope(id='original')]
    types = ['incident']
    if resource == 'events':
        iterator = client.events.iter_search(
            **{**_SEARCH, 'scopes': scopes}, event_types=types, page_size=2, page_token=_TOKEN, locale='ja-JP', max_pages=3
        )
        first = {**_EVENT, 'scope': _SCOPE}
        second = {**first, 'status': 'resolved', 'scope': {'tenants': {'another': {}}}}
    else:
        iterator = client.tenants.iter_all(page_size=2, page_token=_TOKEN, locale='ja-JP', max_pages=3)
        first, second = _TENANT, {**_TENANT, 'name': 'Second'}
    scopes.clear()
    types[:] = ['patch']
    responses.extend(
        [
            httpx.Response(200, json={resource: [first, second], 'nextPageToken': ''}),
            httpx.Response(503, headers={'Retry-After': '0'}),
            httpx.Response(200, json={resource: [], 'nextPageToken': 'final'}),
            httpx.Response(200, json={resource: [first]}),
        ]
    )

    assert not requests
    actual = [next(iterator), next(iterator)]
    assert len(requests) == 1
    actual.extend(iterator)
    assert [item.model_dump(mode='json', by_alias=True, exclude_unset=True) for item in actual] == [first, second, first]
    assert len(requests) == 4
    assert requests[1].url == requests[2].url
    assert requests[1].content == requests[2].content
    for request, token in zip(requests, [_TOKEN, '', '', 'final'], strict=True):
        if resource == 'events':
            assert dict(request.url.params) == {'locale': 'ja-JP'}
            assert json.loads(request.content) == {
                'scopes': [{'type': 'tenant', 'id': 'original'}],
                'eventTypes': ['incident'],
                'startTime': _START.isoformat(),
                'endTime': _END.isoformat(),
                'pageToken': token,
                'pageSize': 2,
            }
        else:
            assert dict(request.url.params) == {'pageSize': '2', 'pageToken': token, 'locale': 'ja-JP'}


@pytest.mark.parametrize('resource', ['tenants', 'events'])
def test_early_exit_leaves_next_page_unrequested(api, resource: str) -> None:
    client, requests, responses = api
    if resource == 'events':
        iterator = client.events.iter_search(**_SEARCH, page_token='')
        item = {**_EVENT, 'scope': _SCOPE}
    else:
        iterator = client.tenants.iter_all(page_token='')
        item = _TENANT
    responses.append(httpx.Response(200, json={resource: [item], 'nextPageToken': _TOKEN}))
    assert next(iterator)
    (request,) = requests
    params = json.loads(request.content) if resource == 'events' else dict(request.url.params)
    assert params['pageToken'] == ''
    assert 'pageSize' not in params
    assert 'locale' not in request.url.params


@pytest.mark.parametrize('resource', ['tenants', 'events'])
@pytest.mark.parametrize(
    ('start', 'tokens', 'limit', 'error', 'message'),
    [
        (None, [None], 1, None, None),
        (None, [_TOKEN], 1, PaginationError, 'exceeded max_pages'),
        (_TOKEN, [_TOKEN], 2, PaginationError, 'repeated a cursor'),
        (None, [_TOKEN, 'other', _TOKEN], 4, PaginationError, 'repeated a cursor'),
        (None, [_TOKEN, 400], 3, APIStatusError, 'HTTP 400'),
    ],
)
def test_collectors_surface_pagination_failures(api, resource, start, tokens, limit, error, message) -> None:
    client, requests, responses = api
    for token in tokens:
        if token == 400:
            responses.append(httpx.Response(400, text='private-payload'))
        else:
            payload = {resource: []}
            if token is not None:
                payload['nextPageToken'] = token
            responses.append(httpx.Response(200, json=payload))
    collect, args = (client.events.search_all, _SEARCH) if resource == 'events' else (client.tenants.list_all, {})
    if error is None:
        assert collect(**args, page_token=start, max_pages=limit) == []
    else:
        with pytest.raises(error, match=message) as exc:
            collect(**args, page_token=start, max_pages=limit)
        _safe_error(exc.value)
        if error is APIStatusError:
            assert exc.value.status_code == 400
    assert len(requests) == len(tokens)
    for request, token in zip(requests, [start, *tokens[:-1]], strict=True):
        params = json.loads(request.content) if resource == 'events' else request.url.params
        assert params.get('pageToken') == token
        assert 'pageSize' not in params


@pytest.mark.parametrize('limit', [False, True, 0, -1, 1.0, '1', None])
def test_pagination_rejects_invalid_limits_before_io(api, limit) -> None:
    client, requests, _ = api
    for iterator in (client.tenants.iter_all(max_pages=limit), client.events.iter_search(**_SEARCH, max_pages=limit)):
        with pytest.raises(ConfigurationError, match='max_pages must be a positive integer'):
            next(iterator)
    assert not requests


def test_iterator_yields_current_page_before_reporting_limit(api) -> None:
    client, requests, responses = api
    responses.append(httpx.Response(200, json={'tenants': [_TENANT], 'nextPageToken': _TOKEN}))
    iterator = client.tenants.iter_all(max_pages=1)
    assert next(iterator).id == _TENANT['id']
    with pytest.raises(PaginationError) as exc:
        next(iterator)
    _safe_error(exc.value)
    assert len(requests) == 1
