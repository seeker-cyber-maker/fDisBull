"""Explicit stable backend reuse must preserve provenance and fail closed."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('native_backend_reuse', Path(__file__).resolve().parents[1] / 'scripts/ci/native_backend_reuse.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


@pytest.fixture
def candidate(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    binary = b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x3e\x00' + b'authored-test-payload'
    (stage / 'dosbox-x').write_bytes(binary)
    manifest = {'baseline_commit': reuse.UPSTREAM, 'patch_sha256': 'a' * 64, 'source_files': []}
    old = json.dumps(manifest).encode()
    (stage / 'build-manifest.json').write_bytes(old)
    current = tmp_path / 'source-manifest.json'
    current.write_bytes(old)
    identity = {'source_commit': 'b' * 40, 'upstream_commit': reuse.UPSTREAM,
                'profile': 'experimental/dosbox-x', 'configure_flags': reuse.FLAGS[:],
                'patch_sha256': 'a' * 64, 'backend_sha256': hashlib.sha256(binary).hexdigest()}
    (stage / 'build-identity.json').write_text(json.dumps(identity))
    image = 'sha256:' + 'c' * 64
    (stage / 'build-process.json').write_text(json.dumps({'source_commit': 'b' * 40,
        'job_name': 'native-debugger-stable', 'execution_origin': 'local-linux', 'image_digest': image}))
    (stage / 'config.log').write_text('authored build log')
    return stage, current, image


def test_verification_preserves_actual_build_provenance(candidate):
    stage, current, image = candidate
    result = reuse.verify(stage, current, image)
    assert result['build_source_commit'] == 'b' * 40
    assert result['build_image_digest'] == image
    assert result['build_identity_sha256'] == hashlib.sha256((stage / 'build-identity.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('defect', ['binary', 'profile', 'manifest', 'image', 'flags', 'architecture'])
def test_reuse_rejects_changed_or_mismatched_build(candidate, defect):
    stage, current, image = candidate
    identity_path = stage / 'build-identity.json'
    identity = json.loads(identity_path.read_text())
    if defect == 'binary':
        (stage / 'dosbox-x').write_bytes(b'wrong')
    elif defect == 'profile':
        identity['profile'] = 'experimental/dosbox-x/layers'
    elif defect == 'manifest':
        current.write_bytes(current.read_bytes() + b' ')
    elif defect == 'image':
        image = 'sha256:' + 'd' * 64
    elif defect == 'flags':
        identity['configure_flags'] = identity['configure_flags'][:-1]
    else:
        binary = bytearray((stage / 'dosbox-x').read_bytes())
        binary[18:20] = b'\xb7\x00'
        (stage / 'dosbox-x').write_bytes(binary)
        identity['backend_sha256'] = hashlib.sha256(binary).hexdigest()
    identity_path.write_text(json.dumps(identity))
    with pytest.raises(ValueError):
        reuse.verify(stage, current, image)


def test_guest_export_retains_raw_build_receipt(candidate, tmp_path, monkeypatch):
    stage, current, image = candidate
    evidence, binary = tmp_path / 'evidence', tmp_path / 'result' / 'dosbox-x'
    raw = (stage / 'build-identity.json').read_bytes()
    monkeypatch.setattr(reuse.sys, 'argv', ['reuse', str(stage), str(current), image, str(evidence), str(binary)])
    reuse.main()
    assert (evidence / 'build-identity.json').read_bytes() == raw
    assert (evidence / 'build-process.json').read_bytes() == (stage / 'build-process.json').read_bytes()
    assert binary.read_bytes() == (stage / 'dosbox-x').read_bytes()
    provenance = json.loads((evidence / 'reuse-provenance.json').read_text())
    assert provenance['build_source_commit'] == 'b' * 40


def test_reused_identity_cannot_relabel_original_build(candidate):
    stage, current, image = candidate
    identity_path = stage / 'build-identity.json'
    identity = json.loads(identity_path.read_text())
    # A previous reuse labels its testing commit as source_commit, while the
    # actual compiler provenance remains in build_source_commit.
    identity.update(source_commit='d' * 40, build_source_commit='b' * 40,
                    build_identity_sha256='e' * 64, build_image_digest=image)
    identity_path.write_text(json.dumps(identity))
    process_path = stage / 'build-process.json'
    process = json.loads(process_path.read_text())
    process['source_commit'] = 'd' * 40
    process_path.write_text(json.dumps(process))
    with pytest.raises(ValueError, match='Original compiled build evidence required'):
        reuse.verify(stage, current, image)
