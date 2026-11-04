# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust
:Synopsis:          Primary module for the sfdctrust package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from ._client import TrustCenterClient
from ._exceptions import (
    APIStatusError,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    PaginationError,
    PATPersistenceError,
    PATProbeResult,
    PATRefreshAmbiguousError,
    PATRefreshPendingError,
    RateLimitError,
    RequestTimeoutError,
    TrustCenterError,
)
from ._pat_refresh import PATRefreshResult
from ._pat_store import PATStore, PATStoreRecord
from ._version import __version__

__all__ = [
    '__version__',
    'TrustCenterClient',
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
    'PATStore',
    'PATStoreRecord',
    'PATRefreshResult',
    'PATProbeResult',
    'PATRefreshPendingError',
    'PATRefreshAmbiguousError',
    'PATPersistenceError',
]
