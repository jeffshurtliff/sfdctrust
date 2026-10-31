# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._compat
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

from __future__ import annotations

import typing_extensions
from typing import Any, Type, Union, Literal
from datetime import date, datetime
from typing_extensions import get_args as _get_args, get_origin as _get_origin

from .._types import StrBytesIntFloat
from ._datetime_parse import parse_date as _parse_date, parse_datetime as _parse_datetime

_LITERAL_TYPES: set[object] = {Literal, typing_extensions.Literal}


def get_args(tp: type[Any]) -> tuple[Any, ...]:
    return _get_args(tp)


def get_origin(tp: type[Any]) -> type[Any] | None:
    return _get_origin(tp)


def is_union(tp: Type[Any] | None) -> bool:
    import types
    return tp is Union or tp is types.UnionType


def is_typeddict(tp: Type[Any]) -> bool:
    return typing_extensions.is_typeddict(tp)


def is_literal_type(tp: Type[Any]) -> bool:
    return get_origin(tp) in _LITERAL_TYPES


def parse_date(value: date | StrBytesIntFloat) -> date:
    return _parse_date(value)


def parse_datetime(value: datetime | StrBytesIntFloat) -> datetime:
    return _parse_datetime(value)
