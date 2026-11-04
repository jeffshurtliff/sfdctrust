# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._exceptions
:Synopsis:          Exception classes that are utilized throughout the package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    'TrustCenterError',
    'ConfigurationError',
    'NetworkError',
    'RequestTimeoutError',
    'APIStatusError',
    'AuthenticationError',
    'RateLimitError',
    'NotFoundError',
    'MalformedResponseError',
    'PaginationError',
    'PATRefreshPendingError',
    'PATRefreshAmbiguousError',
    'PATPersistenceError',
    'PATProbeResult',
]


class TrustCenterError(Exception):
    """Base class for sfdctrust exceptions."""


class ConfigurationError(TrustCenterError):
    """Invalid SDK configuration; messages must be SDK-authored and secret-free."""


class NetworkError(TrustCenterError):
    """A request could not complete because of a network failure.

    Construct with a safe SDK-authored message, never an underlying exception's
    text, request, URL, headers, or response body.
    """


class RequestTimeoutError(NetworkError):
    """A request exceeded its configured timeout."""


class APIStatusError(TrustCenterError):
    """An API request returned an unsuccessful HTTP status.

    Only the status is retained. Raw requests, responses, and server messages
    are deliberately excluded. Request IDs are deferred until a documented,
    safe source is verified; no header name is assumed.

    :param status_code: An HTTP error status from 400 through 599.
    :raises ValueError: If the status is not an integer HTTP error status.
    """

    def __init__(self, status_code: int) -> None:
        if type(status_code) is not int or not 400 <= status_code <= 599:
            raise ValueError('status_code must be an integer from 400 through 599')
        self.status_code = status_code
        super().__init__(f'My Trust Center API returned HTTP {status_code}.')


class AuthenticationError(APIStatusError):
    """HTTP 401: the PAT is missing, invalid, revoked, or expired.

    This error does not identify which condition occurred and never triggers
    PAT refresh or credential replacement.
    """

    def __init__(self) -> None:
        super().__init__(401)


class RateLimitError(APIStatusError):
    """HTTP 429, without assuming JSON content or retry-related headers."""

    def __init__(self) -> None:
        super().__init__(429)


class NotFoundError(APIStatusError):
    """HTTP 404: the resource does not exist or is not authorized."""

    def __init__(self) -> None:
        super().__init__(404)


class MalformedResponseError(TrustCenterError):
    """A successful response could not be decoded or validated.

    Construct with a safe SDK-authored message, without response content or
    validation errors that might echo sensitive input.
    """


class PaginationError(TrustCenterError):
    """A traversal requires another page but reached its limit or repeated a cursor."""


class PATProbeResult(StrEnum):
    """Result of the single read-only check with the old PAT."""

    OLD_PAT_ACCEPTED = 'old_pat_accepted'
    OLD_PAT_REJECTED = 'old_pat_rejected'
    INCONCLUSIVE = 'inconclusive'


class PATRefreshPendingError(TrustCenterError):
    """A pending or competing rotation prevents the requested operation."""


class PATRefreshAmbiguousError(TrustCenterError):
    """Salesforce may have rotated the PAT without returning a usable replacement.

    :param probe: Sanitized result of the old PAT check.
    """

    def __init__(self, probe: PATProbeResult) -> None:
        self.probe = PATProbeResult(probe)
        super().__init__(f'PAT refresh outcome is ambiguous. Old PAT probe: {self.probe.value}.')


class PATPersistenceError(TrustCenterError):
    """A required durable PAT store transition could not be confirmed."""
