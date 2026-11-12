# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources.tenants
:Synopsis:          Synchronous tenant listing and detail
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     12 Nov 2026
"""

from __future__ import annotations

import builtins
from collections.abc import Iterator

from .._transport import _Transport
from ..models.tenants import Tenant, TenantDetail, TenantListResponse
from ._requests import _id_segment, _iterate_pages, _locale_params, _ModelRequest, _page_params


def _tenant_list_request(
    *, page_size: int | None = None, page_token: str | None = None, locale: str | None = None
) -> _ModelRequest[TenantListResponse]:
    params = _page_params(page_size, page_token)
    params.update(_locale_params(locale))
    return _ModelRequest(
        'GET',
        '/tenants',
        TenantListResponse,
        params=params,
        response_error='My Trust Center returned an invalid tenant page.',
        encoding_error='Tenant query arguments could not be encoded in a request URL.',
    )


def _tenant_detail_request(tenant_id: str, *, locale: str | None = None) -> _ModelRequest[TenantDetail]:
    return _ModelRequest(
        'GET',
        f'/tenants/{_id_segment(tenant_id)}',
        TenantDetail,
        params=_locale_params(locale),
        response_error='My Trust Center returned invalid tenant detail.',
    )


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
        return _tenant_list_request(page_size=page_size, page_token=page_token, locale=locale).send(self._transport)

    def iter_all(
        self,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
        max_pages: int = 1000,
    ) -> Iterator[Tenant]:
        """Yield authorized tenants in server order, fetching pages on demand.

        :param page_size: Optional maximum tenants per page, from 1 through 200.
        :param page_token: Optional opaque starting cursor.
        :param locale: BCP 47 locale forwarded to Salesforce.
        :param max_pages: Positive maximum number of fetched pages.
        :raises PaginationError: If a cursor repeats or a further page exceeds the limit.
                                 Earlier items may already have been yielded.
        """

        def fetch(token: str | None) -> tuple[list[Tenant], str | None]:
            page = self.list(page_size=page_size, page_token=token, locale=locale)
            return page.tenants, page.next_page_token

        return _iterate_pages(fetch, page_token, max_pages)

    def list_all(
        self,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
        max_pages: int = 1000,
    ) -> builtins.list[Tenant]:
        """Collect :meth:`iter_all` results, propagating any traversal error.

        :param page_size: Optional maximum tenants per page, from 1 through 200.
        :param page_token: Optional opaque starting cursor.
        :param locale: BCP 47 locale forwarded to Salesforce.
        :param max_pages: Positive maximum number of fetched pages.
        """
        return list(self.iter_all(
            page_size=page_size,
            page_token=page_token,
            locale=locale,
            max_pages=max_pages,
        ))

    def get(self, tenant_id: str, *, locale: str | None = None) -> TenantDetail:
        """Retrieve a tenant and its history in Salesforce's fixed window.

        :param tenant_id: Opaque tenant identifier.
        :param locale: BCP 47 locale forwarded to Salesforce for fallback.
        :returns: Tenant detail with embedded events.
        :raises NotFoundError: If the tenant is nonexistent or unauthorized.
        """
        return _tenant_detail_request(tenant_id, locale=locale).send(self._transport)
