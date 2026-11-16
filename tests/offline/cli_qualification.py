# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.cli_qualification
:Synopsis:          Integrated installed CLI credential isolation and opaque-argument checks
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sfdctrust import PATStoreRecord, SQLitePATStore


def check(closed_pipe):
    """Exercise every installed action with isolated credentials and argparse forms."""
    offline = Path(__file__).resolve().parent
    console = Path(sys.executable).parent / ('sfdctrust.exe' if sys.platform == 'win32' else 'sfdctrust')
    tenant = {'id': 'synthetic-tenant', 'name': 'Synthetic tenant', 'cloud': 'future-cloud'}
    event = {
        'eventId': 'synthetic-event',
        'eventType': 'future-event',
        'status': 'future-status',
        'products': [],
        'services': [],
        'createdAt': '2026-11-01T00:00:00+05:45',
    }
    empty = {category: [] for category in ('patch', 'incident', 'maintenance', 'informationalMessage')}
    search = [
        'events',
        'search',
        '--tenant-id',
        'synthetic-tenant',
        '--start-time',
        '2026-11-01T00:00:00Z',
        '--end-time',
        '2026-11-02T00:00:00Z',
    ]
    body = {
        'scopes': [{'type': 'tenant', 'id': 'synthetic-tenant'}],
        'startTime': '2026-11-01T00:00:00+00:00',
        'endTime': '2026-11-02T00:00:00+00:00',
    }
    # The first five reads are the guide's five command examples, using only synthetic inputs.
    commands = [
        (['tenants', 'list', '--page-size', '25', '--json'], {'tenants': [tenant]}, '/tenants', {'pageSize': '25'}, None),
        (
            ['tenants', 'get', 'synthetic-tenant', '--locale', 'en-US', '--json'],
            {**tenant, 'events': []},
            '/tenants/synthetic-tenant',
            {'locale': 'en-US'},
            None,
        ),
        (
            ['status', 'snapshot', '--locale', 'en-US', '--json'],
            {'ongoing': empty, 'upcoming': empty},
            '/status',
            {'locale': 'en-US'},
            None,
        ),
        (
            [*search, '--event-type', 'incident', '--json'],
            {'events': []},
            '/events/search',
            {},
            {**body, 'eventTypes': ['incident']},
        ),
        (['events', 'get', 'synthetic-event', '--store-alias', 'monitoring'], event, '/events/synthetic-event', {}, None),
    ]
    with TemporaryDirectory() as directory:
        work = Path(directory)
        home, bootstrap = work / 'home', work / 'bootstrap'
        home.mkdir()
        bootstrap.mkdir()
        ready = home / '.sfdctrust/pat.sqlite3'
        alias = home / '.sfdctrust/monitoring.sqlite3'
        pending, unseeded = work / 'private/pending.sqlite3', work / 'private/unseeded.sqlite3'
        for path in (ready, alias, pending, unseeded):
            store = SQLitePATStore.initialize(pat='synthetic-installed-store', path=path)
            if path == pending:
                record = store.load()
                assert store.compare_and_swap(
                    expected_revision=record.revision,
                    expected_attempt=None,
                    replacement=PATStoreRecord(record.revision, record.get_pat(), uuid4()),
                )
        with sqlite3.connect(unseeded) as db:
            db.execute('DELETE FROM credential')
        before = {path: path.read_bytes() for path in (ready, alias, pending, unseeded)}
        scenarios = []
        example_indices = []
        for arguments, payload, path, params, request_body in commands:
            # Drop the example's selector before applying each credential scenario.
            base = arguments[:]
            if '--store-alias' in base:
                del base[base.index('--store-alias') : base.index('--store-alias') + 2]
            example_indices.append(len(scenarios))
            scenarios.append((arguments, payload, path, params, request_body, 0, True))
            for selector, code, present in (
                (['--store'], 0, True),
                (['--store-path', str(ready)], 0, True),
                (['--store-alias', 'monitoring'], 0, True),
                (['--store-path', str(pending)], 3, True),
                (['--store-path', str(unseeded)], 3, True),
                (['--store-path', str(work / 'absent/pat.sqlite3')], 3, True),
                (['--store-alias', 'missing'], 3, True),
                ([], 3, False),  # A valid default store must not be discovered.
            ):
                scenarios.append(([*base, *selector], payload, path, params, request_body, code, present))
        scenarios += [
            (
                ['tenants', 'list', '--page-token=-opaque', '--json'],
                {'tenants': [], 'nextPageToken': '-next'},
                '/tenants',
                {'pageToken': '-opaque'},
                None,
                0,
                True,
            ),
            (
                ['tenants', 'get', '--json', '--', '-tenant'],
                {**tenant, 'id': '-tenant', 'events': []},
                '/tenants/-tenant',
                {},
                None,
                0,
                True,
            ),
            (['events', 'get', '--json', '--', '-event'], {**event, 'eventId': '-event'}, '/events/-event', {}, None, 0, True),
            (
                [*search, '--page-token=-opaque', '--tenant-id=-scope', '--json'],
                {'events': [], 'nextPageToken': '-next'},
                '/events/search',
                {},
                {**body, 'scopes': [*body['scopes'], {'type': 'tenant', 'id': '-scope'}], 'pageToken': '-opaque'},
                0,
                True,
            ),
        ]
        for index, (arguments, payload, path, params, request_body, code, present) in enumerate(scenarios):
            outputs = []
            explicit = any(option in arguments for option in ('--store', '--store-path', '--store-alias'))
            for label, launcher in [('console', [str(console)]), ('module', [sys.executable, '-m', 'sfdctrust'])]:
                evidence = work / f'{index}-{label}.json'
                settings = {
                    'home': str(home),
                    'evidence': str(evidence),
                    'path': path,
                    'params': params,
                    'body': request_body,
                    'method': 'POST' if request_body is not None else 'GET',
                    'pat': 'synthetic-installed-store' if explicit else 'synthetic-installed-env',
                    'payload': payload,
                    'deny_environment': explicit,
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
                if not present:
                    del environment['SFDCTRUST_PAT']
                result = subprocess.run(
                    [*launcher, *arguments],
                    cwd=work,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                assert result.returncode == code, (index, label, result.stdout, result.stderr)
                log = json.loads(evidence.read_text(encoding='utf-8'))
                assert log['active'] and log['closed']
                assert len(log['requests']) == (0 if code else 1)  # No fallback or hidden traversal.
                assert all(
                    secret not in result.stdout + result.stderr
                    for secret in (
                        'synthetic-installed-env',
                        'synthetic-installed-store',
                        'Traceback',
                    )
                )
                if code:
                    assert result.stdout == ''
                    assert result.stderr == (
                        'sfdctrust: credential, configuration, or PAT store failure. '
                        'Check the selected credential and store state.\n'
                    )
                else:
                    assert result.stderr == '' and result.stdout.endswith('\n')
                    if '--json' in arguments:
                        assert json.loads(result.stdout) == payload
                if index in example_indices:
                    closed_pipe([*launcher, *arguments], work, environment)
                    with (bootstrap / 'sitecustomize.py').open('a', encoding='utf-8') as setup:
                        setup.write('import os; os.close(1)\n')
                    broken = subprocess.run(
                        [*launcher, *arguments],
                        cwd=work,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    assert broken.returncode == 1 and broken.stdout == ''
                    assert broken.stderr == 'sfdctrust: internal or output failure.\n'
                outputs.append((result.stdout, result.stderr))
            assert outputs[0] == outputs[1]
        assert not (work / 'absent').exists()
        assert not (home / '.sfdctrust/missing.sqlite3').exists()
        assert all(path.read_bytes() == data for path, data in before.items())
    print('Integrated installed CLI passed (all five examples, explicit-store isolation, no fallback, opaque arguments).')
