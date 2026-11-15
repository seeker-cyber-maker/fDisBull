"""Release qualification must retain absent/failed/wrong-source evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('qualification', Path(__file__).parents[1] / 'scripts/check_ci_qualification.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = 'a' * 40


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def qualified(tmp_path):
    for index, (profile, job) in enumerate(gate.JOBS.items(), 1):
        for name in gate.JUNIT[profile]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            skipped = '1' if profile == 'ordinary' else '0'
            count = 26 if name.endswith('required-contracts.xml') else 2
            if name.endswith('required-contracts.xml'): skipped = '0'
            p.write_text(f'<testsuites><testsuite tests="{count}" failures="0" errors="0" skipped="{skipped}"/></testsuites>')
        artifact = tmp_path / f'backend-{profile}'
        artifact.write_bytes(b'authored fixture')
        receipt = {'status': 'passed', 'source_commit': SHA, 'pipeline_id': '123', 'job_id': str(index),
                   'job_name': job, 'profile': profile, 'python_version': '3.13.5' if profile == 'layers' else '3.12.12',
                   'node_version': 'v22.23.4',
                   'test_results': [gate.identity(tmp_path, name) for name in gate.JUNIT[profile]],
                   'artifacts': [gate.identity(tmp_path, artifact.name)], 'backend_identity': {'source_commit': SHA}}
        if profile == 'unified':
            receipt['artifacts'] = [gate.identity(tmp_path, 'dist/fdisbull-test.whl')]
        if profile == 'ordinary':
            receipt['artifacts'] = []
            packages = {}
            for kind, name in [('core', 'fdisbull-test.whl'), ('player', 'player.whl'), ('sdist', 'source.tar.gz'), ('tool', 'tool.zip')]:
                dest = tmp_path / 'dist' / name
                dest.parent.mkdir(exist_ok=True)
                dest.write_bytes(kind.encode())
                item = gate.identity(tmp_path, 'dist/' + name)
                receipt['artifacts'].append(item)
                packages[kind] = {'name': name, 'sha256': item['sha256'], 'size_bytes': item['size']}
            write(tmp_path, 'artifacts/receipts/package-payloads.json', {'source_commit': SHA, 'tracked_worktree_dirty': False, 'artifacts': packages})
        filename = 'ordinary' if profile == 'ordinary' else 'native-' + profile
        write(tmp_path, f'artifacts/receipts/{filename}.json', receipt)
    return tmp_path


def test_complete_same_pipeline_and_source_qualifies_without_authorizing_release(qualified):
    result = gate.validate(qualified, SHA, '123', legacy_dos_only=True)
    assert result['status'] == 'legacy-dos-only'
    assert set(result['required_jobs']) == set(gate.JOBS.values())
    assert result['release_authorized'] is False


@pytest.mark.parametrize('field,value', [('status', 'manual'), ('status', 'skipped'), ('status', 'failed'),
                                        ('source_commit', 'b' * 40), ('pipeline_id', '999'),
                                        ('python_version', '3.12.12'), ('node_version', 'v18.20.4'), ('job_name', 'other')])
def test_partial_or_different_run_never_qualifies(qualified, field, value):
    path = qualified / 'artifacts/receipts/native-layers.json'
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        gate.validate(qualified, SHA, '123')


def test_missing_job_capture_is_incomplete(qualified):
    (qualified / 'artifacts/receipts/native-stable.json').rename(qualified / 'not-a-receipt.json')
    with pytest.raises(ValueError, match='Missing'):
        gate.validate(qualified, SHA, '123')


def test_changed_package_and_dirty_inventory_are_rejected(qualified):
    path = qualified / 'artifacts/receipts/package-payloads.json'
    receipt = json.loads(path.read_text())
    receipt['tracked_worktree_dirty'] = True
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='dirty'):
        gate.validate(qualified, SHA, '123')
    receipt['tracked_worktree_dirty'] = False
    path.write_text(json.dumps(receipt))
    (qualified / 'dist/fdisbull-test.whl').write_bytes(b'replaced')
    with pytest.raises(ValueError, match='identity mismatch'):
        gate.validate(qualified, SHA, '123')


def test_empty_or_failed_junit_cannot_be_rescued_by_success_status(qualified):
    path = qualified / 'native-evidence/stable/tests.xml'
    receipt_path = qualified / 'artifacts/receipts/native-stable.json'
    for attrs in ['tests="0"', 'tests="2" skipped="2"', 'tests="2" errors="1"', 'tests="2" skipped="1"']:
        path.write_text(f'<testsuites><testsuite {attrs}/></testsuites>')
        receipt = json.loads(receipt_path.read_text())
        receipt['test_results'] = [gate.identity(qualified, 'native-evidence/stable/tests.xml')]
        receipt_path.write_text(json.dumps(receipt))
        with pytest.raises(ValueError, match='skipped tests'):
            gate.validate(qualified, SHA, '123')


def test_artifact_path_cannot_escape_the_qualified_workspace(qualified):
    with pytest.raises(ValueError, match='Unsafe'):
        gate.local_path(qualified, '../unrelated')


def test_duplicate_pe_capture_cannot_stand_in_for_boot_acceptance(qualified):
    p = qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(p.read_text())
    receipt['test_results'][1] = receipt['test_results'][0]
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='captures absent'):
        gate.validate(qualified, SHA, '123')

LOCAL_RUN = 'b4f5594b-2d10-4f1a-bd00-e25412e0f851'


@pytest.fixture
def local_qualified(qualified, monkeypatch):
    for index, (profile, job) in enumerate(gate.JOBS.items(), 1):
        filename = 'ordinary' if profile == 'ordinary' else 'native-' + profile
        p = qualified / f'artifacts/receipts/{filename}.json'
        receipt = json.loads(p.read_text())
        receipt.pop('pipeline_id')
        receipt.pop('job_id')
        job_id = f'00000000-0000-4000-8000-{index:012d}'
        receipt.update(execution_origin='local-linux', local_run_id=LOCAL_RUN, local_job_id=job_id)
        p.write_text(json.dumps(receipt))
        write(qualified, f'artifacts/receipts/local-process-{profile}.json',
              {'execution_origin': 'local-linux', 'local_run_id': LOCAL_RUN, 'local_job_id': job_id,
               'job_name': job, 'source_commit': SHA, 'termination': 'exited', 'exit_code': 0,
               'image_digest': 'sha256:' + 'b' * 64, 'container_state_after_stop': 'stopped',
               'runtime': {'system': 'linux', 'machine': 'x86_64',
                           'python': '3.13.5' if profile == 'layers' else '3.12.12'}})
    # Exercise the real runtime manifest producer and verifier, including the
    # complete firmware set, rather than substituting a mock verifier.
    import hashlib
    monkeypatch.chdir(qualified)
    spec = importlib.util.spec_from_file_location('fixture_runtime_inputs', Path(__file__).parents[1] / 'scripts/ci/unified-runtime-inputs.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    build_job = '00000000-0000-4000-8000-000000000009'
    monkeypatch.setenv('FDISBULL_EXECUTION_ORIGIN', 'local-linux')
    monkeypatch.setenv('CI_COMMIT_SHA', SHA)
    monkeypatch.setenv('FDISBULL_LOCAL_RUN_ID', LOCAL_RUN)
    monkeypatch.setenv('FDISBULL_LOCAL_JOB_ID', build_job)
    identity = {'source_commit': SHA, 'inputs': {}}
    for key, name in runtime.INPUT_PATHS.items():
        path = qualified / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('input-' + key).encode())
        monkeypatch.setenv(key, str(path))
        identity['inputs'][key] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}
    wheel = qualified / 'dist/fdisbull-test.whl'
    installed_wheel = qualified / '.native/pe/packages/fdisbull-test.whl'
    installed_wheel.parent.mkdir(parents=True, exist_ok=True)
    installed_wheel.write_bytes(wheel.read_bytes())
    identity['wheel'] = {'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'size': wheel.stat().st_size}
    pe = qualified / 'native-evidence/pe'
    (pe / 'backend-identity.json').write_text(json.dumps(identity))
    bios = qualified / '.native/pe/qemu-9.2.4/pc-bios'
    bios.mkdir(parents=True)
    for name in ('bios-256k.bin', 'vgabios-stdvga.bin', *(f'fixture-{i:03d}.bin' for i in range(169))):
        (bios / name).write_bytes(name.encode())
    for kind, mapping in runtime.RESOURCES.items():
        resources = {}
        for guest, name in mapping.items():
            path = qualified / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            resources[guest] = hashlib.sha256(path.read_bytes()).hexdigest()
        if kind == 'dos':
            resources['opt/fdisbull/dosbox-x'] = identity['inputs']['FDISBULL_DOSBOX']['sha256']
        name = 'runtime-preparation.json' if kind == 'wine' else 'dos-runtime-preparation.json'
        key = 'FDISBULL_PE_INITRAMFS' if kind == 'wine' else 'FDISBULL_DOS_INITRAMFS'
        (pe / name).write_text(json.dumps({'resources': resources, 'runtime_sha256': identity['inputs'][key]['sha256']}))
    runtime.prepare()
    prepared = json.loads((pe / 'prepared-inputs.json').read_text())
    path = qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(path.read_text())
    receipt.update(backend_identity=identity, prepared_manifest=gate.identity(qualified, 'native-evidence/pe/prepared-inputs.json'),
                   runtime_inputs=list(prepared['inputs'].values()), firmware=prepared['firmware'],
                   resource_receipts=list(prepared['resource_receipts'].values()),
                   artifacts=[prepared['tested_wheel'], *prepared['inputs'].values()])
    path.write_text(json.dumps(receipt))
    acceptance_process = json.loads((qualified / 'artifacts/receipts/local-process-unified.json').read_text())
    preparation_process = dict(acceptance_process, local_job_id=build_job, job_name='native-unified-prepare')
    write(qualified, 'native-evidence/pe/preparation-process.json', preparation_process)
    write(qualified, 'native-evidence/pe/preparation-source-postcheck.json',
          {'source_commit': SHA, 'expected_source_commit': SHA, 'tracked_worktree_dirty': False, 'export_success': True})
    write(qualified, 'native-evidence/pe/preparation-completed.json',
          {'source_commit': SHA, 'local_job_id': build_job, 'completed_at': '2026-11-03T12:00:00Z'})
    return qualified


def test_local_run_qualifies_without_claiming_gitlab(local_qualified):
    result = gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN, legacy_dos_only=True)
    assert result['status'] == 'legacy-dos-only'
    assert result['execution_origin'] == 'local-linux'
    assert result['local_run_id'] == LOCAL_RUN
    assert 'pipeline_id' not in result
    assert all('process_receipt' in job for job in result['required_jobs'].values())


@pytest.mark.parametrize('field,value', [('exit_code', 1), ('exit_code', None), ('exit_code', False),
                                        ('termination', 'signaled'), ('image_digest', 'python:3.12'),
                                        ('local_run_id', 'other'), ('local_job_id', None)])
def test_local_failed_or_incomplete_host_process_is_rejected(local_qualified, field, value):
    p = local_qualified / 'artifacts/receipts/local-process-layers.json'
    data = json.loads(p.read_text())
    data[field] = value
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_local_missing_host_process_is_rejected(local_qualified):
    (local_qualified / 'artifacts/receipts/local-process-stable.json').unlink()
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_mixed_origin_cannot_qualify(local_qualified):
    p = local_qualified / 'artifacts/receipts/native-stable.json'
    data = json.loads(p.read_text())
    data['pipeline_id'] = '123'
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, '123')


def test_local_duplicate_job_or_invalid_run_cannot_qualify(local_qualified):
    p = local_qualified / 'artifacts/receipts/native-stable.json'
    data = json.loads(p.read_text())
    data['local_job_id'] = '00000000-0000-4000-8000-000000000001'
    p.write_text(json.dumps(data))
    process = local_qualified / 'artifacts/receipts/local-process-stable.json'
    proof = json.loads(process.read_text())
    proof['local_job_id'] = data['local_job_id']
    process.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match='Duplicate'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id='not-a-uuid')


def test_local_ordinary_writer_uses_local_identity_without_provider_ids(qualified, monkeypatch):
    monkeypatch.setenv('CI_COMMIT_SHA', SHA)
    monkeypatch.setenv('CI_JOB_NAME', 'test-and-package')
    monkeypatch.setenv('FDISBULL_EXECUTION_ORIGIN', 'local-linux')
    monkeypatch.setenv('FDISBULL_LOCAL_RUN_ID', LOCAL_RUN)
    monkeypatch.setenv('FDISBULL_LOCAL_JOB_ID', '00000000-0000-4000-8000-000000000001')
    monkeypatch.setattr(gate.subprocess, 'check_output', lambda *a, **k: 'v22.23.4\n')
    receipt = gate.write_ordinary(qualified)
    assert receipt['execution_origin'] == 'local-linux'
    assert receipt['local_run_id'] == LOCAL_RUN
    assert 'pipeline_id' not in receipt and 'job_id' not in receipt


@pytest.mark.parametrize('field,value', [
    ('runtime', None),
    ('runtime', {'system': 'darwin', 'machine': 'x86_64', 'python': '3.13.5'}),
    ('runtime', {'system': 'linux', 'machine': 'arm64', 'python': '3.13.5'}),
    ('runtime', {'system': 'linux', 'machine': 'x86_64', 'python': '3.13.4'}),
    ('runtime', {'system': 'linux', 'machine': 'x86_64'}),
    ('container_state_after_stop', None),
    ('container_state_after_stop', 'running'),
    ('container_state_after_stop', 'unknown'),
])
def test_local_guest_runtime_and_stopped_state_required(local_qualified, field, value):
    p = local_qualified / 'artifacts/receipts/local-process-layers.json'
    data = json.loads(p.read_text())
    data[field] = value
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='local process evidence'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def add_reused_backend(root, profile):
    receipt_path = root / f'artifacts/receipts/native-{profile}.json'
    receipt = json.loads(receipt_path.read_text())
    binary = root / f'.native/backends/{profile}/dosbox-x'
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists():
        binary.write_bytes(b'authored backend bytes')
    binary_item = gate.identity(root, str(binary.relative_to(root)))
    receipt['artifacts'].append(binary_item)
    build_sha = 'd' * 40
    image = 'sha256:' + 'b' * 64
    selected = 'experimental/dosbox-x' + ('/layers' if profile == 'layers' else '')
    original = {'source_commit': build_sha, 'profile': selected, 'upstream_commit': 'e' * 40,
                'patch_sha256': 'f' * 64, 'configure_flags': ['authored build flags'],
                'backend_sha256': binary_item['sha256']}
    prior = {'source_commit': build_sha, 'execution_origin': 'local-linux',
             'job_name': gate.JOBS[profile], 'image_digest': image}
    manifest = {'baseline_commit': original['upstream_commit'], 'patch_sha256': original['patch_sha256']}
    base = f'native-evidence/{profile}/'
    write(root, base + 'build-identity.json', original)
    write(root, base + 'build-process.json', prior)
    write(root, base + 'build-manifest.json', manifest)
    (root / base / 'config.log').write_text('authored compiler configuration')
    backend = dict(original, source_commit=SHA, build_source_commit=build_sha, build_image_digest=image)
    for field, name in gate.REUSE_FILES.items():
        backend[field] = gate.identity(root, base + name)['sha256']
    receipt['backend_identity'] = backend
    receipt_path.write_text(json.dumps(receipt))
    return receipt_path


@pytest.mark.parametrize('profile', ['stable', 'layers'])
def test_local_reuse_retains_independently_checked_build_evidence(local_qualified, profile):
    add_reused_backend(local_qualified, profile)
    result = gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN, legacy_dos_only=True)
    proof = result['required_jobs'][gate.JOBS[profile]]['build_provenance']
    assert set(proof) == set(gate.REUSE_FILES.values())
    assert proof['build-identity.json'] == gate.identity(local_qualified, f'native-evidence/{profile}/build-identity.json')


@pytest.mark.parametrize('filename', list(gate.REUSE_FILES.values()))
@pytest.mark.parametrize('missing', [False, True])
def test_local_reuse_rejects_missing_or_tampered_raw_build_provenance(local_qualified, filename, missing):
    add_reused_backend(local_qualified, 'stable')
    path = local_qualified / 'native-evidence/stable' / filename
    if missing:
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_local_reuse_rejects_mismatched_current_job_image(local_qualified):
    add_reused_backend(local_qualified, 'layers')
    path = local_qualified / 'artifacts/receipts/local-process-layers.json'
    process = json.loads(path.read_text())
    process['image_digest'] = 'sha256:' + 'c' * 64
    path.write_text(json.dumps(process))
    with pytest.raises(ValueError, match='image mismatch'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_local_reuse_rejects_binary_or_source_relabel(local_qualified):
    path = add_reused_backend(local_qualified, 'stable')
    receipt = json.loads(path.read_text())
    receipt['backend_identity']['build_source_commit'] = 'c' * 40
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='build source'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)
    receipt['backend_identity']['build_source_commit'] = 'd' * 40
    receipt['backend_identity']['backend_sha256'] = '1' * 64
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='binary identity'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('profile', ['stable', 'layers'])
@pytest.mark.parametrize('indicator', ['reuse-provenance.json', 'build-identity.json',
                                       'build-process.json', 'build-manifest.json'])
def test_reuse_cannot_be_relabelled_fresh_by_dropping_all_build_fields(local_qualified, profile, indicator):
    path = add_reused_backend(local_qualified, profile)
    receipt = json.loads(path.read_text())
    backend = receipt['backend_identity']
    marker = {field: backend[field] for field in gate.REUSE_FIELDS}
    for field in gate.REUSE_FIELDS:
        backend.pop(field)
    path.write_text(json.dumps(receipt))
    base = local_qualified / f'native-evidence/{profile}'
    # Keep exactly one reuse indicator to show each independently triggers the gate.
    for name in ('build-identity.json', 'build-process.json', 'build-manifest.json'):
        if name != indicator:
            (base / name).unlink()
    if indicator == 'reuse-provenance.json':
        (base / indicator).write_text(json.dumps(marker))
    with pytest.raises(ValueError, match='provenance is incomplete'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('profile', ['stable', 'layers'])
def test_reuse_provenance_marker_is_validated_when_present(local_qualified, profile):
    path = add_reused_backend(local_qualified, profile)
    backend = json.loads(path.read_text())['backend_identity']
    marker = local_qualified / f'native-evidence/{profile}/reuse-provenance.json'
    marker.write_text(json.dumps({field: backend[field] for field in gate.REUSE_FIELDS}))
    result = gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN, legacy_dos_only=True)
    assert 'reuse-provenance.json' in result['required_jobs'][gate.JOBS[profile]]['build_provenance']
    data = json.loads(marker.read_text())
    data['build_source_commit'] = '9' * 40
    marker.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='marker mismatch'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)
    marker.unlink()
    marker.symlink_to(local_qualified / 'missing-target')
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_fresh_build_config_log_does_not_imply_reuse(local_qualified):
    path = local_qualified / 'native-evidence/stable/config.log'
    path.write_text('fresh compiler configuration')
    assert gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN, legacy_dos_only=True)['status'] == 'legacy-dos-only'


@pytest.mark.parametrize('field', ['prepared_manifest', 'runtime_inputs', 'resource_receipts', 'firmware'])
def test_local_unified_requires_every_prepared_capture(local_qualified, field):
    path = local_qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(path.read_text())
    receipt.pop(field)
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('name', ['process', 'source-postcheck', 'completed'])
def test_local_unified_missing_preparation_proof_fails(local_qualified, name):
    (local_qualified / f'native-evidence/pe/preparation-{name}.json').unlink()
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('field,value', [
    ('source_commit', 'b' * 40), ('local_run_id', 'b4f5594b-2d10-4f1a-bd00-e25412e0f852'),
    ('job_name', 'native-unified'), ('exit_code', 1), ('exit_code', False),
    ('termination', 'interrupted'), ('container_state_after_stop', 'running'),
    ('image_digest', 'sha256:' + 'c' * 64),
    ('runtime', {'system': 'linux', 'machine': 'arm64', 'python': '3.12.12'}),
])
def test_local_unified_rejects_bad_preparation_process(local_qualified, field, value):
    path = local_qualified / 'native-evidence/pe/preparation-process.json'
    process = json.loads(path.read_text())
    process[field] = value
    path.write_text(json.dumps(process))
    with pytest.raises(ValueError, match='preparation process'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('name,field,value', [
    ('source-postcheck', 'tracked_worktree_dirty', True), ('source-postcheck', 'export_success', False),
    ('source-postcheck', 'source_commit', 'b' * 40), ('completed', 'source_commit', 'b' * 40),
    ('completed', 'local_job_id', '00000000-0000-4000-8000-000000000004'),
    ('completed', 'completed_at', ''),
])
def test_local_unified_rejects_bad_preparation_completion(local_qualified, name, field, value):
    path = local_qualified / f'native-evidence/pe/preparation-{name}.json'
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('path', [
    '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
    'native-evidence/pe/firmware/bios-256k.bin',
    'native-evidence/pe/runtime-preparation.json',
])
def test_local_unified_rehashes_actual_prepared_inputs(local_qualified, path):
    p = local_qualified / path
    p.write_bytes(p.read_bytes() + b'changed')
    with pytest.raises(ValueError):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_local_unified_rejects_duplicate_prepare_job_id(local_qualified):
    path = local_qualified / 'native-evidence/pe/prepared-inputs.json'
    data = json.loads(path.read_text())
    data['build_job_id'] = '00000000-0000-4000-8000-000000000001'
    path.write_text(json.dumps(data))
    receipt_path = local_qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['prepared_manifest'] = gate.identity(local_qualified, str(path.relative_to(local_qualified)))
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='duplicates'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_local_unified_cannot_replace_input_list_in_acceptance_receipt(local_qualified):
    path = local_qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(path.read_text())
    receipt['runtime_inputs'] = receipt['runtime_inputs'][:-1]
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='does not match prepared'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.fixture
def chat_qualified(local_qualified):
    import hashlib
    import zipfile
    root = local_qualified
    packages = json.loads((root / 'artifacts/receipts/package-payloads.json').read_text())['artifacts']
    manifest = {'identities':{'source_commit':SHA,'test_source_commit':SHA},
                'wheel_artifacts':[{'name':packages[k]['name'],'sha256':packages[k]['sha256'],'size':packages[k]['size_bytes']} for k in ('core','player')]}
    data=json.dumps(manifest).encode()
    archive=root/'.native/chat/output/fdisbull-chat-offline.zip';archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive,'w') as z:z.writestr('fdisbull-chat-offline/MANIFEST.json',data)
    archive_ref=gate.identity(root,str(archive.relative_to(root)))
    verifier={'schema':'fdisbull-chat-consumer-verification-v1','status':'passed','source_commit':SHA,'test_source_commit':SHA,
              'archive_sha256':archive_ref['sha256'],'manifest_sha256':hashlib.sha256(data).hexdigest(),
              'python':'3.13.5','network_interfaces':['lo'],'python_origin':'kit','python_mappings':'kit',
              'loader_closure':'kit-lib','elf_objects_checked':2,'skipped':0,'native_failures':0,
              'profiles':['dos','wine','player','z3'],'checks':{name:True for name in gate.CHAT_CHECKS},
              'runtime_sha256':{'dos':'a'*64,'wine':'b'*64,'windows':'e'*64},'dos_screenshot_sha256':'c'*64,'pe_screenshot_sha256':'d'*64}
    write(root,'native-evidence/chat/acceptance.json',verifier)
    verifier_ref=gate.identity(root,'native-evidence/chat/acceptance.json')
    producer='00000000-0000-4000-8000-000000000010';consumer='00000000-0000-4000-8000-000000000011'
    common={'execution_origin':'local-linux','source_commit':SHA,'local_run_id':LOCAL_RUN,'status':'passed',
            'test_source_commit':SHA,'archive':archive_ref,'tracked_worktree_dirty':False,'export_success':True}
    write(root,'artifacts/receipts/chat-prepare.json',dict(common,schema='fdisbull-chat-prepare-job-v1',local_job_id=producer,tracked_worktree_dirty=False,export_success=True))
    write(root,'native-evidence/chat/host-source-postcheck.json',{'schema':'fdisbull-chat-host-source-postcheck-v1','source_commit':SHA,'expected_source_commit':SHA,'tracked_worktree_dirty':False,'export_success':True,'archive_sha256':archive_ref['sha256']})
    postcheck_ref=gate.identity(root,'native-evidence/chat/host-source-postcheck.json')
    junit=root/'native-evidence/chat/tests.xml';junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"/>')
    junit_ref=gate.identity(root,'native-evidence/chat/tests.xml')
    write(root,'artifacts/receipts/chat-consumer.json',dict(common,schema='fdisbull-chat-consumer-job-v1',local_job_id=consumer,producer_job_id=producer,verifier=verifier_ref,source_access='absent',source_check='artifact-and-host-clone',host_source_postcheck=postcheck_ref,junit=junit_ref))
    for name, jobid, jobname in [('prepare',producer,'native-chat-prepare'),('consumer',consumer,'native-chat-consumer')]:
        process={'execution_origin':'local-linux','source_commit':SHA,'local_run_id':LOCAL_RUN,'local_job_id':jobid,
                 'job_name':jobname,'termination':'exited','exit_code':0,'container_state_after_stop':'stopped',
                 'image_digest':'sha256:'+'b'*64,'runtime':{'system':'linux','machine':'x86_64','python':'3.13.5'},'archive':archive_ref}
        if name == 'consumer':process.update(verifier=verifier_ref,host_source_postcheck=postcheck_ref,junit=junit_ref)
        write(root,'artifacts/receipts/local-process-chat-'+name+'.json',process)
    return root


def test_chat_consumer_required_for_final_qualification(local_qualified):
    with pytest.raises(ValueError, match='chat-prepare'):
        gate.validate(local_qualified, SHA, local_run_id=LOCAL_RUN)


def test_chat_consumer_qualifies_when_all_receipts_match(chat_qualified):
    result=gate.validate(chat_qualified,SHA,local_run_id=LOCAL_RUN)
    assert result['status']=='qualified' and result['chat_consumer']['archive']['size'] > 0


@pytest.mark.parametrize('kind', ['prepare', 'consumer'])
def test_chat_rejects_invented_reordered_process_job_names(chat_qualified, kind):
    path = chat_qualified / f'artifacts/receipts/local-process-chat-{kind}.json'
    data = json.loads(path.read_text())
    data['job_name'] = f'chat-native-{kind}'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='process evidence failed'):
        gate.validate(chat_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('runtime_hashes', [
    {'dos': 'a'*64, 'wine': 'b'*64},
    {'dos': 'a'*64, 'wine': 'b'*64, 'windows': 'not-a-sha256'},
    {'dos': 'a'*64, 'wine': 'b'*64, 'windows': 'e'*64, 'unexpected': 'f'*64},
])
def test_chat_requires_exact_full_windows_runtime_identity(chat_qualified, runtime_hashes):
    path = chat_qualified / 'native-evidence/chat/acceptance.json'
    data = json.loads(path.read_text())
    data['runtime_sha256'] = runtime_hashes
    path.write_text(json.dumps(data))
    ref = gate.identity(chat_qualified, 'native-evidence/chat/acceptance.json')
    for name in ('chat-consumer', 'local-process-chat-consumer'):
        path = chat_qualified / f'artifacts/receipts/{name}.json'
        data = json.loads(path.read_text())
        data['verifier'] = ref
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='prepared runtime identity missing'):
        gate.validate(chat_qualified, SHA, local_run_id=LOCAL_RUN)


@pytest.mark.parametrize('field,value', [('network_interfaces',['lo','eth0']),('loader_closure','host'),
    ('python_mappings','host'),('source_commit','b'*40),('archive_sha256','f'*64),('skipped',1),('native_failures',1)])
def test_chat_rejects_bad_isolation_identity_or_failures(chat_qualified,field,value):
    root=chat_qualified; p=root/'native-evidence/chat/acceptance.json';data=json.loads(p.read_text());data[field]=value;p.write_text(json.dumps(data))
    ref=gate.identity(root,'native-evidence/chat/acceptance.json')
    for name in ('chat-consumer','local-process-chat-consumer'):
        p=root/f'artifacts/receipts/{name}.json';obj=json.loads(p.read_text());obj['verifier']=ref;p.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match='verifier isolation'):
        gate.validate(root,SHA,local_run_id=LOCAL_RUN)


def test_chat_rejects_missing_wine_and_wrong_archive_bytes(chat_qualified):
    root=chat_qualified;p=root/'native-evidence/chat/acceptance.json';data=json.loads(p.read_text());data['checks']['pe_restore']=False;p.write_text(json.dumps(data))
    ref=gate.identity(root,'native-evidence/chat/acceptance.json')
    for name in ('chat-consumer','local-process-chat-consumer'):
        q=root/f'artifacts/receipts/{name}.json';obj=json.loads(q.read_text());obj['verifier']=ref;q.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match='capability'):
        gate.validate(root,SHA,local_run_id=LOCAL_RUN)
    archive=root/'.native/chat/output/fdisbull-chat-offline.zip';archive.write_bytes(b'changed')
    with pytest.raises(ValueError, match='identity mismatch'):
        gate.validate(root,SHA,local_run_id=LOCAL_RUN)

@pytest.fixture
def boat_qualified(chat_qualified):
    root = chat_qualified
    sandbox = 'bx_fixture'
    write(root, 'artifacts/receipts/boat-worker.json', {
        'schema':'fdisbull-boat-worker-v1', 'execution_origin':'boat-linux',
        'boat_sandbox_id':sandbox, 'type':'default', 'architecture':'x86_64',
        'host_boot_id':'00000000-0000-4000-8000-000000000020', 'observed_at':'2026-11-04T12:00:00Z'})
    proof = gate.identity(root, 'artifacts/receipts/boat-worker.json')
    binding = {'execution_origin':'boat-linux', 'boat_sandbox_id':sandbox, 'boat_worker_receipt':proof}
    write(root, 'artifacts/receipts/boat-run.json', dict(binding, source_commit=SHA, local_run_id=LOCAL_RUN))
    paths = ['artifacts/receipts/ordinary.json', 'artifacts/receipts/native-stable.json',
             'artifacts/receipts/native-layers.json', 'artifacts/receipts/native-unified.json',
             'artifacts/receipts/chat-prepare.json', 'artifacts/receipts/chat-consumer.json',
             'native-evidence/pe/preparation-process.json', 'native-evidence/pe/preparation-completed.json']
    paths += [f'artifacts/receipts/local-process-{name}.json' for name in
              ('ordinary', 'stable', 'layers', 'unified', 'chat-prepare', 'chat-consumer')]
    for name in paths:
        p = root / name
        value = json.loads(p.read_text()); value.update(binding); p.write_text(json.dumps(value))
    return root


def test_boat_same_worker_qualifies_without_relabeling(boat_qualified):
    result = gate.validate(boat_qualified, SHA, local_run_id=LOCAL_RUN)
    assert result['execution_origin'] == 'boat-linux'
    assert result['boat_sandbox_id'] == 'bx_fixture'


@pytest.mark.parametrize('path,field,value', [
    ('artifacts/receipts/local-process-stable.json', 'boat_sandbox_id', 'bx_other'),
    ('artifacts/receipts/native-layers.json', 'boat_worker_receipt', None),
    ('native-evidence/pe/preparation-process.json', 'execution_origin', 'local-linux'),
    ('artifacts/receipts/chat-consumer.json', 'boat_sandbox_id', 'bx_other'),
    ('artifacts/receipts/boat-run.json', 'source_commit', 'b' * 40),
    ('artifacts/receipts/boat-worker.json', 'architecture', 'arm64'),
])
def test_boat_worker_or_source_mismatch_fails(boat_qualified, path, field, value):
    p = boat_qualified / path; record = json.loads(p.read_text()); record[field] = value
    p.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        gate.validate(boat_qualified, SHA, local_run_id=LOCAL_RUN)


def test_boat_guest_identity_requires_typed_artifact(monkeypatch):
    monkeypatch.setenv('FDISBULL_EXECUTION_ORIGIN', 'boat-linux')
    monkeypatch.setenv('FDISBULL_LOCAL_RUN_ID', LOCAL_RUN)
    monkeypatch.setenv('FDISBULL_LOCAL_JOB_ID', '00000000-0000-4000-8000-000000000021')
    monkeypatch.setenv('CI_JOB_NAME', 'test-and-package')
    monkeypatch.setenv('FDISBULL_BOAT_SANDBOX_ID', 'bx_fixture')
    proof = {'path':'artifacts/receipts/boat-worker.json', 'sha256':'a'*64, 'size':1}
    monkeypatch.setenv('FDISBULL_BOAT_WORKER_RECEIPT', json.dumps(proof))
    assert gate.execution_identity()['boat_worker_receipt'] == proof
    monkeypatch.setenv('FDISBULL_BOAT_WORKER_RECEIPT', '{}')
    with pytest.raises(ValueError): gate.execution_identity()


def test_backend_reuse_accepts_only_bound_original_boat_proofs(local_qualified):
    from test_native_backend_reuse import attach_boat_original
    root = local_qualified
    receipt_path = add_reused_backend(root, 'stable')
    receipt = json.loads(receipt_path.read_text())
    base = root / 'native-evidence/stable'
    attach_boat_original(base, 'stable')
    backend = receipt['backend_identity']
    backend['build_process_sha256'] = gate.identity(root, 'native-evidence/stable/build-process.json')['sha256']
    backend['build_execution_origin'] = 'boat-linux'
    for field, name in gate.BOAT_REUSE_FILES.items():
        backend[field] = gate.identity(root, 'native-evidence/stable/' + name)['sha256']
    current = {'image_digest': backend['build_image_digest']}
    proofs = gate.verify_reused_backend(root, 'stable', backend, receipt['artifacts'], current)
    assert 'build-boat-worker.json' in proofs and 'build-boat-run.json' in proofs
    (base/'build-boat-worker.json').write_text('{}')
    with pytest.raises(ValueError, match='proof hash mismatch'):
        gate.verify_reused_backend(root, 'stable', backend, receipt['artifacts'], current)


def test_current_large_boat_worker_identity_is_accepted(boat_qualified):
    worker = boat_qualified/'artifacts/receipts/boat-worker.json'
    data = json.loads(worker.read_text()); data['type'] = 'large'; worker.write_text(json.dumps(data))
    ref = gate.identity(boat_qualified, 'artifacts/receipts/boat-worker.json')
    run = boat_qualified/'artifacts/receipts/boat-run.json'
    data = json.loads(run.read_text()); data['boat_worker_receipt'] = ref; run.write_text(json.dumps(data))
    assert gate.boat_identity(boat_qualified, SHA, LOCAL_RUN)['boat_worker_receipt'] == ref
