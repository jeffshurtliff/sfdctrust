# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.run
:Synopsis:          Run a module or script with an inherited outbound network guard
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

import os
import runpy
import socket
import sys
from pathlib import Path

guard = Path(__file__).with_name('sitecustomize.py')
os.environ['PYTHONPATH'] = str(guard.parent) + os.pathsep + os.environ.get('PYTHONPATH', '')
runpy.run_path(str(guard))


def external_probe():
    with socket.socket() as connection:
        connection.connect(('192.0.2.1', 443))


for probe in (lambda: socket.getaddrinfo('example.invalid', 443), external_probe):
    try:
        probe()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('Network guard self-test failed.')
print('Outbound network guard active (DNS and external connection self-tests passed).', flush=True)
sys.argv.pop(0)
if sys.argv[0] == '-m':
    sys.argv.pop(0)
    runpy.run_module(sys.argv[0], run_name='__main__', alter_sys=True)
else:
    runpy.run_path(sys.argv[0], run_name='__main__')
