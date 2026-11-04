# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_async_pat_refresh
:Synopsis:          Offline async PAT rotation and cancellation boundary tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import asyncio
import json
import traceback
from uuid import UUID, uuid4

import httpx
import pytest

from sfdctrust import (
    AsyncPATStore,
    AsyncTrustCenterClient,
    AuthenticationError,
    ConfigurationError,
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    PATRefreshResult,
    PATStoreRecord,
    RateLimitError,
)

pytestmark = pytest.mark.asyncio
OLD = 'synthetic-async-original-pat'
NEW = 'synthetic-async-replacement-pat'
OTHER = 'synthetic-async-reseeded-pat'
PAYLOAD = {
    'secret': NEW,
    'tokenId': '9aa0b1c2-d3e4-4f56-a789-0123456789ab',
    'label': 'synthetic-rotation',
    'createdAt': '2026-11-04T03:00:00Z',
    'expiresAt': '2026-12-04T03:00:00Z',
}


class AsyncTestStore:
    """Test-only CAS record that can outlive its clients."""

    def __init__(self) -> None:
        self.record: PATStoreRecord | None = PATStoreRecord(uuid4(), OLD)
        self.loads = 0
        self.swaps = 0
        self.before_swap = None
        self.after_swap = None
        self.fail_load = False

    async def load(self) -> PATStoreRecord | None:
        self.loads += 1
        if self.fail_load:
            raise OSError(f'synthetic load failure for {OLD}')
        return self.record

    async def compare_and_swap(
        self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord
    ) -> bool:
        self.swaps += 1
        if self.before_swap is not None:
            await self.before_swap(replacement)
        current = self.record
        if current is None or (current.revision, current.pending_attempt) != (expected_revision, expected_attempt):
            return False
        self.record = replacement
        if self.after_swap is not None:
            await self.after_swap(replacement)
        return True


async def cancel_at(task: asyncio.Task, reached: asyncio.Event) -> None:
    await asyncio.wait_for(reached.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def no_http(request: httpx.Request) -> httpx.Response:
    pytest.fail(f'Unexpected {request.method} request')


def assert_safe(error: Exception) -> None:
    assert error.__cause__ is error.__context__ is None
    for display in (repr(error), ''.join(traceback.format_exception(error))):
        for secret in (OLD, NEW, OTHER, 'Bearer ', 'api.salesforce.com'):
            assert secret not in display


@pytest.mark.parametrize('failure', ['unseeded', 'load error', 'wrong adapter'])
async def test_store_load_fails_closed_and_ignores_environment(monkeypatch, failure) -> None:
    monkeypatch.setenv('SFDCTRUST_PAT', OTHER)
    store = AsyncTestStore()
    assert isinstance(store, AsyncPATStore)
    if failure == 'unseeded':
        store.record = None
    if failure == 'load error':
        store.fail_load = True
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_http)) as http:
        with pytest.raises(ConfigurationError) as exc:
            await AsyncTrustCenterClient.from_store(object() if failure == 'wrong adapter' else store, http_client=http)
    assert_safe(exc.value)
    assert not store.swaps


@pytest.mark.parametrize('days', [True, 0, 31, 2.0, '1'])
async def test_invalid_lifetime_precedes_store_and_http_io(days) -> None:
    store = AsyncTestStore()
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_http)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http)
        with pytest.raises(ConfigurationError, match='expires_in_days'):
            await client.refresh_pat(expires_in_days=days)
    assert store.loads == 1 and store.swaps == 0


@pytest.mark.parametrize(('days', 'metadata_valid'), [(None, True), (1, True), (30, False)])
async def test_activation_follows_durable_commit_and_old_clients_fail_reads(monkeypatch, days, metadata_valid) -> None:
    monkeypatch.setenv('SFDCTRUST_PAT', OTHER)
    store = AsyncTestStore()
    original = store.record
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == 'POST':
            assert str(request.url) == 'https://api.salesforce.com/platform/mytrust/v1/pats/refresh'
            assert request.headers['Authorization'] == f'Bearer {OLD}'
            assert store.record.revision == original.revision
            assert store.record.pending_attempt is not None
            if days is None:
                assert request.content == b''
            else:
                assert json.loads(request.content) == {'expiresInDays': days}
            return httpx.Response(200, json=PAYLOAD if metadata_valid else {'secret': NEW, 'tokenId': 42})
        assert store.record.pending_attempt is None
        assert request.headers['Authorization'] == f'Bearer {NEW}'
        return httpx.Response(200, json={'tenants': []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        rotator = await AsyncTrustCenterClient.from_store(store, http_client=http)
        stale = await AsyncTrustCenterClient.from_store(store, http_client=http)
        result = await rotator.refresh_pat(expires_in_days=days)
        assert result == PATRefreshResult(metadata_valid)
        assert NEW not in repr(result) and NEW not in repr(store.record)
        assert store.record.revision != original.revision
        assert store.swaps == 2
        await rotator.tenants.list()
        with pytest.raises(ConfigurationError, match='Recreate'):
            await stale.tenants.list()
        reopened = await AsyncTrustCenterClient.from_store(store, http_client=http)
        await reopened.tenants.list()

    assert [request.method for request in requests] == ['POST', 'GET', 'GET']


async def test_competing_rotators_cas_and_same_client_gate() -> None:
    store = AsyncTestStore()
    both_claiming = asyncio.Event()
    post_reached = asyncio.Event()
    allow_post = asyncio.Event()
    contenders = 0
    requests = []

    async def before_swap(replacement):
        if replacement.pending_attempt is not None:
            nonlocal contenders
            contenders += 1
            if contenders == 2:
                both_claiming.set()
            await both_claiming.wait()

    async def handler(request):
        requests.append(request.method)
        post_reached.set()
        await allow_post.wait()
        return httpx.Response(200, json=PAYLOAD)

    store.before_swap = before_swap
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await AsyncTrustCenterClient.from_store(store, http_client=http)
        second = await AsyncTrustCenterClient.from_store(store, http_client=http)
        async with asyncio.timeout(5):
            tasks = [asyncio.create_task(client.refresh_pat()) for client in (first, second)]
            try:
                await post_reached.wait()
                finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                (loser,) = finished
                with pytest.raises(PATRefreshPendingError, match='store changed'):
                    await loser
                winner_index = 1 - tasks.index(loser)
                winner = (first, second)[winner_index]
                with pytest.raises(PATRefreshPendingError, match='already in progress'):
                    await winner.refresh_pat()
                with pytest.raises(PATRefreshPendingError, match='unresolved'):
                    await AsyncTrustCenterClient.from_store(store, http_client=http)
                allow_post.set()
                assert await tasks[winner_index] == PATRefreshResult(True)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    assert requests == ['POST']
    assert store.swaps == 3


@pytest.mark.parametrize(('status', 'error'), [(401, AuthenticationError), (429, RateLimitError)])
async def test_known_rejections_clear_marker_without_probe_or_retry(status, error) -> None:
    store = AsyncTestStore()
    original = store.record
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(status, content=OLD.encode(), headers={'Retry-After': '0'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http, max_retries=5)
        with pytest.raises(error) as exc:
            await client.refresh_pat()

    assert_safe(exc.value)
    assert methods == ['POST']
    assert store.record is original
    assert store.swaps == 2


@pytest.mark.parametrize(
    ('refresh_failure', 'probe_status', 'probe'),
    [
        ('timeout', 200, PATProbeResult.OLD_PAT_ACCEPTED),
        (500, 401, PATProbeResult.OLD_PAT_REJECTED),
        ('duplicate secret', 429, PATProbeResult.INCONCLUSIVE),
        ('old secret', 503, PATProbeResult.INCONCLUSIVE),
        ('timeout', 'timeout', PATProbeResult.INCONCLUSIVE),
    ],
)
async def test_ambiguous_outcomes_probe_once_and_preserve_marker(refresh_failure, probe_status, probe) -> None:
    store = AsyncTestStore()
    original = store.record
    requests = []

    class UnreadableProbeBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail('The probe is status-only.')
            yield b''

    def handler(request):
        requests.append(request)
        assert request.headers['Authorization'] == f'Bearer {OLD}'
        status = refresh_failure if request.method == 'POST' else probe_status
        if status == 'timeout':
            raise httpx.ReadTimeout(OLD, request=request)
        if status == 'duplicate secret':
            return httpx.Response(200, content=f'{{"secret":"{NEW}","secret":"{OTHER}"}}'.encode())
        if status == 'old secret':
            return httpx.Response(200, json={'secret': OLD})
        return httpx.Response(status, stream=UnreadableProbeBody())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http, max_retries=5)
        with pytest.raises(PATRefreshAmbiguousError) as exc:
            await client.refresh_pat()
        assert exc.value.probe == probe
        assert_safe(exc.value)
        with pytest.raises(PATRefreshPendingError):
            await client.tenants.list()
        with pytest.raises(PATRefreshPendingError):
            await AsyncTrustCenterClient.from_store(store, http_client=http)

    assert [(request.method, request.url.path.rsplit('/', 1)[-1]) for request in requests] == [
        ('POST', 'refresh'),
        ('GET', 'tenants'),
    ]
    assert store.record.revision == original.revision
    assert store.record.pending_attempt is not None
    assert store.swaps == 1


@pytest.mark.parametrize('committed', [False, True])
async def test_cancel_at_marker_write_sends_no_post(committed) -> None:
    store = AsyncTestStore()
    original = store.record
    reached = asyncio.Event()

    async def block(_):
        reached.set()
        await asyncio.Future()

    if committed:
        store.after_swap = block
    else:
        store.before_swap = block
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_http)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http)
        await cancel_at(asyncio.create_task(client.refresh_pat()), reached)
        if committed:
            assert store.record.revision == original.revision
            assert store.record.pending_attempt is not None
            with pytest.raises(PATRefreshPendingError):
                await AsyncTrustCenterClient.from_store(store, http_client=http)
        else:
            assert store.record is original
            await AsyncTrustCenterClient.from_store(store, http_client=http)
        with pytest.raises(ConfigurationError, match='no replacement'):
            await client.retry_pat_persistence()


@pytest.mark.parametrize('boundary', ['post', 'probe'])
async def test_cancel_at_http_boundary_preserves_marker_and_sends_no_more_requests(boundary) -> None:
    store = AsyncTestStore()
    reached = asyncio.Event()
    closed = asyncio.Event()
    methods = []

    class BlockingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            reached.set()
            await asyncio.Future()
            yield b''

        async def aclose(self):
            closed.set()

    async def handler(request):
        methods.append(request.method)
        if boundary == 'post':
            return httpx.Response(200, stream=BlockingBody())
        if request.method == 'POST':
            return httpx.Response(500)
        reached.set()
        await asyncio.Future()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http)
        await cancel_at(asyncio.create_task(client.refresh_pat()), reached)
        assert store.record.pending_attempt is not None
        with pytest.raises(PATRefreshPendingError):
            await client.refresh_pat()
        with pytest.raises(PATRefreshPendingError):
            await AsyncTrustCenterClient.from_store(store, http_client=http)

    assert methods == (['POST'] if boundary == 'post' else ['POST', 'GET'])
    assert store.swaps == 1
    if boundary == 'post':
        assert closed.is_set()


@pytest.mark.parametrize('committed', [False, True])
@pytest.mark.parametrize('cancelled', [False, True])
async def test_reconcile_unconfirmed_replacement_using_store_only(committed, cancelled) -> None:
    store = AsyncTestStore()
    reached = asyncio.Event()
    methods = []

    async def interrupt_replacement(replacement):
        if replacement.pending_attempt is None:
            if cancelled:
                reached.set()
                await asyncio.Future()
            raise OSError(f'synthetic unacknowledged commit for {NEW}')

    def handler(request):
        methods.append(request.method)
        if request.method == 'POST':
            return httpx.Response(200, json=PAYLOAD)
        assert request.headers['Authorization'] == f'Bearer {NEW}'
        return httpx.Response(200, json={'tenants': []})

    if committed:
        store.after_swap = interrupt_replacement
    else:
        store.before_swap = interrupt_replacement

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http)
        if cancelled:
            await cancel_at(asyncio.create_task(client.refresh_pat()), reached)
        else:
            with pytest.raises(PATPersistenceError) as exc:
                await client.refresh_pat()
            assert_safe(exc.value)

        assert store.swaps == 2
        assert (store.record.pending_attempt is None) is committed
        assert store.record.get_pat() == (NEW if committed else OLD)
        if committed:
            await AsyncTrustCenterClient.from_store(store, http_client=http)
        else:
            with pytest.raises(PATRefreshPendingError):
                await AsyncTrustCenterClient.from_store(store, http_client=http)
        with pytest.raises(PATPersistenceError, match='Retry persistence'):
            await client.tenants.list()
        with pytest.raises(PATPersistenceError, match='Retry persistence'):
            await client.refresh_pat()

        store.before_swap = store.after_swap = None
        assert await client.retry_pat_persistence() == PATRefreshResult(True)
        assert methods == ['POST']
        assert store.swaps == (2 if committed else 3)
        await client.tenants.list()
    assert methods == ['POST', 'GET']


@pytest.mark.parametrize('reseed', [False, True])
async def test_recovery_does_not_overwrite_a_changed_attempt_or_revision(reseed) -> None:
    store = AsyncTestStore()
    methods = []

    async def fail_before_commit(replacement):
        if replacement.pending_attempt is None:
            raise OSError(NEW)

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, json=PAYLOAD)

    store.before_swap = fail_before_commit
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = await AsyncTrustCenterClient.from_store(store, http_client=http)
        with pytest.raises(PATPersistenceError):
            await client.refresh_pat()
        if reseed:
            observed = PATStoreRecord(uuid4(), OTHER)
        else:
            observed = PATStoreRecord(store.record.revision, OLD, uuid4())
        store.record = observed
        store.before_swap = None
        with pytest.raises(PATPersistenceError, match='store changed'):
            await client.retry_pat_persistence()
    assert methods == ['POST']
    assert store.swaps == 2
    assert store.record is observed
