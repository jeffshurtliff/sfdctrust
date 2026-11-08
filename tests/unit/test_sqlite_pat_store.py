# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_sqlite_pat_store
:Synopsis:          Offline SQLite PAT persistence, permissions, and recovery tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     06 Nov 2026
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
import sys
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from sfdctrust import (
    ConfigurationError,
    PATPersistenceError,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    PATStore,
    PATStoreRecord,
    SQLitePATStore,
    TrustCenterClient,
)
from sfdctrust import _pat_store_files as files
from sfdctrust import _sqlite_pat_store as implementation
from sfdctrust.models.events import EventSearchScope

OLD = 'synthetic-sqlite-original-pat'
NEW = 'synthetic-sqlite-replacement-pat'
PAYLOAD = {
    'secret': NEW,
    'tokenId': '9aa0b1c2-d3e4-4f56-a789-0123456789ab',
    'label': 'synthetic-rotation',
    'createdAt': '2026-11-06T03:00:00.000Z',
    'expiresAt': '2026-11-13T03:00:00.000Z',
}


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / 'private' / 'pat.sqlite3'


@pytest.fixture
def store(path: Path) -> SQLitePATStore:
    return SQLitePATStore.initialize(pat=OLD, path=path)


def assert_safe(error: Exception) -> None:
    assert error.__context__ is error.__cause__ is None
    rendered = ''.join(traceback.format_exception(error))
    assert OLD not in str(error) + repr(error) + rendered
    assert NEW not in str(error) + repr(error) + rendered


def swap(store, current, replacement) -> bool:
    return store.compare_and_swap(
        expected_revision=current.revision, expected_attempt=current.pending_attempt, replacement=replacement
    )


def test_initialize_open_load_and_conditional_updates(store, path) -> None:
    assert isinstance(store, PATStore)
    original = store.load()
    assert original.get_pat() == OLD
    assert original.pending_attempt is None
    assert OLD not in repr(store) + repr(original)
    pending = PATStoreRecord(original.revision, OLD, uuid4())
    assert swap(store, original, pending)
    assert not swap(store, original, PATStoreRecord(uuid4(), NEW))
    assert SQLitePATStore(path).load().pending_attempt == pending.pending_attempt
    replacement = PATStoreRecord(uuid4(), NEW)
    assert swap(store, pending, replacement)
    reopened = SQLitePATStore(str(path)).load()
    assert reopened.revision == replacement.revision
    assert reopened.pending_attempt is None
    assert reopened.get_pat() == NEW


@pytest.mark.parametrize('alias', [None, 'secondary', 'test-store_2'])
def test_default_paths_and_aliases(tmp_path, monkeypatch, alias) -> None:
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    store = SQLitePATStore.initialize(pat=OLD, alias=alias)
    path = tmp_path / '.sfdctrust' / f'{alias or "pat"}.sqlite3'
    assert path.is_file()
    assert SQLitePATStore(alias=alias).load().revision == store.load().revision


@pytest.mark.parametrize('alias', ['', '../outside', 'a/b', 'a\\b', 'a.b', 'a b', '雪', 'CON', 'con', 'LPT9', 'PRN', 1])
def test_bad_aliases_never_create_files(tmp_path, monkeypatch, alias) -> None:
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    with pytest.raises(ConfigurationError) as caught:
        SQLitePATStore.initialize(pat=OLD, alias=alias)
    assert_safe(caught.value)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('value', ['', '\x00', 'bad\npath', 7])
def test_invalid_paths_are_safe(value) -> None:
    with pytest.raises(ConfigurationError) as caught:
        SQLitePATStore(value)
    assert_safe(caught.value)


def test_path_and_alias_are_exclusive(path) -> None:
    with pytest.raises(ConfigurationError):
        SQLitePATStore.initialize(pat=OLD, path=path, alias='secondary')
    assert not path.parent.exists()


@pytest.mark.parametrize('pat', [None, '', ' ', 'Bearer token', 'line\nbreak', '雪'])
def test_invalid_credentials_never_create_files(path, pat) -> None:
    with pytest.raises(ConfigurationError) as caught:
        SQLitePATStore.initialize(pat=pat, path=path)
    assert_safe(caught.value)
    assert not path.parent.exists()


def test_missing_database_and_intermediate_directory_never_created(path) -> None:
    with pytest.raises(ConfigurationError):
        SQLitePATStore(path)
    assert not path.parent.exists()
    with pytest.raises(ConfigurationError):
        SQLitePATStore.initialize(pat=OLD, path=path / 'missing' / 'pat.sqlite3')
    assert not path.exists()


@pytest.mark.parametrize('state', ['empty', 'seeded', 'pending'])
def test_refuse_every_existing_destination(store, path, state) -> None:
    if state == 'empty':
        path.write_bytes(b'')
    elif state == 'pending':
        current = store.load()
        assert swap(store, current, PATStoreRecord(current.revision, OLD, uuid4()))
    before = path.read_bytes()
    with pytest.raises(ConfigurationError) as caught:
        SQLitePATStore.initialize(pat=NEW, path=path)
    assert_safe(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    'mutation',
    [
        'PRAGMA user_version = 0',
        'PRAGMA user_version = 2',
        'PRAGMA application_id = 0',
        'ALTER TABLE credential ADD COLUMN extra TEXT',
        'CREATE TABLE unrelated (value TEXT)',
        'CREATE VIEW unrelated AS SELECT pat FROM credential',
        'CREATE TRIGGER ignore_update BEFORE UPDATE ON credential BEGIN SELECT RAISE(IGNORE); END',
        "UPDATE credential SET revision = 'invalid'",
        "UPDATE credential SET pending_attempt = 'invalid'",
        "UPDATE credential SET pat = 'bad value'",
        'UPDATE credential SET pat = CAST(123 AS BLOB)',
    ],
)
def test_unsupported_formats_and_corrupt_records_fail_without_modification(store, path, mutation) -> None:
    with sqlite3.connect(path) as db:
        db.execute(mutation)
    before = path.read_bytes()
    with pytest.raises(ConfigurationError) as caught:
        SQLitePATStore(path)
    assert_safe(caught.value)
    with pytest.raises(ConfigurationError):
        store.load()
    assert path.read_bytes() == before


def test_unversioned_example_and_non_database_fail_closed(path) -> None:
    # Create a protected file using the supported initializer before changing its contents.
    SQLitePATStore.initialize(pat=OLD, path=path)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA application_id=0')
        db.execute('PRAGMA user_version=0')
    before = path.read_bytes()
    with pytest.raises(ConfigurationError):
        SQLitePATStore(path)
    assert path.read_bytes() == before
    path.write_bytes(b'not a database')
    with pytest.raises(ConfigurationError):
        SQLitePATStore(path)
    assert path.read_bytes() == b'not a database'


def test_empty_supported_store_has_no_credential(store, path) -> None:
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM credential')
    assert store.load() is None
    with pytest.raises(ConfigurationError):
        TrustCenterClient.from_store(store)


def test_required_transaction_settings(store) -> None:
    with store._connect() as db:
        assert db.execute('PRAGMA journal_mode').fetchone() == ('delete',)
        assert db.execute('PRAGMA synchronous').fetchone() == (3,)
        assert db.execute('PRAGMA busy_timeout').fetchone() == (5000,)
        assert db.isolation_level is None
        assert not db.in_transaction
        if sys.platform == 'darwin':
            assert db.execute('PRAGMA fullfsync').fetchone() == (1,)


def test_reject_wal_without_changing_it(store, path) -> None:
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
    with pytest.raises(ConfigurationError):
        store.load()
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA journal_mode').fetchone() == ('wal',)


def test_regular_imports_and_static_client_work_without_sqlite(monkeypatch, store) -> None:
    actual = importlib.import_module

    def unavailable(name, *args, **kwargs):
        if name == 'sqlite3':
            raise ImportError(OLD)
        return actual(name, *args, **kwargs)

    monkeypatch.setattr(implementation.importlib, 'import_module', unavailable)
    import sfdctrust

    with sfdctrust.TrustCenterClient(OLD):
        pass
    with pytest.raises(ConfigurationError) as caught:
        store.load()
    assert_safe(caught.value)


def test_fresh_import_without_optional_storage_facilities(path) -> None:
    script = """
import importlib.abc
import sys
class MissingStorage(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlite3', 'ctypes'}:
            raise ModuleNotFoundError('Storage facility unavailable.')
sys.meta_path.insert(0, MissingStorage())
from sfdctrust import ConfigurationError, SQLitePATStore, TrustCenterClient
with TrustCenterClient('synthetic-import-pat'):
    pass
try:
    SQLitePATStore.initialize(pat='synthetic-import-pat', path=sys.argv[1])
except ConfigurationError as error:
    assert error.__cause__ is error.__context__ is None
else:
    raise AssertionError('Storage must fail clearly when facilities are missing.')
"""
    result = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stderr == result.stdout == ''


@pytest.mark.skipif(os.name != 'posix', reason='POSIX ownership and mode checks')
@pytest.mark.parametrize('target', ['directory', 'database', 'journal'])
def test_posix_permissions_checked_on_every_access(store, path, target) -> None:
    selected = path.parent if target == 'directory' else path if target == 'database' else Path(str(path) + '-journal')
    if target == 'journal':
        selected.touch(mode=0o600)
    before = selected.stat().st_mode
    selected.chmod(0o755 if target == 'directory' else 0o644)
    try:
        with pytest.raises(ConfigurationError) as caught:
            store.load()
        assert_safe(caught.value)
        current = PATStoreRecord(uuid4(), NEW)
        with pytest.raises(PATPersistenceError):
            swap(store, current, current)
        assert selected.stat().st_mode & 0o077
    finally:
        selected.chmod(before)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX ownership check')
def test_wrong_owner_is_rejected(store, monkeypatch) -> None:
    actual = os.getuid()
    monkeypatch.setattr(files.os, 'getuid', lambda: actual + 1)
    with pytest.raises(ConfigurationError):
        store.load()


@pytest.mark.skipif(os.name != 'posix', reason='POSIX untrusted ancestry check')
def test_untrusted_parent_refused_without_repair(tmp_path) -> None:
    parent = tmp_path / 'shared'
    parent.mkdir(mode=0o777)
    parent.chmod(0o777)
    path = parent / 'private' / 'pat.sqlite3'
    with pytest.raises(ConfigurationError):
        SQLitePATStore.initialize(pat=OLD, path=path)
    assert not path.exists()
    assert parent.stat().st_mode & 0o777 == 0o777


def test_replaced_database_and_directory_refused(store, path) -> None:
    replacement = path.parent / 'other.sqlite3'
    SQLitePATStore.initialize(pat=NEW, path=replacement)
    replacement.replace(path)
    with pytest.raises(ConfigurationError):
        store.load()
    reopened = SQLitePATStore(path)
    previous = path.parent.with_name('previous')
    path.parent.rename(previous)
    SQLitePATStore.initialize(pat=OLD, path=path)
    with pytest.raises(ConfigurationError):
        reopened.load()


def test_hard_linked_database_refused(store, path) -> None:
    other = path.with_name('hardlink.sqlite3')
    os.link(path, other)
    with pytest.raises(ConfigurationError):
        store.load()


@pytest.mark.skipif(os.name == 'nt', reason='Windows native reparse test is separate and requires no symlink privilege')
@pytest.mark.parametrize('target', ['directory', 'database', 'journal'])
def test_symbolic_links_refused(store, path, target) -> None:
    if target == 'directory':
        previous = path.parent.with_name('previous')
        path.parent.rename(previous)
        path.parent.symlink_to(previous, target_is_directory=True)
        with pytest.raises(ConfigurationError):
            SQLitePATStore(path)
    else:
        source = path.with_name('source')
        if target == 'database':
            path.rename(source)
            path.symlink_to(source)
        else:
            source.touch(mode=0o600)
            Path(str(path) + '-journal').symlink_to(source)
        with pytest.raises(ConfigurationError):
            store.load()


class FaultStore:
    """Inject an acknowledgment failure around a real SQLite write."""

    def __init__(self, store, *, write_number: int, after: bool) -> None:
        self.store, self.write_number, self.after = store, write_number, after
        self.writes = 0

    def load(self):
        return self.store.load()

    def compare_and_swap(self, **kwargs):
        self.writes += 1
        fail = self.writes == self.write_number
        if fail and not self.after:
            raise OSError(NEW)
        result = self.store.compare_and_swap(**kwargs)
        if fail:
            raise OSError(NEW)
        return result


def test_complete_client_workflow_and_reopen(store, path) -> None:
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/pats/refresh'):
            # The marker is durably visible to another adapter before the POST.
            assert SQLitePATStore(path).load().pending_attempt is not None
            return httpx.Response(200, json=PAYLOAD)
        expected = NEW if any(item.url.path.endswith('/pats/refresh') for item in requests) else OLD
        assert request.headers['Authorization'] == f'Bearer {expected}'
        if request.url.path.endswith('/events/search'):
            return httpx.Response(200, json={'events': []})
        return httpx.Response(200, json={'tenants': []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with TrustCenterClient.from_store(store, http_client=http) as client:
            assert client.tenants.list_all() == []
            end = datetime.now(UTC).replace(second=0, microsecond=0)
            assert (
                client.events.search_all(
                    scopes=[EventSearchScope(id='synthetic-tenant')], start_time=end - timedelta(days=1), end_time=end
                )
                == []
            )
            assert client.refresh_pat(expires_in_days=7).metadata_valid
            assert client.tenants.list_all() == []
        with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as reopened:
            assert reopened.tenants.list_all() == []
    assert sum(request.url.path.endswith('/pats/refresh') for request in requests) == 1


@pytest.mark.parametrize('after', [False, True])
def test_real_database_persistence_recovery_has_no_second_post(store, path, after) -> None:
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(200, json=PAYLOAD)

    fault = FaultStore(store, write_number=2, after=after)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with TrustCenterClient.from_store(fault, http_client=http) as client:
            with pytest.raises(PATPersistenceError) as caught:
                client.refresh_pat()
            assert_safe(caught.value)
            assert store.load().get_pat() == (NEW if after else OLD)
            assert client.retry_pat_persistence().metadata_valid
            assert SQLitePATStore(path).load().get_pat() == NEW
    assert requests == ['POST']


@pytest.mark.parametrize('after', [False, True])
def test_unconfirmed_marker_never_sends_http(store, after) -> None:
    fault = FaultStore(store, write_number=1, after=after)

    def unexpected(request):
        pytest.fail('No HTTP is allowed before marker acknowledgment.')

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as http:
        with TrustCenterClient.from_store(fault, http_client=http) as client:
            with pytest.raises(PATPersistenceError):
                client.refresh_pat()
    assert (store.load().pending_attempt is not None) is after


def test_ambiguous_post_preserves_marker(store) -> None:
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(500 if request.method == 'POST' else 200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with TrustCenterClient.from_store(store, http_client=http) as client:
            with pytest.raises(PATRefreshAmbiguousError):
                client.refresh_pat()
    assert methods == ['POST', 'GET']
    with pytest.raises(PATRefreshPendingError):
        TrustCenterClient.from_store(store)


def test_actual_sqlite_lock_failure_is_safe(store, path, monkeypatch) -> None:
    current = store.load()
    connect = sqlite3.connect

    def short_timeout(*args, **kwargs):
        kwargs['timeout'] = 0.01
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', short_timeout)
    with connect(path) as locked:
        locked.execute('BEGIN IMMEDIATE')
        with pytest.raises(PATPersistenceError) as caught:
            swap(store, current, PATStoreRecord(current.revision, OLD, uuid4()))
        assert_safe(caught.value)
    assert store.load().pending_attempt is None


def test_sqlite_write_error_rolls_back_and_does_not_report_mismatch(store, monkeypatch) -> None:
    current = store.load()
    connect = store._connect

    @contextmanager
    def read_only():
        with connect() as db:
            db.execute('PRAGMA query_only=ON')
            yield db

    monkeypatch.setattr(store, '_connect', read_only)
    with pytest.raises(PATPersistenceError) as caught:
        swap(store, current, PATStoreRecord(uuid4(), NEW))
    assert_safe(caught.value)
    assert store.load().get_pat() == OLD
