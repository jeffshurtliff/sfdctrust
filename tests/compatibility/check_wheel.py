# -*- coding: utf-8 -*-
"""
:Module:            tests.compatibility.check_wheel
:Synopsis:          Network-blocked public compatibility checks for installed wheels
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     11 Nov 2026
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import inspect
import json
import os
import platform
import re
import runpy
import socket
import struct
import sys
import sysconfig
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from importlib.metadata import distribution, version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from zipfile import ZipFile

# No source path is added to sys.path, including when run with -I.
# Import the SDK only after the socket/DNS guard is installed in main().
BLOCKED = 0
PAT = 'synthetic-compatibility-pat'
TIME = '2026-09-01T00:00:00.123456+05:45'
TENANT = {'id': 'synthetic-tenant', 'cloud': 'future-cloud', 'name': 'Synthetic tenant'}
SCOPE = {'tenants': {'synthetic-tenant': {'futureScopeField': 1}}}
EVENT = {
    'eventId': 'synthetic-event',
    'eventType': 'future-event',
    'status': 'future-status',
    'products': [],
    'services': [],
    'createdAt': TIME,
}
BUCKETS = {'patch': [], 'incident': [], 'maintenance': [], 'informationalMessage': []}
MODELS = {
    'tenants': ['Tenant', 'TenantListResponse', 'TenantDetail', 'TenantLocation'],
    'status': ['EventTypeBuckets', 'StatusSnapshot'],
    'events': [
        'EventType',
        'EventSearchScope',
        'EventSearchResponse',
        'EventSearchResult',
        'EventDetail',
        'EventSummary',
        'SubEventScope',
        'PatchEventData',
        'IncidentEventData',
        'MaintenanceEventData',
        'InformationalMessageEventData',
        'TimelineItem',
        'PatchTimelineItem',
        'IncidentTimelineItem',
        'MaintenanceTimelineItem',
        'InformationalMessageTimelineItem',
        'PatchNote',
    ],
}


def deny_network(event, arguments):
    """Block every socket/DNS audit event, including missed mocks."""
    global BLOCKED
    if event.startswith('socket.'):
        BLOCKED += 1
        raise RuntimeError('Networking is disabled during compatibility qualification.')


@contextmanager
def raises(expected):
    try:
        yield
    except expected:
        return
    raise AssertionError('Expected compatibility failure did not occur.')


def installed(wheel, expected):
    assert sys.flags.isolated and not sys.flags.optimize
    assert sys.prefix != sys.base_prefix
    location = Path(sdk.__file__).resolve()
    assert location.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    direct = distribution('sfdctrust').read_text('direct_url.json')
    assert direct and not json.loads(direct).get('dir_info', {}).get('editable', False)
    assert sdk.__version__ == version('sfdctrust') == expected
    assert (location.parent / 'py.typed').is_file()
    with ZipFile(wheel) as archive:
        assert 'sfdctrust/py.typed' in archive.namelist()
        # Prove imported package files are exactly the wheel under test.
        for name in archive.namelist():
            if name.startswith('sfdctrust/') and not name.endswith('/'):
                assert location.parent.joinpath(*Path(name).parts[1:]).read_bytes() == archive.read(name)
    return str(location)


def signature(function):
    # The omission sentinel is private. Record its semantics, not its spelling.
    sig = inspect.signature(function)
    return {
        'parameters': [
            {
                'name': p.name,
                'kind': p.kind.name,
                'type': str(p.annotation).replace('_Unset', '<omitted>') if p.annotation is not inspect.Parameter.empty else '',
                'default': (
                    '<required>'
                    if p.default is inspect.Parameter.empty
                    else '<omitted>'
                    if p.name == 'pat' and p.kind is inspect.Parameter.KEYWORD_ONLY
                    else repr(p.default)
                ),
            }
            for p in sig.parameters.values()
            if p.name not in {'self', 'cls'}
        ],
        'returns': str(sig.return_annotation).replace('builtins.list', 'list')
        if sig.return_annotation is not inspect.Signature.empty
        else '',
        'invocation': 'await' if inspect.iscoroutinefunction(function) else 'call',
    }


def public_contract():
    calls, models = {}, {}
    for client_class in (sdk.TrustCenterClient, sdk.AsyncTrustCenterClient):
        calls[client_class.__name__] = signature(client_class)
        methods = ['from_env', 'from_store', 'refresh_pat', 'retry_pat_persistence']
        methods += (
            ['aclose', '__aenter__', '__aexit__']
            if client_class is sdk.AsyncTrustCenterClient
            else ['close', '__enter__', '__exit__']
        )
        for name in methods:
            calls[f'{client_class.__name__}.{name}'] = signature(getattr(client_class, name))
        # Constructor is network-free; supply caller-owned mocks to avoid opening connections.
        http_class = httpx.AsyncClient if client_class is sdk.AsyncTrustCenterClient else httpx.Client
        http = http_class(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
        client = client_class(PAT, http_client=http)
        for resource, methods in {
            'tenants': ['list', 'get', 'iter_all', 'list_all'],
            'events': ['search', 'get', 'iter_search', 'search_all'],
            'status': ['snapshot'],
        }.items():
            for name in methods:
                calls[f'{client_class.__name__}.{resource}.{name}'] = signature(getattr(getattr(client, resource), name))
    for name, methods in {
        'PATStore': ['load', 'compare_and_swap'],
        'AsyncPATStore': ['load', 'compare_and_swap'],
        'PATStoreRecord': ['get_pat'],
        'PATRefreshResult': [],
        'SQLitePATStore': ['initialize', 'load', 'compare_and_swap'],
    }.items():
        cls = getattr(sdk, name)
        if name not in {'PATStore', 'AsyncPATStore'}:
            calls[name] = signature(cls)
        for method in methods:
            calls[f'{name}.{method}'] = signature(getattr(cls, method))
    for name in ('APIStatusError', 'AuthenticationError', 'NotFoundError', 'RateLimitError', 'PATRefreshAmbiguousError'):
        calls[name] = signature(getattr(sdk, name))
    for module_name, names in MODELS.items():
        module = importlib.import_module(f'sfdctrust.models.{module_name}')
        for name in names:
            model = getattr(module, name)
            fields = getattr(model, 'model_fields', {})
            models[f'sfdctrust.models.{module_name}.{name}'] = {
                key: {
                    'alias': field.alias or key,
                    'required': field.is_required(),
                    'type': re.sub(r' at 0x[0-9a-fA-F]+', '', str(field.annotation)),
                    'default': '<required>' if field.is_required() else repr(field.default),
                }
                for key, field in fields.items()
            }
    exceptions = {
        name: [base.__name__ for base in getattr(sdk, name).__mro__[1:] if issubclass(base, Exception)]
        for name in sdk.__all__
        if isinstance(getattr(sdk, name), type) and issubclass(getattr(sdk, name), Exception)
    }
    return {
        'exports': sorted(sdk.__all__),
        'calls': calls,
        'models': models,
        'exceptions': exceptions,
        'probe_values': {member.name: member.value for member in sdk.PATProbeResult},
    }


def serialization():
    from pydantic import ValidationError

    from sfdctrust.models.events import EventDetail, EventSearchScope
    from sfdctrust.models.status import StatusSnapshot
    from sfdctrust.models.tenants import Tenant, TenantDetail, TenantListResponse

    payload = {**TENANT, 'myDomain': 'synthetic.example', 'extra': {'future': True}}
    tenant = Tenant.model_validate(payload)
    assert tenant.my_domain == 'synthetic.example'
    assert tenant.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload
    assert 'environment' not in tenant.model_fields_set and tenant.environment is None
    with raises(ValidationError):
        Tenant.model_validate({**TENANT, 'environment': None})
    with raises(ValidationError):
        TenantListResponse.model_validate({'tenants': [], 'nextPageToken': None})
    with raises(ValidationError):
        EventSearchScope.model_validate({'id': 'synthetic', 'type': 'future-scope'})
    with raises(ValidationError):
        Tenant.model_validate({**TENANT, 'id': 123})
    for field in ('region', 'version', 'maintenanceWindow'):
        detail = TenantDetail.model_validate({**TENANT, 'events': [], field: None})
        assert detail.model_dump(mode='json', by_alias=True, exclude_unset=True)[field] is None
    event = EventDetail.model_validate(
        {
            **EVENT,
            'endTime': None,
            'data': {'future': 1},
            'extra': 2,
            'timeline': [
                {
                    'subEventId': 'entry',
                    'subEventType': 'future-subtype',
                    'scope': SCOPE,
                    'createdAt': TIME,
                    'future': 3,
                }
            ],
        }
    )
    assert event.event_type == 'future-event' and event.status == 'future-status'
    assert event.created_at.utcoffset() == timedelta(hours=5, minutes=45)
    assert event.created_at.microsecond == 123456
    assert event.end_time is None and 'end_time' in event.model_fields_set
    assert event.start_time is None and 'start_time' not in event.model_fields_set
    assert event.timeline[0].sub_event_type == 'future-subtype'
    assert event.model_dump(mode='json', by_alias=True, exclude_unset=True)['createdAt'] == TIME
    with raises(ValidationError):
        EventDetail.model_validate({**EVENT, 'createdAt': '2026-09-01T00:00:00'})
    patch = {**EVENT, 'eventType': 'patch', 'scope': SCOPE}
    other = {**patch, 'scope': {'tenants': {'another-tenant': {}}}, 'status': 'different-stage'}
    payload = {'ongoing': {**BUCKETS, 'patch': [patch, other]}, 'upcoming': {**BUCKETS, 'patch': [other]}}
    snapshot = StatusSnapshot.model_validate(payload)
    assert [item.event_id for item in snapshot.ongoing.patch] == ['synthetic-event'] * 2
    assert snapshot.model_dump(mode='json', by_alias=True, exclude_unset=True) == payload


class Service:
    def __init__(self):
        self.requests = []
        self.responses = []

    def __call__(self, request):
        assert request.headers['Authorization'] == f'Bearer {PAT}'
        assert request.extensions['timeout'] == {'connect': 5.0, 'pool': 5.0, 'read': 30.0, 'write': 30.0}
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        path = request.url.path
        if path.endswith('/tenants'):
            return httpx.Response(200, json={'tenants': [TENANT]})
        if '/tenants/' in path:
            return httpx.Response(200, json={**TENANT, 'events': []})
        if path.endswith('/status'):
            return httpx.Response(200, json={'ongoing': BUCKETS, 'upcoming': BUCKETS})
        if path.endswith('/events/search'):
            return httpx.Response(200, json={'events': [{**EVENT, 'scope': SCOPE}]})
        return httpx.Response(200, json=EVENT)


def search_args():
    from sfdctrust.models.events import EventSearchScope

    return {
        'scopes': [EventSearchScope(id='synthetic-tenant')],
        'start_time': datetime(2026, 1, 1, tzinfo=UTC),
        'end_time': datetime(2026, 1, 2, tzinfo=UTC),
    }


def sync_behavior():
    service = Service()
    with httpx.Client(transport=httpx.MockTransport(service), timeout=0.01) as http:
        with sdk.TrustCenterClient.from_env(pat=PAT, http_client=http, max_retries=0) as client:
            assert client.tenants.list().tenants[0].id == TENANT['id']
            assert client.tenants.get('synthetic-tenant').events == []
            assert client.status.snapshot().upcoming.patch == []
            assert client.events.search(**search_args()).events[0].event_id == EVENT['eventId']
            assert client.events.get('synthetic-event').event_id == EVENT['eventId']
            assert client.tenants.list_all()[0].id == TENANT['id']
            assert client.events.search_all(**search_args())[0].event_id == EVENT['eventId']
            for failing_page, error_type in [
                (httpx.Response(400), sdk.APIStatusError),
                (httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': 'cursor'}), sdk.PaginationError),
            ]:
                service.responses = [httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': 'cursor'}), failing_page]
                count = len(service.requests)
                iterator = client.tenants.iter_all(page_size=1, locale='en-US')
                assert len(service.requests) == count  # Lazy first request.
                assert next(iterator).id == TENANT['id']
                if error_type is sdk.PaginationError:
                    assert next(iterator).id == TENANT['id']  # Current page delivered before guard.
                with raises(error_type):
                    next(iterator)
                assert len(service.requests) == count + 2
                assert service.requests[-1].url.params['pageToken'] == 'cursor'
                assert service.requests[-1].url.params['pageSize'] == '1'
            service.responses = [
                httpx.Response(200, json={'tenants': [], 'nextPageToken': ''}),
                httpx.Response(200, json={'tenants': [TENANT]}),
            ]
            assert len(client.tenants.list_all(max_pages=2)) == 1
            assert service.requests[-1].url.params['pageToken'] == ''
            service.responses = [httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': 'more'})]
            iterator = client.tenants.iter_all(max_pages=1)
            assert next(iterator).id == TENANT['id']
            with raises(sdk.PaginationError):
                next(iterator)
            with raises(sdk.ConfigurationError):
                client.refresh_pat()
            with raises(sdk.ConfigurationError):
                sdk.TrustCenterClient.from_env(pat=None, http_client=http)
            for status, error_type in [(401, sdk.AuthenticationError), (404, sdk.NotFoundError), (429, sdk.RateLimitError)]:
                service.responses = [httpx.Response(status)]
                try:
                    client.tenants.list()
                except error_type as exc:
                    assert exc.status_code == status and isinstance(exc, sdk.APIStatusError)
                else:
                    raise AssertionError('Expected typed HTTP failure.')
            service.responses = [httpx.Response(200, json={'tenants': 'bad'})]
            with raises(sdk.MalformedResponseError):
                client.tenants.list()
        assert not http.is_closed
        # Deterministic retry with no backoff wait: honor Retry-After: 0.
        service.responses = [httpx.Response(503, headers={'Retry-After': '0'}), httpx.Response(429)]
        count = len(service.requests)
        with sdk.TrustCenterClient(PAT, http_client=http, max_retries=1) as client:
            with raises(sdk.RateLimitError):
                client.tenants.list()
        assert len(service.requests) == count + 2
    owned = sdk.TrustCenterClient(PAT)
    owned.close()
    owned.close()


async def async_behavior():
    service = Service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(service), timeout=0.01) as http:
        async with sdk.AsyncTrustCenterClient.from_env(pat=PAT, http_client=http, max_retries=0) as client:
            assert (await client.tenants.list()).tenants[0].id == TENANT['id']
            assert (await client.tenants.get('synthetic-tenant')).events == []
            assert (await client.status.snapshot()).ongoing.patch == []
            assert (await client.events.search(**search_args())).events[0].event_id == EVENT['eventId']
            assert (await client.events.get('synthetic-event')).event_id == EVENT['eventId']
            assert len(await client.tenants.list_all()) == 1
            assert len(await client.events.search_all(**search_args())) == 1
            count = len(service.requests)
            iterator = client.events.iter_search(**search_args())
            assert len(service.requests) == count and not inspect.isawaitable(iterator)
            assert [event.event_id async for event in iterator] == [EVENT['eventId']]
            service.responses = [httpx.Response(200, json={'tenants': [TENANT], 'nextPageToken': 'next'}), httpx.Response(400)]
            iterator = client.tenants.iter_all()
            assert (await anext(iterator)).id == TENANT['id']
            with raises(sdk.APIStatusError):
                await anext(iterator)
        assert not http.is_closed
    calls = 0
    started = asyncio.Event()

    async def interrupted(request):
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(interrupted)) as http:
        async with sdk.AsyncTrustCenterClient(PAT, http_client=http) as client:
            task = asyncio.create_task(client.tenants.list_all())
            await started.wait()
            task.cancel()
            with raises(asyncio.CancelledError):
                await task
            assert calls == 1
    owned = sdk.AsyncTrustCenterClient(PAT)
    await owned.aclose()
    await owned.aclose()


def seed(path):
    records = {}
    for suffix in ('ready', 'pending'):
        target = path / f'{suffix}.sqlite3'
        store = sdk.SQLitePATStore.initialize(pat=PAT, path=target)
        record = store.load()
        if suffix == 'pending':
            replacement = sdk.PATStoreRecord(record.revision, PAT, uuid4())
            assert store.compare_and_swap(expected_revision=record.revision, expected_attempt=None, replacement=replacement)
            record = store.load()
        records[suffix] = {
            'revision': str(record.revision),
            'pending_attempt': str(record.pending_attempt) if record.pending_attempt else None,
        }
    (path / 'records.json').write_text(json.dumps(records), encoding='utf-8')


def upgrade(path):
    expected = json.loads((path / 'records.json').read_text(encoding='utf-8'))
    for suffix in ('ready', 'pending'):
        store = sdk.SQLitePATStore(path / f'{suffix}.sqlite3')
        record = store.load()
        assert record.revision == UUID(expected[suffix]['revision']) and record.get_pat() == PAT
        assert record.pending_attempt == (
            UUID(expected[suffix]['pending_attempt']) if expected[suffix]['pending_attempt'] else None
        )
        assert not store.compare_and_swap(expected_revision=uuid4(), expected_attempt=record.pending_attempt, replacement=record)
        assert not store.compare_and_swap(expected_revision=record.revision, expected_attempt=uuid4(), replacement=record)
        with httpx.Client(
            transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError('No HTTP expected')))
        ) as http:
            if suffix == 'pending':
                with raises(sdk.PATRefreshPendingError):
                    sdk.TrustCenterClient.from_store(store, http_client=http)
            else:
                with sdk.TrustCenterClient.from_store(store, http_client=http):
                    pass
    # Public initializer is exclusive; do not overwrite even a supported store.
    with raises(sdk.ConfigurationError):
        sdk.SQLitePATStore.initialize(pat=PAT, path=path / 'ready.sqlite3')


def cli(path):
    # Run the real installed module inside the guarded interpreter; no credential discovery.
    sys.argv = ['sfdctrust.pat_store', 'init', '--path', str(path / 'cli.sqlite3'), '--from-env', 'SFDCTRUST_COMPAT_SYNTHETIC']
    os.environ['SFDCTRUST_COMPAT_SYNTHETIC'] = PAT
    try:
        runpy.run_module('sfdctrust.pat_store', run_name='__main__')
    finally:
        del os.environ['SFDCTRUST_COMPAT_SYNTHETIC']
    assert sdk.SQLitePATStore(path / 'cli.sqlite3').load().get_pat() == PAT


def main():
    global sdk, httpx
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--mode', choices=['qualify', 'seed', 'upgrade'], default='qualify')
    parser.add_argument('--store-directory', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument(
        '--record-inventory', action='store_true', help='Explicitly replace the reviewed inventory; never use in CI'
    )
    args = parser.parse_args()
    # Windows asyncio may use an INET socket pair internally. Set up its loop before
    # blocking all sockets; no SDK behavior runs until the guard is active.
    loop = asyncio.new_event_loop()
    sys.addaudithook(deny_network)
    with raises(RuntimeError):
        socket.socket()
    with raises(RuntimeError):
        socket.getaddrinfo('example.invalid', 443)
    assert BLOCKED == 2
    httpx = importlib.import_module('httpx')
    sdk = importlib.import_module('sfdctrust')
    location = installed(args.wheel, args.expected_version)
    try:
        contract = public_contract()
        if args.record_inventory:
            args.snapshot.write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
        else:
            assert contract == json.loads(args.snapshot.read_text(encoding='utf-8')), (
                'Public inventory differs; review before updating.'
            )
        checks = ['installed-wheel-identity', 'py.typed', 'public-inventory']
        if args.mode == 'seed':
            assert args.store_directory is not None
            args.store_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
            seed(args.store_directory)
            checks.append('baseline-public-initializer-ready-and-pending')
        elif args.mode == 'upgrade':
            assert args.store_directory is not None
            upgrade(args.store_directory)
            checks.append('candidate-reopened-baseline-ready-and-pending-stores')
        else:
            serialization()
            sync_behavior()
            loop.run_until_complete(async_behavior())
            with TemporaryDirectory() as temporary:
                cli(Path(temporary))
            checks += [
                'serialization',
                'sync-five-reads-and-pagination-errors',
                'async-five-reads-and-lazy-iteration',
                'timeouts-ownership-and-bounded-retries',
                'async-cancellation',
                'installed-initialization-cli',
            ]
        assert BLOCKED == 2, 'Qualification attempted unexpected networking.'
        os_version = sys.getwindowsversion() if sys.platform == 'win32' else platform.release()
        report = {
            'date_utc': datetime.now(UTC).isoformat(),
            'version': sdk.__version__,
            'wheel': args.wheel.name,
            'sha256': hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
            'installed_from': location,
            'python': sys.version,
            'runtime_dependencies': {name: version(name) for name in ('httpx', 'pydantic', 'pydantic-core')},
            'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'snapshot_sha256': hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
            'platform': f'{sys.platform} {os_version} {struct.calcsize("P") * 8}-bit',
            'mode': args.mode,
            'checks_passed': checks,
            'network_guard_self_checks': BLOCKED,
            'unexpected_network_attempts': BLOCKED - 2,
        }
        if args.evidence:
            args.evidence.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        loop.close()


if __name__ == '__main__':
    main()
