# -*- coding: utf-8 -*-
"""
:Module:            tools.ci.audit
:Synopsis:          Fail-closed advisory scan of every locked runtime variant
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.utils import canonicalize_name


def locked_runtime(lock: dict) -> list[dict]:
    """Include all main-group variants, conservatively ignoring marker exclusions.

    Poetry's resolved main group includes the transitive closure. Scanning its
    union rather than this interpreter's environment covers other Python minors,
    architectures and operating systems, including conditional dependencies.
    """
    packages = {}
    for package in lock['package']:
        if 'main' in package['groups']:
            if package.get('source'):
                raise ValueError('Non-PyPI runtime dependency requires an explicit audit strategy.')
            key = (canonicalize_name(package['name']), package['version'])
            packages[key] = {
                'name': key[0],
                'version': key[1],
                'python_versions': package['python-versions'],
                'markers': package.get('markers', '*'),
            }
    if not packages:
        raise ValueError('No runtime dependencies found in the lockfile.')
    return [packages[key] for key in sorted(packages)]


def exceptions(path: Path, today: date) -> list[dict]:
    """Require a bounded, reviewed exception for one package/version/advisory."""
    records = json.loads(path.read_text(encoding='utf-8'))['exceptions']
    for record in records:
        for key in ('name', 'version', 'id', 'rationale', 'issue', 'approved_by', 'expires'):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f'Exception requires {key}.')
        expiry = date.fromisoformat(record['expires'])
        if not today <= expiry <= date.fromordinal(today.toordinal() + 90):
            raise ValueError('Audit exception is expired or exceeds the 90-day review window.')
    return records


def disposition(report: dict, expected: list[dict], waivers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Reject incomplete scans; retain actionable IDs, aliases and fix versions."""
    dependencies = report['dependencies']
    received = {(canonicalize_name(item['name']), item['version']) for item in dependencies}
    wanted = {(item['name'], item['version']) for item in expected}
    if received != wanted or len(dependencies) != len(wanted) or any('skip_reason' in item for item in dependencies):
        raise ValueError('Advisory service returned an incomplete or skipped dependency scan.')
    findings, accepted = [], []
    for dependency in dependencies:
        for vulnerability in dependency['vulns']:
            if not vulnerability.get('id') or 'fix_versions' not in vulnerability:
                raise ValueError('Malformed advisory response.')
            finding = {'name': dependency['name'], 'version': dependency['version'], **vulnerability}
            ids = {vulnerability['id'], *vulnerability.get('aliases', [])}
            waiver = next(
                (
                    item
                    for item in waivers
                    if canonicalize_name(item['name']) == canonicalize_name(dependency['name'])
                    and item['version'] == dependency['version']
                    and item['id'] in ids
                ),
                None,
            )
            (accepted if waiver else findings).append({**finding, **({'exception': waiver} if waiver else {})})
    return findings, accepted


def scan(packages: list[dict], directory: Path) -> dict:
    """Invoke pip-audit without installation, resolution, ignores or autofixes."""
    # pip-audit rejects duplicate names even when versions differ. Split only
    # those variants into separate batches; every locked version is scanned.
    batches: list[list[dict]] = [[]]
    for package in packages:
        for batch in batches:
            if all(item['name'] != package['name'] for item in batch):
                batch.append(package)
                break
        else:
            batches.append([package])
    results = []
    for index, batch in enumerate(batches):
        requirements = directory / f'runtime-{index}.txt'
        output = directory / f'audit-{index}.json'
        requirements.write_text(''.join(f'{item["name"]}=={item["version"]}\n' for item in batch), encoding='utf-8')
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'pip_audit',
                '--requirement',
                str(requirements),
                '--no-deps',
                '--disable-pip',
                '--format=json',
                '--aliases',
                '--progress-spinner=off',
                '--timeout=30',
                '--output',
                str(output),
            ],
            check=False,
            timeout=300,
        )
        if result.returncode not in (0, 1) or not output.is_file():
            raise ValueError('Audit tooling/advisory service failed; no clean result may be inferred.')
        report = json.loads(output.read_text(encoding='utf-8'))
        disposition(report, batch, [])  # Prove service completeness before collecting results.
        has_findings = any(item['vulns'] for item in report['dependencies'])
        if result.returncode != int(has_findings):
            raise ValueError('Audit exit status disagrees with advisory report.')
        results.extend(report['dependencies'])
    return {'dependencies': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path('poetry.lock'))
    parser.add_argument('--exceptions', type=Path, default=Path('tools/ci/audit-exceptions.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'date_utc': datetime.now(UTC).isoformat(), 'status': 'error'}
    code = 2
    try:
        lock = tomllib.loads(args.lock.read_text(encoding='utf-8'))
        packages = locked_runtime(lock)
        evidence.update(
            lock_sha256=hashlib.sha256(args.lock.read_bytes()).hexdigest(),
            pip_audit_version=version('pip-audit'),
            scope='union of all locked main-group variants; no marker exclusions',
            packages=packages,
        )
        waivers = exceptions(args.exceptions, datetime.now(UTC).date())
        with TemporaryDirectory() as directory:
            report = scan(packages, Path(directory))
        findings, accepted = disposition(report, packages, waivers)
        code = int(bool(findings))
        evidence.update(status='vulnerable' if findings else 'passed', findings=findings, exceptions=accepted, report=report)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        evidence['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
