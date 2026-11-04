# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._pat_refresh
:Synopsis:          Store coordination and recovery for explicit PAT rotation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from uuid import UUID, uuid4

from ._auth import PATAuth, _validate_pat
from ._exceptions import (
    AuthenticationError,
    ConfigurationError,
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    RateLimitError,
)
from ._pat_store import PATStore, PATStoreRecord
from ._transport import _Transport

_METADATA_FIELDS = frozenset({'secret', 'tokenId', 'label', 'createdAt', 'expiresAt'})
_DATE_TIME = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])'
)


@dataclass(frozen=True, slots=True)
class PATRefreshResult:
    """Outcome of a durably saved replacement, with no server-supplied values.

    :param metadata_valid: Whether the response metadata matched the documented schema.
    """

    metadata_valid: bool


def _replacement_secret(payload: dict[str, object], old_pat: str) -> str | None:
    secret = payload.get('secret')
    if not isinstance(secret, str) or secret == old_pat:
        return None
    try:
        _validate_pat(secret)
    except ConfigurationError:
        return None
    return secret


def _validate_metadata(payload: dict[str, object]) -> bool:
    if payload.keys() != _METADATA_FIELDS or not isinstance(payload['label'], str):
        return False
    token_id, created, expires = (payload[key] for key in ('tokenId', 'createdAt', 'expiresAt'))
    if not isinstance(token_id, str) or not isinstance(created, str) or not isinstance(expires, str):
        return False
    if not (_DATE_TIME.fullmatch(created) and _DATE_TIME.fullmatch(expires)):
        return False
    try:
        if str(UUID(token_id)) != token_id.lower():
            return False
        datetime.fromisoformat(created.upper())
        datetime.fromisoformat(expires.upper())
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class _UnconfirmedWrite:
    revision: UUID
    attempt: UUID
    replacement: PATStoreRecord
    result: PATRefreshResult


def _require_ready(record: PATStoreRecord) -> None:
    if record.pending_attempt is not None:
        raise PATRefreshPendingError('The PAT store has an unresolved rotation.')


class _StoredPAT:
    def __init__(self, store: PATStore) -> None:
        try:
            suitable = isinstance(store, PATStore) and callable(store.load) and callable(store.compare_and_swap)
        except Exception:
            suitable = False
        if not suitable:
            raise ConfigurationError('A versioned PAT store adapter is required.')
        self._store = store
        self._operation = Lock()
        self._unconfirmed: _UnconfirmedWrite | None = None
        record = self._load()
        _require_ready(record)
        self._activate(record)

    def _load(self) -> PATStoreRecord:
        try:
            record = self._store.load()
        except Exception:
            record = None
        if type(record) is PATStoreRecord:
            return record
        raise ConfigurationError('The PAT store could not supply a valid seeded record.')

    def _swap(
        self,
        revision: UUID,
        attempt: UUID | None,
        replacement: PATStoreRecord,
        failure: str,
    ) -> bool:
        try:
            changed = self._store.compare_and_swap(expected_revision=revision, expected_attempt=attempt, replacement=replacement)
        except Exception:
            changed = None
        if type(changed) is bool:
            return changed
        raise PATPersistenceError(failure)

    def _activate(self, record: PATStoreRecord) -> None:
        self._loaded = (record.revision, PATAuth(record.get_pat()))

    def read_auth(self) -> PATAuth:
        if self._unconfirmed is not None:
            raise PATPersistenceError('Retry persistence before using this client.')
        revision, auth = self._loaded
        record = self._load()
        _require_ready(record)
        if record.revision != revision:
            raise ConfigurationError('The stored PAT changed. Recreate the store-backed client to reload it.')
        return auth

    def refresh(self, transport: _Transport, days: int | None) -> PATRefreshResult:
        if not self._operation.acquire(blocking=False):
            raise PATRefreshPendingError('A PAT operation is already in progress on this client.')
        try:
            if self._unconfirmed is not None:
                raise PATPersistenceError('Retry persistence before refreshing again.')
            return self._refresh(transport, days)
        finally:
            self._operation.release()

    def _refresh(self, transport: _Transport, days: int | None) -> PATRefreshResult:
        current = self._load()
        _require_ready(current)
        old_pat = current.get_pat()
        auth = PATAuth(old_pat)
        attempt = uuid4()
        pending = PATStoreRecord(current.revision, old_pat, attempt)
        if not self._swap(current.revision, None, pending, 'Could not confirm the pending marker. No refresh was sent.'):
            raise PATRefreshPendingError('The PAT store changed before refresh. No refresh was sent.')

        status, payload = transport.refresh_once(auth, days)
        if status in (401, 429):
            failure = f'Refresh returned HTTP {status}, but the pending marker could not be cleared.'
            if not self._swap(current.revision, attempt, current, failure):
                raise PATPersistenceError(failure)
            if status == 401:
                raise AuthenticationError()
            raise RateLimitError()

        secret = _replacement_secret(payload, old_pat) if payload is not None else None
        if payload is None or secret is None:
            probe_status = transport.probe_once(auth)
            probe = {200: PATProbeResult.OLD_PAT_ACCEPTED, 401: PATProbeResult.OLD_PAT_REJECTED}
            raise PATRefreshAmbiguousError(probe.get(probe_status, PATProbeResult.INCONCLUSIVE))

        replacement = PATStoreRecord(uuid4(), secret)
        result = PATRefreshResult(metadata_valid=_validate_metadata(payload))
        write = _UnconfirmedWrite(current.revision, attempt, replacement, result)
        self._unconfirmed = write
        return self._commit(write)

    def _commit(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        failure = 'Could not confirm durable storage of the replacement. Retry persistence on this client.'
        if not self._swap(write.revision, write.attempt, write.replacement, failure):
            raise PATPersistenceError(failure)
        return self._finish(write)

    def _finish(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        self._activate(write.replacement)
        self._unconfirmed = None
        return write.result

    def retry_persistence(self) -> PATRefreshResult:
        if not self._operation.acquire(blocking=False):
            raise PATRefreshPendingError('A PAT operation is already in progress on this client.')
        try:
            write = self._unconfirmed
            if write is None:
                raise ConfigurationError('This client has no replacement awaiting persistence.')
            return self._reconcile(write)
        finally:
            self._operation.release()

    def _reconcile(self, write: _UnconfirmedWrite) -> PATRefreshResult:
        try:
            current = self._load()
        except ConfigurationError:
            current = None
        if current is None:
            raise PATPersistenceError('Could not read the PAT store to confirm the replacement.')
        if current.revision == write.revision and current.pending_attempt == write.attempt:
            return self._commit(write)
        if (
            current.revision == write.replacement.revision
            and current.pending_attempt is None
            and current.get_pat() == write.replacement.get_pat()
        ):
            return self._finish(write)
        raise PATPersistenceError('The store changed while persistence was unresolved. Reconcile the store before use.')
