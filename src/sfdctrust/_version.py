# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._version
:Synopsis:          Utilities for working with the package version
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     01 Nov 2026
"""

from __future__ import annotations

import logging
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

logger = logging.getLogger(__name__)


def get_full_version() -> str:
    """Returns the current full version of the ``sfdctrust`` package.

    The package version is retrieved from the installed package metadata, which is
    populated from the ``version`` field in ``pyproject.toml``.

    :returns: The current package version as a string
    :rtype: str
    """
    try:
        return version('sfdctrust')
    except PackageNotFoundError:
        # This can happen if the package is not installed in the environment
        # (e.g. running from a source checkout without an editable install)
        logger.debug('Package is not installed and version will be retrieved from pyproject.toml file')
        return get_version_from_pyproject()


def get_major_minor_version(full_version: str | None = None) -> str:
    """Returns the current major.minor (i.e., X.Y) version of the package.

    :param full_version: The full package version (e.g. X.Y.Z)
    :type full_version: str, optional
    :returns: The current package version (X.Y) as a string
    :rtype: str
    """
    if not full_version:
        full_version = get_full_version()
    parts = full_version.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[:2])
    return full_version


def get_version_from_pyproject(pyproject_path: str | None = None) -> str:
    """Retrieves the current version from the pyproject.toml file.

    :param pyproject_path: The path to the pyproject.toml file
    :type pyproject_path: str, optional
    :returns: The current package version as a string
    :rtype: str
    """
    path = Path(pyproject_path) if pyproject_path else Path(__file__).resolve().parents[2] / 'pyproject.toml'

    # tomllib.loads() expects a string, while Path.read_bytes() returns bytes
    # Prefer tomllib.load() with a binary file handle to avoid encoding pitfalls
    with path.open('rb') as fp:
        data = tomllib.load(fp)

    # PEP 621
    project_version = data.get('project', {}).get('version')
    if project_version:
        return str(project_version)

    # Poetry legacy layout
    project_version = data.get('tool', {}).get('poetry', {}).get('version')
    if project_version:
        return str(project_version)

    logger.warning("sfdctrust version could not be retrieved; falling back to '0.0.0' as version")
    return '0.0.0'


# Define __version__ for backward compatibility and to utilize as needed
__version__ = get_full_version()
