# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._client
:Synopsis:          Synchronous My Trust Center client
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
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
    :raises ConfigurationError: If the PAT is invalid.
    """

    def __init__(self, pat: str, *, http_client: httpx.Client | None = None) -> None:
        self._initialize(PATAuth(pat), http_client)

    def _initialize(self, auth: PATAuth, http_client: httpx.Client | None) -> None:
        self._transport = _Transport(auth, client=http_client)
        self.tenants = TenantsResource(self._transport)
        self.status = StatusResource(self._transport)
        self.events = EventsResource(self._transport)

    @classmethod
    def from_env(cls, *, pat: str | None | _Unset = _Unset.PAT, http_client: httpx.Client | None = None) -> Self:
        """Create a client using ``SFDCTRUST_PAT`` or an explicit override.

        :param pat: An explicit override. Omitting it selects the environment.
                    Explicit ``None`` or any invalid override raises immediately.
        :param http_client: Optional caller-owned, trusted HTTPX client.
        :returns: A configured client.
        :raises ConfigurationError: If the selected PAT is absent or invalid.
        """
        auth = PATAuth.from_env(pat=pat)
        client = cls.__new__(cls)
        client._initialize(auth, http_client)
        return client

    def close(self) -> None:
        """Close SDK-owned HTTP connections."""
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
