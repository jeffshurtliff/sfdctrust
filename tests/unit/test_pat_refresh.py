# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_pat_refresh
:Synopsis:          Offline PAT rotation and durable store boundary tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import json
import os
import pickle
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from uuid import UUID, uuid4

import httpx
import pytest

from sfdctrust import (
    AuthenticationError,
    ConfigurationError,
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    PATRefreshResult,
    PATStore,
    PATStoreRecord,
    RateLimitError,
    TrustCenterClient,
)

OLD = 'synthetic-original-test-pat'
NEW = 'synthetic-replacement-test-pat'
STALE = 'synthetic-stale-environment-pat'
ENDPOINT = 'https://api.salesforce.com/platform/mytrust/v1'
PAYLOAD = {
    'secret': NEW,
    'tokenId': '9aa0b1c2-d3e4-4f56-a789-0123456789ab',
    'label': 'synthetic-rotation',
    'createdAt': '2026-11-04T03:00:00.000Z',
    'expiresAt': '2026-12-04T03:00:00.000Z',
}


class MemoryPATStore:
    """Test-only CAS adapter. Its state survives client reconstruction, not process exit."""

    def __init__(self, pat: str | None = OLD) -> None:
        self._lock = Lock()
        self.record = None if pat is None else PATStoreRecord(uuid4(), pat)
        self.load_fails = False
        self.fail_write: tuple[int, str] | None = None
        self.swaps = 0

    def load(self) -> PATStoreRecord | None:
        with self._lock:
            if self.load_fails:
                raise OSError(f'Store error with {NEW}')
            return self.record

    def compare_and_swap(self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord) -> bool:
        with self._lock:
            self.swaps += 1
            if self.fail_write == (self.swaps, 'before'):
                raise OSError(f'Cannot write {replacement.get_pat()}')
            if self.record is None or (self.record.revision, self.record.pending_attempt) != (
                expected_revision,
                expected_attempt,
            ):
                return False
            self.record = replacement
            if self.fail_write == (self.swaps, 'after'):
                raise OSError(f'Lost acknowledgment for {replacement.get_pat()}')
            return True


@pytest.fixture
def api() -> Iterator[Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]]:
    clients: list[httpx.Client] = []

    def make(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def no_http(request: httpx.Request) -> httpx.Response:
    pytest.fail(f'Unexpected {request.method} request')


def assert_safe(error: Exception) -> None:
    assert error.__cause__ is error.__context__ is None
    for display in (str(error), repr(error), ''.join(traceback.format_exception(error))):
        for forbidden in (OLD, NEW, STALE, ENDPOINT, 'Bearer ', 'store-exception-marker'):
            assert forbidden not in display


@pytest.mark.parametrize('source', ['explicit', 'env', 'override'])
def test_static_modes_keep_precedence_and_reject_refresh(source, monkeypatch, api) -> None:
    monkeypatch.setenv('SFDCTRUST_PAT', STALE)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == 'GET'
        assert request.headers['Authorization'] == f'Bearer {STALE if source == "env" else OLD}'
        return httpx.Response(401, text=NEW)

    http = api(handler)
    if source == 'explicit':
        client = TrustCenterClient(OLD, http_client=http)
    elif source == 'env':
        client = TrustCenterClient.from_env(http_client=http)
    else:
        client = TrustCenterClient.from_env(pat=OLD, http_client=http)
    with pytest.raises(ConfigurationError):
        client.refresh_pat()
    with pytest.raises(ConfigurationError):
        client.retry_pat_persistence()
    with pytest.raises(AuthenticationError) as caught:
        client.tenants.list()
    assert_safe(caught.value)
    assert os.environ['SFDCTRUST_PAT'] == STALE


def test_store_loading_fails_closed_and_never_falls_back(monkeypatch, api) -> None:
    class BrokenAdapter(MemoryPATStore):
        @property
        def load(self):
            raise OSError(f'Adapter setup failed: {NEW}')

    monkeypatch.setenv('SFDCTRUST_PAT', STALE)
    unreadable = MemoryPATStore()
    unreadable.load_fails = True
    wrong = MemoryPATStore()
    wrong.record = OLD
    for store in (None, object(), MemoryPATStore(None), unreadable, wrong, BrokenAdapter()):
        with pytest.raises(ConfigurationError) as caught:
            TrustCenterClient.from_store(store, http_client=api(no_http))
        assert_safe(caught.value)
    with pytest.raises(ConfigurationError):
        PATStoreRecord(uuid4(), 'unsafe\nvalue')
    with pytest.raises(ConfigurationError):
        PATStoreRecord('bad-version', OLD)


@pytest.mark.parametrize('days', [True, False, 0, 31, -1, '7', 1.0, [], {}])
def test_invalid_lifetime_never_writes_or_sends(days, api) -> None:
    store = MemoryPATStore()
    client = TrustCenterClient.from_store(store, http_client=api(no_http))
    with pytest.raises(ConfigurationError, match='expires_in_days'):
        client.refresh_pat(expires_in_days=days)
    assert store.swaps == 0
    assert store.record.pending_attempt is None


@pytest.mark.parametrize('days', [None, 1, 30])
def test_store_success_commits_before_auth_switch_and_reloads_other_clients(days, monkeypatch, caplog, api) -> None:
    monkeypatch.setenv('SFDCTRUST_PAT', STALE)
    store = MemoryPATStore()
    original_revision = store.record.revision
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.extensions['timeout'] == dict(connect=5.0, pool=5.0, read=30.0, write=30.0)
        if request.method == 'POST':
            assert str(request.url) == ENDPOINT + '/pats/refresh'
            assert request.headers['Authorization'] == f'Bearer {OLD}'
            assert store.record.pending_attempt is not None
            assert store.record.revision == original_revision
            if days is None:
                assert not request.content
                assert 'Content-Type' not in request.headers
            else:
                assert json.loads(request.content) == {'expiresInDays': days}
            # A response label can contain arbitrary text. It never appears in the result.
            return httpx.Response(200, json={**PAYLOAD, 'label': NEW})
        assert str(request.url) == ENDPOINT + '/tenants'
        assert store.record.get_pat() == NEW
        assert request.headers['Authorization'] == f'Bearer {NEW}'
        return httpx.Response(200, json={'tenants': []})

    assert isinstance(store, PATStore)
    http = api(handler)
    older = TrustCenterClient.from_store(store, http_client=http)
    with TrustCenterClient.from_store(store, http_client=http, max_retries=5) as client:
        with caplog.at_level('INFO'):
            result = client.refresh_pat(expires_in_days=days)
            assert result == PATRefreshResult(metadata_valid=True)
            assert store.record.pending_attempt is None
            assert store.record.revision != original_revision
            assert client.tenants.list().tenants == []
            with pytest.raises(ConfigurationError, match='reload'):
                older.tenants.list()
            with TrustCenterClient.from_store(store, http_client=http) as reloaded:
                assert reloaded.tenants.list().tenants == []
    assert methods == ['POST', 'GET', 'GET']
    assert os.environ['SFDCTRUST_PAT'] == STALE
    assert not http.is_closed
    for output in (repr(store.record), repr(result), repr(vars(client)), caplog.text):
        assert OLD not in output and NEW not in output
    with pytest.raises(TypeError, match='cannot be serialized'):
        pickle.dumps(store.record)


def test_refresh_reads_latest_pat_even_when_client_was_constructed_earlier(api) -> None:
    store = MemoryPATStore()
    auth = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers['Authorization'])
        return httpx.Response(200, json={**PAYLOAD, 'secret': f'{NEW}-{len(auth)}'})

    http = api(handler)
    first = TrustCenterClient.from_store(store, http_client=http)
    second = TrustCenterClient.from_store(store, http_client=http)
    first.refresh_pat()
    second.refresh_pat()
    assert auth == [f'Bearer {OLD}', f'Bearer {NEW}-1']


def test_competing_rotators_compare_and_swap_before_post(api) -> None:
    barrier = Barrier(2, timeout=5)
    post_started, post_can_finish = Event(), Event()

    class RacingStore(MemoryPATStore):
        def compare_and_swap(self, **kwargs) -> bool:
            if kwargs['expected_attempt'] is None:
                barrier.wait()
            return super().compare_and_swap(**kwargs)

    store = RacingStore()
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.method)
        post_started.set()
        assert post_can_finish.wait(timeout=5)
        return httpx.Response(200, json=PAYLOAD)

    clients = [TrustCenterClient.from_store(store, http_client=api(handler)) for _ in range(2)]

    def rotate(client: TrustCenterClient) -> str:
        try:
            client.refresh_pat()
        except PATRefreshPendingError:
            post_can_finish.set()
            return 'blocked'
        return 'success'

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [executor.submit(rotate, client) for client in clients]
        assert post_started.wait(timeout=5)
        assert sorted(outcome.result(timeout=5) for outcome in outcomes) == ['blocked', 'success']
    assert posts == ['POST']


def test_process_loss_does_not_clear_pending_marker(api) -> None:
    class ProcessLost(BaseException):
        pass

    def crash(_: httpx.Request) -> httpx.Response:
        raise ProcessLost

    store = MemoryPATStore()
    client = TrustCenterClient.from_store(store, http_client=api(crash))
    observer = TrustCenterClient.from_store(store, http_client=api(no_http))
    with pytest.raises(ProcessLost):
        client.refresh_pat()
    assert store.record.pending_attempt is not None
    with pytest.raises(PATRefreshPendingError):
        TrustCenterClient.from_store(store, http_client=api(no_http))
    with pytest.raises(PATRefreshPendingError):
        observer.refresh_pat()
    with pytest.raises(PATRefreshPendingError):
        observer.tenants.list()


@pytest.mark.parametrize('failure', ['before', 'after'])
def test_unconfirmed_pending_write_sends_no_post(api, failure) -> None:
    store = MemoryPATStore()
    store.fail_write = (1, failure)
    client = TrustCenterClient.from_store(store, http_client=api(no_http))
    with pytest.raises(PATPersistenceError, match='No refresh was sent') as caught:
        client.refresh_pat()
    assert_safe(caught.value)
    assert (store.record.pending_attempt is not None) == (failure == 'after')
    with pytest.raises(ConfigurationError):
        client.retry_pat_persistence()


@pytest.mark.parametrize('failure', ['before', 'after'])
def test_replacement_persistence_only_recovery(api, failure) -> None:
    store = MemoryPATStore()
    store.fail_write = (2, failure)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        if request.method == 'POST':
            return httpx.Response(200, json=PAYLOAD)
        assert request.headers['Authorization'] == f'Bearer {NEW}'
        return httpx.Response(200, json={'tenants': []})

    http = api(handler)
    client = TrustCenterClient.from_store(store, http_client=http)
    observer = TrustCenterClient.from_store(store, http_client=http)
    with pytest.raises(PATPersistenceError, match='durable storage') as caught:
        client.refresh_pat()
    assert_safe(caught.value)
    assert NEW not in repr(vars(client))
    assert NEW not in repr(vars(client._stored_pat))
    with pytest.raises(PATPersistenceError):
        client.tenants.list()
    with pytest.raises(PATPersistenceError):
        client.refresh_pat()
    with pytest.raises(PATRefreshPendingError if failure == 'before' else ConfigurationError):
        observer.tenants.list()
    if failure == 'before':
        with pytest.raises(PATRefreshPendingError):
            observer.refresh_pat()
        with pytest.raises(PATRefreshPendingError):
            TrustCenterClient.from_store(store, http_client=http)
    assert requests == ['POST']

    store.load_fails = True
    with pytest.raises(PATPersistenceError) as caught:
        client.retry_pat_persistence()
    assert_safe(caught.value)
    store.load_fails = False
    assert client.retry_pat_persistence().metadata_valid
    assert store.swaps == (3 if failure == 'before' else 2)
    assert store.record.pending_attempt is None
    assert store.record.get_pat() == NEW
    with pytest.raises(ConfigurationError):
        client.retry_pat_persistence()
    assert requests == ['POST']
    assert client.tenants.list().tenants == []
    assert requests == ['POST', 'GET']


def test_persistence_retry_never_overwrites_a_reseeded_store(api) -> None:
    store = MemoryPATStore()
    store.fail_write = (2, 'before')
    client = TrustCenterClient.from_store(store, http_client=api(lambda _: httpx.Response(200, json=PAYLOAD)))
    with pytest.raises(PATPersistenceError):
        client.refresh_pat()
    pending = store.record
    recovered = PATStoreRecord(uuid4(), STALE)
    assert store.compare_and_swap(
        expected_revision=pending.revision, expected_attempt=pending.pending_attempt, replacement=recovered
    )
    with pytest.raises(PATPersistenceError, match='store changed'):
        client.retry_pat_persistence()
    assert store.swaps == 3
    assert store.record is recovered


@pytest.mark.parametrize('status,error', [(401, AuthenticationError), (429, RateLimitError)])
def test_known_rejection_clears_marker_without_probe_or_replay(api, status, error) -> None:
    store = MemoryPATStore()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.headers['Authorization'] == f'Bearer {OLD}'
        if request.method == 'POST':
            return httpx.Response(status, text=NEW)
        return httpx.Response(200, json={'tenants': []})

    http = api(handler)
    client = TrustCenterClient.from_store(store, http_client=http, max_retries=5)
    old_record = store.record
    with pytest.raises(error) as caught:
        client.refresh_pat()
    assert_safe(caught.value)
    assert caught.value.status_code == status
    assert calls == ['POST']
    assert store.record is old_record
    if status == 429:
        client.tenants.list()
        assert calls == ['POST', 'GET']


def test_known_rejection_with_uncertain_marker_clear_fails_closed(api) -> None:
    store = MemoryPATStore()
    store.fail_write = (2, 'before')
    client = TrustCenterClient.from_store(store, http_client=api(lambda _: httpx.Response(429, text=NEW)))
    with pytest.raises(PATPersistenceError, match='HTTP 429') as caught:
        client.refresh_pat()
    assert_safe(caught.value)
    assert store.record.pending_attempt is not None


@pytest.mark.parametrize('post', [500, 'timeout', 'hook', 307])
@pytest.mark.parametrize(
    'probe,expected',
    [
        (200, PATProbeResult.OLD_PAT_ACCEPTED),
        (401, PATProbeResult.OLD_PAT_REJECTED),
        (503, PATProbeResult.INCONCLUSIVE),
        ('timeout', PATProbeResult.INCONCLUSIVE),
    ],
)
def test_ambiguous_outcome_probes_old_pat_once_and_preserves_marker(api, post, probe, expected) -> None:
    store = MemoryPATStore()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        assert request.headers['Authorization'] == f'Bearer {OLD}'
        status = post if request.method == 'POST' else probe
        if status == 'timeout':
            raise httpx.ReadTimeout(f'{NEW} {request.url}', request=request)
        if status == 'hook':
            raise RuntimeError(f'{NEW} store-exception-marker {request.url}')
        return httpx.Response(status, text=NEW, headers={'Location': f'https://example.invalid/{NEW}'})

    client = TrustCenterClient.from_store(store, http_client=api(handler), max_retries=5)
    with pytest.raises(PATRefreshAmbiguousError) as caught:
        client.refresh_pat()
    assert caught.value.probe == expected
    assert_safe(caught.value)
    assert store.record.pending_attempt is not None
    with pytest.raises(PATRefreshPendingError):
        client.refresh_pat()
    with pytest.raises(PATRefreshPendingError):
        client.tenants.list()
    assert calls == [('POST', ENDPOINT + '/pats/refresh'), ('GET', ENDPOINT + '/tenants')]


@pytest.mark.parametrize(
    'body',
    [
        b'',
        b'\xff',
        b'{',
        b'[]',
        b'{"secret":true}',
        b'{"secret":"bad\\r\\nvalue"}',
        b'{}',
        json.dumps({'secret': OLD}).encode(),
        b'{"secret":"first","secret":"second"}',
    ],
)
def test_unusable_refresh_response_is_ambiguous(api, body) -> None:
    store = MemoryPATStore()
    client = TrustCenterClient.from_store(
        store, http_client=api(lambda req: httpx.Response(200, content=body) if req.method == 'POST' else httpx.Response(401))
    )
    with pytest.raises(PATRefreshAmbiguousError) as caught:
        client.refresh_pat()
    assert caught.value.probe == PATProbeResult.OLD_PAT_REJECTED
    assert_safe(caught.value)
    assert store.record.pending_attempt is not None


@pytest.mark.parametrize(
    'payload',
    [
        {'secret': NEW},
        {**PAYLOAD, 'label': 42},
        {**PAYLOAD, 'tokenId': NEW},
        {**PAYLOAD, 'createdAt': '2026-11-04T03:00:00.000'},
        {**PAYLOAD, 'expiresAt': '2026-99-04T03:00:00.000Z'},
        {**PAYLOAD, 'extra': NEW},
        json.dumps(PAYLOAD).removesuffix('}') + ', "label": "duplicate"}',
        json.dumps(PAYLOAD).removesuffix('}') + ', "extra": ' + '1' * 5000 + '}',
    ],
)
def test_metadata_drift_cannot_discard_usable_replacement(api, payload) -> None:
    store = MemoryPATStore()

    def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(payload, str):
            return httpx.Response(200, text=payload)
        return httpx.Response(200, json=payload)

    client = TrustCenterClient.from_store(store, http_client=api(handler))
    result = client.refresh_pat()
    assert result == PATRefreshResult(metadata_valid=False)
    assert store.record.get_pat() == NEW
    assert store.record.pending_attempt is None
