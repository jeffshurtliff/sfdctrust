# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.cli_events
:Synopsis:          Installed status and event launcher checks with synthetic HTTP
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sfdctrust import SQLitePATStore


def check(closed_pipe):
    """Qualify both installed launchers outside the checkout, without outbound I/O."""
    offline = Path(__file__).resolve().parent
    console = Path(sys.executable).parent / ('sfdctrust.exe' if sys.platform == 'win32' else 'sfdctrust')
    event = {
        'eventId': 'synthetic-event',
        'eventType': 'patch',
        'status': 'future-status',
        'products': [],
        'services': [],
        'createdAt': '2026-11-01T00:00:00+05:45',
        'title': None,
        'scope': {'tenants': {'synthetic-tenant': {'extra': None}}},
        'extra': None,
    }
    other = {**event, 'scope': {'tenants': {'other-tenant': {}}}}
    empty = {category: [] for category in ('patch', 'incident', 'maintenance', 'informationalMessage')}
    snapshot = {'ongoing': {**empty, 'patch': [event, other]}, 'upcoming': {**empty, 'patch': [other]}, 'extra': None}
    entry = {
        'subEventId': 'synthetic-stage',
        'subEventType': 'future-subtype',
        'scope': event['scope'],
        'createdAt': '2026-11-01T00:00:00-03:30',
        'message': None,
        'extra': None,
    }
    detail = {key: value for key, value in event.items() if key != 'scope'}
    detail['timeline'] = [entry, {**entry, 'scope': other['scope']}]
    start, end = '2026-11-01T00:00:00+05:45', '2026-11-02T00:00:00-04:00'
    search = ['events', 'search', '--tenant-id', 'synthetic-tenant', '--start-time', start, '--end-time', end]
    body = {'scopes': [{'type': 'tenant', 'id': 'synthetic-tenant'}], 'startTime': start, 'endTime': end}
    with TemporaryDirectory() as directory:
        work = Path(directory)
        home, bootstrap = work / 'home', work / 'bootstrap'
        home.mkdir()
        bootstrap.mkdir()
        store_path = work / 'private' / 'pat.sqlite3'
        for path in (store_path, home / '.sfdctrust/pat.sqlite3', home / '.sfdctrust/monitoring.sqlite3'):
            SQLitePATStore.initialize(pat='synthetic-installed-store', path=path)
        # (arguments, response, path, query, body, status, exception, text markers)
        scenarios = [
            (
                ['status', 'snapshot', '--locale', 'ja-JP', '--json'],
                snapshot,
                '/status',
                {'locale': 'ja-JP'},
                None,
                200,
                None,
                [],
            ),
            (
                ['status', 'snapshot'],
                snapshot,
                '/status',
                {},
                None,
                200,
                None,
                ['ongoing:', 'upcoming:', 'Affected tenant IDs:', '  informationalMessage:'],
            ),
            (
                [*search, '--json'],
                {'events': [event, other], 'nextPageToken': '', 'extra': None},
                '/events/search',
                {},
                body,
                200,
                None,
                [],
            ),
            (
                [*search, '--page-token', '', '--page-size', '1', '--locale', ' odd locale ', '--json'],
                {'events': []},
                '/events/search',
                {'locale': ' odd locale '},
                {**body, 'pageToken': '', 'pageSize': 1},
                200,
                None,
                [],
            ),
            (
                [*search],
                {'events': [], 'nextPageToken': ''},
                '/events/search',
                {},
                body,
                200,
                None,
                ['authorized scope', 'does not establish Salesforce-wide health', 'Continuation (nextPageToken): ""'],
            ),
            (['events', 'get', 'synthetic-event', '--json'], detail, '/events/synthetic-event', {}, None, 200, None, []),
            (
                ['events', 'get', 'synthetic-event', '--locale', 'en-US'],
                detail,
                '/events/synthetic-event',
                {'locale': 'en-US'},
                None,
                200,
                None,
                ['Event metadata:', 'Timeline (as supplied):', 'Affected tenant IDs: ["other-tenant"]', '-03:30'],
            ),
        ]
        for category in ('patch', 'incident', 'maintenance', 'informationalMessage'):
            scenarios.append(
                (
                    [*search, '--event-type', category, '--json'],
                    {'events': []},
                    '/events/search',
                    {},
                    {**body, 'eventTypes': [category]},
                    200,
                    None,
                    [],
                )
            )
        for command, payload, path, request_body in (
            (['status', 'snapshot'], snapshot, '/status', None),
            (search, {'events': [event, other]}, '/events/search', body),
            (['events', 'get', 'synthetic-event'], detail, '/events/synthetic-event', None),
        ):
            for selector in (['--store'], ['--store-path', str(store_path)], ['--store-alias', 'monitoring']):
                scenarios.append(([*command, *selector, '--json'], payload, path, {}, request_body, 200, None, []))
            for status in (401, 403, 404, 429, 503):
                scenarios.append(
                    ([*command, '--json'], {'message': 'synthetic-server-private'}, path, {}, request_body, status, None, [])
                )
            scenarios.append(([*command, '--json'], {}, path, {}, request_body, 200, None, []))
            for exception in ('timeout', 'network', 'interrupt'):
                scenarios.append(([*command, '--json'], {}, path, {}, request_body, 200, exception, []))
        scenarios.append(
            (
                [*search, '--page-token', 'stale', '--json'],
                {'message': 'synthetic-server-private'},
                '/events/search',
                {},
                {**body, 'pageToken': 'stale'},
                400,
                None,
                [],
            )
        )
        for index, (arguments, payload, path, params, request_body, status, exception, markers) in enumerate(scenarios):
            outputs = []
            for label, launcher in [('console', [str(console)]), ('module', [sys.executable, '-m', 'sfdctrust'])]:
                evidence = work / f'{index}-{label}.json'
                settings = {
                    'home': str(home),
                    'evidence': str(evidence),
                    'path': path,
                    'params': params,
                    'body': request_body,
                    'method': 'POST' if request_body is not None else 'GET',
                    'pat': 'synthetic-installed-store'
                    if any(option in arguments for option in ('--store', '--store-path', '--store-alias'))
                    else 'synthetic-installed-env',
                    'payload': payload,
                    'status': status,
                    'exception': exception,
                }
                (bootstrap / 'sitecustomize.py').write_text(
                    'import runpy\n'
                    f'runpy.run_path({str(offline / "sitecustomize.py")!r})\n'
                    f'runpy.run_path({str(offline / "cli_tenants.py")!r})["install"]({settings!r})\n',
                    encoding='utf-8',
                )
                environment = {
                    **os.environ,
                    'PYTHONPATH': str(bootstrap),
                    'PYTHONDONTWRITEBYTECODE': '1',
                    'SFDCTRUST_PAT': 'synthetic-installed-env',
                }
                if index == 0:
                    # Prove this bootstrap rejects DNS, outbound I/O, prompts and mismatched HTTP.
                    probe = subprocess.run(
                        [
                            sys.executable,
                            '-c',
                            'import builtins, getpass, socket, httpx\n'
                            'checks = [lambda: socket.getaddrinfo("example.invalid", 443), '
                            'lambda: socket.socket().connect(("192.0.2.1", 443)), '
                            'lambda: builtins.input(""), lambda: getpass.getpass("")]\n'
                            'for call in checks:\n'
                            '    try: call()\n'
                            '    except (AssertionError, RuntimeError): pass\n'
                            '    else: raise AssertionError("read guard inactive")\n'
                            'with httpx.Client() as client:\n'
                            '    try: client.get("https://example.invalid/wrong")\n'
                            '    except AssertionError: pass\n'
                            '    else: raise AssertionError("HTTP guard inactive")\n',
                        ],
                        cwd=work,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    assert probe.returncode == 0 and probe.stdout == '' and probe.stderr == '', probe.stderr
                result = subprocess.run(
                    [*launcher, *arguments], cwd=work, env=environment, capture_output=True, text=True, timeout=15, check=False
                )
                code = (
                    130
                    if exception == 'interrupt'
                    else 3
                    if status == 401
                    else 4
                    if exception or status != 200 or payload == {}
                    else 0
                )
                assert result.returncode == code, (index, label, result.stdout, result.stderr)
                log = json.loads(evidence.read_text(encoding='utf-8'))
                assert log['active'] and log['closed']
                assert len(log['requests']) == (3 if status in (429, 503) or exception in ('timeout', 'network') else 1)
                assert all(request == log['requests'][0] for request in log['requests'])
                assert all(
                    secret not in result.stdout + result.stderr
                    for secret in (
                        'synthetic-installed-env',
                        'synthetic-installed-store',
                        'synthetic-server-private',
                        'Traceback',
                    )
                )
                if code:
                    assert result.stdout == ''
                    assert (
                        result.stderr
                        == 'sfdctrust: '
                        + {
                            3: 'credential, configuration, or PAT store failure. Check the selected credential and store state.\n',
                            4: 'My Trust Center request failed.\n',
                            130: 'interrupted.\n',
                        }[code]
                    )
                else:
                    assert result.stderr == '' and result.stdout.endswith('\n')
                    if '--json' in arguments:
                        assert json.loads(result.stdout) == payload
                    else:
                        assert all(marker in result.stdout for marker in markers)
                if index in (0, 2, 5):
                    closed_pipe([*launcher, *arguments], work, environment)
                outputs.append((result.stdout, result.stderr))
            assert outputs[0] == outputs[1]
    print('Installed status/event commands passed (both launchers, synthetic HTTP, stores, errors, cleanup and outbound guards).')
