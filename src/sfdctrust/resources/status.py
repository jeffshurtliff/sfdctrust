# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.status
:Synopsis:          Synchronous status snapshot
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from .._transport import _Transport
from ..models.status import StatusSnapshot
from ._requests import _locale_params, _ModelRequest


def _snapshot_request(*, locale: str | None = None) -> _ModelRequest[StatusSnapshot]:
    return _ModelRequest(
        'GET',
        '/status',
        StatusSnapshot,
        params=_locale_params(locale),
        response_error='My Trust Center returned an invalid status snapshot.',
    )


class StatusResource:
    """Read status across the client's authorized tenants."""

    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def snapshot(self, *, locale: str | None = None) -> StatusSnapshot:
        """Retrieve ongoing and upcoming events grouped by category.

        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: The tenant-scoped status snapshot, including repeated events.
        """
        return _snapshot_request(locale=locale).send(self._transport)
