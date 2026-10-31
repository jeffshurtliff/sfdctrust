# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._sync
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

from __future__ import annotations

import asyncio
import functools
from typing import TypeVar, Callable, Awaitable
from typing_extensions import ParamSpec

import anyio
import sniffio
import anyio.to_thread

T_Retval = TypeVar("T_Retval")
T_ParamSpec = ParamSpec("T_ParamSpec")


async def to_thread(
    func: Callable[T_ParamSpec, T_Retval], /, *args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs
) -> T_Retval:
    if sniffio.current_async_library() == "asyncio":
        return await asyncio.to_thread(func, *args, **kwargs)

    return await anyio.to_thread.run_sync(
        functools.partial(func, *args, **kwargs),
    )


# inspired by `asyncer`, https://github.com/tiangolo/asyncer
def asyncify(function: Callable[T_ParamSpec, T_Retval]) -> Callable[T_ParamSpec, Awaitable[T_Retval]]:
    """Converts a blocking function to async that receives the same positional and keyword arguments.

    :param function: A blocking regular callable (e.g. a function)
    :returns: An async function that takes the same positional and keyword arguments as the original that,
              when called, runs the same original function in a thread worker and returns the results
    """

    async def wrapper(*args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs) -> T_Retval:
        return await to_thread(function, *args, **kwargs)

    return wrapper
