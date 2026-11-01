# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._exceptions
:Synopsis:          Exception classes that are utilized throughout the package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, cast

import httpx2

from ._utils import is_dict
from ._models import construct_type
from .types.shared.oauth_error_code import OAuthErrorCode

__all__ = []


class MyTrustCenterError(Exception):
    """This is the base class for sfdctrust exceptions."""
    pass


class SubjectTokenProviderError(MyTrustCenterError):
    response: httpx2.Response | None

    def __init__(self, message: str, *, response: httpx2.Response | None = None) -> None:
        super().__init__(message)
        self.response = response


class APIError(MyTrustCenterError):
    message: str
    request: httpx2.Request

    body: object | None
    """The API response body.

    If the API responded with a valid JSON structure then this property will be the
    decoded result.

    If it isn't a valid JSON structure then this will be the raw response.

    If there was no response associated with this error then it will be `None`.
    """

    code: str | None = None
    param: str | None = None
    type: str | None

    def __init__(self, message: str, request: httpx2.Request, *, body: object | None) -> None:
        super().__init__(message)
        self.request = request
        self.message = message
        self.body = body

        if is_dict(body):
            code = body.get("code")
            self.code = str(code) if code is not None else None
            self.param = cast(Any, construct_type(type_=Optional[str], value=body.get("param")))
            self.type = cast(Any, construct_type(type_=str, value=body.get("type")))
        else:
            self.code = None
            self.param = None
            self.type = None
