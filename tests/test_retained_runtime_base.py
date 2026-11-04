"""Immutable OS components cannot be mistaken for candidate qualification."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/ci'))
spec = importlib.util.spec_from_file_location('retained_base_test', ROOT/'scripts/ci/retained-runtime-base.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
SHA = 'a'*40
RUN = 'b4f5594b-2d10-4f1a-bd00-e25412e0f851'
JOB = '00000000-0000-4000-8000-000000000001'


def cpio(path, values):
    with gzip.open(path, 'wb') as out:
        for inode, (name, data) in enumerate([*values.items(), ('TRAILER!!!', b'')], 1):
            encoded = name.encode()+b'\0'
            fields = (inode, stat.S_IFREG|0o755, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0)
            out.write(b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+encoded)
            out.write(b'\0'*(-(110+len(encoded))%4)+data+b'\0'*(-len(data)%4))


@pytest.fixture
def retained(tmp_path, monkeypatch):
    root = tmp_path/'inputs';root.mkdir()
    inputs = {}
    for key, name in base.PATHS.items():
        p = root/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(key.encode())
        inputs[key] = base.item(p, name)
    monkeypatch.setattr(base, 'KERNEL_SHA', inputs['FDISBULL_PE_KERNEL']['sha256'])
    bios = root/base.FIRMWARE;bios.mkdir()
    names = ('bios-256k.bin', 'vgabios-stdvga.bin', *(f'fixture-{n:03d}' for n in range(169)))
    archive = root/base.SOURCE_ARCHIVE
    with tarfile.open(archive, 'w:xz') as out:
        for name in names:
            data = name.encode();(bios/name).write_bytes(data)
            entry = tarfile.TarInfo('qemu-9.2.4/pc-bios/'+name);entry.size=len(data)
            out.addfile(entry, io.BytesIO(data))
    monkeypatch.setattr(base, 'QEMU_SOURCE_SHA', base.digest(archive))
    os_base = tmp_path/'runtime.cpio.gz'
    values = {name: name.encode() for names in base.REQUIRED.values() for name in names}
    values.update({'init':b'old init', 'opt/fdisbull/stale-agent.c':b'old private helper'})
    cpio(os_base, values)
    shared=root/base.OLD_WINE;shared.write_bytes(os_base.read_bytes())
    recipe = base.QEMU_SOURCE_SHA+'\n'+base.KERNEL_SHA
    original = {'execution_origin':'local-linux','source_commit':SHA,'local_run_id':RUN,'local_job_id':JOB,
                'job_name':'native-unified','termination':'exited','exit_code':2,
                'container_state_after_stop':'stopped','runtime':{'system':'linux','machine':'x86_64'},
                'image_digest':'sha256:'+'b'*64}
    value = {'schema':base.SCHEMA,'origin_source_commit':SHA,'origin_process':original,
             'origin_source_postcheck':{'source_commit':SHA,'expected_source_commit':SHA,
                                      'tracked_worktree_dirty':False,'export_success':True},
             'origin_backend_identity':{'source_commit':SHA,'inputs':dict(inputs, FDISBULL_PE_INITRAMFS=base.item(shared,base.OLD_WINE))},
             'original_wine_receipt':{'runtime_sha256':base.digest(shared)},
             'origin_build_recipe':{'text':recipe,'sha256':hashlib.sha256(recipe.encode()).hexdigest()},
             'inputs':inputs,'qemu_source':base.item(archive,base.SOURCE_ARCHIVE),
             'firmware':base.firmware_identity(root),'os_base':base.item(os_base),
             'shared_os_base':base.item(shared,base.OLD_WINE),
             'os_inventory':base.cpio_inventory(os_base),'fixture_source_sha256':hashlib.sha256(b'oracle source').hexdigest()}
    manifest = tmp_path/'components.json';manifest.write_text(json.dumps(value))
    return root, os_base, manifest, value


def test_retained_component_proof_preserves_failed_original_job_without_qualifying_it(retained):
    root, image, manifest, value = retained
    checked = base.verify(manifest,root,image,base.digest(manifest),required=['pe32','win16-guards'])
    assert checked['origin_process']['exit_code']==2
    assert checked['origin_source_commit']==SHA
    assert set(checked['os_inventory']['capabilities'])=={'wine64','dos','pe32','win16-guards'}


@pytest.mark.parametrize('changed', ['manifest-hash','foreign-prepared','origin-source','origin-postcheck',
                                    'origin-process','component','firmware','os-base','recipe','source-pin'])
def test_retained_component_route_rejects_changed_identity(retained,changed):
    root, image, manifest, value = retained
    expected = base.digest(manifest)
    if changed=='manifest-hash': expected='0'*64
    elif changed=='foreign-prepared': value={'schema':'fdisbull-unified-runtime-inputs-1','source_commit':SHA}
    elif changed=='origin-source': value['origin_source_commit']='b'*40
    elif changed=='origin-postcheck': value['origin_source_postcheck']['tracked_worktree_dirty']=True
    elif changed=='origin-process': value['origin_process']['runtime']['machine']='arm64'
    elif changed=='component': (root/base.PATHS['FDISBULL_PE_QEMU']).write_bytes(b'changed')
    elif changed=='firmware': (root/base.FIRMWARE/'bios-256k.bin').write_bytes(b'changed')
    elif changed=='os-base': image.write_bytes(b'changed')
    elif changed=='recipe': value['origin_build_recipe']['text']+=' changed'
    elif changed=='source-pin': value['qemu_source']['sha256']='d'*64
    if changed not in ('manifest-hash','component','firmware','os-base'):
        manifest.write_text(json.dumps(value));expected=base.digest(manifest)
    with pytest.raises((ValueError,KeyError)):
        base.verify(manifest,root,image,expected)


def test_missing_32bit_dependencies_are_an_explicit_capability_refusal(retained):
    root, image, manifest, value = retained
    cpio(image,{name:b'dependency' for name in base.REQUIRED['wine64']})
    value['os_base']=base.item(image);value['os_inventory']=base.cpio_inventory(image)
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='capabilities'):
        base.verify(manifest,root,image,base.digest(manifest),required=['pe32'])


def test_component_rebase_removes_old_helpers_and_records_new_candidate_job(retained,tmp_path,monkeypatch):
    root, image, manifest, value = retained
    work=tmp_path/'work';work.mkdir();monkeypatch.chdir(work)
    fixture=work/'tests/wine_gui_fixture.c';fixture.parent.mkdir();fixture.write_bytes(b'oracle source')
    dosbox=work/'.native/backends/layers/dosbox-x';dosbox.parent.mkdir(parents=True)
    dosbox.write_bytes(b'\x7fELF\x02\x01'+b'\0'*12+b'\x3e\x00'+b'authored elf')
    evidence=work/'native-evidence/layers';evidence.mkdir(parents=True)
    (evidence/'backend-identity.json').write_text(json.dumps({'source_commit':'d'*40,'backend_sha256':base.digest(dosbox)}))
    for key,val in {'FDISBULL_EXECUTION_ORIGIN':'local-linux','CI_COMMIT_SHA':'d'*40,
                    'FDISBULL_LOCAL_RUN_ID':RUN,'FDISBULL_LOCAL_JOB_ID':JOB,'FDISBULL_DOSBOX':str(dosbox),
                    'FDISBULL_PE_INITRAMFS':str(work/'.native/pe/runtime.cpio.gz'),
                    'FDISBULL_DOS_INITRAMFS':str(work/'.native/pe/dos-runtime.cpio.gz')}.items():monkeypatch.setenv(key,val)
    base.prepare(manifest,root,image,base.digest(manifest),['wine64','dos'])
    prepared=json.loads((work/'native-evidence/pe/retained-base-preparation.json').read_text())
    assert prepared['source_commit']=='d'*40 and prepared['origin_source_commit']==SHA
    assert prepared['build_job_id']==JOB and prepared['origin_job_exit_code']==2
    inventory=base.cpio_inventory(work/'.native/pe/runtime.cpio.gz')
    # Old helper is omitted; new resource hashes are the installed product's
    # current bytes. The new /init has replaced the old base's launcher.
    from fdisbull.wine_runtime import resources
    receipt=json.loads((work/'native-evidence/pe/runtime-preparation.json').read_text())
    assert receipt['resources']['init']==base.digest(resources()['init'])
    assert 'opt/fdisbull' in receipt['omitted_prefixes']
    assert inventory['records']>0


def test_allocation_uses_measured_stream_and_three_retained_copies(retained):
    _, image, _, _=retained
    estimate=base.estimate(image,123456,source_root=ROOT)
    assert estimate['measured_compacted_gzip_bytes']>0
    assert estimate['retained_copies']==3
    assert estimate['expected_bytes']>=3*estimate['runtime_bound_bytes']+4_000_000_000
