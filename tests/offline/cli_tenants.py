# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.cli_tenants
:Synopsis:          Test-only mock HTTP bootstrap for real installed read launchers
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import atexit
import builtins
import getpass
import json
import os
from pathlib import Path

import httpx

import sfdctrust._transport


def install(settings):
    """Install synthetic HTTP and home-directory boundaries in a test child only."""
    clients, requests = [], []
    if settings.get('deny_environment'):
        original_getitem = os.environ.__class__.__getitem__

        def environment_getitem(self, key):
            if key == 'SFDCTRUST_PAT':
                raise AssertionError('Explicit stores must not read the ambient PAT.')
            return original_getitem(self, key)

        os.environ.__class__.__getitem__ = environment_getitem
    original = httpx.Client
    Path.home = classmethod(lambda cls: Path(settings['home']))
    sfdctrust._transport.time.sleep = lambda _: None

    def denied(*args, **kwargs):
        raise AssertionError('Read commands must not prompt.')

    builtins.input = getpass.getpass = denied

    def respond(request):
        assert request.method == settings.get('method', 'GET')
        assert request.url.path == '/platform/mytrust/v1' + settings['path']
        assert dict(request.url.params) == settings['params']
        body = json.loads(request.content) if request.content else None
        assert body == settings.get('body')
        assert request.headers['Authorization'] == 'Bearer ' + settings['pat']
        requests.append({'method': request.method, 'params': dict(request.url.params), 'body': body})
        if settings.get('exception') == 'timeout':
            raise httpx.ReadTimeout('synthetic-server-private')
        if settings.get('exception') == 'network':
            raise httpx.ConnectError('synthetic-server-private')
        if settings.get('exception') == 'interrupt':
            raise KeyboardInterrupt('synthetic-server-private')
        return httpx.Response(settings.get('status', 200), json=settings['payload'])

    def client(**kwargs):
        result = original(**{**kwargs, 'transport': httpx.MockTransport(respond)})
        clients.append(result)
        return result

    httpx.Client = client

    def record():
        Path(settings['evidence']).write_text(
            json.dumps({'active': True, 'requests': requests, 'closed': all(client.is_closed for client in clients)}),
            encoding='utf-8',
        )

    atexit.register(record)
