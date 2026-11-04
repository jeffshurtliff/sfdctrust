# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust
:Synopsis:          Primary module for the sfdctrust package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
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
    RateLimitError,
    RequestTimeoutError,
    TrustCenterError,
)
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
]
