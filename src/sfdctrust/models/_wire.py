# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.models._wire
:Synopsis:          Shared response validation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

_TIMESTAMP = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])'
)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError('Expected a full ISO 8601 timestamp with an explicit offset.')
    return datetime.fromisoformat(value.upper())


_Timestamp = Annotated[datetime, BeforeValidator(_parse_timestamp)]


def _reject_null(value: object) -> object:
    if value is None:
        raise ValueError('This field may be omitted but cannot be null.')
    return value


class _WireModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
