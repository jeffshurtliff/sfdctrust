# -*- coding: utf-8 -*-
"""
:Module:            tests.package_smoke
:Synopsis:          Installed-wheel SQLite PAT workflow with synthetic credentials
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     06 Nov 2026
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

import sfdctrust
from sfdctrust import SQLitePATStore, TrustCenterClient
from sfdctrust.models.events import EventSearchScope


def main() -> None:
    """Verify installed imports, module CLI, reads, one refresh, and reopening."""
    assert 'site-packages' in Path(sfdctrust.__file__).parts, (
        'Run this check after installing the wheel, not the editable checkout.'
    )
    original, replacement = 'synthetic-wheel-original-pat', 'synthetic-wheel-replacement-pat'
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        expected = replacement if posts else original
        assert request.headers['Authorization'] == f'Bearer {expected}'
        if request.url.path.endswith('/pats/refresh'):
            posts += 1
            return httpx.Response(200, json={'secret': replacement})
        return httpx.Response(200, json={'events': []} if request.url.path.endswith('/events/search') else {'tenants': []})

    with TemporaryDirectory() as directory:
        path = Path(directory) / 'private' / 'pat.sqlite3'
        initialized = subprocess.run(
            [sys.executable, '-m', 'sfdctrust.pat_store', 'init', '--path', str(path), '--from-env'],
            env={**os.environ, 'SFDCTRUST_PAT': original},
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert initialized.returncode == 0 and initialized.stderr == ''
        assert original not in initialized.stdout
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as client:
                assert client.tenants.list_all() == []
                end = datetime.now(UTC).replace(second=0, microsecond=0)
                assert (
                    client.events.search_all(
                        scopes=[EventSearchScope(id='synthetic-tenant')],
                        start_time=end - timedelta(days=1),
                        end_time=end,
                    )
                    == []
                )
                client.refresh_pat(expires_in_days=7)
                assert client.tenants.list_all() == []
            with TrustCenterClient.from_store(SQLitePATStore(path), http_client=http) as client:
                assert client.tenants.list_all() == []
        assert posts == 1
        assert SQLitePATStore(path).load().get_pat() == replacement
    print('Installed-wheel SQLite PAT workflow passed (synthetic credentials, no network requests).')


if __name__ == '__main__':
    main()
