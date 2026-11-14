# -*- coding: utf-8 -*-
"""
:Module:            tools.ci.registry
:Synopsis:          Verify approved hosted files and their Trusted Publishing provenance
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from artifacts import require, transferred
from pypi_attestations import AttestationType, Distribution, GitHubPublisher, Provenance
from qualify import prepare, qualify

REPOSITORY = 'jeffshurtliff/sfdctrust'
WORKFLOW = 'release.yml'


def provenance_identity(provenance, distribution, destination, sha, ref, run_id) -> list[dict]:
    """Verify signatures, transparency proofs, filename/digest and exact CI identity."""
    expected = GitHubPublisher(repository=REPOSITORY, workflow=WORKFLOW, environment=destination)
    require(bool(provenance.attestation_bundles), 'No hosted attestations.')
    checked = []
    for bundle in provenance.attestation_bundles:
        require(bundle.publisher == expected and bool(bundle.attestations), 'Unexpected or empty Trusted Publisher bundle.')
        for attestation in bundle.attestations:
            predicate, _ = attestation.verify(expected, distribution)
            claims = attestation.certificate_claims
            prefix = '1.3.6.1.4.1.57264.1.'
            expected_claims = {
                '12': f'https://github.com/{REPOSITORY}',
                '13': sha,
                '14': ref,
                '18': f'https://github.com/{REPOSITORY}/.github/workflows/{WORKFLOW}@{ref}',
                '20': 'workflow_dispatch',
            }
            for number, value in expected_claims.items():
                require(claims.get(prefix + number) == value, f'Certificate identity mismatch for claim {number}.')
            invocation = claims.get(prefix + '21', '')
            require(
                invocation.startswith(f'https://github.com/{REPOSITORY}/actions/runs/{run_id}/attempts/'),
                'Certificate identifies another workflow run.',
            )
            checked.append({'predicate': predicate, 'certificate_claims': claims})
    require(
        any(item['predicate'] == AttestationType.PYPI_PUBLISH_V1 for item in checked), 'Missing per-file publish attestation.'
    )
    return checked


def hosted_files(release: dict, manifest: dict) -> dict:
    """Reject partial/extra uploads, yanks and digests different from checked bytes."""
    files = release['urls']
    require(len(files) == len(manifest['files']), 'Registry release is partial or has unexpected files.')
    result = {}
    for file in files:
        name = file['filename']
        require(name in manifest['files'] and name not in result and not file['yanked'], 'Unexpected, duplicate or yanked file.')
        record = manifest['files'][name]
        require(file['digests']['sha256'] == record['sha256'] and file['size'] == record['size'], 'Hosted digest/size mismatch.')
        parsed = urlparse(file['url'])
        require(
            parsed.scheme == 'https' and parsed.hostname in {'files.pythonhosted.org', 'test-files.pythonhosted.org'},
            'Unexpected registry file host.',
        )
        result[name] = file
    return result


def verify_registry(root: Path, bundle: Path, destination: str, ref: str, run_id: str) -> None:
    manifest = json.loads((bundle / 'evidence/release-manifest.json').read_text(encoding='utf-8'))
    transferred(bundle / 'dist', manifest)
    output = bundle / 'evidence/registry'
    output.mkdir(parents=True, exist_ok=False)
    downloads = output / 'downloads'
    downloads.mkdir()
    host = 'https://test.pypi.org' if destination == 'testpypi' else 'https://pypi.org'
    release = manifest['version']
    report = {
        'destination': destination,
        'source_commit': manifest['source_commit'],
        'version': release,
        'run_id': run_id,
        'files': {},
    }
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(f'{host}/pypi/sfdctrust/{release}/json')
        response.raise_for_status()
        (output / 'release.json').write_bytes(response.content)
        for name, file in hosted_files(response.json(), manifest).items():
            downloaded = client.get(file['url'])
            downloaded.raise_for_status()
            require(
                hashlib.sha256(downloaded.content).hexdigest() == manifest['files'][name]['sha256'], 'Downloaded digest mismatch.'
            )
            path = downloads / name
            path.write_bytes(downloaded.content)
            provenance_response = client.get(f'{host}/integrity/sfdctrust/{release}/{name}/provenance')
            provenance_response.raise_for_status()
            (output / f'{name}.provenance.json').write_bytes(provenance_response.content)
            provenance = Provenance.model_validate_json(provenance_response.content)
            identities = provenance_identity(
                provenance, Distribution.from_file(path), destination, manifest['source_commit'], ref, run_id
            )
            report['files'][name] = {'sha256': manifest['files'][name]['sha256'], 'verified_attestations': identities}
    # Retrieval is separate from the network-blocked behavioral phase. Dependencies
    # come from ordinary PyPI with lock constraints, never a mixed extra-index.
    prepare(root, downloads, output / 'wheelhouse')
    qualify(root, downloads, output / 'wheelhouse', output / 'installs')
    report['clean_installations'] = 'wheel and sdist passed offline smoke, compatibility and strict typing'
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', choices=['testpypi', 'pypi'], required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    verify_registry(Path('.').resolve(), args.bundle.resolve(), args.destination, args.ref, args.run_id)


if __name__ == '__main__':
    main()
