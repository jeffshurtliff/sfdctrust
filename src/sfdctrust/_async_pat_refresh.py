# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._async_pat_refresh
:Synopsis:          Asynchronous store coordination for explicit PAT rotation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from asyncio import Lock
from typing import Self
from uuid import UUID, uuid4

from ._async_transport import _AsyncTransport
from ._auth import PATAuth
from ._exceptions import AuthenticationError, ConfigurationError, PATPersistenceError, PATRefreshPendingError, RateLimitError
from ._pat_refresh import (
    PATRefreshResult,
    _matches_replacement,
    _probe_error,
    _replacement_write,
    _require_ready,
    _UnconfirmedWrite,
)
from ._pat_store import AsyncPATStore, PATStoreRecord


class _AsyncStoredPAT:
    def __init__(self, store: AsyncPATStore) -> None:
        try:
            suitable = isinstance(store, AsyncPATStore) and callable(store.load) and callable(store.compare_and_swap)
        except Exception:
            suitable = False
        if not suitable:
            raise ConfigurationError('A versioned async PAT store adapter is required.')
        self._store = store
        self._operation = Lock()
        self._unconfirmed: _UnconfirmedWrite | None = None
        self._loaded: tuple[UUID, PATAuth]

    @classmethod
    async def open(cls, store: AsyncPATStore) -> Self:
        state = cls(store)
        record = await state._load()
        _require_ready(record)
        state._activate(record)
        return state

    async def _load(self) -> PATStoreRecord:
        try:
            record = await self._store.load()
        except Exception:
            record = None
        if type(record) is PATStoreRecord:
            return record
        raise ConfigurationError('The PAT store could not supply a valid seeded record.')

    async def _swap(self, revision: UUID, attempt: UUID | None, replacement: PATStoreRecord, failure: str) -> bool:
        try:
            changed = await self._store.compare_and_swap(
                expected_revision=revision, expected_attempt=attempt, replacement=replacement
            )
        except Exception:
            changed = None
        if type(changed) is bool:
            return changed
        raise PATPersistenceError(failure)

    def _activate(self, record: PATStoreRecord) -> None:
        self._loaded = (record.revision, PATAuth(record.get_pat()))

    async def read_auth(self) -> PATAuth:
        if self._unconfirmed is not None:
            raise PATPersistenceError('Retry persistence before using this client.')
        revision, auth = self._loaded
        record = await self._load()
        _require_ready(record)
        if record.revision != revision:
            raise ConfigurationError('The stored PAT changed. Recreate the store-backed client to reload it.')
        return auth

    async def refresh(self, transport: _AsyncTransport, days: int | None) -> PATRefreshResult:
        if self._operation.locked():
            raise PATRefreshPendingError('A PAT operation is already in progress on this client.')
        async with self._operation:
            if self._unconfirmed is not None:
                raise PATPersistenceError('Retry persistence before refreshing again.')
            return await self._refresh(transport, days)

    async def _refresh(self, transport: _AsyncTransport, days: int | None) -> PATRefreshResult:
        current = await self._load()
        _require_ready(current)
        old_pat = current.get_pat()
        auth = PATAuth(old_pat)
        attempt = uuid4()
        pending = PATStoreRecord(current.revision, old_pat, attempt)
        failure = 'Could not confirm the pending marker. No refresh was sent.'
        if not await self._swap(current.revision, None, pending, failure):
            raise PATRefreshPendingError('The PAT store changed before refresh. No refresh was sent.')

        async with transport.refresh_once(auth, days) as (status, payload):
            write = _replacement_write(current, attempt, payload)
            # Retain the replacement before response cleanup or durable commit can suspend.
            self._unconfirmed = write

        if status in (401, 429):
            failure = f'Refresh returned HTTP {status}, but the pending marker could not be cleared.'
            if not await self._swap(current.revision, attempt, current, failure):
                raise PATPersistenceError(failure)
            if status == 401:
                raise AuthenticationError()
            raise RateLimitError()

        if write is None:
            raise _probe_error(await transport.probe_once(auth))
        return await self._commit(write)

    async def _commit(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        failure = 'Could not confirm durable storage of the replacement. Retry persistence on this client.'
        if not await self._swap(write.revision, write.attempt, write.replacement, failure):
            raise PATPersistenceError(failure)
        return self._finish(write)

    def _finish(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        self._activate(write.replacement)
        self._unconfirmed = None
        return write.result

    async def retry_persistence(self) -> PATRefreshResult:
        if self._operation.locked():
            raise PATRefreshPendingError('A PAT operation is already in progress on this client.')
        async with self._operation:
            write = self._unconfirmed
            if write is None:
                raise ConfigurationError('This client has no replacement awaiting persistence.')
            return await self._reconcile(write)

    async def _reconcile(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        try:
            current = await self._load()
        except ConfigurationError:
            current = None
        if current is None:
            raise PATPersistenceError('Could not read the PAT store to confirm the replacement.')
        if current.revision == write.revision and current.pending_attempt == write.attempt:
            return await self._commit(write)
        if _matches_replacement(current, write):
            return self._finish(write)
        raise PATPersistenceError('The store changed while persistence was unresolved. Reconcile the store before use.')
