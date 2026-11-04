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

    def _initialize(self, auth: PATAuth, http_client: httpx.Client | None, max_retries: int) -> None:
        self._transport = _Transport(auth, client=http_client, max_retries=max_retries)
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

    def close(self) -> None:
        """Close SDK-owned HTTP connections."""
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
