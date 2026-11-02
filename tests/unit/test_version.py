# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_version
:Synopsis:          Regression coverage for installed and source-checkout versions
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     01 Nov 2026
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from sfdctrust import __version__, _version


def test_installed_metadata_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use installed metadata even when a different checkout is present."""
    monkeypatch.setattr(_version, 'version', lambda name: '2.3.4')
    assert _version.get_full_version() == '2.3.4'


def test_source_checkout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Find the repository pyproject when distribution metadata is absent."""

    def missing_metadata(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(_version, 'version', missing_metadata)
    project_file = Path(__file__).resolve().parents[2] / 'pyproject.toml'
    expected = tomllib.loads(project_file.read_text())['project']['version']
    assert _version.get_full_version() == expected


@pytest.mark.parametrize(
    ('configuration', 'expected'),
    [
        ('[project]\nversion = "1.2.3"\n[tool.poetry]\nversion = "4.5.6"\n', '1.2.3'),
        ('[tool.poetry]\nversion = "4.5.6"\n', '4.5.6'),
        ('[project]\nname = "sfdctrust"\n', '0.0.0'),
    ],
)
def test_explicit_version_file(tmp_path: Path, configuration: str, expected: str) -> None:
    """Preserve PEP 621 precedence and the existing legacy fallback."""
    project_file = tmp_path / 'pyproject.toml'
    project_file.write_text(configuration)
    assert _version.get_version_from_pyproject(str(project_file)) == expected


def test_public_version_export() -> None:
    """Expose the package version through the public __version__ attribute."""
    assert __version__ == _version.__version__ == _version.get_full_version()


@pytest.mark.parametrize(('full_version', 'expected'), [('1.0.0.dev0', '1.0'), ('2', '2')])
def test_major_minor_version(full_version: str, expected: str) -> None:
    """Keep development suffixes out of the major/minor version."""
    assert _version.get_major_minor_version(full_version) == expected
