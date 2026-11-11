# -*- coding: utf-8 -*-
"""
:Module:            tests.pat_recovery_rehearsal
:Synopsis:          Offline installed-wheel SQLite PAT operator recovery rehearsal
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     11 Nov 2026
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import sysconfig
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import distribution
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import httpx

import sfdctrust
from sfdctrust import (
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    PATStoreRecord,
    SQLitePATStore,
    TrustCenterClient,
)

OLD = 'synthetic-rehearsal-original-pat'
NEW = 'synthetic-rehearsal-replacement-pat'
FRESH = 'synthetic-rehearsal-fresh-pat'
SCRIPT = Path(__file__).resolve()
BLOCKED = 0


def deny_network(event: str, arguments: tuple) -> None:
    """Block socket creation and DNS in this interpreter, including missed mocks."""
    global BLOCKED
    if event.startswith('socket.'):
        BLOCKED += 1
        raise RuntimeError('Networking is disabled for the offline rehearsal.')


def install_network_guard() -> None:
    """Install and exercise the guard before any rehearsal or child operation."""
    sys.addaudithook(deny_network)
    with raises(RuntimeError):
        socket.socket()
    with raises(RuntimeError):
        socket.getaddrinfo('example.invalid', 443)
    assert BLOCKED == 2


@contextmanager
def raises(expected):
    """Require an exception without rendering its potentially sensitive context."""
    try:
        yield
    except expected:
        return
    raise AssertionError('The expected protective failure did not occur.')


def installed() -> None:
    """Reject source/editable imports and interpreters outside a virtual environment."""
    if sys.flags.optimize or not sys.flags.isolated:
        raise RuntimeError('Run with -I and without -O so isolation and assertions remain enabled.')
    assert sys.prefix != sys.base_prefix
    assert Path(sfdctrust.__file__).resolve().is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    direct = distribution('sfdctrust').read_text('direct_url.json')
    assert not direct or not json.loads(direct).get('dir_info', {}).get('editable', False)


def same(left, right) -> bool:
    return (left.revision, left.pending_attempt, left.get_pat()) == (right.revision, right.pending_attempt, right.get_pat())


def swap(store, observed, replacement) -> bool:
    return store.compare_and_swap(
        expected_revision=observed.revision, expected_attempt=observed.pending_attempt, replacement=replacement
    )


class FaultStore:
    """Reuse the real-store boundary fault pattern from test_sqlite_pat_store."""

    def __init__(self, store, *, write_number: int, after: bool) -> None:
        self.store, self.write_number, self.after = store, write_number, after
        self.writes = 0
        self.unavailable = False

    def load(self):
        if self.unavailable:
            raise OSError('Simulated storage outage.')
        return self.store.load()

    def compare_and_swap(self, **kwargs):
        self.writes += 1
        fail = self.writes == self.write_number
        if fail and not self.after:
            raise OSError('Simulated write failure before commit.')
        result = self.store.compare_and_swap(**kwargs)
        if fail:
            raise OSError('Simulated lost acknowledgment after commit.')
        return result


class Service:
    """Count only methods; never retain requests, headers, or response payloads."""

    def __init__(self, *, probe=200, ambiguous=False, expected=OLD) -> None:
        self.methods = []
        self.probe, self.ambiguous, self.expected = probe, ambiguous, expected

    def __call__(self, request):
        self.methods.append(request.method)
        assert request.headers['Authorization'] == f'Bearer {self.expected}'
        if request.method == 'POST':
            assert request.url.path.endswith('/pats/refresh')
            if self.ambiguous:
                raise httpx.ReadTimeout('Simulated ambiguous refresh.', request=request)
            return httpx.Response(200, json={'secret': NEW})
        assert request.method == 'GET' and request.url.path.endswith('/tenants')
        if self.probe == 'timeout':
            raise httpx.ReadTimeout('Simulated inconclusive probe.', request=request)
        return httpx.Response(self.probe, json={'tenants': []})


def child(mode: str, path: Path, expected='replacement'):
    # Do not forward credentials, proxy settings, PYTHONPATH, or user startup settings.
    environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
    result = subprocess.run(
        [sys.executable, '-I', str(SCRIPT), '--worker', mode, '--path', str(path), '--expected', expected],
        cwd=path.parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.stderr == '', 'Child failed; output withheld to keep evidence sanitized.'
    assert result.returncode == (73 if mode == 'lose' else 0), 'Child did not complete the expected transition.'
    return json.loads(result.stdout)


def worker(mode: str, path: Path, expected: str) -> None:
    installed()
    if mode == 'read':
        service = Service(expected=NEW if expected == 'replacement' else FRESH if expected == 'fresh' else OLD)
        with httpx.Client(transport=httpx.MockTransport(service)) as http:
            with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http, max_retries=0) as client:
                assert client.tenants.list().tenants == []
        assert service.methods == ['GET'] and BLOCKED == 2
        print(json.dumps({'state': 'fresh-process-read-passed', 'refresh_posts': 0, 'http': 1}))
        return

    store = SQLitePATStore(path)
    original_swap = store.compare_and_swap
    service = Service()

    def exit_before_commit(**kwargs):
        if kwargs['replacement'].get_pat() == NEW:
            assert service.methods == ['POST'] and BLOCKED == 2
            print(json.dumps({'state': 'service-rotated-replacement-not-saved', 'methods': service.methods}), flush=True)
            # As in test_sqlite_pat_processes: bypass all Python cleanup.
            os._exit(73)
        return original_swap(**kwargs)

    with patch.object(store, 'compare_and_swap', side_effect=exit_before_commit):
        with httpx.Client(transport=httpx.MockTransport(service)) as http:
            with TrustCenterClient.from_store(store, http_client=http) as client:
                client.refresh_pat()
    raise AssertionError('The crash boundary was not reached.')


def record(rows, case, state, methods, *, recovery_http=0, verification_http=0):
    rows.append(
        {
            'case': case,
            'expected_state': state,
            'observed_state': state,
            'refresh_posts': methods.count('POST'),
            'initial_probe_http': methods.count('GET'),
            'recovery_http': recovery_http,
            'fresh_process_verification_http': verification_http,
            'passed': True,
        }
    )


def pending_cases(root, rows):
    for probe, expected in [
        (200, PATProbeResult.OLD_PAT_ACCEPTED),
        (401, PATProbeResult.OLD_PAT_REJECTED),
        (503, PATProbeResult.INCONCLUSIVE),
        ('timeout', PATProbeResult.INCONCLUSIVE),
    ]:
        path = root / f'pending-{probe}' / 'pat.sqlite3'
        store = SQLitePATStore.initialize(pat=OLD, path=path)
        service = Service(probe=probe, ambiguous=True)
        with httpx.Client(transport=httpx.MockTransport(service)) as http:
            with TrustCenterClient.from_store(store, http_client=http) as client:
                try:
                    client.refresh_pat()
                except PATRefreshAmbiguousError as error:
                    assert error.probe == expected
                else:
                    raise AssertionError('Ambiguous refresh did not fail closed.')
                observed = store.load()
                assert observed.pending_attempt is not None and observed.get_pat() == OLD
                assert same(SQLitePATStore(path).load(), observed)
                with raises(PATRefreshPendingError):
                    TrustCenterClient.from_store(SQLitePATStore(path), http_client=http)
                with raises(PATRefreshPendingError):
                    client.refresh_pat()
                with raises(PATRefreshPendingError):
                    client.tenants.list()
                assert service.methods == ['POST', 'GET']
                assert same(store.load(), observed)

        # Accepted at one instant is insufficient while the request could still settle.
        # The simulated operator now stops all rotators and establishes settlement.
        if probe == 200:
            settled_probe = Service()
            with httpx.Client(transport=httpx.MockTransport(settled_probe)) as http:
                with TrustCenterClient(observed.get_pat(), http_client=http, max_retries=0) as controlled:
                    assert controlled.tenants.list().tenants == []
            assert settled_probe.methods == ['GET']
            assert swap(store, observed, PATStoreRecord(observed.revision, observed.get_pat()))
            cleared = SQLitePATStore(path).load()
            assert cleared.revision == observed.revision and cleared.pending_attempt is None and cleared.get_pat() == OLD
            # Independently stale revision and stale attempt must both leave newer state intact.
            for newer in [
                PATStoreRecord(cleared.revision, OLD, uuid4()),
                PATStoreRecord(uuid4(), FRESH, observed.pending_attempt),
            ]:
                assert swap(store, cleared, newer)
                assert not swap(store, observed, PATStoreRecord(observed.revision, OLD))
                assert same(SQLitePATStore(path).load(), newer)
                assert swap(store, newer, cleared)
            assert child('read', path, 'old')['http'] == 1
            record(
                rows,
                f'pending-probe-{probe}',
                'settled-old-accepted-exact-clear-stale-matches-refused',
                service.methods,
                recovery_http=len(settled_probe.methods),
                verification_http=1,
            )
        else:
            assert same(SQLitePATStore(path).load(), observed)
            record(rows, f'pending-probe-{probe}', 'old-pending-preserved-no-replay', service.methods)


def claim_cases(root, rows):
    for after in (False, True):
        path = root / f'claim-{after}' / 'pat.sqlite3'
        store = SQLitePATStore.initialize(pat=OLD, path=path)
        service = Service()
        fault = FaultStore(store, write_number=1, after=after)
        with httpx.Client(transport=httpx.MockTransport(service)) as http:
            with TrustCenterClient.from_store(fault, http_client=http) as client:
                with raises(PATPersistenceError):
                    client.refresh_pat()
        assert service.methods == []
        reopened = SQLitePATStore(path).load()
        assert reopened.get_pat() == OLD and (reopened.pending_attempt is not None) == after
        if after:
            with httpx.Client(transport=httpx.MockTransport(service)) as http:
                with raises(PATRefreshPendingError):
                    TrustCenterClient.from_store(SQLitePATStore(path), http_client=http)
        assert service.methods == []
        record(rows, f'unacknowledged-claim-{after}', 'old-pending' if after else 'old-ready-no-post', service.methods)


def persistence_cases(root, rows):
    for after in (False, True):
        for conflict in (None, 'revision', 'attempt'):
            path = root / f'persistence-{after}-{conflict}' / 'pat.sqlite3'
            store = SQLitePATStore.initialize(pat=OLD, path=path)
            original = store.load()
            service = Service()
            fault = FaultStore(store, write_number=2, after=after)
            with httpx.Client(transport=httpx.MockTransport(service)) as http:
                with TrustCenterClient.from_store(fault, http_client=http) as client:
                    with raises(PATPersistenceError):
                        client.refresh_pat()
                    observed = SQLitePATStore(path).load()
                    assert observed.get_pat() == (NEW if after else OLD)
                    assert (observed.pending_attempt is None) == after
                    assert (observed.revision != original.revision) == after
                    with raises(PATPersistenceError):
                        client.tenants.list()
                    with raises(PATPersistenceError):
                        client.refresh_pat()
                    before = len(service.methods)
                    fault.unavailable = True
                    with raises(PATPersistenceError):
                        client.retry_pat_persistence()
                    fault.unavailable = False
                    if conflict:
                        changed = PATStoreRecord(
                            uuid4() if conflict == 'revision' else observed.revision,
                            observed.get_pat(),
                            observed.pending_attempt if conflict == 'revision' else uuid4(),
                        )
                        assert swap(store, observed, changed)
                        with raises(PATPersistenceError):
                            client.retry_pat_persistence()
                        assert same(SQLitePATStore(path).load(), changed)
                        state = f'different-{conflict}-preserved-retry-refused'
                        verification = 0
                    else:
                        client.retry_pat_persistence()
                        saved = SQLitePATStore(path).load()
                        assert saved.get_pat() == NEW and saved.pending_attempt is None
                        assert saved.revision != original.revision
                        assert child('read', path)['http'] == 1
                        state, verification = 'replacement-durable-marker-clear-fresh-process-read', 1
                    assert len(service.methods) == before and service.methods == ['POST']
                    record(
                        rows,
                        f'persistence-{after}-{conflict}',
                        state,
                        service.methods,
                        recovery_http=len(service.methods) - before,
                        verification_http=verification,
                    )


def lost_case(root, rows):
    path = root / 'lost' / 'pat.sqlite3'
    SQLitePATStore.initialize(pat=OLD, path=path)
    crashed = child('lose', path)
    assert crashed['methods'] == ['POST']
    observed = SQLitePATStore(path).load()
    assert observed.get_pat() == OLD and observed.pending_attempt is not None
    with raises(PATRefreshPendingError):
        TrustCenterClient.from_store(SQLitePATStore(path))
    # Simulate pausing ALL jobs, revoking the active PAT, and issuing a fresh PAT.
    jobs = {'monitor': path, 'rotator': path}
    running = False
    new_path = path.with_name('recovered.sqlite3')
    SQLitePATStore.initialize(pat=FRESH, path=new_path)
    for job in jobs:
        jobs[job] = new_path
    assert not running and set(jobs.values()) == {new_path}
    verification = child('read', new_path, 'fresh')
    assert verification['http'] == 1 and verification['refresh_posts'] == 0
    assert same(SQLitePATStore(path).load(), observed)
    running = True
    assert running
    # Old sources remain quarantined; disposal is an operator policy, not secure erasure.
    record(
        rows,
        'replacement-lost-process-exit',
        'old-blocked-all-jobs-new-store-verified-before-resume',
        crashed['methods'],
        verification_http=verification['http'],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--source-commit')
    parser.add_argument('--source-branch')
    parser.add_argument('--source-state')
    parser.add_argument('--worker', choices=('read', 'lose'))
    parser.add_argument('--path', type=Path)
    parser.add_argument('--expected', default='replacement')
    args = parser.parse_args()
    install_network_guard()
    installed()
    if args.worker:
        worker(args.worker, args.path, args.expected)
        return
    assert args.wheel and args.source_commit and args.source_branch and args.source_state
    wheel = args.wheel.resolve()
    # Check every installed package file against the supplied artifact.
    with ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith('sfdctrust/') and not name.endswith('/'):
                assert (Path(sfdctrust.__file__).parent.parent / name).read_bytes() == archive.read(name)
    rows = []
    with TemporaryDirectory(prefix='sfdctrust-recovery-') as directory:
        root = Path(directory)
        pending_cases(root, rows)
        claim_cases(root, rows)
        persistence_cases(root, rows)
        lost_case(root, rows)
    assert BLOCKED == 2, 'An unexpected networking attempt was blocked.'
    print(
        json.dumps(
            {
                'source_commit': args.source_commit,
                'source_branch': args.source_branch,
                'source_state': args.source_state,
                'package_version': distribution('sfdctrust').version,
                'wheel': wheel.name,
                'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                'rehearsal_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                'python': platform.python_version(),
                'runtime_dependencies': {
                    name: distribution(name).version
                    for name in (
                        'httpx',
                        'httpcore',
                        'anyio',
                        'certifi',
                        'idna',
                        'h11',
                        'pydantic',
                        'pydantic-core',
                        'annotated-types',
                        'typing-extensions',
                        'typing-inspection',
                    )
                },
                'platform': f'{platform.system()} {platform.release()} {platform.machine()}',
                'date_utc': datetime.now(UTC).isoformat(),
                'imports': 'non-editable site-packages; package files match wheel; isolated venv interpreter',
                'network_guard': 'socket audit guard tested in parent and every child; zero unexpected attempts',
                'scope': 'synthetic PATs, disposable SQLite, mocked HTTP and operator actions',
                'cases': rows,
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
