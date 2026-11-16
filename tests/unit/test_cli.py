# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_cli
:Synopsis:          Secret-safe CLI foundation and module launcher behavior
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     16 Nov 2026
"""

import builtins
import getpass
import os
import runpy
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from sfdctrust import SQLitePATStore, TrustCenterClient, __version__
from sfdctrust._cli import main

SECRET = 'synthetic-secret-\x1b[31m-value'


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail('Help, version and syntax errors must not access credentials, stores, prompts or clients.')

    monkeypatch.setenv('SFDCTRUST_PAT', SECRET)
    original = os.environ.__class__.__getitem__

    def getitem(self, key):
        if key == 'SFDCTRUST_PAT':
            denied()
        return original(self, key)

    monkeypatch.setattr(os.environ.__class__, '__getitem__', getitem)
    for target, name in [
        (builtins, 'input'),
        (getpass, 'getpass'),
        (sqlite3, 'connect'),
        (socket, 'getaddrinfo'),
        (socket.socket, 'connect'),
        (httpx.Client, '__init__'),
        (TrustCenterClient, '__init__'),
        (TrustCenterClient, 'from_env'),
        (TrustCenterClient, 'from_store'),
        (SQLitePATStore, '__init__'),
        (SQLitePATStore, 'initialize'),
    ]:
        monkeypatch.setattr(target, name, denied)


@pytest.mark.parametrize('launcher', ['entrypoint', 'module'])
@pytest.mark.parametrize(
    ('arguments', 'status'),
    [
        (['--help'], 0),
        (['-h'], 0),
        (['--version'], 0),
        ([], 2),
        (['tenants'], 2),
        (['tenants', 'list', '--help'], 0),
        (['tenants', 'get', '--help'], 0),
        (['tenants', '--help'], 0),
        (['tenants', 'get'], 2),
        (['tenants', 'get', ''], 2),
        *[
            (['tenants', 'get', value], 2)
            for value in ('.', '..', '/', 'a/b', 'a\\b', 'x%20', 'x?', 'x#', 'x;', '\x00', '\x1b', '\x7f', '\ud800')
        ],
        *[(['tenants', 'list', '--page-size', value], 2) for value in ('0', '201', 'x', SECRET)],
        (['tenants', 'list', '--page-token', 'x' * 4097], 2),
        (['tenants', 'list', '--page-token', '\ud800'], 2),
        (['tenants', 'list', '--locale', 'x' * 70000], 2),
        (['tenants', 'get', 'safe', '--locale', '\ud800'], 2),
        (['tenants', 'list', '--store', '--store-path', SECRET], 2),
        (['tenants', 'get', 'safe', '--store-alias', SECRET, '--store-path', SECRET], 2),
        (['tenants', 'list', '--store-alias', '../unsafe'], 2),
        (['tenants', 'list', '--store-path', ''], 2),
        (['tenants', 'list', '--page-s', '1'], 2),
        (['tenants', 'get', 'safe', '--page-size', '1'], 2),
        (['tenants', '--json', 'list'], 2),
        *[
            ([*command, '--help'], 0)
            for command in (['status'], ['status', 'snapshot'], ['events'], ['events', 'search'], ['events', 'get'])
        ],
        (['status'], 2),
        (['events'], 2),
        (['status', '--json', 'snapshot'], 2),
        (['status', 'snapshot', '--page-size', '1'], 2),
        (['status', 'snapshot', '--locale', '\ud800'], 2),
        (['status', 'snapshot', '--locale', 'x' * 70000], 2),
        (['status', 'snapshot', '--store', '--store-path', SECRET], 2),
        (['events', 'get'], 2),
        (['events', 'get', 'safe', '--event-type', 'incident'], 2),
        (['events', 'get', 'safe', '--store-alias', '../unsafe'], 2),
        *[
            (['events', 'get', value], 2)
            for value in ('', '.', '..', '/', 'a/b', 'a\\b', 'x%20', 'x?', 'x#', 'x;', '\x00', '\x1b', '\x7f', '\ud800')
        ],
        (['events', 'search'], 2),
        (['--ver'], 2),
        (['--hel'], 2),
        ([SECRET], 2),
        (['--pat', SECRET], 2),
        ([f'--{SECRET}'], 2),
        ([f'--version={SECRET}'], 2),
        ([f'--help={SECRET}'], 2),
        (['--store-path', SECRET], 2),
        (['--', SECRET], 2),
    ],
)
def test_launchers_keep_streams_exit_codes_and_values_safe(monkeypatch, capsys, launcher, arguments, status):
    monkeypatch.setattr(sys, 'argv', [SECRET, *arguments])
    with pytest.raises(SystemExit) as caught:
        if launcher == 'module':
            runpy.run_module('sfdctrust', run_name='__main__', alter_sys=True)
        else:
            main()
    assert caught.value.code == status
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert 'Traceback' not in captured.out + captured.err
    if status == 2:
        assert captured.out == ''
        assert captured.err.startswith('usage: sfdctrust')
        assert captured.err.endswith('sfdctrust: error: invalid arguments. Use --help for available options.\n')
    else:
        assert captured.err == ''
        if arguments == ['--version']:
            assert captured.out == f'sfdctrust {__version__}\n'
        else:
            assert captured.out.startswith('usage: sfdctrust')
            assert '--help' in captured.out
            if arguments in (['--help'], ['-h']):
                assert 'tenants' in captured.out and '--version' in captured.out
            if arguments[:2] in (['tenants', 'list'], ['tenants', 'get']):
                assert '--store-path' in captured.out and '--locale' in captured.out and '--json' in captured.out
            assert '--pat ' not in captured.out


SEARCH = [
    'events',
    'search',
    '--tenant-id',
    'synthetic',
    '--start-time',
    '2026-11-01T00:00:00Z',
    '--end-time',
    '2026-11-02T00:00:00Z',
]


@pytest.mark.parametrize('launcher', ['entrypoint', 'module'])
@pytest.mark.parametrize(
    'options',
    [
        ['--tenant-id', ''],
        ['--tenant-id', '\ud800'],
        ['--tenant-id', 'extra'] * 50,
        ['--start-time', '2026'],
        ['--start-time', '2026-11-01'],
        ['--start-time', '2026-11-01 00:00:00Z'],
        ['--start-time', '2026-11-01T00:00:00'],
        ['--start-time', '2026-11-01T00:00Z'],
        ['--start-time', '2026-11-01T00:00:00+0530'],
        ['--start-time', '2026-11-01T00:00:00+05:30:01'],
        ['--start-time', '2026-11-01T00:00:00+24:00'],
        ['--start-time', '2026-02-30T00:00:00Z'],
        ['--start-time', '2026-11-01T24:00:00Z'],
        ['--start-time', SECRET],
        ['--end-time', SECRET],
        ['--end-time', '2026-11-01T00:00:00Z'],
        ['--end-time', '2026-10-31T23:59:59Z'],
        ['--end-time', '2026-11-01T05:30:00+05:30'],
        ['--event-type', 'future-type'],
        ['--event-type', 'incident', '--event-type', 'incident'],
        ['--event-type', SECRET],
        ['--page-size', '0'],
        ['--page-size', '201'],
        ['--page-size', SECRET],
        ['--page-token', 'x' * 4097],
        ['--page-token', '\ud800'],
        ['--locale', '\ud800'],
        ['--store', '--store-alias', SECRET],
        ['--store-path', ''],
        ['--store-alias', '../unsafe'],
        ['--tenant-i', 'synthetic'],
        ['--all-pages'],
    ],
)
def test_search_validation_precedes_all_side_effects(monkeypatch, capsys, launcher, options):
    monkeypatch.setattr(sys, 'argv', ['sfdctrust', *SEARCH, *options])
    with pytest.raises(SystemExit) as caught:
        if launcher == 'module':
            runpy.run_module('sfdctrust', run_name='__main__', alter_sys=True)
        else:
            main()
    assert caught.value.code == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err.startswith('usage: sfdctrust')
    assert output.err.endswith('sfdctrust: error: invalid arguments. Use --help for available options.\n')
    assert SECRET not in output.err and 'Traceback' not in output.err


@pytest.mark.parametrize('missing', ['--tenant-id', '--start-time', '--end-time'])
def test_missing_required_search_inputs_are_side_effect_free(capsys, missing):
    args = SEARCH.copy()
    index = args.index(missing)
    del args[index : index + 2]
    with pytest.raises(SystemExit) as caught:
        main(args)
    assert caught.value.code == 2
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('argument', ['--help', '--version'])
@pytest.mark.parametrize('launcher', ['console-target', 'module'])
def test_closed_stdout_descriptor_keeps_exit_one_without_shutdown_traceback(tmp_path, argument, launcher):
    script = tmp_path / 'closed_stdout.py'
    invocation = (
        f'from sfdctrust._cli import main; main([{argument!r}])'
        if launcher == 'console-target'
        else f'import runpy, sys; sys.argv = ["sfdctrust", {argument!r}]; runpy.run_module("sfdctrust", run_name="__main__")'
    )
    script.write_text('import os; os.close(1)\n' + invocation + '\n', encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-I', str(Path(__file__).resolve().parents[1] / 'offline/run.py'), str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    # The wrapper's guard announcement precedes the deliberate descriptor close.
    assert result.stdout == 'Outbound network guard active (DNS and external connection self-tests passed).\n'
    assert result.stderr == 'sfdctrust: internal or output failure.\n'
