# -*- coding: utf-8 -*-
"""
:Module:            local_pat_store
:Synopsis:          Single-machine PAT store for the Getting Started walkthrough
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import warnings
from contextlib import closing
from getpass import GetPassWarning, getpass
from pathlib import Path
from uuid import UUID, uuid4

from sfdctrust import ConfigurationError, PATStoreRecord

DEFAULT_DIRECTORY = Path.home() / '.sfdctrust'


class LocalPATStore:
    """Keep one test PAT in SQLite on a private, encrypted local filesystem.

    :param directory: Private directory containing the SQLite database.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY) -> None:
        self._database = directory.expanduser() / 'pat.sqlite3'

    def _connect(self) -> sqlite3.Connection:
        if os.name == 'posix':
            for path in (self._database.parent, self._database):
                info = path.stat()
                if info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise PermissionError('The test store directory and database must be private to your account.')
        # Open an existing database. Only seed() may create it.
        # Python 3.12 added the autocommit keyword. Keep legacy mode explicit
        # so isolation_level still applies and PRAGMA synchronous runs before
        # a transaction starts, even when Python changes the default.
        db = sqlite3.connect(
            self._database.absolute().as_uri() + '?mode=rw',
            uri=True,
            timeout=5.0,
            isolation_level='IMMEDIATE',
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        )
        try:
            db.execute('PRAGMA synchronous = EXTRA')
        except sqlite3.Error:
            db.close()
            raise
        return db

    def seed(self, pat: str) -> None:
        """Save the first PAT. Refuse to replace a seeded or pending record.

        :param pat: Initial PAT copied from My Trust Center.
        """
        record = PATStoreRecord(uuid4(), pat)
        self._database.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            fd = os.open(self._database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)

        with closing(self._connect()) as db, db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS credential ('
                'slot INTEGER PRIMARY KEY CHECK (slot = 1), '
                'revision TEXT NOT NULL, pat TEXT NOT NULL, pending_attempt TEXT)'
            )
            inserted = db.execute(
                'INSERT INTO credential VALUES (1, ?, ?, NULL) ON CONFLICT(slot) DO NOTHING',
                (str(record.revision), record.get_pat()),
            ).rowcount
            if inserted != 1:
                raise ConfigurationError('This test store already has a PAT. Use a fresh store directory to reseed.')

    def load(self) -> PATStoreRecord | None:
        """Read the currently committed credential and pending marker."""
        with closing(self._connect()) as db:
            row = db.execute('SELECT revision, pat, pending_attempt FROM credential WHERE slot = 1').fetchone()
        if row is None:
            return None
        revision, pat, pending_attempt = row
        return PATStoreRecord(UUID(revision), pat, UUID(pending_attempt) if pending_attempt is not None else None)

    def compare_and_swap(self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord) -> bool:
        """Commit a change only if the credential version and pending marker match.

        :param expected_revision: Current credential version.
        :param expected_attempt: Current pending marker, or None.
        :param replacement: Record to save in the same transaction.
        :returns: Boolean indicating whether the write committed.
        """
        with closing(self._connect()) as db, db:
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
        return changed == 1


def _main() -> None:
    parser = argparse.ArgumentParser(description='Seed a private local PAT store for the sfdctrust walkthrough.')
    parser.add_argument('command', choices=['seed'])
    parser.add_argument('--directory', type=Path, default=DEFAULT_DIRECTORY, help='Private local store directory')
    args = parser.parse_args()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', GetPassWarning)
            pat = getpass('My Trust Center PAT (input is hidden): ')
        LocalPATStore(args.directory).seed(pat)
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        parser.exit(1, 'Use an interactive terminal with hidden input to seed the test store.\n')
    except ConfigurationError as exc:
        parser.exit(1, f'{exc}\n')
    except (OSError, sqlite3.Error):
        parser.exit(1, 'Cannot write the test store. Check the directory, file permissions, and available disk space.\n')

    print('Saved the PAT in the local test store.')


if __name__ == '__main__':
    _main()
