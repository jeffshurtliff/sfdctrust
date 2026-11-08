# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_pat_store_cli
:Synopsis:          Secret-safe built-in PAT store initialization command tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     06 Nov 2026
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
from getpass import GetPassWarning
from pathlib import Path

import pytest

from sfdctrust import SQLitePATStore, pat_store

PAT = 'synthetic-cli-pat'


def test_hidden_prompt_initialization(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    prompts = []

    def prompt(message):
        prompts.append(message)
        return PAT

    monkeypatch.setattr(pat_store, 'getpass', prompt)
    pat_store._main(['init', '--path', str(path)])
    assert len(prompts) == 1
    assert SQLitePATStore(path).load().get_pat() == PAT
    assert PAT not in capsys.readouterr().out


@pytest.mark.parametrize('environment', ['SFDCTRUST_PAT', 'CUSTOM_TRUST_PAT'])
def test_environment_initialization_never_prompts_or_changes_environment(tmp_path, monkeypatch, capsys, environment) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    monkeypatch.setenv(environment, PAT)
    monkeypatch.setattr(pat_store, 'getpass', lambda message: pytest.fail('Environment mode must not prompt.'))
    snapshot = dict(os.environ)
    flag = '--from-env' if environment == 'SFDCTRUST_PAT' else f'--from-env={environment}'
    pat_store._main(['init', '--path', str(path), flag])
    assert SQLitePATStore(path).load().get_pat() == PAT
    assert dict(os.environ) == snapshot
    assert PAT not in capsys.readouterr().out


@pytest.mark.parametrize('value', [None, '', 'bad value'])
def test_invalid_selected_environment_does_not_fall_back(tmp_path, monkeypatch, capsys, value) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    monkeypatch.setenv('SFDCTRUST_PAT', PAT)
    monkeypatch.delenv('CUSTOM_TRUST_PAT', raising=False)
    if value is not None:
        monkeypatch.setenv('CUSTOM_TRUST_PAT', value)
    monkeypatch.setattr(pat_store, 'getpass', lambda message: pytest.fail('No prompt fallback is allowed.'))
    with pytest.raises(SystemExit) as caught:
        pat_store._main(['init', '--path', str(path), '--from-env=CUSTOM_TRUST_PAT'])
    assert caught.value.code == 1
    assert not path.parent.exists()
    assert PAT not in capsys.readouterr().err


@pytest.mark.parametrize('failure', ['warning', 'eof', 'cancelled'])
def test_unavailable_hidden_input_never_seeds(tmp_path, monkeypatch, capsys, failure) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'

    def prompt(message):
        if failure == 'warning':
            warnings.warn(PAT, GetPassWarning, stacklevel=2)
            pytest.fail('getpass fallback must be interrupted.')
        raise EOFError(PAT) if failure == 'eof' else KeyboardInterrupt(PAT)

    monkeypatch.setattr(pat_store, 'getpass', prompt)
    with pytest.raises(SystemExit) as caught:
        pat_store._main(['init', '--path', str(path)])
    assert caught.value.code == 1
    assert not path.exists()
    assert PAT not in capsys.readouterr().err


@pytest.mark.parametrize(
    'arguments', [[], ['refresh'], ['init', '--pat', PAT], ['init', PAT], ['init', '--alias', PAT, '--path', PAT]]
)
def test_argument_errors_do_not_echo_supplied_values(capsys, arguments) -> None:
    with pytest.raises(SystemExit) as caught:
        pat_store._main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert PAT not in captured.out + captured.err


def test_duplicate_cli_seed_is_refused(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    original = SQLitePATStore.initialize(pat=PAT, path=path).load().revision
    monkeypatch.setenv('SFDCTRUST_PAT', 'synthetic-other-pat')
    with pytest.raises(SystemExit) as caught:
        pat_store._main(['init', '--path', str(path), '--from-env'])
    assert caught.value.code == 1
    assert SQLitePATStore(path).load().revision == original
    assert 'Initialized' not in capsys.readouterr().out


def test_module_execution_has_no_runpy_warning_and_reopens(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    result = subprocess.run(
        [sys.executable, '-m', 'sfdctrust.pat_store', 'init', '--path', str(path), '--from-env'],
        env={**os.environ, 'SFDCTRUST_PAT': PAT},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ''
    assert PAT not in result.stdout
    assert SQLitePATStore(Path(path)).load().get_pat() == PAT
