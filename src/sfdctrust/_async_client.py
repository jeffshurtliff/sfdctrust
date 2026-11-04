# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._async_client
:Synopsis:          Asynchronous My Trust Center client
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from typing import Self

import httpx

from ._async_pat_refresh import _AsyncStoredPAT
from ._async_transport import _AsyncTransport
from ._auth import PATAuth, _Unset
from ._exceptions import ConfigurationError
from ._pat_refresh import PATRefreshResult, _validate_refresh_days
from ._pat_store import AsyncPATStore
from .resources._async_events import AsyncEventsResource
from .resources._async_status import AsyncStatusResource
from .resources._async_tenants import AsyncTenantsResource


class AsyncTrustCenterClient:
    """Asynchronous client for the Salesforce My Trust Center API.

    Construction makes no network requests. The SDK owns its transport and
    closes its default HTTP client on context exit or :meth:`aclose`.

    :param pat: Personal access token without the Bearer prefix.
    :param http_client: Trusted async HTTPX client whose lifecycle and TLS, proxy,
                        hook, and transport settings remain the caller's responsibility.
    :param max_retries: Additional SDK attempts per request, from 0 through 5.
    :raises ConfigurationError: If the PAT or retry limit is invalid.
    """

    def __init__(self, pat: str, *, http_client: httpx.AsyncClient | None = None, max_retries: int = 2) -> None:
        self._initialize(PATAuth(pat), http_client, max_retries)

    def _initialize(self, auth: PATAuth | _AsyncStoredPAT, http_client: httpx.AsyncClient | None, max_retries: int) -> None:
        self._stored_pat = auth if isinstance(auth, _AsyncStoredPAT) else None
        self._transport = _AsyncTransport(
            auth.read_auth if isinstance(auth, _AsyncStoredPAT) else auth, client=http_client, max_retries=max_retries
        )
        self.tenants = AsyncTenantsResource(self._transport)
        self.status = AsyncStatusResource(self._transport)
        self.events = AsyncEventsResource(self._transport)

    @classmethod
    def from_env(
        cls, *, pat: str | None | _Unset = _Unset.PAT, http_client: httpx.AsyncClient | None = None, max_retries: int = 2
    ) -> Self:
        """Create a client using ``SFDCTRUST_PAT`` or an explicit override.

        :param pat: An explicit override. Omitting it selects the environment.
                    Explicit ``None`` or any invalid override raises immediately.
        :param http_client: Optional caller-owned, trusted async HTTPX client.
        :param max_retries: Additional SDK attempts per request, from 0 through 5.
        :returns: A configured client.
        :raises ConfigurationError: If the selected PAT is absent or invalid, or the retry limit is invalid.
        """
        auth = PATAuth.from_env(pat=pat)
        client = cls.__new__(cls)
        client._initialize(auth, http_client, max_retries)
        return client

    @classmethod
    async def from_store(
        cls, store: AsyncPATStore, *, http_client: httpx.AsyncClient | None = None, max_retries: int = 2
    ) -> Self:
        """Load an explicitly configured, seeded PAT store for one lineage.

        :param store: Trusted durable adapter shared by all rotators of this PAT.
        :param http_client: Optional caller-owned, trusted async HTTPX client. Its
                            transport and hooks must never replay a refresh.
        :param max_retries: Additional SDK attempts per eligible read, from 0 through 5.
        :returns: A configured client.
        :raises ConfigurationError: If the store is unsuitable, unreadable,
                                    unseeded, or the retry limit is invalid.
        :raises PATRefreshPendingError: If the store has an unresolved rotation.
        """
        auth = await _AsyncStoredPAT.open(store)
        client = cls.__new__(cls)
        client._initialize(auth, http_client, max_retries)
        return client

    async def refresh_pat(self, *, expires_in_days: int | None = None) -> PATRefreshResult:
        """Explicitly rotate a stored PAT once and activate its durable replacement.

        Cancellation propagates. If the replacement was received, keep this client
        available to reconcile an interrupted commit with :meth:`retry_pat_persistence`.

        :param expires_in_days: Replacement lifetime from 1 through 30.
                                None omits the body and uses Salesforce's default.
        :returns: A secret-free result indicating whether response metadata validated.
        :raises ConfigurationError: If the client uses a static credential, the
                                    lifetime is invalid, or the store is unreadable.
        :raises PATRefreshPendingError: If a pending or competing operation blocks rotation.
        :raises AuthenticationError: If Salesforce rejected refresh with HTTP 401.
        :raises RateLimitError: If Salesforce rejected refresh with HTTP 429.
        :raises PATRefreshAmbiguousError: If Salesforce may have rotated without a usable replacement.
        :raises PATPersistenceError: If a required durable state transition cannot be confirmed.
        """
        if self._stored_pat is None:
            raise ConfigurationError('PAT refresh requires a store-backed client.')
        _validate_refresh_days(expires_in_days)
        return await self._stored_pat.refresh(self._transport, expires_in_days)

    async def retry_pat_persistence(self) -> PATRefreshResult:
        """Reconcile or retry saving a replacement held by this client, using only store I/O.

        :returns: The original secret-free result once durable storage is confirmed.
        :raises ConfigurationError: If this client has no replacement awaiting persistence.
        :raises PATRefreshPendingError: If another PAT operation is running on this client.
        :raises PATPersistenceError: If the replacement still cannot be confirmed or saved.
        """
        if self._stored_pat is None:
            raise ConfigurationError('PAT persistence requires a store-backed client.')
        return await self._stored_pat.retry_persistence()

    async def aclose(self) -> None:
        """Close SDK-owned HTTP connections."""
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
