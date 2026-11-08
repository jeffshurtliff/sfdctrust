# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._windows_pat_files
:Synopsis:          Native Windows ACL protection for local PAT store files
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     08 Nov 2026
"""

from __future__ import annotations

import ctypes as c
from contextlib import contextmanager
from ctypes import wintypes as w
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class _SecurityAttributes(c.Structure):
    _fields_ = [('length', w.DWORD), ('descriptor', c.c_void_p), ('inherit', w.BOOL)]


class _ACL(c.Structure):
    _fields_ = [('revision', w.BYTE), ('reserved', w.BYTE), ('size', w.WORD), ('count', w.WORD), ('reserved2', w.WORD)]


class _ACEHeader(c.Structure):
    _fields_ = [('kind', w.BYTE), ('flags', w.BYTE), ('size', w.WORD)]


class _WindowsFiles:
    """Use Unicode Windows APIs and SIDs, without subprocesses or privilege changes."""

    def __init__(self) -> None:
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.security = c.WinDLL('advapi32', use_last_error=True)
        pointer = c.c_void_p
        out = c.POINTER(pointer)
        signatures = [
            (self.kernel, 'GetCurrentProcess', [], w.HANDLE),
            (self.kernel, 'CloseHandle', [w.HANDLE], w.BOOL),
            (self.kernel, 'LocalFree', [pointer], pointer),
            (self.kernel, 'CreateDirectoryW', [w.LPCWSTR, c.POINTER(_SecurityAttributes)], w.BOOL),
            (
                self.kernel,
                'CreateFileW',
                [w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(_SecurityAttributes), w.DWORD, w.DWORD, w.HANDLE],
                w.HANDLE,
            ),
            (self.kernel, 'GetVolumePathNameW', [w.LPCWSTR, w.LPWSTR, w.DWORD], w.BOOL),
            (self.kernel, 'GetDriveTypeW', [w.LPCWSTR], w.UINT),
            (
                self.kernel,
                'GetVolumeInformationW',
                [w.LPCWSTR, w.LPWSTR, w.DWORD, c.POINTER(w.DWORD), c.POINTER(w.DWORD), c.POINTER(w.DWORD), w.LPWSTR, w.DWORD],
                w.BOOL,
            ),
            (self.security, 'OpenProcessToken', [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL),
            (self.security, 'GetTokenInformation', [w.HANDLE, c.c_int, pointer, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            (self.security, 'ConvertSidToStringSidW', [pointer, c.POINTER(w.LPWSTR)], w.BOOL),
            (
                self.security,
                'ConvertStringSecurityDescriptorToSecurityDescriptorW',
                [w.LPCWSTR, w.DWORD, out, c.POINTER(w.DWORD)],
                w.BOOL,
            ),
            (self.security, 'GetNamedSecurityInfoW', [w.LPCWSTR, c.c_int, w.DWORD, out, out, out, out, out], w.DWORD),
            (self.security, 'GetSecurityDescriptorControl', [pointer, c.POINTER(w.WORD), c.POINTER(w.DWORD)], w.BOOL),
            (self.security, 'IsValidAcl', [pointer], w.BOOL),
            (self.security, 'IsValidSid', [pointer], w.BOOL),
            (self.security, 'GetLengthSid', [pointer], w.DWORD),
            (self.security, 'GetAce', [pointer, w.DWORD, out], w.BOOL),
        ]
        for library, name, arguments, result in signatures:
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
        self.user = self._current_user()
        self.trusted = {self.user, 'S-1-5-18', 'S-1-5-32-544'}

    @staticmethod
    def _require(success: object) -> None:
        if not success:
            raise OSError('Windows could not enforce private PAT store access.')

    def _sid(self, address: object) -> str:
        self._require(self.security.IsValidSid(address))
        value = w.LPWSTR()
        self._require(self.security.ConvertSidToStringSidW(address, c.byref(value)))
        try:
            return value.value
        finally:
            self.kernel.LocalFree(c.cast(value, c.c_void_p))

    def _current_user(self) -> str:
        token = w.HANDLE()
        self._require(self.security.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, c.byref(token)))
        try:
            size = w.DWORD()
            self.security.GetTokenInformation(token, 1, None, 0, c.byref(size))  # TokenUser
            self._require(size.value)
            data = c.create_string_buffer(size.value)
            self._require(self.security.GetTokenInformation(token, 1, data, size, c.byref(size)))
            return self._sid(c.cast(data, c.POINTER(c.c_void_p))[0])
        finally:
            self.kernel.CloseHandle(token)

    def _volume(self, path: Path) -> None:
        root = c.create_unicode_buffer(32768)
        self._require(self.kernel.GetVolumePathNameW(str(path), root, len(root)))
        self._require(self.kernel.GetDriveTypeW(root) in {2, 3})  # Local removable/fixed disks only.
        flags = w.DWORD()
        self._require(self.kernel.GetVolumeInformationW(root, None, 0, None, None, c.byref(flags), None, 0))
        self._require(flags.value & 8)  # FS_PERSISTENT_ACLS

    @contextmanager
    def _descriptor(self, sddl: str) -> Iterator[c.c_void_p]:
        descriptor = c.c_void_p()
        self._require(self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None))
        try:
            yield descriptor
        finally:
            self.kernel.LocalFree(descriptor)

    def create(self, path: Path, *, directory: bool) -> None:
        self._volume(path.parent)
        inheritance = 'OICI' if directory else ''
        grants = ''.join(f'(A;{inheritance};FA;;;{sid})' for sid in sorted(self.trusted))
        with self._descriptor(f'O:{self.user}D:P{grants}') as descriptor:
            attributes = _SecurityAttributes(c.sizeof(_SecurityAttributes), descriptor, False)
            if directory:
                self._require(self.kernel.CreateDirectoryW(str(path), c.byref(attributes)))
            else:
                # CREATE_NEW is exclusive. The restrictive ACL exists before any PAT is written.
                handle = self.kernel.CreateFileW(str(path), 0x40000000, 3, c.byref(attributes), 1, 0x80, None)
                self._require(handle != c.c_void_p(-1).value)
                self.kernel.CloseHandle(handle)

    def _inspect(self, path: Path, *, protected: bool, ancestor: bool = False) -> None:
        owner, acl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        self._require(
            self.security.GetNamedSecurityInfoW(str(path), 1, 5, c.byref(owner), None, c.byref(acl), None, c.byref(descriptor))
            == 0
        )
        try:
            self._require(owner.value and acl.value)
            trusted = self.trusted.copy()
            if ancestor:
                # Windows protects system directories with this well-known service identity
                trusted.add('S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')  # TrustedInstaller
            # SQLite-created journals can inherit an elevated token's default Administrators owner
            # Their grants must still be strictly private
            self._require(self._sid(owner) in ({self.user} if protected else trusted))
            # OWNER RIGHTS grants apply to the verified owner. CPython uses this
            # SID on private directories created by tempfile and mkdir(mode=0o700).
            trusted.add('S-1-3-4')
            control, revision = w.WORD(), w.DWORD()
            self._require(self.security.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)))
            if protected:
                self._require(control.value & 0x1000)  # SE_DACL_PROTECTED
            self._require(self.security.IsValidAcl(acl))
            count = c.cast(acl, c.POINTER(_ACL)).contents.count
            for index in range(count):
                entry = c.c_void_p()
                self._require(self.security.GetAce(acl, index, c.byref(entry)))
                header = c.cast(entry, c.POINTER(_ACEHeader)).contents
                self._require(header.kind in {0, 1} and header.size >= 16)
                if header.kind == 1:  # A deny entry cannot grant access
                    continue
                mask = c.cast(entry.value + 4, c.POINTER(w.DWORD)).contents.value
                if ancestor and (header.flags & 8 or not mask & 0x500D0040):
                    # Inherit-only ACEs cannot affect this ancestor. Other users may
                    # traverse/create children, but must not replace it or change its ACL
                    continue
                sid = entry.value + 8
                self._require(self.security.IsValidSid(sid))
                self._require(self.security.GetLengthSid(sid) <= header.size - 8)
                self._require(self._sid(sid) in trusted)
        finally:
            self.kernel.LocalFree(descriptor)

    def check(self, path: Path, *, protected: bool) -> None:
        self._volume(path)
        self._inspect(path, protected=protected)

    def check_ancestors(self, directory: Path) -> None:
        for parent in directory.parents:
            self._require(not parent.lstat().st_file_attributes & 0x400)
            self._inspect(parent, protected=False, ancestor=True)

    @contextmanager
    def pin(self, path: Path, *, directory: bool) -> Iterator[None]:
        flags = 0x00200000 | (0x02000000 if directory else 0)  # OPEN_REPARSE_POINT, BACKUP_SEMANTICS
        # No FILE_SHARE_DELETE: the directory/database cannot be renamed while SQLite is open
        handle = self.kernel.CreateFileW(str(path), 0x20080, 3, None, 3, flags, None)
        self._require(handle != c.c_void_p(-1).value)
        try:
            yield
        finally:
            self.kernel.CloseHandle(handle)
