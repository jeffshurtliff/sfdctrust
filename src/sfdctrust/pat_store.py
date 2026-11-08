# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.pat_store
:Synopsis:          Hidden-prompt initialization of a built-in SQLite PAT store
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     08 Nov 2026
"""

from __future__ import annotations

import argparse
import os
import warnings
from getpass import GetPassWarning, getpass

from ._auth import _validate_pat
from ._exceptions import ConfigurationError
from ._sqlite_pat_store import SQLitePATStore


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's usual error echoes unrecognized arguments, which may contain a PAT
        self.print_usage()
        self.exit(2, 'Invalid arguments. Use --help for initialization options.\n')


def _main(argv: list[str] | None = None) -> None:
    parser = _Parser(description='Initialize a private SQLite PAT store on an encrypted local volume.', allow_abbrev=False)
    parser.add_argument('command', choices=['init'])
    location = parser.add_mutually_exclusive_group()
    location.add_argument('--path', help='New database path in a private directory')
    location.add_argument('--alias', help='Alternative database name under ~/.sfdctrust')
    parser.add_argument(
        '--from-env',
        nargs='?',
        const='SFDCTRUST_PAT',
        metavar='NAME',
        help='Read a PAT from NAME (SFDCTRUST_PAT if omitted)',
    )
    args = parser.parse_args(argv)
    try:
        if args.from_env is None:
            with warnings.catch_warnings():
                warnings.simplefilter('error', GetPassWarning)
                pat = getpass('My Trust Center PAT (input is hidden): ')
        else:
            pat = os.environ.get(args.from_env)
        _validate_pat(pat)
        SQLitePATStore.initialize(pat=pat, path=args.path, alias=args.alias)
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        parser.exit(1, 'Hidden input is unavailable or cancelled. Use an interactive terminal or --from-env.\n')
    except (OSError, ValueError):
        parser.exit(1, 'Cannot read the selected PAT input. Use a working terminal or environment variable.\n')
    except ConfigurationError as exc:
        parser.exit(1, f'{exc}\n')
    print('Initialized the private SQLite PAT store.')


if __name__ == '__main__':
    _main()
