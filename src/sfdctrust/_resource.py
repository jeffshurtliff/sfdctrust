# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._resource
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from ._client import MyTrustCenter, AsyncMyTrustCenter


class SyncAPIResource:
    _client: MyTrustCenter

    def __init__(self, client: MyTrustCenter) -> None:
        self._client = client
        self._get = client.get
        self._post = client.post
        self._patch = client.patch
        self._put = client.put
        self._delete = client.delete
        self._get_api_list = client.get_api_list

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class AsyncAPIResource:
    _client: AsyncMyTrustCenter

    def __init__(self, client: AsyncMyTrustCenter) -> None:
        self._client = client
        self._get = client.get
        self._post = client.post
        self._patch = client.patch
        self._put = client.put
        self._delete = client.delete
        self._get_api_list = client.get_api_list

    async def _sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)
