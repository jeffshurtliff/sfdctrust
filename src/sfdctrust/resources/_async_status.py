# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources._async_status
:Synopsis:          Asynchronous status snapshot
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from .._async_transport import _AsyncTransport
from ..models.status import StatusSnapshot
from .status import _snapshot_request


class AsyncStatusResource:
    """Read status across the client's authorized tenants."""

    def __init__(self, transport: _AsyncTransport) -> None:
        self._transport = transport

    async def snapshot(self, *, locale: str | None = None) -> StatusSnapshot:
        """Retrieve ongoing and upcoming events grouped by category.

        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: The tenant-scoped status snapshot, including repeated events.
        """
        return await _snapshot_request(locale=locale).send_async(self._transport)
