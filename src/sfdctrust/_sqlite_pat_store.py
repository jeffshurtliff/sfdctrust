# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._sqlite_pat_store
:Synopsis:          Durable single-host SQLite PAT storage
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     08 Nov 2026
"""

from __future__ import annotations

import importlib
import re
import sys
from contextlib import closing, contextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, Self, TypeVar
from uuid import UUID, uuid4

from ._exceptions import ConfigurationError, PATPersistenceError
from ._pat_store import PATStoreRecord
from ._pat_store_files import _canonical_path, _create_directory, _create_file, _StoreFiles

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Iterator

_APPLICATION_ID = 0x53464454  # SFDT
_SCHEMA_VERSION = 1
_SCHEMA = (
    'CREATE TABLE credential ('
    'slot INTEGER PRIMARY KEY CHECK (slot = 1), '
    'revision TEXT NOT NULL, pat TEXT NOT NULL, pending_attempt TEXT)'
)
_RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL', *(f'{prefix}{digit}' for prefix in ('COM', 'LPT') for digit in range(1, 10))}
_OPEN_ERROR = (
    'Cannot open the PAT store. Check that it exists, uses the supported format, '
    'and has private ownership and permissions on a trusted local path.'
)


_P = ParamSpec('_P')
_T = TypeVar('_T')


def _safe_errors(
    error_type: type[ConfigurationError] | type[PATPersistenceError], message: str
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    def decorate(function: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(function)
        def safe(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            try:
                return function(*args, **kwargs)
            except Exception:
                failure = error_type(message)
            # A normal call boundary (not a generator's throw) removes the raw context
            raise failure

        return safe

    return decorate


def _path(path: str | Path | None, alias: str | None) -> Path:
    if path is not None and alias is not None:
        raise ConfigurationError('Choose either a PAT store path or an alias, not both.')
    if alias is not None and (
        not isinstance(alias, str) or re.fullmatch(r'[A-Za-z0-9_-]+', alias) is None or alias.upper() in _RESERVED_NAMES
    ):
        raise ConfigurationError('A store alias must use ASCII letters, digits, hyphens, or underscores and not a reserved name.')
    if path is not None and (not isinstance(path, (str, Path)) or not str(path)):
        raise ConfigurationError('A PAT store path must be a nonempty string or Path.')
    try:
        selected = Path(path).expanduser() if path is not None else Path.home() / '.sfdctrust' / f'{alias or "pat"}.sqlite3'
        if any(ord(char) < 32 for char in str(selected)):
            raise ValueError('Invalid path.')
        selected = selected.absolute()
        if selected.name.split('.')[0].upper() in _RESERVED_NAMES or selected.name in {'', '.', '..'}:
            raise ValueError('Invalid filename.')
        if sys.platform == 'win32' and (':' in selected.name or selected.name.endswith((' ', '.'))):
            raise ValueError('Invalid Windows filename.')
        return selected
    except Exception:
        failure = ConfigurationError('Cannot determine a valid PAT store path.')
    raise failure


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError('Invalid record identifier.')
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError('Invalid record identifier.')
    return parsed


class SQLitePATStore:
    """Open a private, seeded SQLite PAT store on this host.

    All users of one PAT lineage must use the same database under the same
    operating-system account. Use an encrypted local volume outside shared,
    network, or synchronized folders. Ordinary construction never creates files.
    Connections are opened and closed per operation; no close method is needed.

    :param path: Existing database path. Omit to use ``~/.sfdctrust/pat.sqlite3``.
    :param alias: Alternative basename in ``~/.sfdctrust``; mutually exclusive with path.
    :raises ConfigurationError: If the path, protection, format, or stored record is unsuitable.
    """

    @_safe_errors(ConfigurationError, _OPEN_ERROR)
    def __init__(self, path: str | Path | None = None, *, alias: str | None = None) -> None:
        selected = _path(path, alias)
        self._files = _StoreFiles(selected)
        with self._connect() as db:
            self._validate_schema(db)
            self._load_record(db)

    @classmethod
    @_safe_errors(
        ConfigurationError,
        'Cannot initialize the PAT store. Supply a valid PAT and a new destination with a trusted containing path '
        'and private directory. Check permissions and available disk space.',
    )
    def initialize(cls, *, pat: str, path: str | Path | None = None, alias: str | None = None) -> Self:
        """Exclusively create a private database and durably save the initial PAT.

        Every existing destination is refused, even an empty file or a pending
        store. No existing permissions are changed. On failure, a newly created
        file may remain; inspect it before removing it or choose a fresh path.

        :param pat: Initial PAT without the Bearer prefix, obtained through a trusted input path.
        :param path: New database path; defaults to ``~/.sfdctrust/pat.sqlite3``.
        :param alias: Alternative basename in the default directory; mutually exclusive with path.
        :returns: An adapter for the initialized store.
        :raises ConfigurationError: If validation, exclusive creation, protection, or durable seeding fails.
        """
        record = PATStoreRecord(uuid4(), pat)
        selected = _path(path, alias)
        try:
            selected.parent.lstat()
        except FileNotFoundError:
            # Only the final directory may be created. Its parent must exist.
            _create_directory(selected.parent)
        selected = _canonical_path(selected)
        _create_file(selected)
        store = cls.__new__(cls)
        store._files = _StoreFiles(selected)
        with store._connect(_new=True) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute(f'PRAGMA application_id = {_APPLICATION_ID}')
            db.execute(f'PRAGMA user_version = {_SCHEMA_VERSION}')
            db.execute(_SCHEMA)
            db.execute('INSERT INTO credential VALUES (1, ?, ?, NULL)', (str(record.revision), record.get_pat()))
            db.commit()
            store._validate_schema(db)
        return store

    @contextmanager
    def _connect(self, *, _new: bool = False) -> Iterator[sqlite3.Connection]:
        with self._files.access():
            if not _new:
                # Check the immutable format identifiers before a writable SQLite
                # open could recover a hot journal belonging to another format.
                with self._files.path.open('rb') as source:
                    header = source.read(100)
                if (
                    len(header) != 100
                    or header[:16] != b'SQLite format 3\x00'
                    or int.from_bytes(header[60:64], 'big') != _SCHEMA_VERSION
                    or int.from_bytes(header[68:72], 'big') != _APPLICATION_ID
                ):
                    raise ValueError('Unsupported PAT store header.')
            # sqlite3 is optional in some Python distributions; base SDK imports still work.
            sqlite = importlib.import_module('sqlite3')
            with closing(
                sqlite.connect(
                    self._files.path.as_uri() + '?mode=rw',
                    uri=True,
                    timeout=5.0,
                    isolation_level=None,
                    autocommit=sqlite.LEGACY_TRANSACTION_CONTROL,
                )
            ) as db:
                db.execute('PRAGMA trusted_schema = OFF')
                db.execute('PRAGMA synchronous = EXTRA')
                if db.execute('PRAGMA synchronous').fetchone() != (3,):
                    raise ValueError('Required durability is unavailable.')
                # Do not change an existing database's persistent journal mode on open.
                if db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                    raise ValueError('Only rollback DELETE journaling is supported.')
                if sys.platform == 'darwin':
                    db.execute('PRAGMA fullfsync = ON')
                    if db.execute('PRAGMA fullfsync').fetchone() != (1,):
                        raise ValueError('Required synchronization is unavailable.')
                try:
                    yield db
                finally:
                    if db.in_transaction:
                        db.rollback()

    @staticmethod
    def _validate_schema(db: sqlite3.Connection) -> None:
        if (
            db.execute('PRAGMA application_id').fetchone() != (_APPLICATION_ID,)
            or db.execute('PRAGMA user_version').fetchone() != (_SCHEMA_VERSION,)
            or db.execute('SELECT type, name, sql FROM sqlite_schema ORDER BY name').fetchall()
            != [('table', 'credential', _SCHEMA)]
        ):
            raise ValueError('Unsupported PAT store format.')

    @staticmethod
    def _load_record(db: sqlite3.Connection) -> PATStoreRecord | None:
        rows = db.execute('SELECT slot, revision, pat, pending_attempt FROM credential').fetchall()
        if not rows:
            return None
        if len(rows) != 1 or rows[0][0] != 1:
            raise ValueError('Invalid credential slot.')
        _, revision, pat, attempt = rows[0]
        return PATStoreRecord(_uuid(revision), pat, _uuid(attempt) if attempt is not None else None)

    @_safe_errors(ConfigurationError, _OPEN_ERROR)
    def load(self) -> PATStoreRecord | None:
        """Read the latest committed record, including any unresolved attempt.

        :returns: A redacted record, or None if the supported database has no credential.
        :raises ConfigurationError: If access, protection, format, or record validation fails.
        """
        with self._connect() as db:
            self._validate_schema(db)
            record = self._load_record(db)
        return record

    @_safe_errors(PATPersistenceError, 'Could not confirm the durable PAT store write.')
    def compare_and_swap(self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord) -> bool:
        """Durably replace the record only while both observed identifiers match.

        :param expected_revision: Credential revision that must still be current.
        :param expected_attempt: Pending attempt that must still match, including None.
        :param replacement: Complete next credential record and marker.
        :returns: True after durable commit; False only for a comparison mismatch.
        :raises PATPersistenceError: If arguments are invalid or a safe, durable write cannot be confirmed.
        """
        if (
            type(expected_revision) is not UUID
            or (expected_attempt is not None and type(expected_attempt) is not UUID)
            or type(replacement) is not PATStoreRecord
        ):
            raise ConfigurationError('PAT store writes require UUID identifiers and a PATStoreRecord.')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._validate_schema(db)
            self._load_record(db)
            changed = db.execute(
                'UPDATE credential SET revision = ?, pat = ?, pending_attempt = ? '
                'WHERE slot = 1 AND revision = ? AND pending_attempt IS ?',
                (
                    str(replacement.revision),
                    replacement.get_pat(),
                    str(replacement.pending_attempt) if replacement.pending_attempt is not None else None,
                    str(expected_revision),
                    str(expected_attempt) if expected_attempt is not None else None,
                ),
            ).rowcount
            db.commit()
        return changed == 1
