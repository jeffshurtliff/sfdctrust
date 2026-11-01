# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._streams
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     01 Nov 2026

This file contains code from https://github.com/openai/openai-python/
"""
# TODO: Determine if this utilities module is needed and remove it if unneeded

from typing import Any
from typing_extensions import Iterator, AsyncIterator


def consume_sync_iterator(iterator: Iterator[Any]) -> None:
    for _ in iterator:
        ...


async def consume_async_iterator(iterator: AsyncIterator[Any]) -> None:
    async for _ in iterator:
        ...
