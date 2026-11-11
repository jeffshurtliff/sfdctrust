# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_pat_recovery_rehearsal
:Synopsis:          Recovery evidence reporting under the irreversible socket audit guard
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     11 Nov 2026
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'pat_recovery_rehearsal.py'


@pytest.mark.parametrize('mode', ['native', 'windows'])
def test_platform_evidence_does_not_attempt_socket_operations(mode) -> None:
    # Audit hooks cannot be removed. Exercise reporting and guard enforcement
    # in a child so no hook or simulated Windows state escapes into pytest.
    code = """
import json
import os
import platform
import socket
import struct
import sys
from importlib.util import module_from_spec, spec_from_file_location
from types import SimpleNamespace

spec = spec_from_file_location('pat_recovery_rehearsal', sys.argv[1])
rehearsal = module_from_spec(spec)
spec.loader.exec_module(rehearsal)
if sys.argv[2] == 'windows':
    sys.platform = 'win32'
    sys.getwindowsversion = lambda: SimpleNamespace(major=10, minor=0, build=26100)
    if hasattr(os, 'uname'):
        del os.uname
    platform._uname_cache = None

rehearsal.install_network_guard()
description = rehearsal.platform_description()
assert description and rehearsal.BLOCKED == 2
if sys.argv[2] == 'windows':
    assert description == f'Windows 10.0.26100 ({struct.calcsize("P") * 8}-bit Python)'
    # Reproduce the original failure, even on a non-Windows test host.
    with rehearsal.raises(RuntimeError):
        platform.system()
    assert rehearsal.BLOCKED == 3

before = rehearsal.BLOCKED
for operation in (socket.socket, lambda: socket.getaddrinfo('example.invalid', 443), socket.gethostname):
    with rehearsal.raises(RuntimeError):
        operation()
assert rehearsal.BLOCKED == before + 3
print(json.dumps({'description': description, 'guard_enforced': True}))
"""
    result = subprocess.run(
        [sys.executable, '-I', '-c', code, str(SCRIPT), mode],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ''
    evidence = json.loads(result.stdout)
    assert evidence['description'] and evidence['guard_enforced'] is True
