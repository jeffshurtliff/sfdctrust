# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._cli
:Synopsis:          Private command-line parser and My Trust Center read commands
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import suppress
from typing import NoReturn, TextIO, get_args

import httpx
from pydantic import ValidationError

from . import SQLitePATStore, TrustCenterClient
from ._exceptions import (
    AuthenticationError,
    ConfigurationError,
    PATPersistenceError,
    PATRefreshPendingError,
    TrustCenterError,
)
from ._sqlite_pat_store import _path
from ._transport import _build_request, _destination, _request_timeout
from ._version import __version__
from .models._wire import _parse_timestamp
from .models.events import EventDetail, EventSearchResponse, EventSearchScope, EventSummary, EventType
from .models.status import StatusSnapshot
from .models.tenants import TenantDetail, TenantListResponse
from .resources._requests import _ModelRequest
from .resources.events import _event_detail_request, _event_search_request
from .resources.status import _snapshot_request
from .resources.tenants import _tenant_detail_request, _tenant_list_request

_Response = TenantListResponse | TenantDetail | StatusSnapshot | EventSearchResponse | EventDetail


class _Parser(argparse.ArgumentParser):
    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if status == 0:
            # Surface buffered help/version failures inside the CLI error boundary.
            sys.stdout.flush()
        super().exit(status, message)

    def error(self, message: str) -> NoReturn:
        # argparse messages can contain supplied values, including secrets.
        self.print_usage(sys.stderr)
        self.exit(2, 'sfdctrust: error: invalid arguments. Use --help for available options.\n')


def _parser() -> _Parser:
    parser = _Parser(
        prog='sfdctrust',
        description='Read authorized tenants, status snapshots, and events through the Salesforce My Trust Center SDK.',
        allow_abbrev=False,
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}', help='show package version and exit')
    groups = parser.add_subparsers(dest='resource', required=True)
    tenants = groups.add_parser('tenants', help='read authorized tenants', allow_abbrev=False)
    actions = tenants.add_subparsers(dest='action', required=True)
    listing = actions.add_parser('list', help='retrieve one page of authorized tenants', allow_abbrev=False)
    detail = actions.add_parser('get', help='retrieve a tenant and its supplied history', allow_abbrev=False)
    detail.add_argument('tenant_id', metavar='TENANT_ID')

    status = groups.add_parser('status', help='read tenant-scoped status', allow_abbrev=False)
    snapshot = status.add_subparsers(dest='action', required=True).add_parser(
        'snapshot', help='retrieve ongoing and upcoming events in all four category buckets', allow_abbrev=False
    )
    events = groups.add_parser('events', help='search events and read supplied timelines', allow_abbrev=False)
    event_actions = events.add_subparsers(dest='action', required=True)
    search = event_actions.add_parser('search', help='retrieve one page of tenant-scoped events', allow_abbrev=False)
    search.add_argument('--tenant-id', action='append', required=True, metavar='TENANT_ID', help='repeat for 1–50 tenant scopes')
    for bound, description in (('start', 'inclusive start'), ('end', 'exclusive end, later than start')):
        search.add_argument(
            f'--{bound}-time',
            type=_parse_timestamp,
            required=True,
            metavar='TIMESTAMP',
            help=f'{description}; full ISO 8601 timestamp with Z or ±HH:MM offset',
        )
    search.add_argument(
        '--event-type',
        action='append',
        choices=get_args(EventType),
        help='repeat distinct categories; omission includes all types',
    )
    event_detail = event_actions.add_parser('get', help='retrieve event metadata and its supplied timeline', allow_abbrev=False)
    event_detail.add_argument('event_id', metavar='EVENT_ID')
    for paged in (listing, search):
        paged.add_argument('--page-size', type=int, metavar='N', help='page size from 1 through 200 (default: SDK/API default)')
        paged.add_argument(
            '--page-token',
            metavar='TOKEN',
            help='opaque continuation, up to 4096 characters; empty string is a cursor; keep all other query inputs unchanged',
        )
    for action in (listing, detail, snapshot, search, event_detail):
        action.add_argument('--locale', help='locale forwarded unchanged to Salesforce')
        action.add_argument('--json', action='store_true', help='write the complete SDK response as JSON')
        credential = action.add_mutually_exclusive_group()
        credential.add_argument('--store', action='store_true', help='use the existing ~/.sfdctrust/pat.sqlite3 store')
        credential.add_argument('--store-path', metavar='PATH', help='use this existing SQLite PAT store')
        credential.add_argument('--store-alias', metavar='ALIAS', help='use an existing named store under ~/.sfdctrust')
    return parser


def _preflight(args: argparse.Namespace) -> None:
    """Validate with pure SDK helpers, including transport path/URL safety."""
    request: (
        _ModelRequest[TenantListResponse]
        | _ModelRequest[TenantDetail]
        | _ModelRequest[StatusSnapshot]
        | _ModelRequest[EventSearchResponse]
        | _ModelRequest[EventDetail]
    )
    if args.resource == 'tenants' and args.action == 'list':
        request = _tenant_list_request(page_size=args.page_size, page_token=args.page_token, locale=args.locale)
    elif args.resource == 'tenants':
        request = _tenant_detail_request(args.tenant_id, locale=args.locale)
    elif args.resource == 'status':
        request = _snapshot_request(locale=args.locale)
    elif args.action == 'search':
        args.scopes = tuple(EventSearchScope(id=identifier) for identifier in args.tenant_id)
        request = _event_search_request(
            scopes=args.scopes,
            start_time=args.start_time,
            end_time=args.end_time,
            event_types=args.event_type,
            page_size=args.page_size,
            page_token=args.page_token,
            locale=args.locale,
        )
    else:
        request = _event_detail_request(args.event_id, locale=args.locale)
    # Request construction checks encoding without constructing a client or sending.
    _build_request(
        request.method, _destination(request.path), _request_timeout(None), params=request.params, json_body=request.json_body
    )
    if args.store or args.store_path is not None or args.store_alias is not None:
        _path(args.store_path, args.store_alias)


def _client(args: argparse.Namespace) -> TrustCenterClient:
    if args.store or args.store_path is not None or args.store_alias is not None:
        return TrustCenterClient.from_store(SQLitePATStore(args.store_path, alias=args.store_alias))
    return TrustCenterClient.from_env()


def _read(client: TrustCenterClient, args: argparse.Namespace) -> _Response:
    if args.resource == 'tenants':
        if args.action == 'list':
            return client.tenants.list(page_size=args.page_size, page_token=args.page_token, locale=args.locale)
        return client.tenants.get(args.tenant_id, locale=args.locale)
    if args.resource == 'status':
        return client.status.snapshot(locale=args.locale)
    if args.action == 'search':
        return client.events.search(
            scopes=args.scopes,
            start_time=args.start_time,
            end_time=args.end_time,
            event_types=args.event_type,
            page_size=args.page_size,
            page_token=args.page_token,
            locale=args.locale,
        )
    return client.events.get(args.event_id, locale=args.locale)


def _escape(value: str) -> str:
    """Keep response text on its labeled line without terminal controls."""
    return ''.join(char if char.isprintable() else char.encode('unicode_escape').decode('ascii') for char in value)


def _value(value: object) -> str:
    return _escape(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def _tenant_text(response: TenantListResponse | TenantDetail) -> str:
    if isinstance(response, TenantListResponse):
        lines = ['Authorized tenants (one page):']
        for tenant in response.tenants:
            lines.append(' | '.join(_value(value) for value in (tenant.id, tenant.name, tenant.cloud, tenant.environment)))
        if not response.tenants:
            lines.append('No tenants returned in this authorized scope; this does not establish Salesforce-wide health.')
        if response.next_page_token is not None:
            cursor = _value(response.next_page_token) if response.next_page_token else '""'
            lines.append(f'Continuation (nextPageToken): {cursor}')
        return '\n'.join(lines) + '\n'

    lines = ['Authorized tenant:']
    fields = response.model_dump(mode='json', by_alias=True, exclude_unset=True)
    for key in ('id', 'name', 'cloud', 'environment', 'myDomain', 'region', 'version', 'maintenanceWindow', 'location'):
        if key in fields:
            lines.append(f'{key}: {_value(fields[key])}')
    lines.append('History (as supplied):')
    for event in response.events:
        lines.append(f'Event: {_value(event.event_id)}')
        for key, value in event.model_dump(mode='json', by_alias=True, exclude_unset=True).items():
            if key not in {'eventId', 'scope'}:
                lines.append(f'  {_escape(key)}: {_value(value)}')
        lines.append('  Affected tenant IDs: ' + _value(list(event.scope.tenants)))
    if not response.events:
        lines.append('No history returned in this authorized scope; this does not establish Salesforce-wide health.')
    return '\n'.join(lines) + '\n'


def _event_rows(event: EventSummary) -> list[str]:
    return [
        'Event: ' + ' | '.join(_value(value) for value in (event.event_id, event.event_type, event.status, event.title)),
        '  Affected tenant IDs: ' + _value(list(event.scope.tenants)),
    ]


def _text(response: _Response) -> str:
    if isinstance(response, (TenantListResponse, TenantDetail)):
        return _tenant_text(response)
    if isinstance(response, StatusSnapshot):
        lines = ['Authorized tenant status:']
        for name, group in (('ongoing', response.ongoing), ('upcoming', response.upcoming)):
            lines.append(f'{name}:')
            for category, events in (
                ('patch', group.patch),
                ('incident', group.incident),
                ('maintenance', group.maintenance),
                ('informationalMessage', group.informational_message),
            ):
                lines.append(f'  {category}:')
                for event in events:
                    lines.extend('    ' + line for line in _event_rows(event))
                if not events:
                    lines.append('    No events returned in this authorized scope.')
        lines.append('Empty buckets do not establish Salesforce-wide health.')
    elif isinstance(response, EventSearchResponse):
        lines = ['Authorized tenant events (one page):']
        for event in response.events:
            lines.extend(_event_rows(event))
        if not response.events:
            lines.append('No events returned in this authorized scope; this does not establish Salesforce-wide health.')
        if response.next_page_token is not None:
            cursor = _value(response.next_page_token) if response.next_page_token else '""'
            lines.append(f'Continuation (nextPageToken): {cursor}')
    else:
        lines = ['Event metadata:']
        for key, value in response.model_dump(mode='json', by_alias=True, exclude_unset=True).items():
            if key != 'timeline':
                lines.append(f'{_escape(key)}: {_value(value)}')
        if 'timeline' not in response.model_fields_set:
            lines.append('Timeline: omitted from response.')
        else:
            lines.append('Timeline (as supplied):')
            for entry in response.timeline or ():
                lines.append(f'Sub-event: {_value(entry.sub_event_id)}')
                for key, value in entry.model_dump(mode='json', by_alias=True, exclude_unset=True).items():
                    if key not in {'subEventId', 'scope'}:
                        lines.append(f'  {_escape(key)}: {_value(value)}')
                lines.append('  Affected tenant IDs: ' + _value(list(entry.scope.tenants)))
            if not response.timeline:
                lines.append(
                    'No timeline entries supplied in this authorized scope; this does not establish Salesforce-wide health.'
                )
    return '\n'.join(lines) + '\n'


def _render(response: _Response, as_json: bool) -> str:
    return response.model_dump_json(by_alias=True, exclude_unset=True) + '\n' if as_json else _text(response)


def _silence_output(stream: TextIO) -> None:
    # Prevent Python's shutdown flush from replacing exit 1 with 120 and printing
    # an ignored-exception diagnostic after an output device/pipe has failed.
    with suppress(Exception):
        descriptor = stream.fileno()
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, descriptor)
        finally:
            # Opening devnull can itself repair a closed standard descriptor.
            if null != descriptor:
                os.close(null)


def _diagnostic(message: str) -> None:
    try:
        sys.stderr.write(f'sfdctrust: {message}\n')
        sys.stderr.flush()
    except OSError:
        _silence_output(sys.stderr)
    except (Exception, KeyboardInterrupt):
        pass  # A failed diagnostic stream must not expose a traceback.


def main(argv: list[str] | None = None) -> None:
    """Run a read command, or show credential-free help/version.

    :param argv: Arguments without the program name; defaults to process arguments.
    :raises SystemExit: 0 success/help/version, 1 internal/output error, 2 invalid
                        arguments, 3 credential/configuration/store error, 4 API/
                        network/response error, or 130 interruption.
    """
    try:
        parser = _parser()
        args = parser.parse_args(argv)
        try:
            _preflight(args)
        except (ConfigurationError, ValidationError, UnicodeEncodeError, httpx.InvalidURL):
            parser.error('Invalid command inputs.')
        with _client(args) as client:
            response = _read(client, args)
            rendered = _render(response, args.json)
        # Finish rendering and close connections before touching stdout.
        sys.stdout.write(rendered)
        sys.stdout.flush()
    except OSError:
        _silence_output(sys.stdout)
        code, message = 1, 'internal or output failure.'
    except KeyboardInterrupt:
        code, message = 130, 'interrupted.'
    except (ConfigurationError, AuthenticationError, PATRefreshPendingError, PATPersistenceError):
        code, message = 3, 'credential, configuration, or PAT store failure. Check the selected credential and store state.'
    except TrustCenterError:
        code, message = 4, 'My Trust Center request failed.'
    except Exception:
        code, message = 1, 'internal or output failure.'
    else:
        raise SystemExit(0)
    _diagnostic(message)
    raise SystemExit(code)
