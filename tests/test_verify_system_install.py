import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_system_install', ROOT / 'scripts/verify_system_install.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def proofs(version='0.35.0'):
    source = 'a' * 40
    sha = 'b' * 64
    output = {'path': 'share/native-logs/oracle.log', 'sha256': 'c' * 64, 'size': 10}
    command = {'argv': ['python', '-m', 'pytest', 'native_oracles'], 'returncode': 0,
               'native_cases': 6, 'profiles': sorted(v.NATIVE_PROFILES), 'stdout': output, 'stderr': output}
    url = f'https://release.brewsterjennings.ca/ci-{version}/transfer-{"0" * 32}-fdisbull-{version}-{source}-chat-offline.zip'
    # Synthetic protocol records for rejection tests; no native execution claim.
    documents = {
        'ci': {'schema': 'fdisbull-ci-qualification-1', 'status': 'qualified', 'source_commit': source,
               'package_inventory': {'sha256': 'd' * 64}},
        'native': {'schema': 'fdisbull-macos-native-qualification-1', 'status': 'passed',
                   'source_commit': source, 'version': version, 'platform': 'darwin', 'architecture': 'arm64',
                   'backends': {'qemu': sha}, 'commands': [command],
                   'build_receipts': {'qemu': {'artifact_sha256': sha, 'upstream_sha256': 'e' * 64,
                                               'patch_sha256': None,
                                               'commands': [{'argv': ['ninja', '-j1'], 'returncode': 0}]}}},
        'release': {'schema': 'fdisbull-production-release-result-1', 'status': 'complete',
                    'source_sha': source, 'tag': 'v' + version,
                    'release_url': v.REPO + '/releases/tag/v' + version, 'download_url': url},
        'delivery': {'schema': 'fdisbull-cdn-delivery-1', 'status': 'passed', 'source_sha': source,
                     'sha256': sha, 'full_sha256': sha, 'resume_sha256': sha, 'size': 100, 'url': url},
    }
    return source, {'qemu': sha}, documents


@pytest.mark.parametrize('version', ['0.35.0', '0.36.1'])
def test_proof_contract_uses_candidate_version(version):
    source, backends, docs = proofs(version)
    assert v.validate_proofs(docs, version, source, backends) == docs


@pytest.mark.parametrize('mutation', [
    lambda d: d['ci'].update(source_commit='f' * 40),
    lambda d: d['native']['commands'][0].update(native_cases=0),
    lambda d: d['native']['commands'][0].update(returncode=1),
    lambda d: d['native']['commands'][0].pop('stdout'),
    lambda d: d['native']['commands'][0].update(profiles=['qemu-machine']),
    lambda d: d['native'].update(build_receipts={}),
    lambda d: d['native']['build_receipts']['qemu'].update(artifact_sha256='f' * 64),
    lambda d: d['delivery'].update(resume_sha256='f' * 64),
    lambda d: d['release'].update(release_url='https://github.com/other/repo/releases/tag/v0.35.0'),
    lambda d: d['release'].update(download_url='https://other.invalid/archive.zip'),
])
def test_incomplete_wrong_source_or_failed_qualification_is_rejected(mutation):
    source, backends, docs = proofs()
    mutation(docs)
    with pytest.raises(ValueError):
        v.validate_proofs(docs, '0.35.0', source, backends)


def test_disposable_prefix_hash_readback_rejects_changed_identity(tmp_path):
    prefix = tmp_path / 'prefix';prefix.mkdir()
    payload = prefix / 'backend';payload.write_bytes(b'authored test payload')
    ref = {'path': 'backend', 'size': payload.stat().st_size,
           'sha256': hashlib.sha256(payload.read_bytes()).hexdigest()}
    assert v.checked_ref(prefix, ref) == payload
    payload.write_bytes(b'changed bytes')
    with pytest.raises(ValueError, match='hash mismatch'):
        v.checked_ref(prefix, ref)


def test_native_qualification_binds_installed_guest_resources():
    source, backends, docs = proofs()
    resources = {'resources/kernel': 'e' * 64}
    docs['native']['resources'] = resources
    assert v.validate_proofs(docs, '0.35.0', source, backends, resources) == docs
    with pytest.raises(ValueError, match='resource hashes mismatch'):
        v.validate_proofs(docs, '0.35.0', source, backends, {'resources/kernel': 'f' * 64})


def test_payload_reference_cannot_escape_or_follow_symlinks(tmp_path):
    prefix = tmp_path / 'prefix';prefix.mkdir()
    outside = tmp_path / 'outside';outside.write_bytes(b'private')
    (prefix / 'linked').symlink_to(outside)
    for name in ('../outside', '/absolute', 'a/../outside', 'linked'):
        with pytest.raises(ValueError):
            v.relative(prefix, name)


def test_existing_checker_invocation_and_explicit_stage_flags_are_supported(tmp_path, monkeypatch, capsys):
    prefix = tmp_path / 'release'
    observed = []
    monkeypatch.setattr(v, 'verify_prefix', lambda p, m: observed.append((p, m)) or {'status': 'passed', 'active_default': False})
    assert v.main(['verify', '--prefix', str(prefix)]) == 0
    assert observed == [(prefix, prefix / 'share/install-manifest.json')]
    assert '"active_default": false' in capsys.readouterr().out


def test_tool_archive_selection_contains_installer_and_independent_verifier():
    spec = importlib.util.spec_from_file_location('install_release_builder', ROOT / 'scripts/build_release.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    files = {path.relative_to(ROOT).as_posix() for path in builder.release_files(ROOT)}
    assert {'scripts/install_system.py', 'scripts/verify_system_install.py', 'scripts/check_local_install.py'} <= files
