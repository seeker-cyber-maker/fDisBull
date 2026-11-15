"""Authored small lineage fixtures; production pins remain immutable defaults."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('retained_chat_inputs', Path(__file__).parents[1] / 'scripts/ci/prepare-retained-chat-inputs.py')
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return str(path)


def edit(path, mutate):
    value = json.loads(Path(path).read_text())
    mutate(value)
    Path(path).write_text(json.dumps(value))


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    # The small authored image/wheels avoid reading private multi-GB originals.
    root = tmp_path / 'exported'; root.mkdir()
    paths = {}
    for key, name in producer.INPUTS.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key.encode()); paths[key] = path
    for name in producer.PINS:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith('.whl'):
            dist = 'fdisbull_player' if 'player' in name else 'fdisbull'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr(dist + '-0.34.1.dist-info/METADATA', 'Name: ' + dist.replace('_', '-') + '\nVersion: 0.34.1\n')
                z.writestr(dist + '/wine_guest/broker.py', 'authored broker')
        else:
            path.write_bytes(name.encode())
    pins = {name: digest((root / name).read_bytes()) for name in producer.PINS}
    monkeypatch.setattr(producer, 'PINS', pins)
    firmware = root / '.native/pe/qemu-9.2.4/pc-bios'; firmware.mkdir(parents=True)
    for name in ['bios-256k.bin', 'vgabios-stdvga.bin'] + [f'file{i}' for i in range(169)]:
        (firmware / name).write_bytes(name.encode())
    def ref(path):
        return {'path': '/builds/fdisbull/' + path.relative_to(root).as_posix(), **producer.identity(path)}
    backend = {'source_commit': producer.SOURCE, 'version': producer.VERSION,
               'inputs': {key: ref(path) for key, path in paths.items()},
               'wheel': ref(root / 'dist/fdisbull-0.34.1-py3-none-any.whl')}
    write(root / 'native-evidence/pe/backend-identity.json', backend)
    wheels = tmp_path / 'wheels'; wheels.mkdir()
    for distribution in producer.builder.RUNTIME_WHEELS:
        dist = distribution.replace('-', '_'); wheel = wheels / (dist + '.whl')
        version = producer.VERSION if distribution in ('fdisbull', 'fdisbull-player') else '1'
        if distribution in ('fdisbull', 'fdisbull-player'):
            name = next(n for n in pins if n.endswith('.whl') and (('player' in n) == (distribution == 'fdisbull-player')))
            wheel = wheels / Path(name).name; wheel.write_bytes((root / name).read_bytes())
        else:
            with zipfile.ZipFile(wheel, 'w') as z:
                z.writestr(dist + '-1.dist-info/METADATA', f'Name: {distribution}\nVersion: {version}\n')
    image = tmp_path / 'windows.cpio.gz'; image.write_bytes(b'authored full Windows stand-in')
    monkeypatch.setattr(producer, 'WINDOWS', producer.identity(image))
    manifest = {'schema': 'fdisbull-retained-runtime-base-1', 'qualification_claimed': False,
        'origin_source_commit': producer.ORIGIN_SOURCE,
        'origin_process': {'source_commit': producer.ORIGIN_SOURCE, 'exit_code': 2, 'termination': 'exited',
            'execution_origin': 'local-linux', 'container_state_after_stop': 'stopped', 'job_name': 'native-unified'},
        'origin_source_postcheck': {'source_commit': producer.ORIGIN_SOURCE, 'expected_source_commit': producer.ORIGIN_SOURCE,
                                  'tracked_worktree_dirty': False, 'export_success': True},
        'os_inventory': {'capabilities': ['wine64', 'dos', 'pe32', 'win16-guards']}, 'os_base': {'sha256': 'b' * 64}}
    manifest_path = tmp_path / 'manifest.json'; write(manifest_path, manifest)
    cap = {'schema': 'fdisbull-retained-base-preparation-1', 'source_commit': producer.PREPARATION_SOURCE,
        'build_job_id': '4d618755-0b1e-4169-b8ed-9adc1ef43ee1', 'local_run_id': 'be739d4d-4291-424a-b0b3-e416e1c84c5b',
        'origin_source_commit': producer.ORIGIN_SOURCE, 'origin_job_exit_code': 2,
        'manifest_sha256': producer.identity(manifest_path)['sha256'], 'os_capabilities': manifest['os_inventory']['capabilities']}
    cap_path = tmp_path / 'cap.json'; write(cap_path, cap)
    resource_path = tmp_path / 'resources.json'
    write(resource_path, {'runtime_sha256': producer.WINDOWS['sha256'], 'base_sha256': 'b' * 64})
    prepared = {'schema': 'fdisbull-unified-runtime-inputs-1', 'source_commit': producer.PREPARATION_SOURCE,
                'build_job_id': cap['build_job_id'], 'local_run_id': cap['local_run_id'], 'retained_base': {
                    'windows_runtime': producer.identity(image), 'manifest': producer.identity(manifest_path),
                    'preparation': producer.identity(cap_path), 'windows_resources': producer.identity(resource_path)}}
    prepared_path = tmp_path / 'prepared.json'; write(prepared_path, prepared)
    post = {'source_commit': producer.PREPARATION_SOURCE, 'expected_source_commit': producer.PREPARATION_SOURCE,
            'tracked_worktree_dirty': False, 'export_success': True}
    report = {'schema': 'fdisbull-retained-full-windows-runtime-inventory-1',
        'candidate': {'sha256_streamed': producer.WINDOWS['sha256'], 'sha256_expected': producer.WINDOWS['sha256'],
            'size_bytes': producer.WINDOWS['size'], 'runtime_preparation_sidecar': producer.identity(resource_path)},
        'resource_schemas': {'retained_base_manifest': producer.identity(manifest_path),
            'capability_receipt': producer.identity(cap_path), 'prepared_inputs': producer.identity(prepared_path)},
        'capabilities': {'os_capabilities': cap['os_capabilities']},
        'source_and_provenance_bindings': {'build_job_id': cap['build_job_id'], 'local_run_id': cap['local_run_id'],
            'preparation_source_commit': producer.PREPARATION_SOURCE, 'prepared_inputs_source_commit': producer.PREPARATION_SOURCE,
            'preparation_process': {'source_commit': producer.PREPARATION_SOURCE, 'exit_code': 0,
                'termination': 'exited', 'local_job_id': cap['build_job_id'], 'local_run_id': cap['local_run_id']},
            'preparation_source_postcheck': post},
        'qualification_ceiling': {'qualification_claimed': False, 'origin_job_exit_code': 2}}
    report_path = tmp_path / 'report.json'; write(report_path, report)
    monkeypatch.setattr(producer, 'DOCUMENT_PINS', {
        'report': producer.identity(report_path)['sha256'], 'manifest': producer.identity(manifest_path)['sha256'],
        'capability_receipt': producer.identity(cap_path)['sha256'], 'prepared_inputs': producer.identity(prepared_path)['sha256'],
        'resource_receipt': producer.identity(resource_path)['sha256']})
    rows = [{'path': p.relative_to(root).as_posix(), **producer.identity(p)} for p in root.rglob('*') if p.is_file()]
    metadata = {'schema': 'fdisbull-ovh-result-export-v1', 'source_commit': producer.SOURCE,
        'pipeline_id': producer.PIPELINE, 'job_id': producer.JOB, 'job_name': 'native-unified',
        'job_status': 'success', 'export_success': True, 'project_directory': '/builds/fdisbull', 'files': len(rows)}
    prefix = tmp_path / 'prefix'; prefix.mkdir()
    license = tmp_path / 'copyright'; license.write_text('Authored fixture')
    write(tmp_path / 'inventory.json', rows)
    monkeypatch.setattr(producer, 'EXPORT_INVENTORY_SHA', producer.identity(tmp_path / 'inventory.json')['sha256'])
    return {'schema': 'fdisbull-chat-retained-inputs-v1', 'application_source_commit': producer.SOURCE,
        'application_version': producer.VERSION, 'export_root': str(root), 'python_prefix': str(prefix), 'wheelhouse': str(wheels),
        'export_inventory': write(tmp_path / 'inventory.json', rows), 'job_metadata': write(tmp_path / 'job.json', metadata),
        'source_postcheck': write(tmp_path / 'post.json', {'source_commit': producer.SOURCE, 'expected_source_commit': producer.SOURCE,
                               'tracked_worktree_dirty': False, 'export_success': True}), 'licenses': [str(license)],
        'full_windows': {'image': str(image), 'report': str(report_path), 'manifest': str(manifest_path),
            'capability_receipt': str(cap_path), 'prepared_inputs': str(prepared_path), 'resource_receipt': str(resource_path)}}


def test_validated_retained_components_keep_provider_and_failed_donor_distinct(bundle):
    result = producer.validate(bundle)
    assert result['hosted_origin'] == {'execution_origin': 'gitlab', 'pipeline_id': producer.PIPELINE,
        'job_id': producer.JOB, 'source_commit': producer.SOURCE, 'job_status': 'success'}
    assert result['windows']['origin_exit_code'] == 2
    assert result['windows']['qualification_claimed'] is False
    assert result['windows']['preparation_source_commit'] == producer.PREPARATION_SOURCE
    assert len(result['firmware']) == 171
    assert 'local_run_id' not in result['hosted_origin']


@pytest.mark.parametrize('field,value', [('application_source_commit', '0' * 40), ('application_version', '0.32.0')])
def test_refuses_different_application(bundle, field, value):
    bundle[field] = value
    with pytest.raises(ValueError, match='application'):
        producer.validate(bundle)


@pytest.mark.parametrize('field,value', [('pipeline_id', '1'), ('job_id', '2'), ('job_status', 'failed')])
def test_refuses_foreign_or_failed_provider_job(bundle, field, value):
    edit(bundle['job_metadata'], lambda doc: doc.update({field: value}))
    with pytest.raises(ValueError, match='hosted export'):
        producer.validate(bundle)


def test_refuses_dirty_provider_source(bundle):
    edit(bundle['source_postcheck'], lambda doc: doc.update(tracked_worktree_dirty=True))
    with pytest.raises(ValueError, match='postcheck'):
        producer.validate(bundle)


@pytest.mark.parametrize('change', ['bytes', 'extra', 'traversal', 'symlink'])
def test_closed_export_rejects_changed_missing_or_escaping_inputs(bundle, change):
    root = Path(bundle['export_root'])
    target = root / producer.INPUTS['FDISBULL_PE_KERNEL']
    if change == 'bytes': target.write_bytes(b'corrupt')
    elif change == 'extra': (root / 'extra').write_text('unexpected')
    elif change == 'traversal':
        edit(bundle['export_inventory'], lambda rows: rows[0].update(path='../escape'))
    else:
        target.unlink(); target.symlink_to(Path(bundle['licenses'][0]))
    with pytest.raises(ValueError): producer.validate(bundle)


def test_rehashed_backend_still_must_match_selected_actual_bytes(bundle, monkeypatch):
    root = Path(bundle['export_root']); path = root / 'native-evidence/pe/backend-identity.json'
    edit(path, lambda doc: doc['inputs']['FDISBULL_PE_QEMU'].update(sha256='0' * 64))
    edit(bundle['export_inventory'], lambda rows: next(r for r in rows if r['path'] == path.relative_to(root).as_posix()).update(producer.identity(path)))
    monkeypatch.setattr(producer, 'EXPORT_INVENTORY_SHA', producer.identity(bundle['export_inventory'])['sha256'])
    with pytest.raises(ValueError, match='FDISBULL_PE_QEMU'): producer.validate(bundle)


def test_actual_windows_image_hash_is_mandatory(bundle):
    Path(bundle['full_windows']['image']).write_bytes(b'different Windows')
    with pytest.raises(ValueError, match='pinned Windows'): producer.validate(bundle)


def test_changed_donor_receipt_is_rejected_even_if_image_unchanged(bundle):
    edit(bundle['full_windows']['capability_receipt'], lambda doc: doc.update(origin_job_exit_code=0))
    with pytest.raises(ValueError, match='capability_receipt'): producer.validate(bundle)


def test_missing_full_windows_is_not_optional(bundle):
    Path(bundle['full_windows']['image']).unlink()
    with pytest.raises(ValueError, match='regular'): producer.validate(bundle)


def test_honest_failed_origin_must_not_be_promoted(bundle):
    # Rehash the report edge to prove the semantic guard is independent of hashes.
    manifest = bundle['full_windows']['manifest']; edit(manifest, lambda doc: doc.update(qualification_claimed=True))
    edit(bundle['full_windows']['report'], lambda doc: doc['resource_schemas']['retained_base_manifest'].update(producer.identity(manifest)))
    with pytest.raises(ValueError, match='pinned Windows (report|manifest)'): producer.validate(bundle)


def test_refuses_output_reuse_before_any_materialization(bundle, tmp_path):
    output = tmp_path / 'output'; output.mkdir(); (output / 'keep').write_text('unique')
    with pytest.raises(ValueError, match='empty'): producer.prepare(bundle, output)
    assert (output / 'keep').read_text() == 'unique'


def test_installed_core_guest_bytes_must_match_pinned_wheel(bundle):
    prefix = Path(bundle['python_prefix'])
    wheel = Path(bundle['wheelhouse']) / 'fdisbull-0.34.1-py3-none-any.whl'
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            path = prefix / 'lib/python3.13/site-packages' / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.read(name))
    producer.verify_installed_core(prefix, wheel)
    (prefix / 'lib/python3.13/site-packages/fdisbull/wine_guest/broker.py').write_text('stale broker')
    with pytest.raises(ValueError, match='missing or changed'):
        producer.verify_installed_core(prefix, wheel)


@pytest.mark.parametrize('harness', ['not-a-commit', True, '0' * 39])
def test_harness_identity_refuses_invalid_value_before_output(bundle, harness):
    bundle['harness_source_commit'] = harness
    with pytest.raises(ValueError, match='harness'):
        producer.validate(bundle)


def test_donor_report_cannot_self_attest_changed_lineage(bundle):
    edit(bundle['full_windows']['report'], lambda doc: doc['qualification_ceiling'].update(qualification_claimed=True))
    with pytest.raises(ValueError, match='pinned Windows report'):
        producer.validate(bundle)


def test_rehashed_export_cannot_replace_pinned_provider_inventory(bundle):
    root = Path(bundle['export_root']); name = producer.INPUTS['FDISBULL_PE_QEMU']
    (root / name).write_bytes(b'replacement native component')
    edit(bundle['export_inventory'], lambda rows: next(r for r in rows if r['path'] == name).update(producer.identity(root / name)))
    with pytest.raises(ValueError, match='pinned hosted inventory'):
        producer.validate(bundle)
