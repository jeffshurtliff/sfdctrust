# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_sqlite_pat_processes
:Synopsis:          Spawned-process coordination and crash recovery with real SQLite
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     08 Nov 2026
"""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
from contextlib import contextmanager
from multiprocessing.connection import wait
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from sfdctrust import ConfigurationError, PATRefreshPendingError, PATStoreRecord, SQLitePATStore, TrustCenterClient

OLD = 'synthetic-process-original-pat'
NEW = 'synthetic-process-replacement-pat'
PAYLOAD = {'secret': NEW}


@pytest.fixture(autouse=True)
def spawn_imports(monkeypatch) -> None:
    # importlib-mode pytest does not put the checkout on sys.path. A spawned
    # interpreter must be able to import its test worker functions by module name.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))


def _refresh_worker(path, barrier, release, channel):
    def handler(request):
        assert request.method == 'POST'
        channel.send('POST')
        assert release.wait(15)
        return httpx.Response(200, json=PAYLOAD)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as client:
            barrier.wait(timeout=15)
            try:
                client.refresh_pat()
            except PATRefreshPendingError:
                channel.send('blocked')
            else:
                channel.send('saved')


def _init_worker(path, barrier, channel):
    barrier.wait(timeout=15)
    try:
        SQLitePATStore.initialize(pat=OLD, path=path)
    except ConfigurationError:
        channel.send('refused')
    else:
        channel.send('created')


def _exit_worker(path, mode, channel):
    store = SQLitePATStore(path)
    current = store.load()
    attempt = uuid4()
    pending = PATStoreRecord(current.revision, OLD, attempt)
    assert store.compare_and_swap(expected_revision=current.revision, expected_attempt=None, replacement=pending)
    if mode in {'uncommitted', 'unsupported'}:
        db = sqlite3.connect(path, isolation_level=None)
        if mode == 'unsupported':
            db.execute('PRAGMA user_version=2')
        db.execute('PRAGMA synchronous=EXTRA')
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE credential SET revision=?, pat=?, pending_attempt=NULL', (str(uuid4()), NEW))
    channel.send(str(attempt))
    # Deliberately bypass connection cleanup to leave the journal for SQLite recovery
    os._exit(0)


def _lost_replacement_worker(path, channel):
    store = SQLitePATStore(path)

    class ExitBeforeCommit:
        def load(self):
            return store.load()

        def compare_and_swap(self, **kwargs):
            if kwargs['replacement'].get_pat() == NEW:
                channel.send('replacement-lost')
                os._exit(0)
            return store.compare_and_swap(**kwargs)

    def handler(request):
        assert request.method == 'POST'
        channel.send('POST')
        return httpx.Response(200, json=PAYLOAD)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with TrustCenterClient.from_store(ExitBeforeCommit(), http_client=http) as client:
            client.refresh_pat()


@contextmanager
def _children(target, arguments):
    context = multiprocessing.get_context('spawn')
    children = []
    channels = []
    try:
        for args in arguments:
            receive, send = context.Pipe(duplex=False)
            child = context.Process(target=target, args=(*args, send))
            child.start()
            send.close()
            children.append(child)
            channels.append(receive)
        yield children, channels
    finally:
        for child in children:
            child.join(timeout=5)
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
        for channel in channels:
            channel.close()


def _receive(channel):
    assert channel.poll(15), 'Child did not report its state.'
    return channel.recv()


def test_two_processes_can_send_only_one_refresh_post(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=OLD, path=path)
    context = multiprocessing.get_context('spawn')
    barrier, release = context.Barrier(2), context.Event()
    with _children(_refresh_worker, [(path, barrier, release)] * 2) as (children, channels):
        first = []
        remaining = channels.copy()
        try:
            while remaining:
                ready = wait(remaining, timeout=15)
                assert ready
                for channel in ready:
                    first.append(_receive(channel))
                    remaining.remove(channel)
            assert sorted(first) == ['POST', 'blocked']
        finally:
            release.set()
        # Find the winner by readiness; the loser has exited and its pipe is at EOF
        saved = []
        for channel in channels:
            try:
                if channel.poll(15):
                    saved.append(channel.recv())
            except EOFError:
                pass
        assert saved == ['saved']
        for child in children:
            child.join(timeout=15)
            assert child.exitcode == 0
    assert store.load().get_pat() == NEW
    assert store.load().pending_attempt is None


def test_competing_initializers_never_overwrite(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    barrier = multiprocessing.get_context('spawn').Barrier(2)
    with _children(_init_worker, [(path, barrier)] * 2) as (children, channels):
        assert sorted(_receive(channel) for channel in channels) == ['created', 'refused']
        for child in children:
            child.join(timeout=15)
            assert child.exitcode == 0
    assert SQLitePATStore(path).load().get_pat() == OLD


@pytest.mark.parametrize('mode', ['pending', 'uncommitted'])
def test_pending_survives_process_exit_and_uncommitted_replacement_rolls_back(tmp_path, mode) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    SQLitePATStore.initialize(pat=OLD, path=path)
    with _children(_exit_worker, [(path, mode)]) as (children, channels):
        attempt = _receive(channels[0])
        children[0].join(timeout=15)
        assert children[0].exitcode == 0
    current = SQLitePATStore(path).load()
    assert current.get_pat() == OLD
    assert str(current.pending_attempt) == attempt
    with pytest.raises(PATRefreshPendingError):
        TrustCenterClient.from_store(SQLitePATStore(path))


def test_replacement_lost_on_process_exit_preserves_pending_attempt(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    SQLitePATStore.initialize(pat=OLD, path=path)
    with _children(_lost_replacement_worker, [(path,)]) as (children, channels):
        assert _receive(channels[0]) == 'POST'
        assert _receive(channels[0]) == 'replacement-lost'
        children[0].join(timeout=15)
        assert children[0].exitcode == 0
    record = SQLitePATStore(path).load()
    assert record.get_pat() == OLD
    assert record.pending_attempt is not None


def test_unsupported_format_hot_journal_is_not_recovered_or_modified(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    SQLitePATStore.initialize(pat=OLD, path=path)
    with _children(_exit_worker, [(path, 'unsupported')]) as (children, channels):
        _receive(channels[0])
        children[0].join(timeout=15)
        assert children[0].exitcode == 0
    journal = Path(str(path) + '-journal')
    before, journal_before = path.read_bytes(), journal.read_bytes()
    with pytest.raises(ConfigurationError):
        SQLitePATStore(path)
    assert path.read_bytes() == before
    assert journal.read_bytes() == journal_before
