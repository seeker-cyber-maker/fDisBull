"""Prepared local runtime evidence is tied to exact inputs and source resources."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
SHA = 'a' * 40
RUN = 'b4f5594b-2d10-4f1a-bd00-e25412e0f851'
JOB = '00000000-0000-4000-8000-000000000001'


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location('runtime_inputs_test', ROOT / 'scripts/ci/unified-runtime-inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('FDISBULL_EXECUTION_ORIGIN', 'local-linux')
    monkeypatch.setenv('CI_COMMIT_SHA', SHA)
    monkeypatch.setenv('FDISBULL_LOCAL_RUN_ID', RUN)
    monkeypatch.setenv('FDISBULL_LOCAL_JOB_ID', JOB)
    monkeypatch.setenv('FDISBULL_UNIFIED_BUILD_JOB_ID', JOB)
    identity = {'source_commit': SHA, 'inputs': {}}
    for index, key in enumerate(module.KEYS):
        p = tmp_path / module.INPUT_PATHS[key]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(('input-' + key).encode())
        monkeypatch.setenv(key, str(p))
        identity['inputs'][key] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size}
    wheel_name = 'fdisbull-0.30.0-py3-none-any.whl'
    for parent in ('dist', '.native/pe/packages'):
        wheel = tmp_path / parent / wheel_name
        wheel.parent.mkdir(parents=True, exist_ok=True)
        wheel.write_bytes(b'wheel-original')
    identity['wheel'] = {'sha256': hashlib.sha256(b'wheel-original').hexdigest(), 'size': len(b'wheel-original')}
    pe = tmp_path / 'native-evidence/pe'
    pe.mkdir(parents=True)
    (pe / 'backend-identity.json').write_text(json.dumps(identity))
    bios = tmp_path / '.native/pe/qemu-9.2.4/pc-bios'
    bios.mkdir(parents=True)
    for name in ('bios-256k.bin', 'vgabios-stdvga.bin', *(f'fixture-{i:03d}.bin' for i in range(169))):
        (bios / name).write_bytes(name.encode())
    for kind, mapping in module.RESOURCES.items():
        values = {}
        for guest, source in mapping.items():
            p = tmp_path / source
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(source.encode())
            values[guest] = hashlib.sha256(p.read_bytes()).hexdigest()
        if kind == 'dos':
            values['opt/fdisbull/dosbox-x'] = identity['inputs']['FDISBULL_DOSBOX']['sha256']
        name = 'runtime-preparation.json' if kind == 'wine' else 'dos-runtime-preparation.json'
        key = 'FDISBULL_PE_INITRAMFS' if kind == 'wine' else 'FDISBULL_DOS_INITRAMFS'
        (pe / name).write_text(json.dumps({'resources': values, 'runtime_sha256': identity['inputs'][key]['sha256']}))
    module.prepare()
    return module, tmp_path


def test_prepared_runtime_host_and_guest_checks(prepared):
    module, root = prepared
    assert module.verify()['source_commit'] == SHA
    value = module.verify(root, SHA, RUN, JOB, source_root=root)
    assert len(value['inputs']) == 6 and len(value['firmware']) == 171
    assert value['build_job_id'] == JOB


@pytest.mark.parametrize('change', ['source', 'run', 'job', 'input', 'firmware', 'resource', 'resource32', 'receipt', 'extra', 'wheel', 'ordinary-wheel', 'extra-wheel'])
def test_prepared_runtime_rejects_mismatch(prepared, change):
    module, root = prepared
    sha, run, job = SHA, RUN, JOB
    if change == 'source': sha = 'b' * 40
    if change == 'run': run = 'b4f5594b-2d10-4f1a-bd00-e25412e0f852'
    if change == 'job': job = '00000000-0000-4000-8000-000000000002'
    if change == 'input': (root / module.INPUT_PATHS['FDISBULL_PE_QEMU']).write_bytes(b'changed')
    if change == 'firmware': (root / module.FIRMWARE / 'bios-256k.bin').write_bytes(b'changed')
    if change == 'resource': (root / module.RESOURCES['wine']['init']).write_bytes(b'changed')
    if change == 'resource32': (root / module.RESOURCES['wine']['opt/fdisbull/selftest32.c']).write_bytes(b'changed')
    if change == 'receipt': (root / 'native-evidence/pe/runtime-preparation.json').write_text('{}')
    if change == 'extra': (root / module.FIRMWARE / 'extra').write_bytes(b'extra')
    if change == 'wheel': next((root / '.native/pe/packages').glob('*.whl')).write_bytes(b'substituted')
    if change == 'ordinary-wheel': next((root / 'dist').glob('*.whl')).write_bytes(b'substituted')
    if change == 'extra-wheel': (root / 'dist/fdisbull-extra.whl').write_bytes(b'extra')
    with pytest.raises((ValueError, KeyError)):
        module.verify(root, sha, run, job, source_root=root)


def test_prepared_runtime_rejects_symlinked_input(prepared):
    module, root = prepared
    p = root / module.INPUT_PATHS['FDISBULL_PE_QEMU']
    p.unlink()
    p.symlink_to(root / module.INPUT_PATHS['FDISBULL_PE_KERNEL'])
    with pytest.raises(ValueError):
        module.verify(root, SHA, RUN, JOB, source_root=root)


def test_verified_firmware_install_rejects_existing_destination(prepared, tmp_path):
    module, root = prepared
    target = tmp_path / 'installed-qemu'
    module.verify(root, SHA, RUN, JOB, source_root=root, install_firmware=target)
    assert len(list(target.rglob('*.bin'))) == 171
    with pytest.raises(ValueError, match='already exists'):
        module.verify(root, SHA, RUN, JOB, source_root=root, install_firmware=target)


def test_verified_firmware_install_rejects_dangling_symlink(prepared, tmp_path):
    module, root = prepared
    target = tmp_path / 'bad-link'
    target.symlink_to(tmp_path / 'absent')
    with pytest.raises(ValueError, match='already exists'):
        module.verify(root, SHA, RUN, JOB, source_root=root, install_firmware=target)


def test_prepare_and_acceptance_library_evidence_paths_are_distinct():
    prepare = (ROOT / 'scripts/ci/native-unified.sh').read_text()
    acceptance = (ROOT / 'scripts/ci/unified-acceptance.sh').read_text()
    assert 'native-evidence/pe/dos-libraries.txt' in prepare
    for name in ('acceptance-dos-libraries.txt', 'acceptance-qemu-libraries.txt'):
        assert name not in prepare
        assert acceptance.count('native-evidence/pe/' + name) == 2


@pytest.mark.parametrize('change', [None, 'source', 'run', 'job', 'windows-resource', 'fixture'])
def test_retained_os_proof_is_bound_to_fresh_source_job_and_windows_overlay(prepared, monkeypatch, change):
    module, root = prepared
    checker = module.retained_base_checker()
    inputs = json.loads((root/module.MANIFEST).read_text())['inputs']
    monkeypatch.setattr(checker, 'KERNEL_SHA', inputs['FDISBULL_PE_KERNEL']['sha256'])
    monkeypatch.setattr(module, 'retained_base_checker', lambda: checker)
    recipe = checker.QEMU_SOURCE_SHA+'\n'+checker.KERNEL_SHA
    shared = {'sha256':'c'*64,'size':123}
    origin_inputs = {k:inputs[k] for k in checker.PATHS}
    origin_inputs['FDISBULL_PE_INITRAMFS']=shared
    origin_sha='e'*40
    origin = {'schema':checker.SCHEMA,'origin_source_commit':origin_sha,
        'origin_process':{'source_commit':origin_sha,'execution_origin':'local-linux','local_run_id':RUN,
            'local_job_id':'00000000-0000-4000-8000-000000000009','job_name':'native-unified',
            'termination':'exited','exit_code':2,'container_state_after_stop':'stopped',
            'image_digest':'sha256:'+'f'*64,'runtime':{'system':'linux','machine':'x86_64'}},
        'origin_source_postcheck':{'source_commit':origin_sha,'expected_source_commit':origin_sha,
            'tracked_worktree_dirty':False,'export_success':True},
        'origin_backend_identity':{'source_commit':origin_sha,'inputs':origin_inputs},
        'inputs':{k:inputs[k] for k in checker.PATHS},'qemu_source':{'sha256':checker.QEMU_SOURCE_SHA},
        'original_wine_receipt':{'runtime_sha256':shared['sha256']},'shared_os_base':shared,
        'origin_build_recipe':{'text':recipe,'sha256':hashlib.sha256(recipe.encode()).hexdigest()},
        'os_base':{'sha256':'d'*64},'os_inventory':{'capabilities':['wine64','dos','pe32']}}
    pe=root/'native-evidence/pe'
    for name in ('runtime-preparation.json','dos-runtime-preparation.json'):
        path=pe/name;doc=json.loads(path.read_text());doc['base_sha256']=shared['sha256'];path.write_text(json.dumps(doc))
    image=pe/'windows-runtime.cpio.gz';image.write_bytes(b'authored windows runtime')
    wine=json.loads((pe/'runtime-preparation.json').read_text())
    windows={'base_sha256':origin['os_base']['sha256'],'runtime_sha256':module.item(image,root)['sha256'],
             'resources':dict(wine['resources'])}
    if change=='windows-resource':windows['resources']['opt/fdisbull/selftest32.c']='0'*64
    (pe/'windows-runtime-preparation.json').write_text(json.dumps(windows))
    manifest=pe/'retained-base-manifest.json';manifest.write_text(json.dumps(origin))
    receipt={'schema':'fdisbull-retained-base-preparation-1','source_commit':SHA,'local_run_id':RUN,
        'build_job_id':JOB,'manifest_sha256':module.item(manifest,root)['sha256'],
        'origin_source_commit':origin_sha,'origin_job_exit_code':2,'os_capabilities':['wine64','dos','pe32'],
        'required_os_capabilities':['pe32'],'previous_project_resources_removed':list(checker.EXTRA_OMIT)}
    if change=='source':receipt['source_commit']=origin_sha
    if change=='run':receipt['local_run_id']='00000000-0000-4000-8000-000000000003'
    if change=='job':receipt['build_job_id']='00000000-0000-4000-8000-000000000004'
    receipt_path=pe/'retained-base-preparation.json';receipt_path.write_text(json.dumps(receipt))
    identity=json.loads((pe/'backend-identity.json').read_text())
    identity['retained_base']=module.item(receipt_path,root)
    binary=pe/'selftest32.exe';binary.write_bytes(b'authored pe32')
    identity['authored_pe32_fixture']={'source':module.item(root/'src/fdisbull/wine_guest/selftest32.c',root),
                                     'binary':module.item(binary,root)}
    if change=='fixture':binary.write_bytes(b'changed authored pe32')
    if change is None:
        result=module.retained_provenance(root,SHA,RUN,JOB,inputs,identity,root)
        assert result['windows_runtime']==module.item(image,root)
    else:
        with pytest.raises(ValueError):module.retained_provenance(root,SHA,RUN,JOB,inputs,identity,root)
