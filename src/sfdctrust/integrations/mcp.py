# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.integrations.mcp
:Synopsis:          Local stdio tools for authorized My Trust Center reads
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.2 Sol)
:Modified Date:     18 Nov 2026
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from typing import Annotated, Any

from mcp import types
from mcp.server import MCPServer
from mcp.server.context import Context
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, ValidationError

from sfdctrust import (
    APIStatusError,
    AsyncTrustCenterClient,
    AuthenticationError,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    __version__,
)
from sfdctrust.models._wire import _parse_timestamp
from sfdctrust.models.events import EventSearchScope, EventType

_LIMIT = 64 * 1024
# Language-tag lexical structure, including private-use and grandfathered forms.
_LANGUAGE_TAG = re.compile(
    r'(?:(?:[a-z]{2,3}(?:-[a-z]{3}){0,3}|[a-z]{4,8})(?:-[a-z]{4})?(?:-[a-z]{2}|-[0-9]{3})?'
    r'(?P<variants>(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*)'
    r'(?P<extensions>(?:-[0-9a-wy-z](?:-[a-z0-9]{2,8})+)*)'
    r'(?:-x(?:-[a-z0-9]{1,8})+)?|x(?:-[a-z0-9]{1,8})+)'
)
_GRANDFATHERED = frozenset(
    'en-gb-oed i-ami i-bnn i-default i-enochian i-hak i-klingon i-lux i-mingo i-navajo i-pwn i-tao i-tay i-tsu '
    'sgn-be-fr sgn-be-nl sgn-ch-de art-lojban cel-gaulish no-bok no-nyn zh-guoyu zh-hakka zh-min zh-min-nan zh-xiang'.split()
)


def _locale(value: str) -> str:
    tag = value.lower()
    if value.isascii() and tag in _GRANDFATHERED:
        return value
    match = _LANGUAGE_TAG.fullmatch(tag)
    if not value.isascii() or match is None:
        raise ValueError('Invalid language tag.')
    variants = (match['variants'] or '').split('-')[1:]
    extensions = [part for part in (match['extensions'] or '').split('-') if len(part) == 1]
    if len(set(variants)) != len(variants) or len(set(extensions)) != len(extensions):
        raise ValueError('Repeated language tag component.')
    return value


def _identifier(value: str) -> str:
    if not value.strip() or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ValueError('Invalid identifier.')
    value.encode('utf-8')
    return value


_Id = Annotated[str, Field(min_length=1), AfterValidator(_identifier)]
_Locale = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_locale)]


class _Arguments(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    locale: _Locale | None = None


class _Page(_Arguments):
    page_size: int = Field(default=25, ge=1, le=100)
    page_token: str | None = Field(default=None, max_length=4096)


class _Tenants(_Page):
    """List one page of authorized tenants in upstream order."""

    async def read(self, client: AsyncTrustCenterClient) -> BaseModel:
        return await client.tenants.list(page_size=self.page_size, page_token=self.page_token, locale=self.locale)


class _Tenant(_Arguments):
    """Read an authorized tenant with optional embedded history. Use get_status for ongoing and upcoming events."""

    tenant_id: _Id
    include_history: bool = Field(default=True, description='Set to false to return tenant detail without the events field.')

    async def read(self, client: AsyncTrustCenterClient) -> BaseModel:
        return await client.tenants.get(self.tenant_id, locale=self.locale)


class _Status(_Arguments):
    """Read ongoing and upcoming status buckets for authorized tenants."""

    async def read(self, client: AsyncTrustCenterClient) -> BaseModel:
        return await client.status.snapshot(locale=self.locale)


class _Search(_Page):
    """Search one page of scoped events within an inclusive-start, exclusive-end time window."""

    tenant_ids: list[_Id] = Field(min_length=1, max_length=50)
    start_time: str = Field(json_schema_extra={'format': 'date-time'})
    end_time: str = Field(json_schema_extra={'format': 'date-time'})
    event_types: list[EventType] | None = Field(default=None, min_length=1, max_length=4)

    async def read(self, client: AsyncTrustCenterClient) -> BaseModel:
        # The SDK also checks window ordering, offset precision and distinct filters before HTTP.
        return await client.events.search(
            scopes=[EventSearchScope(id=value) for value in self.tenant_ids],
            start_time=_parse_timestamp(self.start_time),
            end_time=_parse_timestamp(self.end_time),
            event_types=self.event_types,
            page_size=self.page_size,
            page_token=self.page_token,
            locale=self.locale,
        )


class _Event(_Arguments):
    """Read an authorized event and its tenant-scoped timeline when supplied."""

    event_id: _Id

    async def read(self, client: AsyncTrustCenterClient) -> BaseModel:
        return await client.events.get(self.event_id, locale=self.locale)


_TOOLS = {'list_tenants': _Tenants, 'get_tenant': _Tenant, 'get_status': _Status, 'search_events': _Search, 'get_event': _Event}
_ERRORS = {
    'invalid_input': 'Check the arguments against the tool schema and search constraints.',
    'authentication': 'My Trust Center rejected the configured credential.',
    'rate_limit': 'My Trust Center rate-limited the read.',
    'not_found': 'The resource does not exist or is outside the authorized scope.',
    'timeout': 'The read timed out.',
    'network': 'The read could not reach My Trust Center.',
    'upstream': 'My Trust Center rejected the request.',
    'malformed_response': 'My Trust Center returned an invalid response.',
    'unsafe_output': 'The response contained credential material.',
    'internal_error': 'The server could not complete the read.',
}
_SDK_ERRORS = (
    (ConfigurationError, 'invalid_input'),
    (AuthenticationError, 'authentication'),
    (RateLimitError, 'rate_limit'),
    (NotFoundError, 'not_found'),
    (RequestTimeoutError, 'timeout'),
    (NetworkError, 'network'),
    (APIStatusError, 'upstream'),
    (MalformedResponseError, 'malformed_response'),
)


def _result(payload: dict, *, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[
            types.TextContent(type='text', text=json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
        ],
        # MCP 2.3 adds this identity and resultType on modern transports.
        # Include both now so the byte check counts the entire result.
        meta={types.SERVER_INFO_META_KEY: {'name': 'sfdctrust', 'version': __version__}},
        result_type='complete',
        structured_content=payload,
        is_error=error,
    )


def _error(code: str, *, message: str | None = None) -> types.CallToolResult:
    return _result({'error': {'code': code, 'message': _ERRORS[code] if message is None else message}}, error=True)


def _unsafe(value: object, pat: str) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower().replace('_', '').replace('-', '')
            in {'authorization', 'proxyauthorization', 'pat', 'accesstoken', 'refreshtoken'}
            or _unsafe(key, pat)
            or _unsafe(item, pat)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_unsafe(item, pat) for item in value)
    return isinstance(value, str) and (pat in value or 'bearer ' in value.lower())


class _Server(MCPServer):
    """Validate raw protocol arguments before the MCP SDK can coerce cursors or echo invalid input."""

    def __init__(self, client: AsyncTrustCenterClient, pat: SecretStr) -> None:
        super().__init__('sfdctrust', version=__version__, subscriptions=False)
        self.client = client
        self.pat = pat

    async def list_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=model.__doc__,
                input_schema=model.model_json_schema(),
                annotations=types.ToolAnnotations(read_only_hint=True, destructive_hint=False),
            )
            for name, model in _TOOLS.items()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any], context: Context | None = None) -> types.CallToolResult:
        model = _TOOLS.get(name)
        if model is None:
            return _error('invalid_input')
        try:
            request = model.model_validate(arguments)
            response = await request.read(self.client)
        except (ValidationError, ValueError, OverflowError):
            return _error('invalid_input')
        except Exception as exc:
            return _error(next((code for cls, code in _SDK_ERRORS if isinstance(exc, cls)), 'internal_error'))
        try:
            omit_history = isinstance(request, _Tenant) and not request.include_history
            data = response.model_dump(
                mode='json', by_alias=True, exclude_unset=True, exclude={'events'} if omit_history else None
            )
            payload = {'retrieved_at': datetime.now(UTC).isoformat(), 'data': data}
            result = _result(payload)
            serialized_bytes = len(result.model_dump_json(by_alias=True).encode('utf-8'))
            if serialized_bytes > _LIMIT:
                message = f'The complete result is {serialized_bytes:,} bytes and exceeds the {_LIMIT:,}-byte output limit.'
                if isinstance(request, _Tenant) and request.include_history:
                    message += (
                        ' Retry get_tenant with include_history=false for tenant detail, or use search_events for paged events.'
                    )
                return _error('output_limit', message=message)
            if _unsafe(data, self.pat.get_secret_value()):
                return _error('unsafe_output')
            return result
        except Exception:
            return _error('malformed_response')


async def _serve() -> None:
    pat = SecretStr(os.environ.get('SFDCTRUST_PAT', ''))
    async with AsyncTrustCenterClient.from_env(pat=pat.get_secret_value()) as client:
        await _Server(client, pat).run_stdio_async()


def main() -> int:
    """Run the local stdio server until the host closes the connection."""
    # Transport diagnostics may contain peer inputs, raw URLs or validation payloads.
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(_serve())
    except ConfigurationError:
        print('Configure a valid SFDCTRUST_PAT for the local server.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    except Exception:
        print('The local My Trust Center server stopped unexpectedly.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
