# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_live_read_smoke
:Synopsis:          Offline qualification of the live read-only smoke procedure
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     09 Nov 2026
"""

from __future__ import annotations

import asyncio
import json
import warnings
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import httpx
import pytest

import sfdctrust
from sfdctrust import AsyncTrustCenterClient, TrustCenterClient

_SCRIPT = Path(__file__).resolve().parents[1] / 'live_read_smoke.py'
_PAT = 'synthetic-qualification-pat'
_TENANT = {'id': 'synthetic-private-tenant', 'cloud': 'Core', 'name': 'synthetic-private-name'}
_OTHER_TENANT = {**_TENANT, 'id': 'synthetic-other-tenant'}
_EVENT = {
    'eventId': 'synthetic-private-event',
    'eventType': 'incident',
    'status': 'active',
    'products': [],
    'services': [],
    'createdAt': '2026-11-01T00:00:00Z',
}
_SCOPE = {'tenants': {_TENANT['id']: {}}}
_SUMMARY = {**_EVENT, 'scope': _SCOPE}
_BUCKET = {'patch': [], 'incident': [], 'maintenance': [], 'informationalMessage': []}
_TENANT_CURSOR = 'synthetic-tenant-cursor'
_EVENT_CURSOR = 'synthetic-event-cursor'


@pytest.fixture
def smoke():
    spec = spec_from_file_location('live_read_smoke', _SCRIPT)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('scenario', ['full', 'no-tenants', 'no-events', 'snapshot-fallback', 'errors'])
def test_read_only_smoke(smoke, scenario, monkeypatch, capsys):
    requests: dict[str, list[tuple[str, dict]]] = {'sync': [], 'async': []}

    def handler(name, request):
        assert request.url.host == 'api.salesforce.com'
        assert request.headers['Authorization'] == f'Bearer {_PAT}'
        query = dict(request.url.params)
        assert query.pop('locale') == 'en-US'
        path = request.url.path.removeprefix('/platform/mytrust/v1')
        body = json.loads(request.content) if request.content else {}
        assert request.method == ('POST' if path == '/events/search' else 'GET')
        requests[name].append((path, body if path == '/events/search' else query))

        if path == '/tenants':
            assert query.pop('pageSize') == '1'
            if query:
                assert query == {'pageToken': _TENANT_CURSOR}
                if scenario == 'errors':
                    return httpx.Response(400, text=f'{_PAT} {_TENANT_CURSOR} synthetic-raw-response')
                return httpx.Response(200, json={'tenants': [_OTHER_TENANT]})
            tenants = [] if scenario == 'no-tenants' else [_TENANT]
            result = {'tenants': tenants}
            if scenario in ('full', 'errors'):
                result['nextPageToken'] = _TENANT_CURSOR
            return httpx.Response(200, json=result)

        if path == f'/tenants/{_TENANT["id"]}':
            return httpx.Response(200, json={**_TENANT, 'events': [_SUMMARY] if scenario == 'full' else []})

        if path == '/status':
            if scenario == 'errors':
                raise RuntimeError(f'{request.url} {_PAT} synthetic-raw-response')
            ongoing = {**_BUCKET, 'incident': [_SUMMARY, _SUMMARY]} if scenario == 'snapshot-fallback' else _BUCKET
            return httpx.Response(200, json={'ongoing': ongoing, 'upcoming': _BUCKET})

        if path == '/events/search':
            assert body['pageSize'] == 1
            if scenario == 'full':
                assert body['scopes'] == [{'type': 'tenant', 'id': tenant['id']} for tenant in (_TENANT, _OTHER_TENANT)]
                if 'pageToken' in body:
                    return httpx.Response(200, json={'events': [_SUMMARY]})
                return httpx.Response(200, json={'events': [_SUMMARY], 'nextPageToken': _EVENT_CURSOR})
            if scenario == 'errors':
                return httpx.Response(200, json={'events': [_EVENT], 'extra': 'synthetic-raw-response'})
            return httpx.Response(200, json={'events': []})

        assert path == f'/events/{_EVENT["eventId"]}'
        timeline = {
            'subEventId': 'synthetic-private-timeline',
            'subEventType': 'incident_started',
            'scope': _SCOPE,
            'createdAt': _EVENT['createdAt'],
        }
        payload = {**_EVENT, 'timeline': [timeline]} if scenario == 'full' else _EVENT
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(lambda request: handler('sync', request))) as http:

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: handler('async', request))) as async_http:
                monkeypatch.setattr(smoke, 'TrustCenterClient', lambda **options: TrustCenterClient(**options, http_client=http))
                monkeypatch.setattr(
                    smoke, 'AsyncTrustCenterClient', lambda **options: AsyncTrustCenterClient(**options, http_client=async_http)
                )
                return await smoke._run(_PAT)

        assert asyncio.run(run()) == (1 if scenario == 'errors' else 0)

    assert requests['sync'] == requests['async']
    paths = [path for path, _ in requests['sync']]
    out, err = capsys.readouterr()
    assert not err
    assert 'synthetic-' not in out
    assert 'https://' not in out
    assert 'Traceback' not in out
    if scenario == 'full':
        assert paths == [
            '/tenants',
            '/tenants',
            f'/tenants/{_TENANT["id"]}',
            '/status',
            '/events/search',
            '/events/search',
            f'/events/{_EVENT["eventId"]}',
        ]
        first, second = [body for path, body in requests['sync'] if path == '/events/search']
        assert second == {**first, 'pageToken': _EVENT_CURSOR}
        assert 'SUMMARY pass=18 fail=0 skip=0' in out
    elif scenario == 'no-tenants':
        assert paths == ['/tenants', '/status']
        assert 'SUMMARY pass=4 fail=0 skip=14' in out
    elif scenario == 'no-events':
        assert paths[-1] == '/events/search'
        assert 'PASS sync event search (records=0)' in out
        assert 'SKIP async event detail (no event ID available from completed reads)' in out
        assert 'SUMMARY pass=8 fail=0 skip=10' in out
    elif scenario == 'snapshot-fallback':
        assert paths[-1] == f'/events/{_EVENT["eventId"]}'
        assert 'PASS async status snapshot (ongoing=2, upcoming=0)' in out
        assert 'SKIP sync event timeline (records=0)' in out
    else:
        assert paths.count('/tenants') == 2
        assert 'FAIL sync tenant pagination (HTTP 400)' in out
        assert 'FAIL async status snapshot (unexpected error)' in out
        assert 'FAIL async event search (response schema or identity mismatch)' in out
        assert 'SUMMARY pass=4 fail=6 skip=8' in out


def test_explicit_opt_in_and_hidden_prompt(smoke, monkeypatch, capsys):
    monkeypatch.setattr(smoke.sysconfig, 'get_path', lambda _: str(Path(sfdctrust.__file__).parent.parent))
    monkeypatch.setenv('SFDCTRUST_PAT', 'synthetic-default-unused')
    monkeypatch.setenv('QUALIFICATION_PAT', _PAT)
    calls = []

    async def run(pat):
        calls.append(pat)
        return 0

    def hidden_input_unavailable(_):
        warnings.warn('synthetic-hidden-input-warning', smoke.GetPassWarning, stacklevel=2)
        pytest.fail('The warning must prevent echo fallback.')

    monkeypatch.setattr(smoke, '_run', run)
    monkeypatch.setattr(smoke, 'getpass', hidden_input_unavailable)
    with pytest.raises(SystemExit, match='2'):
        smoke.main(['--from-env', 'QUALIFICATION_PAT'])
    with pytest.raises(SystemExit, match='2'):
        smoke.main(['--live', _PAT])
    assert smoke.main(['--live']) == 1
    assert smoke.main(['--live', '--from-env', 'MISSING_QUALIFICATION_PAT']) == 1
    assert calls == []
    monkeypatch.setattr(smoke, 'getpass', lambda _: _PAT)
    assert smoke.main(['--live']) == 0
    assert smoke.main(['--live', '--from-env', 'QUALIFICATION_PAT']) == 0
    assert calls == [_PAT, _PAT]
    out, err = capsys.readouterr()
    assert 'synthetic-' not in out + err
