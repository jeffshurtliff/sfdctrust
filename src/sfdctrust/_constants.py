# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._constants
:Synopsis:          Constants that are utilized throughout the package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Final, Mapping

import httpx2

# -----------------------------
# Versioning / Meta
# -----------------------------

PACKAGE_NAME = "sfdctrust"

# --------------------------------------
# Common Validation Criteria / Mapping
# --------------------------------------

SALESFORCE_ID_SUFFIX_ALPHABET: Final[str] = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'
VALID_SALESFORCE_URL_PATTERN: Final[str] = r'^https://[a-zA-Z0-9._-]+\.salesforce\.com(/|$)'
YAML_BOOLEAN_MAPPING: Final[Mapping[str | bool, bool]] = MappingProxyType(
    {
        True: True,
        False: False,
        'yes': True,
        'no': False,
    }
)


# -----------------------------
# HTTP / REST API
# -----------------------------

# default timeout is 10 minutes
DEFAULT_TIMEOUT = httpx2.Timeout(timeout=600, connect=5.0)
DEFAULT_MAX_RETRIES = 2
DEFAULT_CONNECTION_LIMITS = httpx2.Limits(max_connections=1000, max_keepalive_connections=100)
# A 30-second Live PCM16 fixture takes 1,920,000 base64 bytes before its JSON envelope
DEFAULT_LIVE_SEND_QUEUE_MAX_BYTES = 2_097_152

INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
MAX_RETRY_AFTER_DELAY = 2 * 60
