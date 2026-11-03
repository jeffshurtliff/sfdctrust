# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.status
:Synopsis:          Synchronous status snapshot
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from .._transport import _Transport
from ..models.status import StatusSnapshot
from ._requests import _locale_params, _request_model


class StatusResource:
    """Read status across the client's authorized tenants."""

    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def snapshot(self, *, locale: str | None = None) -> StatusSnapshot:
        """Retrieve ongoing and upcoming events grouped by category.

        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: The tenant-scoped status snapshot, including repeated events.
        """
        return _request_model(
            self._transport,
            'GET',
            '/status',
            StatusSnapshot,
            params=_locale_params(locale),
            response_error='My Trust Center returned an invalid status snapshot.',
        )
