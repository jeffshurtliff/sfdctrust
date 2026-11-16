# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.cli_guard
:Synopsis:          Test-only failures for CLI credential, store, prompt and client access
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import builtins
import getpass
import os
import sqlite3
import sys


def denied(*args, **kwargs):
    raise AssertionError('CLI foundation must not access credentials, stores, prompts or clients.')


def audit(event, arguments):
    if event == 'sqlite3.connect':
        denied()
    if event == 'open' and isinstance(arguments[0], (str, bytes)):
        path = os.fsdecode(arguments[0]).replace('\\', '/')
        if '.sfdctrust' in path.split('/') or path.rsplit('/', 1)[-1].startswith('.env'):
            denied()


sys.addaudithook(audit)
original_getitem = os.environ.__class__.__getitem__


def environment_getitem(self, key):
    if key == 'SFDCTRUST_PAT':
        denied()
    return original_getitem(self, key)


os.environ.__class__.__getitem__ = environment_getitem
builtins.input = denied
getpass.getpass = denied
sqlite3.connect = denied

# Import after installing the guards so import-time credential I/O also fails.
import httpx  # noqa: E402

from sfdctrust import SQLitePATStore, TrustCenterClient  # noqa: E402

httpx.Client.__init__ = denied
TrustCenterClient.__init__ = denied
TrustCenterClient.from_env = denied
TrustCenterClient.from_store = denied
SQLitePATStore.__init__ = denied
SQLitePATStore.initialize = denied
