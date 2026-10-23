"""Initial DOS pointer bytes are not proven values after runtime writes."""
import hashlib
import json
import struct

import pytest

from fdisbull.dos_analysis import DOS_POINTER_REVISION
from fdisbull.project import Project
from test_dos_loader import mz_file


def pointer_program(kind='les',initial='zero'):
    module=bytearray(0x120)
    # DS=CS. The returning far callee's AX/DX are unknown. These stores replace
    # the entire pointer descriptor before LES/LDS, but static input bytes stay
    # unchanged. The analyzer must not resurrect that initial descriptor.
    prefix=bytes.fromhex('0e1f9a00010000a3a0008916a200')
    pointer_load=bytes.fromhex('c41ea000' if kind=='les' else 'c51ea000')
    pointer_read=bytes.fromhex('268b879400' if kind=='les' else '8b879400')
    code=prefix+pointer_load+pointer_read+b'\xcb'
    module[:len(code)]=code;module[0x100]=0xcb
    relocations=[(5,0)]
    if initial=='nonzero':
        struct.pack_into('<HH',module,0xa0,0x20,6)
        relocations.append((0xa2,0))
    return mz_file(bytes(module),relocations=relocations,ss=0,sp=0x110),len(prefix),len(prefix)+len(pointer_load)


@pytest.mark.parametrize('kind',['les','lds'])
@pytest.mark.parametrize('initial',['zero','nonzero'])
def test_far_load_does_not_restore_initial_pointer_after_unknown_stores(tmp_path,kind,initial):
    data,load_ip,read_ip=pointer_program(kind,initial)
    source=tmp_path/'pointer.exe';source.write_bytes(data)
    with Project.create(tmp_path/'pointer.fdb',source) as project:
        digest=project.version()['sha256'];original=project.regions(1)[0].data
        result=project.analyze()
        assert result['stable']
        row=project.disassembly(f'1000:{read_ip:04x}',lines=1)['instructions'][0]
        assert row['references']==[]
        assert '94h' in row['operands'].lower()
        state=row['assumptions']['registers']
        assert 'bx' not in state and ('es' if kind=='les' else 'ds') not in state
        assert not any(x['kind']=='data' for x in project.xrefs(f'1000:{read_ip:04x}',direction='from'))
        descriptor=project.disassembly(f'1000:{load_ip:04x}',lines=1)['instructions'][0]['references']
        assert len(descriptor)==1 and descriptor[0]['target']=='0x100a0' and descriptor[0]['width']==4
        facts=[json.loads(r[0]) for r in project.db.execute('SELECT detail FROM memory_refs WHERE version=1 AND source=?',(f'{0x10000+read_ip:016x}',))]
        assert facts and all(f['concrete_target'] is None and not f['interval_exact'] for f in facts)
        assert project.version()['sha256']==digest and project.regions(1)[0].data==original
        retained=bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])
        assert retained==data and hashlib.sha256(retained).digest()==hashlib.sha256(data).digest()
        issues=project.issues(limit=100)
        assert any('descriptor' in (r['detail'] or '') and r['address']==hex(0x10000+load_ip) for r in issues)
        path=project.path
    source.unlink()
    with Project(path) as reopened:
        assert reopened.disassembly(f'1000:{read_ip:04x}',lines=1)['instructions'][0]['references']==[]
        assert int(reopened.db.execute('SELECT value FROM metadata WHERE key=?',('dos_pointer_revision_1',)).fetchone()[0])==DOS_POINTER_REVISION


def test_far_snapshot_without_a_store_also_requires_reaching_value_evidence(tmp_path):
    # Removing the local stores cannot establish that an arbitrary invoked
    # routine runs before every mutation of this writable global descriptor.
    module=bytearray(0xa0)
    code=bytes.fromhex('0e1fc41e8000268b879400cb90')
    module[:len(code)]=code
    struct.pack_into('<HH',module,0x80,0x10,4)
    source=tmp_path/'snapshot.exe';source.write_bytes(mz_file(bytes(module),relocations=[(0x82,0)]))
    with Project.create(tmp_path/'snapshot.fdb',source) as project:
        assert project.analyze()['stable']
        row=project.disassembly('1000:0006',lines=1)['instructions'][0]
        assert row['references']==[] and 'es' not in row['assumptions']['registers']


def test_immediate_segments_registers_and_stack_tracking_still_resolve(tmp_path):
    module=bytearray(0x120)
    # SET ES=CS through PUSH/POP, set BX directly, then read ES:[BX+94].
    module[:12]=bytes.fromhex('0e07bb2000268b879400cb90')
    source=tmp_path/'constant.exe';source.write_bytes(mz_file(bytes(module),ss=0,sp=0x110))
    with Project.create(tmp_path/'constant.fdb',source) as project:
        assert project.analyze()['stable']
        row=project.disassembly('1000:0005',lines=1)['instructions'][0]
        assert row['references'][0]['target']=='0x100b4'
        assert row['assumptions']['registers']['es']==0x1000 and row['assumptions']['registers']['bx']==0x20


def test_revision_is_recorded_on_fresh_reset_and_child_patch(tmp_path):
    data,_,_=pointer_program()
    source=tmp_path/'revision.exe';source.write_bytes(data)
    with Project.create(tmp_path/'revision.fdb',source) as project:
        def revision(version):
            row=project.db.execute('SELECT value FROM metadata WHERE key=?',(f'dos_pointer_revision_{version}',)).fetchone()
            return int(row[0]) if row else None
        assert revision(1)==DOS_POINTER_REVISION
        project.analyze()
        with project.transaction(True):
            project.db.execute('DELETE FROM metadata WHERE key=?',('dos_pointer_revision_1',))
            project._reset_analysis(1)
        assert revision(1)==DOS_POINTER_REVISION
        child=project.patch('1000:0000','90')['version']
        assert revision(child)==DOS_POINTER_REVISION and revision(1)==DOS_POINTER_REVISION
