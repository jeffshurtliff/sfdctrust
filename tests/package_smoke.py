# -*- coding: utf-8 -*-
"""
:Module:            tests.package_smoke
:Synopsis:          Installed-wheel SQLite PAT workflow with synthetic credentials
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

import sfdctrust
from sfdctrust import SQLitePATStore, TrustCenterClient
from sfdctrust.models.events import EventSearchScope


def closed_pipe(arguments: list[str], work: Path, environment: dict[str, str]) -> None:
    """Verify a real closed output pipe returns 1 without shutdown tracebacks."""
    with subprocess.Popen(
        arguments, cwd=work, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as child:
        assert child.stdout is not None
        child.stdout.close()
        child.stdout = None
        _, diagnostic = child.communicate(timeout=15)
        assert child.returncode == 1, diagnostic
        assert diagnostic == 'sfdctrust: internal or output failure.\n'


def cli_foundation() -> None:
    """Run both real installed launchers outside the checkout with strict guards."""
    tests = Path(__file__).resolve().parent
    console = Path(sys.executable).parent / ('sfdctrust.exe' if sys.platform == 'win32' else 'sfdctrust')
    assert console.is_file(), 'The installed console script is missing.'
    with TemporaryDirectory() as directory:
        work = Path(directory)
        bootstrap = work / 'bootstrap'
        bootstrap.mkdir()
        (bootstrap / 'sitecustomize.py').write_text(
            'import runpy\n'
            f'runpy.run_path({str(tests / "offline/sitecustomize.py")!r})\n'
            f'runpy.run_path({str(tests / "offline/cli_guard.py")!r})\n',
            encoding='utf-8',
        )
        environment = {
            **os.environ,
            'PYTHONPATH': str(bootstrap),
            'PYTHONDONTWRITEBYTECODE': '1',
            'SFDCTRUST_PAT': 'synthetic-cli-secret',
        }
        probe = subprocess.run(
            [
                sys.executable,
                '-c',
                'import os, socket\n'
                'from sfdctrust import TrustCenterClient\n'
                'checks = [lambda: os.getenv("SFDCTRUST_PAT"), lambda: TrustCenterClient.from_env(), '
                'lambda: socket.getaddrinfo("example.invalid", 443)]\n'
                'for check in checks:\n'
                '    try: check()\n'
                '    except (AssertionError, RuntimeError): pass\n'
                '    else: raise AssertionError("CLI guard is inactive")\n',
            ],
            env=environment,
            cwd=work,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert probe.returncode == 0 and probe.stdout == '' and probe.stderr == '', probe.stderr
        for arguments, status in [
            (['--help'], 0),
            (['-h'], 0),
            (['--version'], 0),
            (['tenants', '--help'], 0),
            (['tenants', 'list', '--help'], 0),
            (['tenants', 'get', '--help'], 0),
            *[
                ([*command, '--help'], 0)
                for command in (['status'], ['status', 'snapshot'], ['events'], ['events', 'search'], ['events', 'get'])
            ],
            *[
                ([*command, '--store-alias', '../synthetic-cli-secret'], 2)
                for command in (
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
                )
            ],
            (['tenants', 'list', '--page-token=' + 'x' * 4097], 2),
            (['events', 'get', '../unsafe'], 2),
            (['events', 'search'], 2),
            (['status', 'snapshot', '--store', '--store-path', 'synthetic-cli-secret'], 2),
            *[
                (['events', 'search', '--tenant-id', tenant, '--start-time', start, '--end-time', end, *extra], 2)
                for tenant, start, end, extra in (
                    ('', '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z', []),
                    ('synthetic', '2026-11-01', '2026-11-02T00:00:00Z', []),
                    ('synthetic', '2026-11-01T00:00:00Z', '2026-11-01T05:30:00+05:30', []),
                    ('synthetic', '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z', ['--event-type', 'synthetic-cli-secret']),
                    ('synthetic', '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z', ['--page-size', '201']),
                    ('synthetic', '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z', ['--tenant-id', 'extra'] * 50),
                )
            ],
            (['tenants', 'get', '../unsafe'], 2),
            (['tenants', 'list', '--store', '--store-alias', 'conflict'], 2),
            ([], 2),
            (['--ver'], 2),
            (['--hel'], 2),
            (['tenants', 'list', '--page-size', '0'], 2),
            (['synthetic-cli-secret'], 2),
            (['--pat', 'synthetic-cli-secret'], 2),
            (['--help=synthetic-cli-secret'], 2),
            (['--version=synthetic-cli-secret'], 2),
        ]:
            outputs = []
            for launcher in ([str(console)], [sys.executable, '-m', 'sfdctrust']):
                result = subprocess.run(
                    [*launcher, *arguments], env=environment, cwd=work, capture_output=True, text=True, timeout=15, check=False
                )
                assert result.returncode == status, result.stderr
                assert 'synthetic-cli-secret' not in result.stdout + result.stderr
                assert 'Traceback' not in result.stdout + result.stderr
                if status == 2:
                    assert result.stdout == ''
                    assert result.stderr.startswith('usage: sfdctrust')
                    assert 'invalid arguments' in result.stderr
                else:
                    assert result.stderr == ''
                    if arguments == ['--version']:
                        assert result.stdout == f'sfdctrust {sfdctrust.__version__}\n'
                    else:
                        assert result.stdout.startswith('usage: sfdctrust')
                        assert '--help' in result.stdout
                        if arguments in (['--help'], ['-h']):
                            assert '--version' in result.stdout and 'tenants' in result.stdout
                outputs.append((result.stdout, result.stderr))
            assert outputs[0] == outputs[1]
        for launcher in ([str(console)], [sys.executable, '-m', 'sfdctrust']):
            for arguments in (['--help'], ['--version']):
                closed_pipe([*launcher, *arguments], work, environment)
            with (bootstrap / 'sitecustomize.py').open('a', encoding='utf-8') as setup:
                setup.write('import os; os.close(1)\n')
            for arguments in (['--help'], ['--version']):
                result = subprocess.run(
                    [*launcher, *arguments],
                    cwd=work,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                assert result.returncode == 1 and result.stdout == ''
                assert result.stderr == 'sfdctrust: internal or output failure.\n'
            # Restore the bootstrap for the other real launcher.
            setup_path = bootstrap / 'sitecustomize.py'
            setup_path.write_text(setup_path.read_text().removesuffix('import os; os.close(1)\n'), encoding='utf-8')
    print('Installed CLI foundation passed (both launchers, guarded credentials/stores/prompts/network).')


def cli_tenants() -> None:
    """Exercise installed read commands using test-only HTTP and disposable stores."""
    tests = Path(__file__).resolve().parent
    console = Path(sys.executable).parent / ('sfdctrust.exe' if sys.platform == 'win32' else 'sfdctrust')
    tenant = {'id': 'synthetic-tenant', 'name': 'Synthetic tenant', 'cloud': 'future-cloud'}
    event = {
        'eventId': 'synthetic-event',
        'eventType': 'future-type',
        'status': 'future-status',
        'products': [],
        'services': [],
        'createdAt': '2026-11-01T00:00:00+05:45',
        'title': None,
        'scope': {'tenants': {'synthetic-tenant': {'extra': True}}},
    }
    detail = {**tenant, 'events': [event, event], 'region': None, 'extra': True}
    with TemporaryDirectory() as directory:
        work = Path(directory)
        home = work / 'home'
        home.mkdir()
        store_path = work / 'private' / 'pat.sqlite3'
        SQLitePATStore.initialize(pat='synthetic-installed-store', path=store_path)
        SQLitePATStore.initialize(pat='synthetic-installed-store', path=home / '.sfdctrust' / 'pat.sqlite3')
        SQLitePATStore.initialize(pat='synthetic-installed-store', path=home / '.sfdctrust' / 'monitoring.sqlite3')
        bootstrap = work / 'bootstrap'
        bootstrap.mkdir()
        scenarios = [
            (['tenants', 'list', '--json'], {'tenants': [tenant], 'future': None}, '/tenants', {}, 0),
            (
                ['tenants', 'list', '--page-size', '1', '--page-token', '', '--locale', 'ja-JP', '--json'],
                {'tenants': [], 'nextPageToken': ''},
                '/tenants',
                {'pageSize': '1', 'pageToken': '', 'locale': 'ja-JP'},
                0,
            ),
            (
                ['tenants', 'get', tenant['id'], '--locale', 'en-US', '--json'],
                detail,
                '/tenants/' + tenant['id'],
                {'locale': 'en-US'},
                0,
            ),
            (['tenants', 'get', tenant['id']], detail, '/tenants/' + tenant['id'], {}, 0),
            (
                ['tenants', 'list', '--page-token', 'stale', '--json'],
                {'message': 'synthetic-server-private'},
                '/tenants',
                {'pageToken': 'stale'},
                400,
            ),
            (['tenants', 'list'], {'message': 'synthetic-server-private'}, '/tenants', {}, 401),
        ]
        for selector in (['--store'], ['--store-path', str(store_path)], ['--store-alias', 'monitoring']):
            scenarios.append((['tenants', 'list', *selector, '--json'], {'tenants': [], 'nextPageToken': ''}, '/tenants', {}, 0))
        scenarios.append((['tenants', 'list', '--store-alias', 'missing'], {'tenants': []}, '/tenants', {}, -1))
        for index, (arguments, payload, path, params, failure) in enumerate(scenarios):
            outputs = []
            for label, launcher in [('console', [str(console)]), ('module', [sys.executable, '-m', 'sfdctrust'])]:
                evidence = work / f'{index}-{label}.json'
                settings = {
                    'home': str(home),
                    'evidence': str(evidence),
                    'path': path,
                    'params': params,
                    'pat': 'synthetic-installed-store'
                    if any(option in arguments for option in ('--store', '--store-path', '--store-alias'))
                    else 'synthetic-installed-env',
                    'payload': payload,
                    'status': failure if failure > 0 else 200,
                }
                (bootstrap / 'sitecustomize.py').write_text(
                    'import runpy\n'
                    f'runpy.run_path({str(tests / "offline/sitecustomize.py")!r})\n'
                    f'runpy.run_path({str(tests / "offline/cli_tenants.py")!r})["install"]({settings!r})\n',
                    encoding='utf-8',
                )
                result = subprocess.run(
                    [*launcher, *arguments],
                    cwd=work,
                    env={
                        **os.environ,
                        'PYTHONPATH': str(bootstrap),
                        'PYTHONDONTWRITEBYTECODE': '1',
                        'SFDCTRUST_PAT': 'synthetic-installed-env',
                    },
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                assert result.returncode == (3 if failure in {-1, 401} else 4 if failure else 0), (index, label, result.stderr)
                log = json.loads(evidence.read_text(encoding='utf-8'))
                assert log['active'] and log['closed']
                assert len(log['requests']) == (0 if failure == -1 else 1)
                assert 'Traceback' not in result.stdout + result.stderr
                assert all(
                    secret not in result.stdout + result.stderr
                    for secret in ('synthetic-installed-env', 'synthetic-installed-store', 'synthetic-server-private')
                )
                if failure:
                    assert not result.stdout and result.stderr.startswith('sfdctrust: ')
                else:
                    assert not result.stderr
                    if '--json' in arguments:
                        assert json.loads(result.stdout) == payload
                    else:
                        assert result.stdout.count('Event: synthetic-event') == 2
                        assert '+05:45' in result.stdout and 'Affected tenant IDs:' in result.stdout
                if index == 0:
                    closed_pipe(
                        [*launcher, *arguments],
                        work,
                        {
                            **os.environ,
                            'PYTHONPATH': str(bootstrap),
                            'PYTHONDONTWRITEBYTECODE': '1',
                            'SFDCTRUST_PAT': 'synthetic-installed-env',
                        },
                    )
                outputs.append((result.stdout, result.stderr))
            assert outputs[0] == outputs[1]
    print('Installed tenant commands passed (both launchers, mock HTTP, disposable stores, cleanup and outbound guard).')


def main() -> None:
    """Verify installed imports, module CLI, reads, one refresh, and reopening."""
    assert 'site-packages' in Path(sfdctrust.__file__).parts, (
        'Run this check after installing the wheel, not the editable checkout.'
    )
    cli_foundation()
    cli_tenants()
    runpy.run_path(str(Path(__file__).resolve().parent / 'offline/cli_events.py'))['check'](closed_pipe)
    runpy.run_path(str(Path(__file__).resolve().parent / 'offline/cli_qualification.py'))['check'](closed_pipe)
    original, replacement = 'synthetic-wheel-original-pat', 'synthetic-wheel-replacement-pat'
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        expected = replacement if posts else original
        assert request.headers['Authorization'] == f'Bearer {expected}'
        if request.url.path.endswith('/pats/refresh'):
            posts += 1
            return httpx.Response(200, json={'secret': replacement})
        return httpx.Response(200, json={'events': []} if request.url.path.endswith('/events/search') else {'tenants': []})

    with TemporaryDirectory() as directory:
        path = Path(directory) / 'private' / 'pat.sqlite3'
        initialized = subprocess.run(
            [sys.executable, '-m', 'sfdctrust.pat_store', 'init', '--path', str(path), '--from-env'],
            env={**os.environ, 'SFDCTRUST_PAT': original},
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert initialized.returncode == 0 and initialized.stderr == ''
        assert original not in initialized.stdout
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as client:
                assert client.tenants.list_all() == []
                end = datetime.now(UTC).replace(second=0, microsecond=0)
                assert (
                    client.events.search_all(
                        scopes=[EventSearchScope(id='synthetic-tenant')],
                        start_time=end - timedelta(days=1),
                        end_time=end,
                    )
                    == []
                )
                client.refresh_pat(expires_in_days=7)
                assert client.tenants.list_all() == []
            with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as client:
                assert client.tenants.list_all() == []
        assert posts == 1
        assert SQLitePATStore(path).load().get_pat() == replacement
    print('Installed-wheel SQLite PAT workflow passed (synthetic credentials, no network requests).')


if __name__ == '__main__':
    main()
