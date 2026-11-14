# -*- coding: utf-8 -*-
"""
:Module:            tools.ci.artifacts
:Synopsis:          Verify release payloads, source identity and transferred checksums
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     14 Nov 2026
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tomllib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.version import Version

PROJECT_TOML_FILE = 'pyproject.toml'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *arguments], text=True).strip()


def source_policy(root: Path, destination: str, expected_sha: str, expected_version: str, ref: str) -> None:
    """Authorize immutable source before building; uploading needs separate approval."""
    require(re.fullmatch(r'[0-9a-f]{40}', expected_sha) is not None, 'Expected a full source commit SHA.')
    require(git(root, 'rev-parse', 'HEAD') == expected_sha, 'Checkout differs from approved commit.')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Release source must be clean.')
    project = tomllib.loads((root / PROJECT_TOML_FILE).read_text(encoding='utf-8'))['project']
    require(project['version'] == expected_version, 'Metadata differs from approved version.')
    parsed = Version(expected_version)
    require(str(parsed) == expected_version and parsed.local is None, 'Use a canonical public version.')
    if destination == 'pypi':
        require(
            not parsed.is_prerelease and not parsed.is_devrelease and not parsed.is_postrelease,
            'Production requires a stable version.',
        )
        require(ref == f'refs/tags/{expected_version}', 'Production tag must exactly equal package version (no v prefix).')
        require(git(root, 'rev-parse', f'{ref}^{{commit}}') == expected_sha, 'Tag does not identify approved source.')
        subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', expected_sha, 'origin/main'], check=True)
    elif destination == 'testpypi':
        require(parsed.is_prerelease and not parsed.is_devrelease, 'TestPyPI requires a unique alpha/beta/rc version.')
        require(ref == 'refs/heads/release/testpypi', 'TestPyPI is restricted to the dedicated rehearsal branch.')
    else:
        require(destination == 'validate', 'Unknown destination.')
        require(
            ref == 'refs/heads/main' or ref == 'refs/heads/release/testpypi',
            'Validation requires reviewed source.',
        )


def safe_name(name: str) -> None:
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, f'Unsafe archive path: {name}')
    for part in path.parts:
        lower = part.lower()
        require(
            lower
            not in {'local', 'dev', '.git', '.aws', '.ssh', '.venv', '__pycache__', '.pypirc', 'credentials', 'secrets.toml'}
            and not lower.startswith(('.env', '._'))
            and not lower.endswith(('.key', '.pem', '.p12', '.pfx', '.sqlite3', '.sqlite3-wal', '.sqlite3-shm', '.pyc')),
            f'Forbidden local/credential file: {name}',
        )


def payload(path: Path) -> dict[str, bytes]:
    if path.suffix == '.whl':
        with ZipFile(path) as archive:
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
            require(len(names) == len(set(names)), 'Duplicate wheel entries.')
            for name in names:
                safe_name(name)
            return {name: archive.read(name) for name in names}
    with tarfile.open(path, 'r:gz') as archive:
        files = {}
        for member in archive.getmembers():
            safe_name(member.name)
            require(member.isfile() or member.isdir(), 'sdist must not contain links or special files.')
            if member.isfile():
                require(member.name not in files, 'Duplicate sdist entries.')
                stream = archive.extractfile(member)
                require(stream is not None, 'Unreadable sdist member.')
                files[member.name] = stream.read()
        prefix = f'sfdctrust-{path.name.removeprefix("sfdctrust-").removesuffix(".tar.gz")}/'
        require(all(name.startswith(prefix) for name in files), 'Unexpected sdist root.')
        return {name.removeprefix(prefix): data for name, data in files.items()}


def metadata(data: bytes, project: dict) -> None:
    message = BytesParser().parsebytes(data)
    for key, expected in {
        'Name': 'sfdctrust',
        'Version': project['version'],
        'Requires-Python': project['requires-python'],
        'License-Expression': project['license'],
    }.items():
        require(message[key] == expected, f'Incorrect {key} metadata: {message[key]}')
    require('LICENSE' in message.get_all('License-File', []), 'Missing license metadata.')
    require(set(message.get_all('Classifier', [])) == set(project['classifiers']), 'Classifier policy changed.')
    require(
        {str(Requirement(value)) for value in message.get_all('Requires-Dist', [])}
        == {str(Requirement(value)) for value in project['dependencies']},
        'Runtime requirements differ from source.',
    )


def verify(root: Path, directory: Path) -> dict:
    project = tomllib.loads((root / PROJECT_TOML_FILE).read_text(encoding='utf-8'))['project']
    release = project['version']
    names = {f'sfdctrust-{release}-py3-none-any.whl', f'sfdctrust-{release}.tar.gz'}
    require({path.name for path in directory.iterdir()} == names, 'Expected exactly one wheel and one sdist in dist/.')
    sources = {
        str(path.relative_to(root / 'src')).replace('\\', '/'): path.read_bytes()
        for path in (root / 'src/sfdctrust').rglob('*')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
    }
    require('sfdctrust/py.typed' in sources, 'Source lacks py.typed.')
    records = {}
    source_hashes = {}
    for name in sorted(names):
        path = directory / name
        files = payload(path)
        if path.suffix == '.whl':
            info = f'sfdctrust-{release}.dist-info'
            allowed = set(sources) | {f'{info}/{item}' for item in ('METADATA', 'WHEEL', 'RECORD', 'licenses/LICENSE')}
            require(set(files) == allowed, 'Wheel payload differs from approved package files.')
            for source, data in sources.items():
                require(files[source] == data, f'Wheel source mismatch: {source}')
            require(files[f'{info}/licenses/LICENSE'] == (root / 'LICENSE').read_bytes(), 'Wheel license mismatch.')
            metadata(files[f'{info}/METADATA'], project)
        else:
            required = {PROJECT_TOML_FILE, 'poetry.lock', 'LICENSE', 'README.md', 'PKG-INFO'} | {
                f'src/{item}' for item in sources
            }
            require(required <= files.keys(), 'sdist lacks required source, lock, license or metadata.')
            metadata(files['PKG-INFO'], project)
            for source, data in files.items():
                if source == 'PKG-INFO':
                    continue
                require(
                    source in {PROJECT_TOML_FILE, 'poetry.lock', 'LICENSE', 'README.md', 'CONTRIBUTING.md'}
                    or source.startswith(('src/sfdctrust/', 'tests/', 'tools/ci/'))
                    or source in {'docs/CHANGELOG.md', 'docs/API_CONTRACT.md'},
                    f'Unexpected sdist payload: {source}',
                )
                original = root / source
                require(original.is_file() and original.read_bytes() == data, f'sdist source mismatch: {source}')
                source_hashes[source] = hashlib.sha256(data).hexdigest()
        records[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}
    return {
        'version': release,
        'source_commit': git(root, 'rev-parse', 'HEAD'),
        'source_status': git(root, 'status', '--short'),
        'sdist_source_sha256': source_hashes,
        'files': records,
    }


def transferred(directory: Path, manifest: dict) -> None:
    """Verify the complete transferred file set before upload; never rebuild."""
    require(
        {item.name for item in directory.iterdir()} == set(manifest['files']), 'Transferred artifact set differs from manifest.'
    )
    for name, record in manifest['files'].items():
        require(Path(name).name == name and name.endswith(('.whl', '.tar.gz')), 'Invalid artifact filename.')
        path = directory / name
        require(path.stat().st_size == record['size'], f'Transferred artifact size mismatch: {name}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'], f'Transferred SHA-256 mismatch: {name}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['source', 'inspect', 'transfer'])
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--manifest', type=Path, default=Path('release-manifest.json'))
    parser.add_argument('--destination', choices=['validate', 'testpypi', 'pypi'], default='validate')
    parser.add_argument('--sha')
    parser.add_argument('--version')
    parser.add_argument('--ref')
    args = parser.parse_args()
    if args.mode == 'source':
        source_policy(args.root, args.destination, args.sha, args.version, args.ref)
    elif args.mode == 'inspect':
        report = verify(args.root, args.dist)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        args.manifest.with_name('SHA256SUMS').write_text(
            ''.join(f'{item["sha256"]}  {name}\n' for name, item in report['files'].items()), encoding='utf-8'
        )
        print(json.dumps(report, indent=2))
    else:
        transferred(args.dist, json.loads(args.manifest.read_text(encoding='utf-8')))
        print('Transferred artifact file set and SHA-256 checksums verified.')


if __name__ == '__main__':
    main()
