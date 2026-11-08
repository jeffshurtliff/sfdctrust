# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_pat_store_native_permissions
:Synopsis:          Native macOS and Windows PAT store access-control regression tests
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     06 Nov 2026
"""

from __future__ import annotations

import ctypes as c
import os
import subprocess
import sys
from ctypes import wintypes as w
from pathlib import Path

import pytest

from sfdctrust import ConfigurationError, SQLitePATStore
from sfdctrust._pat_store_files import _windows

PAT = 'synthetic-native-permissions-pat'
windows_only = pytest.mark.skipif(os.name != 'nt', reason='Native Windows APIs')


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native macOS ACL')
@pytest.mark.parametrize('target', ['directory', 'database', 'ancestor'])
def test_macos_extended_allow_entries_are_rejected(tmp_path, target) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    selected = path if target == 'database' else path.parent if target == 'directory' else tmp_path
    # The runtime uses native APIs. chmod here provisions a real adversarial ACL fixture.
    subprocess.run(['/bin/chmod', '+a', 'everyone allow read', str(selected)], check=True, capture_output=True)
    try:
        assert selected.stat().st_mode & 0o077 == 0
        with pytest.raises(ConfigurationError):
            store.load()
    finally:
        subprocess.run(['/bin/chmod', '-N', str(selected)], check=True, capture_output=True)


def _replace_windows_acl(path: Path, sddl: str, *, protected: bool = True) -> None:
    native = _windows()
    get_dacl = native.security.GetSecurityDescriptorDacl
    get_dacl.argtypes = [c.c_void_p, c.POINTER(w.BOOL), c.POINTER(c.c_void_p), c.POINTER(w.BOOL)]
    get_dacl.restype = w.BOOL
    set_security = native.security.SetNamedSecurityInfoW
    set_security.argtypes = [w.LPWSTR, c.c_int, w.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
    set_security.restype = w.DWORD
    with native._descriptor(sddl) as descriptor:
        present, defaulted, acl = w.BOOL(), w.BOOL(), c.c_void_p()
        native._require(get_dacl(descriptor, c.byref(present), c.byref(acl), c.byref(defaulted)))
        protection = 0x80000000 if protected else 0x20000000
        native._require(set_security(str(path), 1, 4 | protection, None, None, acl, None) == 0)


@windows_only
def test_windows_creates_protected_user_owned_directory_database_and_journal(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    native = _windows()
    native.check(path.parent, protected=True)
    native.check(path, protected=True)
    with store._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE credential SET pat=?', ('synthetic-update',))
        journal = Path(str(path) + '-journal')
        assert journal.exists()
        native.check(journal, protected=False)
    assert store.load().get_pat() == PAT


@windows_only
@pytest.mark.parametrize('target', ['directory', 'database', 'journal'])
@pytest.mark.parametrize('grant', ['(A;;FA;;;WD)', '(A;OICI;FA;;;BU)', ''])
def test_windows_broad_and_null_acls_fail_closed(tmp_path, target, grant) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    selected = path if target == 'database' else path.parent if target == 'directory' else Path(str(path) + '-journal')
    native = _windows()
    if target == 'journal':
        native.create(selected, directory=False)
    # NO_ACCESS_CONTROL is a null DACL and must never be accepted as private.
    sddl = f'D:P(A;;FA;;;{native.user}){grant}' if grant else 'D:NO_ACCESS_CONTROL'
    _replace_windows_acl(selected, sddl)
    with pytest.raises(ConfigurationError):
        store.load()


@windows_only
def test_windows_unprotected_database_rejected(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    _replace_windows_acl(path, f'D:(A;;FA;;;{_windows().user})', protected=False)
    with pytest.raises(ConfigurationError):
        store.load()


@windows_only
def test_windows_parent_that_allows_substitution_is_rejected(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    _replace_windows_acl(tmp_path, f'D:P(A;;FA;;;{_windows().user})(A;;0x40;;;WD)')  # FILE_DELETE_CHILD
    with pytest.raises(ConfigurationError):
        store.load()


@windows_only
def test_windows_filesystem_without_persistent_acls_is_rejected(tmp_path, monkeypatch) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    store = SQLitePATStore.initialize(pat=PAT, path=path)
    native = _windows()

    def without_acls(root, label, label_size, serial, component, flags, filesystem, filesystem_size):
        flags._obj.value = 0
        return 1

    monkeypatch.setattr(native.kernel, 'GetVolumeInformationW', without_acls)
    with pytest.raises(ConfigurationError):
        store.load()


@windows_only
def test_windows_junction_directory_rejected(tmp_path) -> None:
    path = tmp_path / 'private' / 'pat.sqlite3'
    SQLitePATStore.initialize(pat=PAT, path=path)
    linked = tmp_path / 'junction'
    subprocess.run(
        ['cmd', '/c', 'mklink', '/J', str(linked), str(path.parent)],
        check=True,
        capture_output=True,
        timeout=15,
    )
    try:
        with pytest.raises(ConfigurationError):
            SQLitePATStore(linked / 'pat.sqlite3')
    finally:
        linked.rmdir()
