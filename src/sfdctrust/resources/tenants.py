# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.tenants
:Synopsis:          Synchronous tenant listing and detail
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from .._transport import _Transport
from ..models.tenants import TenantDetail, TenantListResponse
from ._requests import _id_segment, _locale_params, _page_params, _request_model


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
        params = _page_params(page_size, page_token)
        params.update(_locale_params(locale))
        return _request_model(
            self._transport,
            'GET',
            '/tenants',
            TenantListResponse,
            params=params,
            response_error='My Trust Center returned an invalid tenant page.',
            encoding_error='Tenant query arguments could not be encoded in a request URL.',
        )

    def get(self, tenant_id: str, *, locale: str | None = None) -> TenantDetail:
        """Retrieve a tenant and its history in Salesforce's fixed window.

        :param tenant_id: Opaque tenant identifier.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: Tenant detail with embedded events.
        :raises NotFoundError: If the tenant is nonexistent or unauthorized.
        """
        return _request_model(
            self._transport,
            'GET',
            f'/tenants/{_id_segment(tenant_id)}',
            TenantDetail,
            params=_locale_params(locale),
            response_error='My Trust Center returned invalid tenant detail.',
        )
