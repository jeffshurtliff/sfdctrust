# -*- coding: utf-8 -*-
"""
:Module:            tools.ci.qualify
:Synopsis:          Separate retrieval from clean offline wheel and sdist qualification
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
import venv
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from audit import locked_runtime


def run(arguments: list[str], **kwargs) -> None:
    subprocess.run(arguments, check=True, timeout=300, **kwargs)


def prepare(root: Path, dist: Path, wheelhouse: Path) -> None:
    """Retrieve dependencies only; behavior checks happen in a separate phase."""
    wheelhouse.mkdir(parents=True, exist_ok=False)
    lock = tomllib.loads((root / 'poetry.lock').read_text(encoding='utf-8'))
    pins = set()
    variants: dict[str, set[str]] = {}
    for package in locked_runtime(lock):
        variants.setdefault(package['name'], set()).add(package['version'])
    for name, versions in variants.items():
        try:
            installed = version(name)
        except PackageNotFoundError:
            continue  # Non-active platform/Python marker; pip checks closure below.
        if installed not in versions:
            raise ValueError(f'Installed runtime dependency {name} differs from the lock; run poetry install first.')
        pins.add(f'{name}=={installed}')
    # Pin all active runtime dependencies, the build backend and the type checker.
    # Additional checker dependencies are tooling, never shipped runtime packages.
    pins.update(f'{name}=={version(name)}' for name in ('poetry-core', 'mypy'))
    constraints = wheelhouse / 'locked-active.txt'
    constraints.write_text('\n'.join(sorted(pins)) + '\n', encoding='utf-8')
    run(
        [
            sys.executable,
            '-m',
            'pip',
            'download',
            '--only-binary=:all:',
            '--dest',
            str(wheelhouse),
            '--constraint',
            str(constraints),
            str(next(dist.glob('*.whl'))),
            *sorted(pins),
        ]
    )


def qualify(root: Path, dist: Path, wheelhouse: Path, work: Path) -> None:
    """Install each artifact independently; run guarded behavior and strict typing."""
    work.mkdir(parents=True, exist_ok=False)
    release = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    wheel = next(dist.glob('*.whl'))
    constraints = wheelhouse / 'locked-active.txt'
    for label, artifact in [('wheel', wheel), ('sdist', next(dist.glob('*.tar.gz')))]:
        environment = work / label
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        install = [str(python), '-I', '-m', 'pip', 'install', '--no-cache-dir', '--no-index', '--find-links', str(wheelhouse)]
        run([*install, '--constraint', str(constraints), f'poetry-core=={version("poetry-core")}', f'mypy=={version("mypy")}'])
        run([*install, '--constraint', str(constraints), '--no-build-isolation', str(artifact)])
        run([str(python), '-I', '-m', 'pip', 'check'])
        frozen = subprocess.check_output([str(python), '-I', '-m', 'pip', 'freeze'], text=True)
        (work / f'{label}-freeze.txt').write_text(frozen, encoding='utf-8')
        run([str(python), '-I', str(root / 'tests/offline/run.py'), str(root / 'tests/package_smoke.py')], cwd=work)
        run(
            [
                str(python),
                '-I',
                str(root / 'tests/compatibility/check_wheel.py'),
                '--wheel',
                str(wheel),
                '--expected-version',
                release,
                '--snapshot',
                str(root / 'tests/compatibility/public-api.json'),
                '--evidence',
                str(work / f'{label}-compatibility.json'),
            ],
            cwd=work,
        )
        run(
            [
                str(python),
                '-I',
                str(root / 'tests/offline/run.py'),
                '-m',
                'mypy',
                '--config-file',
                str(root / 'tests/compatibility/mypy.ini'),
                '--no-incremental',
                str(root / 'tests/compatibility/downstream.py'),
            ],
            cwd=work,
        )
    (work / 'result.json').write_text(
        json.dumps({'version': release, 'wheel': 'passed', 'sdist': 'passed'}) + '\n', encoding='utf-8'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'qualify'])
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.root.resolve(), args.dist.resolve(), args.wheelhouse.resolve())
    else:
        qualify(args.root.resolve(), args.dist.resolve(), args.wheelhouse.resolve(), args.work.resolve())


if __name__ == '__main__':
    main()
