# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.mcp_mock
:Synopsis:          Child-process HTTP transport for installed MCP protocol qualification
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.2 Astra)
:Modified Date:     18 Nov 2026
"""

import json
import os
from pathlib import Path

import httpx


class MockSalesforce(httpx.MockTransport):
    """Record client lifetime and only accept synthetic requests to the SDK origin."""

    def __init__(self):
        self.work = Path(os.environ['SFDCTRUST_MCP_TEST_DIR'])
        self.record('opened')
        super().__init__(self.respond)

    def record(self, event):
        with (self.work / 'trace.jsonl').open('a', encoding='utf-8') as trace:
            trace.write(json.dumps(event) + '\n')

    def respond(self, request):
        assert request.url.scheme == 'https' and request.url.host == 'api.salesforce.com'
        assert request.headers['Authorization'] == 'Bearer synthetic-mcp-credential'
        assert request.url.path.startswith('/platform/mytrust/v1/')
        self.record(
            {
                'method': request.method,
                'path': request.url.path.removeprefix('/platform/mytrust/v1'),
                'query': dict(request.url.params),
                'body': json.loads(request.content) if request.content else None,
            }
        )
        reply = json.loads((self.work / 'reply.json').read_text(encoding='utf-8'))
        if reply['status'] == 'timeout':
            raise httpx.ReadTimeout(reply['payload'])
        if reply['status'] == 'network':
            raise httpx.ReadError(reply['payload'])
        return httpx.Response(reply['status'], json=reply['payload'], headers={'Retry-After': '0'})

    async def aclose(self):
        self.record('closed')
        await super().aclose()


# Inject below the SDK client so its real credential selection, transport, models,
# request validation and ownership/close paths all execute in the installed server.
original_init = httpx.AsyncClient.__init__


def mocked_init(self, *args, **kwargs):
    kwargs['transport'] = MockSalesforce()
    original_init(self, *args, **kwargs)


httpx.AsyncClient.__init__ = mocked_init
