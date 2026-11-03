# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.tenants
:Synopsis:          Synchronous tenant listing
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     02 Nov 2026
"""
from __future__ import annotations

import httpx
from pydantic import ValidationError

from .._exceptions import ConfigurationError, MalformedResponseError
from .._transport import _Transport
from ..models.tenants import TenantListResponse


class TenantsResource:
    """Access the tenants authorized for the client's PAT."""

    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def list(
        self, *, page_size: int | None = None, page_token: str | None = None, locale: str | None = None
    ) -> TenantListResponse:
        """Retrieve one page of authorized tenants.

        :param page_size: Maximum tenants to return, from 1 to 200.
        :param page_token: Opaque continuation token from the previous page.
            Keep the same page size and locale when continuing.
        :param locale: BCP 47 locale passed through to Salesforce, which handles fallback.
        :returns: A typed page, which may contain zero tenants.
        :raises ConfigurationError: If a supplied query argument is invalid.
        :raises APIStatusError: If Salesforce rejects the request, including a stale cursor.
        :raises MalformedResponseError: If the response is invalid JSON or violates the tenant schema.
        """
        params: dict[str, str | int] = {}
        if page_size is not None:
            if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 200:
                raise ConfigurationError('page_size must be an integer from 1 through 200.')
            params['pageSize'] = page_size
        if page_token is not None:
            if not isinstance(page_token, str) or len(page_token) > 4096:
                raise ConfigurationError('page_token must be a string of at most 4096 characters.')
            params['pageToken'] = page_token
        if locale is not None:
            if not isinstance(locale, str):
                raise ConfigurationError('locale must be a string.')
            params['locale'] = locale

        try:
            payload = self._transport.request('GET', '/tenants', params=params)
        except (UnicodeEncodeError, httpx.InvalidURL):
            pass
        else:
            try:
                return TenantListResponse.model_validate(payload)
            except ValidationError:
                pass
            raise MalformedResponseError('My Trust Center returned an invalid tenant page.')
        raise ConfigurationError('Tenant query arguments could not be encoded in a request URL.')
