# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._resources_proxy
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     01 Nov 2026

This file contains code from https://github.com/openai/openai-python/
"""

from __future__ import annotations

from typing import Any
from typing_extensions import override

from ._proxy import LazyProxy


class ResourcesProxy(LazyProxy[Any]):
    """A proxy for the `sfdctrust.resources` module.

    This is used so that we can lazily import `sfdctrust.resources` only when
    needed *and* so that users can just import `sfdctrust` and reference `sfdctrust.resources`
    """

    @override
    def __load__(self) -> Any:
        import importlib

        mod = importlib.import_module('sfdctrust.resources')
        return mod


resources = ResourcesProxy().__as_proxied__()
