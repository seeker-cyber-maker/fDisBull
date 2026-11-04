"""Original build evidence must be present before any reuse can be considered."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('unified_base_reuse', ROOT / 'scripts/ci/unified-base-reuse.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_missing_original_process_is_rejected(tmp_path):
    export = tmp_path / 'unified-prepare/guest-data/exported'
    export.mkdir(parents=True)
    with pytest.raises(ValueError, match='original unified build evidence'):
        module.validate(export, ROOT, 'sha256:' + 'a' * 64)


def test_failed_original_process_is_rejected_before_loading_any_runtime(tmp_path):
    phase = tmp_path / 'unified-prepare'
    export = phase / 'guest-data/exported'
    export.mkdir(parents=True)
    source = phase / 'work'
    source.mkdir()
    sha = 'a' * 40
    job = 'd0c36dcb-43d6-457c-889e-c97a0e82d6dd'
    run = '27680f97-aaad-4846-a2fd-4a48b7bad36b'
    process = {'source_commit': sha, 'local_run_id': run, 'local_job_id': job,
               'execution_origin': 'local-linux', 'job_name': 'native-unified-prepare',
               'exit_code': 1, 'termination': 'exited', 'container_state_after_stop': 'stopped',
               'image_digest': 'sha256:' + 'a' * 64,
               'runtime': {'machine': 'x86_64', 'system': 'linux', 'python': '3.12.7'}}
    (phase / 'process.json').write_text(json.dumps(process))
    (phase / 'completed.json').write_text(json.dumps({'local_job_id': job, 'source_commit': sha}))
    (phase / 'guest-data/source-postcheck.json').write_text(json.dumps({'source_commit': sha,
        'expected_source_commit': sha, 'tracked_worktree_dirty': False, 'export_success': True}))
    with pytest.raises(ValueError, match='did not complete'):
        module.validate(export, ROOT, process['image_digest'])


def test_reuse_marker_cannot_omit_raw_proofs(tmp_path):
    (tmp_path / 'origin.json').write_text(json.dumps({'schema': 'fdisbull-unified-base-origin-v1', 'files': {}}))
    with pytest.raises(ValueError, match='Invalid unified reuse origin'):
        module.verify_reuse(tmp_path, ROOT)


def valid_staged_origin(path):
    import shutil
    sha = 'a' * 40
    run = '27680f97-aaad-4846-a2fd-4a48b7bad36b'
    job = 'd0c36dcb-43d6-457c-889e-c97a0e82d6dd'
    image = 'sha256:' + 'a' * 64
    def put(name, value):
        (path / name).write_text(json.dumps(value))
    process = {'source_commit': sha, 'local_run_id': run, 'local_job_id': job,
               'execution_origin': 'local-linux', 'job_name': 'native-unified-prepare',
               'exit_code': 0, 'termination': 'exited', 'container_state_after_stop': 'stopped',
               'image_digest': image, 'runtime': {'machine': 'x86_64', 'system': 'linux', 'python': '3.12.7'}}
    put('process.json', process)
    put('completed.json', {'source_commit': sha, 'local_job_id': job})
    put('source-postcheck.json', {'source_commit': sha, 'expected_source_commit': sha,
                                 'tracked_worktree_dirty': False, 'export_success': True})
    put('host-source-postcheck.json', {'source_commit': sha, 'tracked_worktree_dirty': False,
                                      'method': 'host-git-frozen-source-before-staging'})
    for dest, source in [('old-native-unified.sh', 'scripts/ci/native-unified.sh'),
                         ('old-Containerfile', 'experimental/wine/ci/Containerfile'),
                         ('old-build_runtime.py', 'experimental/wine/ci/build_runtime.py')]:
        shutil.copy2(ROOT / source, path / dest)
    mapping = {'FDISBULL_PE_QEMU': 'qemu', 'FDISBULL_PE_KERNEL': 'kernel',
               'FDISBULL_PE_FIXTURE': 'oracle', 'FDISBULL_PE_INITRAMFS': 'wine-base'}
    inputs = {}
    for key, name in mapping.items():
        (path / name).write_bytes(name.encode())
        inputs[key] = {'sha256': module.digest(path / name), 'size': (path / name).stat().st_size}
    for key, content in [('FDISBULL_DOSBOX', b'original dosbox'), ('FDISBULL_DOS_INITRAMFS', b'original dos runtime')]:
        import hashlib
        inputs[key] = {'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content)}
    put('backend-identity.json', {'source_commit': sha, 'inputs': inputs})
    (path / 'wine-packages.txt').write_text('wine package fixture\n')
    for name in ('wine-preparation.json', 'dos-preparation.json'):
        put(name, {'runtime_sha256': 'b' * 64})
    firmware = path / 'firmware'
    firmware.mkdir()
    for i in range(171):
        (firmware / str(i)).write_text(str(i))
    fw = {'firmware/' + p.name: module.digest(p) for p in firmware.iterdir()}
    manifest = {'schema': 'fdisbull-unified-runtime-inputs-1', 'source_commit': sha, 'local_run_id': run, 'build_job_id': job, 'inputs': inputs,
                'backend_identity': {'sha256': module.digest(path / 'backend-identity.json'),
                                     'size': (path / 'backend-identity.json').stat().st_size},
                'resource_receipts': {kind: {'sha256': module.digest(path / name), 'size': (path / name).stat().st_size}
                    for kind, name in [('wine', 'wine-preparation.json'), ('dos', 'dos-preparation.json')]},
                'firmware': [{'path': 'native-evidence/pe/' + name, 'sha256': digest} for name, digest in fw.items()]}
    put('prepared-inputs.json', manifest)
    files = {p.name: module.digest(p) for p in path.iterdir() if p.is_file()}
    origin = {'schema': 'fdisbull-unified-base-origin-v1', 'source_commit': sha, 'local_run_id': run,
              'local_job_id': job, 'image_digest': image, 'files': files, 'firmware': fw,
              'process_sha256': files['process.json'], 'completed_sha256': files['completed.json'],
              'source_postcheck_sha256': files['source-postcheck.json'],
              'prepared_inputs_sha256': files['prepared-inputs.json']}
    put('origin.json', origin)
    return origin


def test_reuse_rejects_contradictory_top_level_proof(tmp_path):
    origin = valid_staged_origin(tmp_path)
    assert module.verify_reuse(tmp_path, ROOT) == origin
    origin['process_sha256'] = 'b' * 64
    (tmp_path / 'origin.json').write_text(json.dumps(origin))
    with pytest.raises(ValueError, match='top-level proof'):
        module.verify_reuse(tmp_path, ROOT)


def test_reuse_rejects_original_identity_from_another_source(tmp_path):
    origin = valid_staged_origin(tmp_path)
    identity = json.loads((tmp_path / 'backend-identity.json').read_text())
    identity['source_commit'] = 'b' * 40
    (tmp_path / 'backend-identity.json').write_text(json.dumps(identity))
    origin['files']['backend-identity.json'] = module.digest(tmp_path / 'backend-identity.json')
    manifest = json.loads((tmp_path / 'prepared-inputs.json').read_text())
    manifest['backend_identity'].update(sha256=origin['files']['backend-identity.json'],
                                        size=(tmp_path / 'backend-identity.json').stat().st_size)
    (tmp_path / 'prepared-inputs.json').write_text(json.dumps(manifest))
    origin['files']['prepared-inputs.json'] = module.digest(tmp_path / 'prepared-inputs.json')
    origin['prepared_inputs_sha256'] = origin['files']['prepared-inputs.json']
    (tmp_path / 'origin.json').write_text(json.dumps(origin))
    with pytest.raises(ValueError, match='backend identity'):
        module.verify_reuse(tmp_path, ROOT)


def test_reuse_rejects_missing_original_dos_input(tmp_path):
    origin = valid_staged_origin(tmp_path)
    manifest = json.loads((tmp_path / 'prepared-inputs.json').read_text())
    del manifest['inputs']['FDISBULL_DOSBOX']
    (tmp_path / 'prepared-inputs.json').write_text(json.dumps(manifest))
    origin['files']['prepared-inputs.json'] = module.digest(tmp_path / 'prepared-inputs.json')
    origin['prepared_inputs_sha256'] = origin['files']['prepared-inputs.json']
    (tmp_path / 'origin.json').write_text(json.dumps(origin))
    with pytest.raises(ValueError, match='Incomplete original unified input manifest'):
        module.verify_reuse(tmp_path, ROOT)


def test_reuse_preserves_and_requires_original_wine_package_inventory(tmp_path):
    origin = valid_staged_origin(tmp_path)
    assert origin['files']['wine-packages.txt'] == module.digest(tmp_path / 'wine-packages.txt')
    assert module.verify_reuse(tmp_path, ROOT) == origin
    script = (ROOT / 'scripts/ci/native-unified-reuse.sh').read_text()
    assert 'cp .native/reuse-unified/wine-packages.txt native-evidence/pe/runtime-packages.txt' in script
    (tmp_path / 'wine-packages.txt').write_text('altered package inventory')
    with pytest.raises(ValueError, match='original proof or input changed'):
        module.verify_reuse(tmp_path, ROOT)
    (tmp_path / 'wine-packages.txt').unlink()
    with pytest.raises(ValueError, match='original unified build evidence'):
        module.verify_reuse(tmp_path, ROOT)
