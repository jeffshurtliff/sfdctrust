# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._utils._logs
:Synopsis:
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff
:Modified Date:     31 Oct 2026

This file contains code from https://github.com/openai/openai-python/
"""

import os
import logging
from typing_extensions import override

from ._utils import is_dict
from .._constants import PACKAGE_NAME

logger: logging.Logger = logging.getLogger(PACKAGE_NAME)


SENSITIVE_HEADERS = {"api-key", "authorization", "x-amz-security-token"}
_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def _basic_config() -> None:
    # e.g. [2023-10-05 14:12:26 - openai._base_client:818 - DEBUG] HTTP Response: POST 200
    logging.basicConfig(
        format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_http_method_for_logging(method: str) -> str:
    normalized = method.upper()
    # TODO: Move set below into a frozenset constant in _constants.py
    if normalized in {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}:
        return normalized
    return "<custom>"


def setup_logging() -> None:
    # Transport loggers may include complete URLs. Leave their configuration to
    # the application instead of enabling them with the SDK's logging switch.
    env = os.environ.get("SFDCTRUST_LOG")
    if env is None:
        return

    level = _LOG_LEVELS.get(env)
    if level is None:
        return

    _basic_config()
    logger.setLevel(level)


class SensitiveHeadersFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        if is_dict(record.args) and "headers" in record.args and is_dict(record.args["headers"]):
            headers = record.args["headers"] = {**record.args["headers"]}
            for header in headers:
                if str(header).lower() in SENSITIVE_HEADERS:
                    headers[header] = "<redacted>"
        return True
