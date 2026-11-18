# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.mcp_qualification
:Synopsis:          Qualify the installed MCP stdio command using the official client
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.2 Astra)
:Modified Date:     18 Nov 2026
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment

OFFLINE = Path(__file__).resolve().parent
COMMAND = ['-m', 'sfdctrust.integrations.mcp']
SECRET = 'synthetic-mcp-credential'
RAW = 'synthetic-private-upstream-message'
CURSOR = ' opaque/?+雪 '
TENANT = {'id': 'cloud:tenant-A', 'name': 'A', 'cloud': 'synthetic-cloud'}
EVENT = {
    'eventId': 'event-A',
    'eventType': 'patch',
    'status': 'active',
    'products': [],
    'services': [],
    'createdAt': '2026-11-18T07:00:00+03:00',
}
HISTORY = [{**EVENT, 'scope': {'tenants': {tenant: {}}}} for tenant in ('cloud:tenant-B', 'cloud:tenant-A')]
EMPTY = {bucket: [] for bucket in ('patch', 'incident', 'maintenance', 'informationalMessage')}
SNAPSHOT = {'ongoing': {**EMPTY, 'patch': HISTORY}, 'upcoming': EMPTY}
DETAIL = {
    **EVENT,
    'timeline': [
        {
            'subEventId': f'entry-{idx}',
            'subEventType': 'patch_release_started',
            'createdAt': EVENT['createdAt'],
            'scope': item['scope'],
        }
        for idx, item in enumerate(HISTORY)
    ],
}
SEARCH = {
    'tenant_ids': [TENANT['id'], 'cloud:tenant-B', TENANT['id']],
    'start_time': '2026-11-18T00:00:00Z',
    'end_time': '2026-11-19T00:00:00Z',
    'event_types': ['patch', 'incident'],
    'locale': 'fr-CA',
}
TOOLS = {'list_tenants', 'get_tenant', 'get_status', 'search_events', 'get_event'}


def trace(work):
    path = work / 'trace.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def server_environment(work):
    bootstrap = work / 'bootstrap'
    bootstrap.mkdir()
    # Site startup normally prints and ignores exceptions. Exit before launching
    # any server if the inherited guard or synthetic HTTP transport fails to load.
    start = 'import os, runpy\ntry:\n'
    for file in ('sitecustomize.py', 'mcp_mock.py'):
        start += f'    runpy.run_path({str(OFFLINE / file)!r})\n'
    (bootstrap / 'sitecustomize.py').write_text(start + 'except BaseException:\n    os._exit(91)\n', encoding='utf-8')
    return {
        'HOME': str(work),
        'USERPROFILE': str(work),
        'PYTHONPATH': str(bootstrap),
        'PYTHONNOUSERSITE': '1',
        'SFDCTRUST_PAT': SECRET,
        'SFDCTRUST_MCP_TEST_DIR': str(work),
    }


async def exercise(client, work):
    listing = await client.list_tools()
    assert len(listing.tools) == 5 and {tool.name for tool in listing.tools} == TOOLS

    assert all(tool.annotations and tool.annotations.read_only_hint for tool in listing.tools)

    async def call(name, args, payload=None, *, status=200, error=False, retries=0, min_bytes=0):
        before = trace(work)
        (work / 'reply.json').write_text(json.dumps({'status': status, 'payload': payload}), encoding='utf-8')
        observed = datetime.now(UTC)
        result = await client.call_tool(name, args)
        raw = result.model_dump_json(by_alias=True, exclude_unset=True)
        assert min_bytes <= len(raw.encode('utf-8')) <= 65_536 and all(marker not in raw for marker in (SECRET, RAW)), name
        entries = [row for row in trace(work)[len(before) :] if isinstance(row, dict)]
        assert len(entries) == int(payload is not None) + retries, (name, args, entries)
        body = result.structured_content
        assert result.is_error == error, (name, body, result.content)
        if error:
            assert body and set(body) == {'error'} and set(body['error']) == {'code', 'message'}, (name, result.content)
            assert all(isinstance(value, str) and value for value in body['error'].values())
            return body['error']['code']
        assert set(body) == {'retrieved_at', 'data'}
        stamp = datetime.fromisoformat(body['retrieved_at'])
        assert stamp.utcoffset() == timedelta(0) and observed <= stamp <= datetime.now(UTC)
        assert body['data'] == payload, (name, body)
        return entries[0]

    for name, items, key, base in [('list_tenants', [TENANT], 'tenants', {}), ('search_events', HISTORY, 'events', SEARCH)]:
        for token, following in ((None, ''), ('', CURSOR), (CURSOR, 'null'), ('null', '[]'), ('[]', None)):
            args = dict(base)
            if token is not None:
                args['page_token'] = token
            payload = {key: items, **({'nextPageToken': following} if following is not None else {})}
            request = await call(name, args, payload)
            if name == 'list_tenants':
                assert (request['method'], request['path'], request['body']) == ('GET', '/tenants', None)
                assert request['query'] == {'pageSize': '25', **({'pageToken': token} if token is not None else {})}
            else:
                assert (request['method'], request['path'], request['query']) == ('POST', '/events/search', {'locale': 'fr-CA'})
                body = request['body']
                assert body['pageSize'] == 25 and body['eventTypes'] == args['event_types']
                assert body['scopes'] == [{'id': tenant, 'type': 'tenant'} for tenant in SEARCH['tenant_ids']]
                for key_wire, key_tool in [('startTime', 'start_time'), ('endTime', 'end_time')]:
                    assert datetime.fromisoformat(body[key_wire]) == datetime.fromisoformat(args[key_tool])
                assert ('pageToken' in body) == (token is not None) and body.get('pageToken') == token

    request = await call('list_tenants', {'page_size': 100}, {'tenants': []})
    assert request['query'] == {'pageSize': '100'}

    calls = [
        ('get_tenant', {'tenant_id': TENANT['id']}, {**TENANT, 'events': HISTORY}, f'/tenants/{TENANT["id"]}'),
        ('get_status', {}, SNAPSHOT, '/status'),
        ('get_event', {'event_id': EVENT['eventId']}, DETAIL, f'/events/{EVENT["eventId"]}'),
    ]
    for name, args, data, path in calls:
        request = await call(name, {**args, 'locale': 'en-US'}, data)
        assert request == {'method': 'GET', 'path': path, 'body': None, 'query': {'locale': 'en-US'}}

    invalid = [
        ('get_tenant', {'tenant_id': ''}),
        ('get_event', {'event_id': '..'}),
        ('get_status', {'locale': 123}),
        ('get_status', {'locale': 'en_US'}),
        ('get_status', {'locale': 'en-US-a-foo-a-bar'}),
        ('list_tenants', {'page_size': 0}),
        ('list_tenants', {'page_size': True}),
        ('list_tenants', {'page_size': 101}),
        ('list_tenants', {'page_token': 'a' * 4097}),
        ('get_status', {'pat': SECRET}),
    ]
    invalid.extend(
        ('search_events', SEARCH | update)
        for update in [
            {'tenant_ids': []},
            {'tenant_ids': ['a'] * 51},
            {'tenant_ids': ['']},
            {'event_types': ['unrecognized']},
            {'event_types': []},
            {'event_types': ['patch', 'patch']},
            {'start_time': SEARCH['end_time']},
            {'end_time': '2026-11-19T00:00:00'},
            {'start_time': '2026-11-18'},
        ]
    )
    for name, args in invalid:
        assert await call(name, args, error=True) == 'invalid_input'

    oversized = [*calls, ('list_tenants', {}, {'tenants': []}, ''), ('search_events', SEARCH, {'events': []}, '')]
    for name, args, payload, _ in oversized:
        # 26k characters are 78k UTF-8 bytes even before JSON escaping.
        assert await call(name, args, {**payload, 'extension': '雪' * 26_000}, error=True) == 'output_limit'
    # Each multibyte value appears in both structuredContent and its text fallback.
    near = {'tenants': [], 'extra': '雪' * 10_850}
    await call('list_tenants', {}, near, min_bytes=65_000)
    assert await call('list_tenants', {}, {**near, 'extra': near['extra'] + '雪' * 100}, error=True) == 'output_limit'
    upstream = {'detail': RAW, 'credential': SECRET}
    assert await call('get_event', {'event_id': 'no-access'}, upstream, status=401, error=True) == 'authentication'
    assert await call('get_tenant', {'tenant_id': 'missing'}, upstream, status=404, error=True) == 'not_found'
    assert await call('get_status', {}, upstream, error=True) == 'malformed_response'
    assert await call('list_tenants', {'page_token': CURSOR}, upstream, status=400, error=True) == 'upstream'
    assert await call('get_status', {}, upstream, status=429, error=True, retries=2) == 'rate_limit'
    assert await call('get_status', {}, RAW, status='timeout', error=True, retries=2) == 'timeout'
    assert await call('get_status', {}, RAW, status='network', error=True) == 'network'
    for reflected in (SECRET, {'Authorization': 'Bearer synthetic-private-upstream-message'}):
        assert await call('get_status', {}, {**SNAPSHOT, 'future': [reflected]}, error=True) == 'unsafe_output'


async def check(work):
    # Relay the documented launch command's stdout without altering its bytes.
    # The real MCP client owns stdin and initiates graceful shutdown. Every byte,
    # including trailing output after shutdown, remains available for verification.
    relay = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), '--relay'],
        cwd=work,
        env=server_environment(work),
    )
    async with asyncio.timeout(60), Client(relay) as client:
        await exercise(client, work)
    lifecycle = [entry for entry in trace(work) if isinstance(entry, str)]
    assert lifecycle == ['opened', 'closed'], lifecycle
    wire = (work / 'stdout.jsonl').read_bytes()
    for row in wire.splitlines():
        assert json.loads(row)['jsonrpc'] == '2.0'
    assert wire and wire.endswith(b'\n')
    stderr = (work / 'stderr.log').read_bytes()
    for marker in (SECRET, RAW, 'Authorization: Bearer', 'Traceback (most recent call last)'):
        assert marker.encode() not in wire and marker.encode() not in stderr
    assert (work / 'exit.txt').read_text() == '0'
    # A direct launch with an absent or malformed synthetic credential must fail
    # before creating a transport. Preserve the same fail-closed child bootstrap.
    env = get_default_environment() | relay.env
    del env['SFDCTRUST_PAT']
    for extra in ({}, {'SFDCTRUST_PAT': SECRET + ' invalid'}):
        process = subprocess.run(
            [sys.executable, *COMMAND], cwd=work, env=env | extra, input=b'', capture_output=True, timeout=10
        )
        assert process.returncode != 0 and process.stdout == b''
        assert b'SFDCTRUST_PAT' in process.stderr and SECRET.encode() not in process.stderr
    assert [entry for entry in trace(work) if isinstance(entry, str)] == lifecycle


def relay_stdio():
    work = Path(os.environ['SFDCTRUST_MCP_TEST_DIR'])
    with (work / 'stderr.log').open('wb') as errors, (work / 'stdout.jsonl').open('wb') as capture:
        with subprocess.Popen(
            [sys.executable, *COMMAND], cwd=work, stdin=sys.stdin.buffer, stdout=subprocess.PIPE, stderr=errors
        ) as server:
            for line in server.stdout:
                capture.write(line)
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
        (work / 'exit.txt').write_text(str(server.returncode))
        return server.returncode


if __name__ == '__main__':
    if '--relay' in sys.argv:
        sys.exit(relay_stdio())
    with TemporaryDirectory() as temp:
        asyncio.run(check(Path(temp)))
    print('Installed MCP stdio protocol qualification passed.')
