# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_ci_tooling
:Synopsis:          Audit failure, release identity, archive and workflow regressions
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tomllib
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(f'ci_{name}', ROOT / f'tools/ci/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('audit')
artifacts = load('artifacts')
matrix = load('matrix')


def test_lock_audit_includes_all_platform_python_and_transitive_variants():
    packages = [
        {
            'name': 'Shared-Name',
            'version': '1',
            'groups': ['main'],
            'python-versions': '<3.14',
            'markers': 'sys_platform == "win32"',
        },
        {
            'name': 'Shared_Name',
            'version': '2',
            'groups': ['main'],
            'python-versions': '>=3.14',
            'markers': 'sys_platform == "linux"',
        },
        {'name': 'transitive', 'version': '3', 'groups': ['main', 'dev'], 'python-versions': '*'},
        {'name': 'tooling', 'version': '4', 'groups': ['dev'], 'python-versions': '*'},
    ]
    found = audit.locked_runtime({'package': packages})
    assert [(item['name'], item['version']) for item in found] == [
        ('shared-name', '1'),
        ('shared-name', '2'),
        ('transitive', '3'),
    ]
    assert found[0]['markers'] == 'sys_platform == "win32"'
    with pytest.raises(ValueError, match='Non-PyPI'):
        audit.locked_runtime({'package': [{**packages[0], 'source': {'type': 'git'}}]})


def vulnerable_report():
    return {
        'dependencies': [
            {
                'name': 'requests',
                'version': '2.31.0',
                'vulns': [{'id': 'CVE-2024-35195', 'aliases': ['GHSA-9wx4-h78v-vm56'], 'fix_versions': ['2.32.0']}],
            }
        ]
    }


def test_audit_actionable_findings_and_scoped_alias_exception(tmp_path):
    report = vulnerable_report()
    expected = [{'name': 'requests', 'version': '2.31.0'}]
    findings, accepted = audit.disposition(report, expected, [])
    assert findings[0]['id'] == 'CVE-2024-35195' and findings[0]['fix_versions'] == ['2.32.0'] and accepted == []
    record = {
        'name': 'requests',
        'version': '2.31.0',
        'id': 'GHSA-9wx4-h78v-vm56',
        'expires': '2026-11-20',
        'rationale': 'Controlled test fixture only',
        'approved_by': 'synthetic maintainer',
        'issue': 'https://example.invalid/triage',
    }
    path = tmp_path / 'exceptions.json'
    path.write_text(json.dumps({'exceptions': [record]}))
    waivers = audit.exceptions(path, date(2026, 11, 13))
    findings, accepted = audit.disposition(report, expected, waivers)
    assert findings == [] and accepted[0]['exception'] == record
    assert audit.disposition(report, expected, [{**record, 'version': '2.30.0'}])[0]
    for today in (date(2026, 11, 21), date(2026, 1, 1)):
        with pytest.raises(ValueError, match='expired or exceeds'):
            audit.exceptions(path, today)
    path.write_text(json.dumps({'exceptions': [{**record, 'rationale': ''}]}))
    with pytest.raises(ValueError, match='rationale'):
        audit.exceptions(path, date(2026, 11, 13))


@pytest.mark.parametrize(
    'dependencies', [[], [{'name': 'requests', 'version': '2.31.0', 'skip_reason': 'HTTP 404', 'vulns': []}]]
)
def test_advisory_incompleteness_is_not_a_clean_result(dependencies):
    with pytest.raises(ValueError, match='incomplete or skipped'):
        audit.disposition({'dependencies': dependencies}, [{'name': 'requests', 'version': '2.31.0'}], [])


def test_audit_batches_duplicate_versions_and_fails_on_service_error(tmp_path, monkeypatch):
    calls = []

    def invoke(arguments, **kwargs):
        requirements = Path(arguments[arguments.index('--requirement') + 1]).read_text().splitlines()
        calls.append(requirements)
        output = Path(arguments[arguments.index('--output') + 1])
        output.write_text(
            json.dumps(
                {
                    'dependencies': [
                        dict(zip(('name', 'version'), line.split('=='), strict=True), vulns=[]) for line in requirements
                    ]
                }
            )
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(audit.subprocess, 'run', invoke)
    packages = [{'name': 'variant', 'version': '1'}, {'name': 'variant', 'version': '2'}, {'name': 'other', 'version': '3'}]
    result = audit.scan(packages, tmp_path)
    assert len(calls) == 2 and len(result['dependencies']) == 3
    monkeypatch.setattr(audit.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=2))
    with pytest.raises(ValueError, match='tooling/advisory service failed'):
        audit.scan(packages, tmp_path)


def test_qualification_retrieval_rejects_runtime_drift_from_lock(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'tools/ci'))
    qualifier = load('qualify')
    monkeypatch.setattr(qualifier, 'version', lambda name: '999.0')
    with pytest.raises(ValueError, match='differs from the lock'):
        qualifier.prepare(ROOT, tmp_path, tmp_path / 'wheelhouse')


def test_real_pip_audit_cli_reports_controlled_vulnerable_fixture_without_network(tmp_path):
    pytest.importorskip('pip_audit')
    requirements = tmp_path / 'vulnerable.txt'
    output = tmp_path / 'result.json'
    requirements.write_text('requests==2.31.0\n')
    # Exercise the maintained tool's actual parser, advisory decoder, formatter
    # and failing exit code. Only the HTTP feed is replaced; no vulnerable package
    # is installed, and the process has an irreversible socket/DNS guard.
    code = """
import json, runpy, sys
from types import SimpleNamespace
import pip_audit._service.pypi as service

def deny(event, args):
    if event.startswith('socket.'):
        raise RuntimeError('Unexpected networking in controlled advisory test')
sys.addaudithook(deny)
data = {'vulnerabilities': [{'id': 'CVE-2024-35195', 'aliases': ['GHSA-9wx4-h78v-vm56'],
    'fixed_in': ['2.32.0'], 'details': 'Controlled fixture: requests verify=False credential leakage'}]}
response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)
service.caching_session = lambda *args, **kwargs: SimpleNamespace(get=lambda **kwargs: response)
sys.argv = ['pip-audit', '--requirement', sys.argv[1], '--no-deps', '--disable-pip',
    '--format=json', '--aliases', '--progress-spinner=off', '--output', sys.argv[2]]
runpy.run_module('pip_audit', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, '-I', '-c', code, str(requirements), str(output)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 1, result.stderr
    findings, _ = audit.disposition(json.loads(output.read_text()), [{'name': 'requests', 'version': '2.31.0'}], [])
    assert findings[0]['id'] == 'CVE-2024-35195' and findings[0]['fix_versions'] == ['2.32.0']


def test_supported_matrix_uses_metadata_and_retains_minimum_native_platforms():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
    rows = matrix.matrix(project)['include']
    assert {row['python'] for row in rows} == {'3.12', '3.13', '3.14', '3.15'}
    assert {row['os'] for row in rows if row['python'] == '3.12'} == {'macos-latest', 'windows-latest', 'ubuntu-latest'}
    with pytest.raises(ValueError, match='Review the CI policy'):
        matrix.matrix({**project, 'requires-python': '>=3.13'})


@pytest.mark.parametrize(
    'name', ['../escape', '/absolute', 'local/pat.txt', '.env', 'src/.env.prod', 'tests/private.key', '.aws/config']
)
def test_artifact_paths_exclude_local_and_credential_files(name):
    with pytest.raises(ValueError):
        artifacts.safe_name(name)


def test_sdist_rejects_links(tmp_path):
    archive = tmp_path / 'sfdctrust-1.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        member = tarfile.TarInfo('sfdctrust-1/LICENSE')
        member.type = tarfile.SYMTYPE
        member.linkname = '../../secret'
        stream.addfile(member)
    with pytest.raises(ValueError, match='links or special files'):
        artifacts.payload(archive)


def artifact_fixture(tmp_path):
    source = tmp_path / 'source'
    (source / 'src/sfdctrust').mkdir(parents=True)
    (source / 'src/sfdctrust/py.typed').write_bytes(b'')
    (source / 'src/sfdctrust/__init__.py').write_bytes(b'__version__ = "1.0.0rc1"\n')
    project = {
        'version': '1.0.0rc1',
        'requires-python': '>=3.12',
        'license': 'MIT',
        'classifiers': [],
        'dependencies': ['httpx>=0.28.1,<1'],
    }
    (source / 'pyproject.toml').write_text(
        '[project]\nversion="1.0.0rc1"\nrequires-python=">=3.12"\nlicense="MIT"\nclassifiers=[]\ndependencies=["httpx>=0.28.1,<1"]\n'
    )
    for name in ('LICENSE', 'README.md', 'poetry.lock'):
        (source / name).write_text(f'Synthetic {name}')
    metadata = (
        b'Metadata-Version: 2.4\nName: sfdctrust\nVersion: 1.0.0rc1\nRequires-Python: >=3.12\n'
        b'License-Expression: MIT\nLicense-File: LICENSE\nRequires-Dist: httpx>=0.28.1,<1\n\n'
    )
    dist = tmp_path / 'dist'
    dist.mkdir()
    wheel = dist / 'sfdctrust-1.0.0rc1-py3-none-any.whl'
    with ZipFile(wheel, 'w') as archive:
        for path in (source / 'src').rglob('*'):
            if path.is_file():
                archive.write(path, str(path.relative_to(source / 'src')))
        info = 'sfdctrust-1.0.0rc1.dist-info'
        for name, data in [
            ('METADATA', metadata),
            ('WHEEL', b'Wheel-Version: 1.0'),
            ('RECORD', b''),
            ('licenses/LICENSE', (source / 'LICENSE').read_bytes()),
        ]:
            archive.writestr(f'{info}/{name}', data)
    with tarfile.open(dist / 'sfdctrust-1.0.0rc1.tar.gz', 'w:gz') as archive:
        for path in source.rglob('*'):
            if path.is_file():
                archive.add(path, arcname='sfdctrust-1.0.0rc1/' + str(path.relative_to(source)))
        member = tarfile.TarInfo('sfdctrust-1.0.0rc1/PKG-INFO')
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))
    return source, dist, project


def test_artifact_verification_and_transfer_reject_tampering(tmp_path, monkeypatch):
    source, dist, _ = artifact_fixture(tmp_path)
    monkeypatch.setattr(artifacts, 'git', lambda *args: 'a' * 40 if args[-1] == 'HEAD' else '')
    manifest = artifacts.verify(source, dist)
    artifacts.transferred(dist, manifest)
    wheel = next(dist.glob('*.whl'))
    wheel.write_bytes(wheel.read_bytes() + b'tampered')
    with pytest.raises(ValueError, match='size mismatch'):
        artifacts.transferred(dist, manifest)
    wheel.write_bytes(b'X' * manifest['files'][wheel.name]['size'])
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        artifacts.transferred(dist, manifest)


def test_artifact_inspection_rejects_version_source_and_extra_payload(tmp_path, monkeypatch):
    source, dist, _ = artifact_fixture(tmp_path)
    monkeypatch.setattr(artifacts, 'git', lambda *args: '')
    wheel = next(dist.glob('*.whl'))
    with ZipFile(wheel, 'a') as archive:
        archive.writestr('local/credential.txt', b'synthetic')
    with pytest.raises(ValueError, match='Forbidden'):
        artifacts.verify(source, dist)
    with pytest.raises(ValueError, match='Incorrect Version'):
        artifacts.metadata(b'Name: sfdctrust\nVersion: 9\n', {'version': '1', 'requires-python': '>=3.12', 'license': 'MIT'})


def test_release_source_policy_rejects_unapproved_refs_and_dirty_source(tmp_path, monkeypatch):
    source, _, _ = artifact_fixture(tmp_path)
    monkeypatch.setattr(artifacts, 'git', lambda root, *args: 'a' * 40 if args == ('rev-parse', 'HEAD') else '')
    artifacts.source_policy(source, 'testpypi', 'a' * 40, '1.0.0rc1', 'refs/heads/release/testpypi')
    for ref in ('refs/heads/main', 'refs/heads/release/testpypi'):
        artifacts.source_policy(source, 'validate', 'a' * 40, '1.0.0rc1', ref)
    for destination, sha, release, ref in [
        ('testpypi', 'b' * 40, '1.0.0rc1', 'refs/heads/release/testpypi'),
        ('testpypi', 'a' * 40, '1.0.0rc1', 'refs/heads/main'),
        ('testpypi', 'a' * 40, '1.0.0rc1', 'refs/heads/release/testpypi/1.0.0rc1'),
        ('testpypi', 'a' * 40, '1.0.0rc1', 'refs/heads/release/testpypi-extra'),
        ('pypi', 'a' * 40, '1.0.0rc1', 'refs/tags/1.0.0rc1'),
        ('validate', 'a' * 40, '1.0.0rc1', 'refs/heads/untrusted'),
    ]:
        with pytest.raises(ValueError):
            artifacts.source_policy(source, destination, sha, release, ref)
    monkeypatch.setattr(artifacts, 'git', lambda root, *args: 'a' * 40 if args == ('rev-parse', 'HEAD') else ' M pyproject.toml')
    with pytest.raises(ValueError, match='clean'):
        artifacts.source_policy(source, 'testpypi', 'a' * 40, '1.0.0rc1', 'refs/heads/release/testpypi')


def workflow(name):
    return yaml.load((ROOT / f'.github/workflows/{name}.yml').read_text(), Loader=yaml.BaseLoader)


def test_workflow_event_and_permission_boundaries():
    ci, release = workflow('ci'), workflow('release')
    assert {'push', 'pull_request', 'workflow_dispatch', 'workflow_call', 'schedule'} == ci['on'].keys()
    assert ci['on']['pull_request'] == '' and ci['on']['push'] == ''  # No path/branch filters, including docs-only PRs.
    assert ci['permissions'] == release['permissions'] == {'contents': 'read'}
    assert set(release['on']) == {'workflow_dispatch'}
    assert release['on']['workflow_dispatch']['inputs']['upload']['default'] == 'false'
    assert "github.ref == 'refs/heads/release/testpypi'" in release['jobs']['publish-testpypi']['if']
    for name, job in release['jobs'].items():
        if name.startswith('publish-'):
            assert job['permissions'] == {'contents': 'read', 'id-token': 'write'}
            assert job['environment']['name'] == name.removeprefix('publish-')
            assert 'inputs.upload' in job['if']
            assert not any('checkout' in step.get('uses', '') for step in job['steps'])
            assert any(step.get('with', {}).get('attestations') == 'true' for step in job['steps'])
        else:
            assert 'id-token' not in job.get('permissions', {})
    quality = '\n'.join(step.get('run', '') for step in ci['jobs']['quality']['steps'])
    assert 'bandit' in quality and 'sphinx-build -W --keep-going -E -a' in quality
    assert 'qualify.py qualify' in quality


@pytest.mark.parametrize('job', ['publish-testpypi', 'publish-pypi'])
def test_actual_publishing_job_verifier_rejects_changed_transferred_bytes(tmp_path, job):
    release = workflow('release')
    script = next(step['run'] for step in release['jobs'][job]['steps'] if 'run' in step)
    code = script.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    dist = tmp_path / 'bundle/dist'
    evidence = tmp_path / 'bundle/evidence'
    dist.mkdir(parents=True)
    evidence.mkdir()
    files = {f'sfdctrust-1.0.0{suffix}': b'approved bytes' for suffix in ('-py3-none-any.whl', '.tar.gz')}
    for name, data in files.items():
        (dist / name).write_bytes(data)
    manifest = {
        'source_commit': 'a' * 40,
        'source_status': '',
        'version': '1.0.0',
        'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()},
    }
    (evidence / 'release-manifest.json').write_text(json.dumps(manifest))
    env = {
        **os.environ,
        'APPROVED_SHA': 'a' * 40,
        'GITHUB_SHA': 'a' * 40,
        'APPROVED_VERSION': '1.0.0',
        'GITHUB_REF': 'refs/tags/1.0.0',
    }

    def execute():
        return subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path, env=env, capture_output=True, timeout=15)

    assert execute().returncode == 0
    next(dist.iterdir()).write_bytes(b'tampered bytes')
    assert execute().returncode != 0


def test_offline_guard_inherits_into_child_process(tmp_path):
    script = tmp_path / 'probe.py'
    script.write_text("""
import socket, subprocess, sys
try:
    socket.socket().connect(('192.0.2.1', 443))
except RuntimeError:
    pass
else:
    raise AssertionError('Parent guard missing')
child = subprocess.run([sys.executable, '-c', "import socket; socket.getaddrinfo('example.invalid', 443)"], capture_output=True)
assert child.returncode != 0 and b'DNS is disabled' in child.stderr
""")
    result = subprocess.run(
        [sys.executable, '-I', str(ROOT / 'tests/offline/run.py'), str(script)], capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr


def registry_tool(monkeypatch):
    pytest.importorskip('pypi_attestations')
    monkeypatch.syspath_prepend(str(ROOT / 'tools/ci'))
    return load('registry')


def test_registry_rejects_partial_upload_and_changed_digest(monkeypatch):
    registry = registry_tool(monkeypatch)
    manifest = {'files': {'sfdctrust-1.tar.gz': {'sha256': 'a' * 64, 'size': 3}}}
    file = {
        'filename': 'sfdctrust-1.tar.gz',
        'digests': {'sha256': 'a' * 64},
        'size': 3,
        'yanked': False,
        'url': 'https://test-files.pythonhosted.org/synthetic/sfdctrust-1.tar.gz',
    }
    assert registry.hosted_files({'urls': [file]}, manifest)[file['filename']] == file
    with pytest.raises(ValueError, match='partial'):
        registry.hosted_files({'urls': []}, manifest)
    with pytest.raises(ValueError, match='digest/size mismatch'):
        registry.hosted_files({'urls': [{**file, 'size': 4}]}, manifest)
    with pytest.raises(ValueError, match='file host'):
        registry.hosted_files({'urls': [{**file, 'url': 'https://example.invalid/artifact'}]}, manifest)


def test_registry_verifies_signed_identity_and_rejects_other_source(monkeypatch):
    registry = registry_tool(monkeypatch)
    publisher = registry.GitHubPublisher(repository='jeffshurtliff/sfdctrust', workflow='release.yml', environment='testpypi')
    ref = 'refs/heads/release/testpypi'
    claims = {
        f'1.3.6.1.4.1.57264.1.{key}': value
        for key, value in {
            '12': 'https://github.com/jeffshurtliff/sfdctrust',
            '13': 'a' * 40,
            '14': ref,
            '18': f'https://github.com/jeffshurtliff/sfdctrust/.github/workflows/release.yml@{ref}',
            '20': 'workflow_dispatch',
            '21': 'https://github.com/jeffshurtliff/sfdctrust/actions/runs/123/attempts/1',
        }.items()
    }
    verified = []

    def verify(identity, distribution):
        verified.append((identity, distribution))
        return registry.AttestationType.PYPI_PUBLISH_V1, {}

    attestation = SimpleNamespace(verify=verify, certificate_claims=claims)
    provenance = SimpleNamespace(attestation_bundles=[SimpleNamespace(publisher=publisher, attestations=[attestation])])
    distribution = registry.Distribution(name='sfdctrust-1.tar.gz', digest='b' * 64)
    checked = registry.provenance_identity(provenance, distribution, 'testpypi', 'a' * 40, ref, '123')
    assert len(checked) == 1 and verified == [(publisher, distribution)]
    for sha, expected_ref, run_id in [('c' * 40, ref, '123'), ('a' * 40, 'refs/heads/main', '123'), ('a' * 40, ref, '456')]:
        with pytest.raises(ValueError):
            registry.provenance_identity(provenance, distribution, 'testpypi', sha, expected_ref, run_id)
    with pytest.raises(ValueError, match='Unexpected or empty'):
        registry.provenance_identity(provenance, distribution, 'pypi', 'a' * 40, ref, '123')

    def invalid_signature(*args):
        raise ValueError('Invalid synthetic signature')

    attestation.verify = invalid_signature
    with pytest.raises(ValueError, match='Invalid synthetic signature'):
        registry.provenance_identity(provenance, distribution, 'testpypi', 'a' * 40, ref, '123')
