# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._auth
:Synopsis:          Internal PAT validation and single-request Bearer authentication
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     02 Nov 2026
"""

from __future__ import annotations

import os
from collections.abc import Generator
from enum import Enum
from typing import NoReturn, Self

import httpx
from pydantic import SecretStr

from ._constants import DEFAULT_BASE_URL
from ._exceptions import ConfigurationError


class _Unset(Enum):
    PAT = 'unset'


class PATAuth(httpx.Auth):
    """Internal HTTPX authentication using an explicitly supplied PAT.

    Construction performs no I/O and does not inspect the environment. PATs
    are opaque, nonempty strings of visible ASCII characters; whitespace and
    control characters are rejected, never stripped. No JWT parsing occurs.
    Ordinary representations redact the secret, and pickling is disabled.

    This component only attaches credentials. It does not translate HTTP
    statuses, retry, or refresh a PAT. Future transport code must disable
    redirects; HTTPX handles redirect requests outside this auth flow.

    :param pat: The PAT itself, without a Bearer prefix.
    :raises ConfigurationError: If the PAT is missing, blank, or unsafe for a header.
    """

    def __init__(self, pat: str) -> None:
        if not isinstance(pat, str) or not pat or any(not 0x21 <= ord(char) <= 0x7E for char in pat):
            raise ConfigurationError('PAT must be a nonempty string of visible ASCII characters without whitespace.')
        self._pat = SecretStr(pat)

    @classmethod
    def from_env(cls, *, pat: str | None | _Unset = _Unset.PAT) -> Self:
        """Read only ``SFDCTRUST_PAT``, unless an override is supplied.

        An explicit override wins without reading the environment. Empty,
        blank, and explicitly supplied ``None`` overrides fail validation;
        they never fall back to the environment. No credential files or
        ``.env`` files are read, and the environment is never modified.

        :param pat: Optional explicit override; omission selects the environment.
        :returns: A validated authentication object.
        :raises ConfigurationError: If the selected credential is invalid or absent.
        """
        selected = os.environ.get('SFDCTRUST_PAT') if pat is _Unset.PAT else pat
        if not isinstance(selected, str):
            raise ConfigurationError('PAT must be a nonempty string of visible ASCII characters without whitespace.')
        return cls(selected)

    def __repr__(self) -> str:
        return f'{type(self).__name__}(pat=**********)'

    def __getstate__(self) -> NoReturn:
        """Prevent accidental credential serialization through pickle."""
        raise TypeError('PAT authentication objects cannot be serialized.')

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        """Attach the PAT once, only to the production HTTPS origin.

        :param request: The request to authenticate.
        :yields: The request with its Authorization header replaced.
        :raises ConfigurationError: If the destination is outside the allowed origin
            or contains URL user information.
        """
        destination = request.url
        production = httpx.URL(DEFAULT_BASE_URL)
        if (
            destination.scheme != production.scheme
            or destination.host != production.host
            or destination.port != production.port
            or destination.userinfo
        ):
            raise ConfigurationError('PAT authentication requires the production HTTPS origin without URL user information.')
        request.headers['Authorization'] = f'Bearer {self._pat.get_secret_value()}'
        yield request
