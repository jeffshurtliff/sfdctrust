# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._pat_store_files
:Synopsis:          Private local files used by the built-in PAT store
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     08 Nov 2026
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from contextlib import ExitStack, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@lru_cache(maxsize=1)
def _windows():
    # Platform libraries are loaded only when a store is actually used
    from ._windows_pat_files import _WindowsFiles

    return _WindowsFiles()


def _darwin_acl(path: Path) -> None:
    """Conservatively reject extended allow entries, even with private mode bits."""
    import ctypes

    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    pointer = ctypes.c_void_p
    lib.acl_get_file.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.acl_get_file.restype = pointer
    lib.acl_get_entry.argtypes = [pointer, ctypes.c_int, ctypes.POINTER(pointer)]
    lib.acl_get_entry.restype = ctypes.c_int
    lib.acl_get_tag_type.argtypes = [pointer, ctypes.POINTER(ctypes.c_int)]
    lib.acl_get_tag_type.restype = ctypes.c_int
    lib.acl_free.argtypes = [pointer]
    lib.acl_free.restype = ctypes.c_int
    acl = lib.acl_get_file(os.fsencode(path), 0x100)  # ACL_TYPE_EXTENDED
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:
            # Darwin uses ENOENT when an existing file has no extended ACL
            path.lstat()
            return
        raise OSError('Cannot inspect the local ACL.')
    try:
        entry = pointer()
        selector = 0  # ACL_FIRST_ENTRY; subsequent entries use ACL_NEXT_ENTRY
        while True:
            result = lib.acl_get_entry(acl, selector, ctypes.byref(entry))
            if result == -1:
                # Darwin reports EINVAL at the end, rather than POSIX's 0.
                if ctypes.get_errno() == 22:
                    break
                raise OSError('Cannot inspect the local ACL.')
            tag = ctypes.c_int()
            if lib.acl_get_tag_type(entry, ctypes.byref(tag)) != 0 or tag.value != 2:  # ACL_EXTENDED_DENY
                raise OSError('Extended allow ACLs are unsupported for the private store path.')
            selector = -1
    finally:
        lib.acl_free(acl)


def _ancestors(directory: Path) -> None:
    """Require an ancestry that unrelated unprivileged users cannot replace."""
    if os.name == 'nt':
        _windows().check_ancestors(directory)
        return
    for parent in directory.parents:
        link_info = parent.lstat()
        info = parent.stat()
        if (
            link_info.st_uid not in {0, os.getuid()}
            or info.st_uid not in {0, os.getuid()}
            or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)
        ):
            raise OSError('The store needs a trusted containing directory.')
        if sys.platform == 'darwin':
            _darwin_acl(parent)


def _check(path: Path, *, directory: bool = False, sidecar: bool = False) -> tuple[int, int]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise OSError('Linked store paths are unsupported.')
    if directory:
        suitable = stat.S_ISDIR(info.st_mode)
    else:
        suitable = stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not suitable:
        raise OSError('The store path has an unsuitable file type.')
    if os.name == 'nt':
        _windows().check(path, protected=not sidecar)
    elif os.name == 'posix':
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise OSError('The store directory and files must be private to the current account.')
        if sys.platform == 'darwin':
            _darwin_acl(path)
    else:
        raise OSError('This platform cannot enforce private PAT store access.')
    return info.st_dev, info.st_ino


def _canonical_path(path: Path) -> Path:
    # Do not resolve away a linked store directory before inspecting it
    _check(path.parent, directory=True)
    _ancestors(path.parent)
    canonical = path.parent.resolve(strict=True) / path.name
    _ancestors(canonical.parent)
    return canonical


def _create_directory(path: Path) -> None:
    if os.name == 'nt':
        _windows().create(path, directory=True)
    elif os.name == 'posix':
        path.mkdir(mode=0o700)
    else:
        raise OSError('This platform cannot enforce private PAT store access.')


def _create_file(path: Path) -> None:
    if os.name == 'nt':
        _windows().create(path, directory=False)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)


class _StoreFiles:
    """Pin one private directory and database identity for the adapter lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = _canonical_path(path)
        self.directory_id = _check(self.path.parent, directory=True)
        self.file_id = _check(self.path)

    def check(self) -> None:
        _ancestors(self.path.parent)
        if _check(self.path.parent, directory=True) != self.directory_id or _check(self.path) != self.file_id:
            raise OSError('The store directory or database was replaced.')
        for suffix in ('-journal', '-wal', '-shm'):
            sidecar = self.path.with_name(self.path.name + suffix)
            try:
                _check(sidecar, sidecar=True)
            except FileNotFoundError:
                # Another connection may just have removed its rollback journal
                continue

    @contextmanager
    def access(self) -> Iterator[None]:
        self.check()
        with ExitStack() as stack:
            for path, identity, directory in (
                (self.path.parent, self.directory_id, True),
                (self.path, self.file_id, False),
            ):
                if os.name == 'nt':
                    stack.enter_context(_windows().pin(path, directory=directory))
                else:
                    flags = os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0)
                    fd = os.open(path, flags)
                    stack.callback(os.close, fd)
                    info = os.fstat(fd)
                    if (info.st_dev, info.st_ino) != identity:
                        raise OSError('The store path changed while opening it.')
            self.check()
            yield
            self.check()
