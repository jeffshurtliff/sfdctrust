# -*- coding: utf-8 -*-
"""
:Module:            tests.live_read_smoke
:Synopsis:          Opt-in read-only qualification of an installed wheel
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     09 Nov 2026
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sysconfig
import warnings
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from getpass import GetPassWarning, getpass
from inspect import isawaitable
from pathlib import Path

import sfdctrust
from sfdctrust import (
    APIStatusError,
    AsyncTrustCenterClient,
    ConfigurationError,
    MalformedResponseError,
    NetworkError,
    PaginationError,
    RequestTimeoutError,
    TrustCenterClient,
)
from sfdctrust.models.events import EventSearchScope, EventSummary
from sfdctrust.models.status import EventTypeBuckets

_PAGE_OPTIONS = {'page_size': 1, 'locale': 'en-US'}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unexpected arguments. A user may have supplied a PAT.
        self.exit(2, 'FAIL input: use --help for the required opt-in and supported PAT inputs.\n')


def _failure_reason(error: Exception) -> str:
    if isinstance(error, APIStatusError):
        return f'HTTP {error.status_code}'
    if isinstance(error, MalformedResponseError):
        return 'response schema or identity mismatch'
    if isinstance(error, PaginationError):
        return 'server repeated the continuation token'
    if isinstance(error, RequestTimeoutError):
        return 'request timed out'
    if isinstance(error, NetworkError):
        return 'network error'
    if isinstance(error, ConfigurationError):
        return 'invalid configuration or PAT input'
    return 'unexpected error'


class _Report:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def record(self, outcome: str, client: str, step: str, reason: str = '') -> None:
        self.counts[outcome] += 1
        suffix = f' ({reason})' if reason else ''
        print(f'{outcome} {client} {step}{suffix}')

    async def check[T](
        self, client: str, step: str, read: Callable[[], T | Awaitable[T]], summarize: Callable[[T], str]
    ) -> T | None:
        """Report a single read and keep its typed data in memory for later checks."""
        try:
            result = read()
            if isawaitable(result):
                result = await result
            summary = summarize(result)
        except Exception as error:
            self.record('FAIL', client, step, _failure_reason(error))
            return None
        self.record('PASS', client, step, summary)
        return result


def _continuation_count(token: str, next_token: str | None, count: int) -> str:
    if next_token == token:
        raise PaginationError('Repeated continuation token.')
    return f'records={count}'


def _detail_match(requested: str, returned: str) -> str:
    if requested != returned:
        raise MalformedResponseError('Detail identifier did not match the request.')
    return ''


def _bucket_events(bucket: EventTypeBuckets) -> list[EventSummary]:
    return [*bucket.patch, *bucket.incident, *bucket.maintenance, *bucket.informational_message]


async def _qualify(client: TrustCenterClient | AsyncTrustCenterClient, name: str, report: _Report, end: datetime) -> None:
    tenant_page = await report.check(
        name, 'tenant list', lambda: client.tenants.list(**_PAGE_OPTIONS), lambda page: f'records={len(page.tenants)}'
    )
    tenants = list(tenant_page.tenants) if tenant_page else []
    if tenant_page is None:
        report.record('SKIP', name, 'tenant pagination', 'initial read failed')
    elif (token := tenant_page.next_page_token) is None:
        report.record('SKIP', name, 'tenant pagination', 'no continuation token')
    else:
        next_page = await report.check(
            name,
            'tenant pagination',
            lambda: client.tenants.list(page_token=token, **_PAGE_OPTIONS),
            lambda page: _continuation_count(token, page.next_page_token, len(page.tenants)),
        )
        if next_page:
            tenants.extend(next_page.tenants)

    history: list[EventSummary] = []
    if tenants:
        tenant_id = tenants[0].id
        detail = await report.check(
            name,
            'tenant detail',
            lambda: client.tenants.get(tenant_id, locale='en-US'),
            lambda response: _detail_match(tenant_id, response.id),
        )
        if detail:
            history = detail.events
            report.record('PASS' if history else 'SKIP', name, 'tenant history', f'records={len(history)}')
        else:
            report.record('SKIP', name, 'tenant history', 'tenant detail failed')
    else:
        reason = 'no tenants in sampled pages' if tenant_page else 'tenant list failed'
        report.record('SKIP', name, 'tenant detail', reason)
        report.record('SKIP', name, 'tenant history', reason)

    snapshot = await report.check(
        name,
        'status snapshot',
        lambda: client.status.snapshot(locale='en-US'),
        lambda status: f'ongoing={len(_bucket_events(status.ongoing))}, upcoming={len(_bucket_events(status.upcoming))}',
    )

    events: list[EventSummary] = []
    if tenants:
        scopes = [EventSearchScope(id=tenant_id) for tenant_id in dict.fromkeys(tenant.id for tenant in tenants)]
        search_options = {'scopes': scopes, 'start_time': end - timedelta(days=90), 'end_time': end, **_PAGE_OPTIONS}
        search_page = await report.check(
            name, 'event search', lambda: client.events.search(**search_options), lambda page: f'records={len(page.events)}'
        )
        if search_page is None:
            report.record('SKIP', name, 'event pagination', 'initial read failed')
        else:
            events.extend(search_page.events)
            if (event_token := search_page.next_page_token) is None:
                report.record('SKIP', name, 'event pagination', 'no continuation token')
            else:
                next_events = await report.check(
                    name,
                    'event pagination',
                    lambda: client.events.search(page_token=event_token, **search_options),
                    lambda page: _continuation_count(event_token, page.next_page_token, len(page.events)),
                )
                if next_events:
                    events.extend(next_events.events)
    else:
        reason = 'no tenants in sampled pages' if tenant_page else 'tenant list failed'
        report.record('SKIP', name, 'event search', reason)
        report.record('SKIP', name, 'event pagination', reason)

    if not events:
        events = history or (_bucket_events(snapshot.ongoing) + _bucket_events(snapshot.upcoming) if snapshot else [])
    if not events:
        report.record('SKIP', name, 'event detail', 'no event ID available from completed reads')
        report.record('SKIP', name, 'event timeline', 'no event detail')
        return

    event_id = events[0].event_id
    event = await report.check(
        name,
        'event detail',
        lambda: client.events.get(event_id, locale='en-US'),
        lambda response: _detail_match(event_id, response.event_id),
    )
    if event:
        timeline_count = len(event.timeline or [])
        report.record('PASS' if timeline_count else 'SKIP', name, 'event timeline', f'records={timeline_count}')
    else:
        report.record('SKIP', name, 'event timeline', 'event detail failed')


async def _run(pat: str) -> int:
    report = _Report()
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    try:
        with TrustCenterClient(pat=pat, max_retries=0) as client:
            await _qualify(client, 'sync', report, end)
    except Exception as error:
        report.record('FAIL', 'sync', 'client', _failure_reason(error))

    try:
        async with AsyncTrustCenterClient(pat=pat, max_retries=0) as async_client:
            await _qualify(async_client, 'async', report, end)
    except Exception as error:
        report.record('FAIL', 'async', 'client', _failure_reason(error))

    print(f'SUMMARY pass={report.counts["PASS"]} fail={report.counts["FAIL"]} skip={report.counts["SKIP"]}')
    return int(report.counts['FAIL'] > 0)


def main(argv: list[str] | None = None) -> int:
    """Run the explicit live procedure using a hidden prompt or a selected environment variable."""
    parser = _Parser(description='Read-only My Trust Center smoke test for an installed sfdctrust wheel.', allow_abbrev=False)
    parser.add_argument('--live', action='store_true', required=True, help='Opt in to real, read-only Salesforce requests')
    parser.add_argument('--from-env', metavar='NAME', help='Read the PAT only from this environment variable')
    args = parser.parse_args(argv)

    if not Path(sfdctrust.__file__).resolve().is_relative_to(Path(sysconfig.get_path('purelib')).resolve()):
        print('FAIL installation: install the candidate wheel into a clean virtual environment.')
        return 1

    try:
        if args.from_env is None:
            with warnings.catch_warnings():
                warnings.simplefilter('error', GetPassWarning)
                pat = getpass('My Trust Center PAT (input is hidden): ')
        else:
            pat = os.environ.get(args.from_env)
        if not pat:
            print('FAIL input: no PAT supplied.')
            return 1
    except (GetPassWarning, EOFError, KeyboardInterrupt, OSError, ValueError):
        print('FAIL input: hidden or environment input unavailable.')
        return 1

    try:
        return asyncio.run(_run(pat))
    except KeyboardInterrupt:
        print('FAIL run: cancelled.')
        return 1


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    raise SystemExit(main())
