"""Real DOS 5Bh/40h guest-create provenance and keep policy witnesses."""
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid

import pytest
from fdisbull.project import Project
from support.dos_process_fixture import assemble
from test_qemu_dos_workspace_native import _inputs,_launch,_mz,_runtime_base,_word

PAYLOAD=bytes.fromhex('1000ff41')


def _runtime():
    runtime=_inputs();binary=os.environ.get('FDISBULL_QEMU_PROVENANCE')
    if not binary:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS')=='1':
            pytest.fail('FDISBULL_QEMU_PROVENANCE is required')
        pytest.skip('Supply FDISBULL_QEMU_PROVENANCE')
    runtime['qemu']=binary
    return runtime


def _probe(directory,nasm,variant='good'):
    operations={
      'good':'',
      'irq':'',
      'existing':'',
      'create3c':'',
      'rename':"push ds\npop es\nmov dx,filename\nmov di,other\nmov ah,56h\nint 21h",
      'dup':"mov bx,[handle]\nmov ah,45h\nint 21h\njc failed\nmov bx,ax\nmov ah,3eh\nint 21h",
      'seek':"mov bx,[handle]\nxor cx,cx\nxor dx,dx\nmov ax,4200h\nint 21h",
      'raw13':"mov ah,08h\nxor dx,dx\nint 13h",
      'rawout':"xor eax,eax\nmov dx,0cf8h\nout dx,eax",
    }
    create='3c00h' if variant=='create3c' else '5b00h'
    code=assemble(directory,'guest-provenance-'+variant,r'''
bits 16
org 100h
    push cs
    pop ds
    mov dx,filename
    xor cx,cx
    mov ax,CREATE_OP
    int 21h
    jc failed
    mov [handle],ax
    UNSUPPORTED_OP
    mov bx,[handle]
    mov dx,payload
    mov cx,2
    mov ah,40h
    int 21h
    jc failed
    cmp ax,2
    jne failed
    IRQ_DELAY
    mov bx,[handle]
    mov dx,payload+2
    mov cx,2
    mov ah,40h
    int 21h
    jc failed
    cmp ax,2
    jne failed
open_ready:
    nop
    mov bx,[handle]
    mov ah,68h
    int 21h
    jc failed
    mov bx,[handle]
    mov ah,3eh
    int 21h
    jc failed
    mov ah,0dh
    int 21h
    mov word [status],0beefh
    jmp short done
failed:
    mov word [status],0deadh
done:
    nop
    mov ax,4c2ah
    int 21h
handle: dw 0
status: dw 0
filename: db 'D:\SAVE.DAT',0
other: db 'D:\OTHER.DAT',0
payload: db 10h,00h,0ffh,41h
    db 'FDPR'
    dw done-100h,status-100h,open_ready-100h
'''.replace('CREATE_OP',create).replace('UNSUPPORTED_OP',operations[variant]).replace(
    'IRQ_DELAY','sti\nhlt\nhlt\nhlt' if variant=='irq' else '').replace(
    "D:\\SAVE.DAT", "D:\\ORIG.DAT" if variant=='existing' else "D:\\SAVE.DAT"),nasm)
    if code[-10:-6]!=b'FDPR':raise ValueError('Provenance test marker missing')
    return code,dict(zip(('done','status','open_ready'),struct.unpack_from('<3H',code,len(code)-6)))


def _setup(tmp_path,runtime,kind='com',variant='good'):
    build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    program,marker=_probe(build,runtime['NASM'],variant);source=_mz(program) if kind=='mz' else program
    binary=directory/('PROBE.EXE' if kind=='mz' else 'PROBE.COM');binary.write_bytes(source)
    (directory/'ORIG.DAT').write_bytes(b'original')
    return directory,binary,source,marker


def _finish(debug,base,marker):
    point=debug.breakpoint(base+marker['done'])
    result=debug.run(timeout_ms=20000)
    assert result['outcome']=='breakpoint',result
    assert _word(debug,base+marker['status'])==0xbeef
    debug.delete_breakpoint(point['breakpoint_id'])


def _proof_doc(project,receipt):
    row=project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',(receipt['artifact'],)).fetchone()
    data=bytes(row['data']);assert hashlib.sha256(data).hexdigest()==receipt['sha256']==row['sha256']
    return json.loads(data)


@pytest.mark.parametrize('kind',['com','mz'])
def test_guest_create_proof_and_explicit_keep(tmp_path,kind):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,kind)
    with Project.create(tmp_path/'project.fdb',binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            with pytest.raises(ValueError,match='exists|protected'):
                debug.workspace_provenance_start('orig.dat')
            armed=debug.workspace_provenance_start('D:\\SAVE.DAT')
            assert armed['native']['phase']=='armed' and armed['native']['valid']
            _finish(debug,base,marker)
            state=debug.workspace_provenance_status()['native']
            assert state['phase']=='ready' and state['valid'] and not state['pending']
            assert state['create-seen'] and state['close-seen'] and state['flush-seen']
            assert state['write-count']==2 and state['bytes-written']==len(PAYLOAD)
            assert state['payload-sha256']==hashlib.sha256(PAYLOAD).hexdigest()
            assert [event['function'] for event in state['events']]==[0x5b,0x40,0x40,0x68,0x3e,0x0d]
            proof=debug.workspace_provenance_capture();doc=_proof_doc(project,proof)
            assert bytes.fromhex(doc['native']['payload-hex'])==PAYLOAD
            assert proof['payload_sha256']==hashlib.sha256(PAYLOAD).hexdigest()
            generation=proof['generation']
            with pytest.raises(ValueError,match='witnessed new'):
                debug.workspace_keep('SAVE.DAT',tmp_path/'unproven.dat',generation)
            with pytest.raises(ValueError):
                debug.workspace_keep('SAVE.DAT',tmp_path/'corrupt.dat',generation,
                                     provenance={'artifact':proof['artifact'],'sha256':'0'*64})
            result=debug.workspace_keep('SAVE.DAT',tmp_path/'kept.dat',generation,
                         provenance={'artifact':proof['artifact'],'sha256':proof['sha256']})
            assert result['guest_create_provenance'] is True and (tmp_path/'kept.dat').read_bytes()==PAYLOAD
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'
    assert not (directory/'SAVE.DAT').exists()


def test_keep_policy_survives_rewind_without_duplicate_copy(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    output=tmp_path/'keeps';output.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            policy=debug.workspace_keep_policy('SAVE.DAT',output)['policy']['artifact']
            checkpoint=debug.save_state()
            _finish(debug,base,marker)
            first=debug.workspace_seal(timeout_ms=60000)['keep_policy']
            assert first['outcome']=='kept'
            files=list(output.iterdir());assert len(files)==1 and files[0].read_bytes()==PAYLOAD
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['outcome']=='already-kept'
            debug.load_state(checkpoint['artifact'],timeout_ms=60000)
            _finish(debug,base,marker)
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['outcome']=='already-kept'
            assert len(list(output.iterdir()))==1 and files[0].read_bytes()==PAYLOAD
            debug.workspace_keep_policy_enabled(policy,False)
            debug.load_state(checkpoint['artifact'],timeout_ms=60000)
            _finish(debug,base,marker)
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['status']=='disabled'
            assert len(list(output.iterdir()))==1 and files[0].read_bytes()==PAYLOAD
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


def test_inflight_int21_checkpoint_restores_guest_create(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_provenance_start('SAVE.DAT')
            offset,segment=struct.unpack_from('<HH',debug._vectors_before,0x21*4)
            point=debug.breakpoint(segment*16+offset)
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            native=debug.workspace_provenance_status()['native']
            assert native['pending'] and native['pending-function']==0x5b
            saved=debug.save_state();debug.delete_breakpoint(point['breakpoint_id'])
            _finish(debug,base,marker)
            first=debug.workspace_provenance_capture();assert first['payload_sha256']==hashlib.sha256(PAYLOAD).hexdigest()
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            assert debug.workspace_provenance_status()['native']['pending']
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            _finish(debug,base,marker)
            proof=debug.workspace_provenance_capture();assert proof['payload_sha256']==first['payload_sha256']
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source


def test_open_output_cannot_yet_certify_or_keep(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    output=tmp_path/'keeps';output.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',output)
            point=debug.breakpoint(base+marker['open_ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            native=debug.workspace_provenance_status()['native']
            assert native['valid'] and native['phase']=='writing' and not native['close-seen']
            with pytest.raises(ValueError):debug.workspace_provenance_capture()
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['status']=='not-ready'
            assert not list(output.iterdir()) and not debug.closed
            debug.delete_breakpoint(point['breakpoint_id'])
            _finish(debug,base,marker)
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['outcome']=='kept'
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


def test_native_wire_existing_file_exclusive_create_reports_carry(tmp_path):
    """Exercise failed AH=5Bh return flags, not a public-policy bypass."""
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant='existing')
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            with pytest.raises(ValueError,match='exists|protected'):
                debug.workspace_provenance_start('ORIG.DAT')
            base=_runtime_base(debug);token=uuid.uuid4().hex
            ranges=[dict(start=item['runtime_address'],size=item['length'])
                    for item in debug._process['source_mapping']['live_ranges']]
            vector=int.from_bytes(debug._vectors_before[0x84:0x88],'little')
            armed=debug.vm.qmp.call('x-fdisbull-arm-dos-save-witness',
                {'token':token,'child-psp':debug._ready['child_psp'],'source-ranges':ranges,
                 'dos-path':'D:\\ORIG.DAT','int21-vector':vector})
            assert armed['active'] and armed['valid']
            done=debug.breakpoint(base+marker['done'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xdead
            native=debug.vm.qmp.call('x-fdisbull-query-dos-save-witness')
            assert native['active'] and not native['valid'] and not native['create-seen']
            assert native['events'][0]['function']==0x5b and native['events'][0]['carry'] is True
            assert native['events'][0]['ax']!=0
            debug.delete_breakpoint(done['breakpoint_id'])
            debug.vm.qmp.call('x-fdisbull-disarm-dos-save-witness',
                {'token':token,'expected-generation':native['generation']})
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


def test_guest_create_proof_survives_real_timer_interrupts(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant='irq')
    output=tmp_path/'keeps';output.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            def ticks():
                return int.from_bytes(bytes.fromhex(debug.memory(0x46c,length=4,space='physical')['hex']),'little')
            before=ticks();debug.workspace_keep_policy('SAVE.DAT',output)
            _finish(debug,base,marker)
            after=ticks();assert after>before
            state=debug.workspace_provenance_status()['native']
            assert state['valid'] and state['phase']=='ready' and state['hardware-interrupt-depth']==0
            assert state['payload-sha256']==hashlib.sha256(PAYLOAD).hexdigest()
            kept=debug.workspace_seal(timeout_ms=60000)['keep_policy']
            assert kept['outcome']=='kept'
            files=list(output.iterdir());assert len(files)==1 and files[0].read_bytes()==PAYLOAD
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


@pytest.mark.parametrize('variant',['create3c','rename','dup','seek','raw13','rawout'])
def test_unsupported_dos_or_raw_disk_activity_taints_without_keep(tmp_path,variant):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant=variant)
    output=tmp_path/'keeps';output.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',output)
            _finish(debug,base,marker)
            native=debug.workspace_provenance_status()['native']
            assert not native['valid']
            with pytest.raises(ValueError):debug.workspace_provenance_capture()
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['status']=='not-ready'
            assert list(output.iterdir())==[]
            debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and not (directory/'SAVE.DAT').exists()
