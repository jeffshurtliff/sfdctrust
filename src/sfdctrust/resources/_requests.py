# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.resources._requests
:Synopsis:          Shared synchronous resource request validation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from .._exceptions import ConfigurationError, MalformedResponseError
from .._transport import _Transport


def _locale_params(locale: str | None) -> dict[str, str]:
    if locale is None:
        return {}
    if not isinstance(locale, str):
        raise ConfigurationError('locale must be a string.')
    return {'locale': locale}


def _page_params(page_size: int | None, page_token: str | None) -> dict[str, str | int]:
    params: dict[str, str | int] = {}
    if page_size is not None:
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 200:
            raise ConfigurationError('page_size must be an integer from 1 through 200.')
        params['pageSize'] = page_size
    if page_token is not None:
        if not isinstance(page_token, str) or len(page_token) > 4096:
            raise ConfigurationError('page_token must be a string of at most 4096 characters.')
        params['pageToken'] = page_token
    return params


def _id_segment(identifier: str) -> str:
    if not isinstance(identifier, str) or not identifier:
        raise ConfigurationError('A nonempty string ID is required.')
    try:
        # The transport also checks the decoded segment for ambiguous syntax.
        return quote(identifier, safe='')
    except UnicodeEncodeError:
        pass
    raise ConfigurationError('The resource ID could not be encoded in a request URL.')


def _request_model[Model: BaseModel](
    transport: _Transport,
    method: str,
    path: str,
    model: type[Model],
    *,
    params: Mapping[str, str | int],
    response_error: str,
    encoding_error: str = 'Request arguments could not be encoded.',
    json_body: dict[str, object] | None = None,
) -> Model:
    try:
        payload = transport.request(method, path, params=params, json_body=json_body)
    except (UnicodeEncodeError, httpx.InvalidURL):
        pass
    else:
        try:
            return model.model_validate(payload)
        except ValidationError:
            pass
        raise MalformedResponseError(response_error)
    raise ConfigurationError(encoding_error)
