# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._json
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

import json
from typing import Any
from datetime import datetime
from typing_extensions import override

import pydantic

from .._compat import model_dump


def sfdctrust_dumps(obj: Any) -> bytes:
    """
    Serialize an object to UTF-8 encoded JSON bytes.

    Extends the standard json.dumps with support for additional types
    commonly used in the SDK, such as `datetime`, `pydantic.BaseModel`, etc.
    """
    return json.dumps(
        obj,
        cls=_CustomEncoder,
        # Uses the same defaults as httpx's JSON serialization
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class _CustomEncoder(json.JSONEncoder):
    @override
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, pydantic.BaseModel):
            return model_dump(o, exclude_unset=True, mode="json", by_alias=True)
        return super().default(o)
