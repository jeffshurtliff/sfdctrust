# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._client
:Synopsis:          Synchronous My Trust Center client
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from typing import Self

import httpx

from ._auth import PATAuth, _Unset
from ._exceptions import ConfigurationError
from ._pat_refresh import PATRefreshResult, _StoredPAT
from ._pat_store import PATStore
from ._transport import _Transport
from .resources.events import EventsResource
from .resources.status import StatusResource
from .resources.tenants import TenantsResource


class TrustCenterClient:
    """Synchronous client for the Salesforce My Trust Center API.

    Construction makes no network requests. The SDK owns its transport and
    closes its default HTTP client on context exit or :meth:`close`.

    :param pat: Personal access token without the Bearer prefix.
    :param http_client: Trusted HTTPX client whose lifecycle and TLS, proxy,
                        hook, and transport settings remain the caller's responsibility.
    :param max_retries: Additional SDK attempts per request, from 0 through 5.
    :raises ConfigurationError: If the PAT or retry limit is invalid.
    """

    def __init__(self, pat: str, *, http_client: httpx.Client | None = None, max_retries: int = 2) -> None:
        self._initialize(PATAuth(pat), http_client, max_retries)

    def _initialize(self, auth: PATAuth | _StoredPAT, http_client: httpx.Client | None, max_retries: int) -> None:
        self._stored_pat = auth if isinstance(auth, _StoredPAT) else None
        self._transport = _Transport(
            auth.read_auth if isinstance(auth, _StoredPAT) else auth, client=http_client, max_retries=max_retries
        )
        self.tenants = TenantsResource(self._transport)
        self.status = StatusResource(self._transport)
        self.events = EventsResource(self._transport)

    @classmethod
    def from_env(
        cls, *, pat: str | None | _Unset = _Unset.PAT, http_client: httpx.Client | None = None, max_retries: int = 2
    ) -> Self:
        """Create a client using ``SFDCTRUST_PAT`` or an explicit override.

        :param pat: An explicit override. Omitting it selects the environment.
                    Explicit ``None`` or any invalid override raises immediately.
        :param http_client: Optional caller-owned, trusted HTTPX client.
        :param max_retries: Additional SDK attempts per request, from 0 through 5.
        :returns: A configured client.
        :raises ConfigurationError: If the selected PAT is absent or invalid, or the retry limit is invalid.
        """
        auth = PATAuth.from_env(pat=pat)
        client = cls.__new__(cls)
        client._initialize(auth, http_client, max_retries)
        return client

    @classmethod
    def from_store(cls, store: PATStore, *, http_client: httpx.Client | None = None, max_retries: int = 2) -> Self:
        """Load an explicitly configured, seeded PAT store for one lineage.

        :param store: Trusted durable adapter shared by all rotators of this PAT.
        :param http_client: Optional caller-owned, trusted HTTPX client. Its
                            transport and hooks must never replay a refresh.
        :param max_retries: Additional SDK attempts per eligible read, from 0 through 5.
        :returns: A configured client.
        :raises ConfigurationError: If the store is unsuitable, unreadable,
                                    unseeded, or the retry limit is invalid.
        :raises PATRefreshPendingError: If the store has an unresolved rotation.
        """
        auth = _StoredPAT(store)
        client = cls.__new__(cls)
        client._initialize(auth, http_client, max_retries)
        return client

    def refresh_pat(self, *, expires_in_days: int | None = None) -> PATRefreshResult:
        """Explicitly rotate a stored PAT once and activate its durable replacement.

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
        if expires_in_days is not None and (type(expires_in_days) is not int or not 1 <= expires_in_days <= 30):
            raise ConfigurationError('expires_in_days must be an integer from 1 through 30 or None.')
        return self._stored_pat.refresh(self._transport, expires_in_days)

    def retry_pat_persistence(self) -> PATRefreshResult:
        """Reconcile or retry saving a replacement held by this client, using only store I/O.

        :returns: The original secret-free result once durable storage is confirmed.
        :raises ConfigurationError: If this client has no replacement awaiting persistence.
        :raises PATRefreshPendingError: If another PAT operation is running on this client.
        :raises PATPersistenceError: If the replacement still cannot be confirmed or saved.
        """
        if self._stored_pat is None:
            raise ConfigurationError('PAT persistence requires a store-backed client.')
        return self._stored_pat.retry_persistence()

    def close(self) -> None:
        """Close SDK-owned HTTP connections."""
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
