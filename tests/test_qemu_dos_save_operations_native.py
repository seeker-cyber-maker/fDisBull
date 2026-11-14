"""N23 save-v2: source-owned DOS overwrite, seek, truncate and rename evidence."""
import hashlib
import os
import struct
import pytest
from fdisbull.project import Project
from support.dos_process_fixture import assemble
from test_qemu_dos_workspace_native import _inputs,_launch,_mz,_runtime_base,_word
from test_qemu_dos_provenance_native import _proof_doc


def _runtime():
    runtime=_inputs();binary=os.environ.get('FDISBULL_QEMU_SAVE_OPERATIONS')
    if not binary:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS')=='1':pytest.fail('FDISBULL_QEMU_SAVE_OPERATIONS is required')
        pytest.skip('Supply FDISBULL_QEMU_SAVE_OPERATIONS')
    runtime['qemu']=binary
    return runtime


def _fixture(directory,nasm,variant='cycles'):
    if variant=='cycles':
        program=r'''
    mov dx,finalname
    xor cx,cx
    mov ax,3c00h
    int 21h
    jc failed
    mov [handle],ax
    mov bx,ax
    mov dx,abcd
    mov cx,4
    mov ah,40h
    int 21h
    jc failed
    cmp ax,4
    jne failed
    sti
    hlt
    hlt
    hlt
    mov bx,[handle]
    xor cx,cx
    mov dx,1
    mov ax,4200h
before_seek:
    int 21h
    jc failed
    mov bx,[handle]
    mov dx,xy
    mov cx,2
    mov ah,40h
    int 21h
    jc failed
    mov bx,[handle]
    mov cx,0ffffh
    mov dx,0ffffh
    mov ax,4201h
    int 21h
    jc failed
    mov bx,[handle]
    mov dx,zbyte
    mov cx,1
    mov ah,40h
    int 21h
    jc failed
    mov bx,[handle]
    mov cx,0ffffh
    mov dx,0ffffh
    mov ax,4202h
    int 21h
    jc failed
    mov bx,[handle]
    xor cx,cx
    mov ah,40h
    int 21h
    jc failed
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
    mov word [status],0a11ah
first_done:
    nop
    mov dx,finalname
    mov ax,3d02h
    int 21h
    jc failed
    mov [handle],ax
    mov bx,ax
    mov cx,0ffffh
    mov dx,0ffffh
    mov ax,4202h
    int 21h
    jc failed
    mov bx,[handle]
    mov dx,exclamation
    mov cx,1
    mov ah,40h
    int 21h
    jc failed
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
    jmp success
before_rename:
    nop
'''
    elif variant=='replace':
        program=r'''
    mov dx,tempname
    xor cx,cx
    mov ax,3c00h
    int 21h
    jc failed
    mov [handle],ax
    mov bx,ax
    mov dx,newbytes
    mov cx,3
    mov ah,40h
    int 21h
    jc failed
    mov bx,[handle]
    mov ah,68h
    int 21h
    jc failed
    mov bx,[handle]
    mov ah,3eh
    int 21h
    jc failed
    mov dx,finalname
    mov ah,41h
    int 21h
    jc failed
    push ds
    pop es
    mov dx,tempname
    mov di,finalname
    mov ah,56h
before_rename:
    int 21h
    jc failed
    mov ah,0dh
    int 21h
    jmp success
before_seek:
    nop
first_done:
    nop
'''
    elif variant=='overwrite-existing':
        program=r'''
    mov dx,finalname
    xor cx,cx
    mov ax,3c00h
    int 21h
    jc failed
    mov bx,ax
    mov dx,newbytes
    mov cx,3
    mov ah,40h
    int 21h
    jc failed
    mov ah,3eh
    int 21h
    jc failed
    mov ah,0dh
    int 21h
    jmp success
before_seek:
    nop
before_rename:
    nop
first_done:
    nop
'''
    elif variant=='open-existing':
        program=r'''
    mov dx,finalname
    mov ax,3d02h
    int 21h
    jc failed
    mov [handle],ax
    mov bx,ax
    xor cx,cx
    mov dx,1
    mov ax,4200h
before_seek:
    int 21h
    jc failed
    mov bx,[handle]
    mov dx,xy
    mov cx,2
    mov ah,40h
    int 21h
    jc failed
    mov bx,[handle]
    mov ah,3eh
    int 21h
    jc failed
    mov ah,0dh
    int 21h
    jmp success
before_rename:
    nop
first_done:
    nop
'''
    else:
        extra={
          'gap':r'''mov bx,[handle]
    xor cx,cx
    mov dx,5
    mov ax,4200h
    int 21h
    mov bx,[handle]
    mov dx,zbyte
    mov cx,1
    mov ah,40h
    int 21h''',
          'gap-zero':r'''mov bx,[handle]
    xor cx,cx
    mov dx,5
    mov ax,4200h
    int 21h
    mov bx,[handle]
    xor cx,cx
    mov ah,40h
    int 21h''',
          'failed-seek':r'''mov bx,[handle]
    mov cx,0ffffh
    mov dx,0ffffh
    mov ax,4200h
    int 21h''',
          'dup':r'''mov bx,[handle]
    mov ah,45h
    int 21h
    jc afterdup
    mov bx,ax
    mov ah,3eh
    int 21h
afterdup:''',
          'failed-rename':r'''mov bx,[handle]
    mov ah,3eh
    int 21h
    mov dx,tempname
    xor cx,cx
    mov ax,3c00h
    int 21h
    jc afterclose
    mov bx,ax
    mov ah,3eh
    int 21h
    push ds
    pop es
    mov dx,finalname
    mov di,tempname
    mov ah,56h
before_rename:
    int 21h
    jmp afterclose''',
        }[variant]
        if variant!='failed-rename':extra+='\n    mov bx,[handle]\n    mov ah,3eh\n    int 21h'
        program=r'''
    mov dx,finalname
    xor cx,cx
    mov ax,3c00h
    int 21h
    jc failed
    mov [handle],ax
    BAD_OPERATION
afterclose:
    mov ah,0dh
    int 21h
    jmp success
before_seek:
    nop
first_done:
    nop
'''.replace('BAD_OPERATION',extra)
        if variant!='failed-rename': program+='\nbefore_rename:\n    nop\n'
    code=assemble(directory,'save-ops-'+variant,r'''
bits 16
org 100h
    push cs
    pop ds
    PROGRAM
success:
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
finalname: db 'D:\SAVE.DAT',0
tempname: db 'D:\TEMP.DAT',0
abcd: db 'ABCD'
xy: db 'XY'
zbyte: db 'Z'
exclamation: db '!'
newbytes: db 'NEW'
    db 'FDSO'
    dw first_done-100h,done-100h,status-100h,before_seek-100h,before_rename-100h
'''.replace('PROGRAM',program),nasm)
    if code[-14:-10]!=b'FDSO':raise ValueError('Save operations fixture marker missing')
    return code,dict(zip(('first','done','status','seek','rename'),struct.unpack_from('<5H',code,len(code)-10)))


def _setup(tmp_path,runtime,variant='cycles',kind='com'):
    build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    program,marker=_fixture(build,runtime['NASM'],variant);source=_mz(program) if kind=='mz' else program
    binary=directory/('PROBE.EXE' if kind=='mz' else 'PROBE.COM');binary.write_bytes(source)
    (directory/'ORIG.DAT').write_bytes(b'original')
    return directory,binary,source,marker


def _stop_at(debug,address):
    point=debug.breakpoint(address);assert debug.run(timeout_ms=25000)['outcome']=='breakpoint'
    debug.delete_breakpoint(point['breakpoint_id'])


def _finish(debug,base,marker):
    _stop_at(debug,base+marker['done']);assert _word(debug,base+marker['status'])==0xbeef


def _initial_file_generation(project,runtime,directory):
    with _launch(project,runtime,directory) as debug:
        base=debug.workspace_status()['generation']['artifact']
        return debug.workspace_edit(base,'create',path='SAVE.DAT',data=b'OLD')['generation']['artifact']


@pytest.mark.parametrize('kind',['com','mz'])
def test_overwrite_seek_truncate_reopen_versions_and_rewind(tmp_path,kind):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,kind=kind)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            def ticks():
                return int.from_bytes(bytes.fromhex(debug.memory(0x46c,length=4,space='physical')['hex']),'little')
            before=ticks();policy=debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save')['policy']['artifact']
            _stop_at(debug,base+marker['first'])
            assert ticks()>before
            assert debug.workspace_provenance_status()['native']['hardware-interrupt-depth']==0
            first=debug.workspace_seal(timeout_ms=60000);assert first['keep_policy']['outcome']=='kept'
            assert debug.workspace_read('SAVE.DAT',first['workspace']['generation']['artifact'])['data']==b'AXZ'
            checkpoint=debug.save_state()
            _finish(debug,base,marker)
            second=debug.workspace_seal(timeout_ms=60000);assert second['keep_policy']['outcome']=='kept'
            assert debug.workspace_read('SAVE.DAT',second['workspace']['generation']['artifact'])['data']==b'AX!'
            assert sorted(p.read_bytes() for p in keeps.iterdir())==[b'AX!',b'AXZ']
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['outcome']=='already-kept'
            debug.load_state(checkpoint['artifact'],timeout_ms=60000)
            _finish(debug,base,marker)
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['outcome']=='already-kept'
            assert sorted(p.read_bytes() for p in keeps.iterdir())==[b'AX!',b'AXZ']
            debug.workspace_keep_policy_enabled(policy,False);debug.workspace_provenance_stop()
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'
    assert not (directory/'SAVE.DAT').exists()


def test_temp_replaces_eligible_prior_file_by_delete_and_rename(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant='replace')
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        generation=_initial_file_generation(project,runtime,directory)
        with _launch(project,runtime,directory,generation=generation) as debug:
            base=_runtime_base(debug);armed=debug.workspace_provenance_start('SAVE.DAT',mode='save',temporary_path='TEMP.DAT')
            assert armed['native']['initial-exists'] and bytes.fromhex(armed['native']['initial-payload-hex'])==b'OLD'
            _finish(debug,base,marker);proof=debug.workspace_provenance_capture()
            assert proof['payload_sha256']==hashlib.sha256(b'NEW').hexdigest()
            assert debug.workspace_read('SAVE.DAT',proof['generation'])['data']==b'NEW'
            assert 'TEMP.DAT' not in {x['dos_path'] for x in debug.workspace_files(proof['generation'])['entries']}
            doc=_proof_doc(project,proof);events=doc['native']['events']
            assert any(e['function']==0x41 and not e['carry'] for e in events)
            assert any(e['function']==0x56 and not e['carry'] for e in events)
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


@pytest.mark.parametrize('variant,expected',[('open-existing',b'OXY'),('overwrite-existing',b'NEW')])
def test_open_or_truncate_preexisting_authored_eligible_file(tmp_path,variant,expected):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant=variant)
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        generation=_initial_file_generation(project,runtime,directory)
        with _launch(project,runtime,directory,generation=generation) as debug:
            base=_runtime_base(debug);debug.workspace_provenance_start('SAVE.DAT',mode='save')
            _finish(debug,base,marker);proof=debug.workspace_provenance_capture()
            assert debug.workspace_read('SAVE.DAT',proof['generation'])['data']==expected
            assert proof['payload_sha256']==hashlib.sha256(expected).hexdigest()
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source


def test_reopen_unproven_save_requires_exact_stored_v2_predecessor(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    database=tmp_path/'project.fdb'
    with Project.create(database,binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_provenance_start('SAVE.DAT',mode='save')
            _finish(debug,base,marker)
            first=debug.workspace_provenance_capture()
            assert debug.workspace_read('SAVE.DAT',first['generation'])['data']==b'AX!'
            old_doc=_proof_doc(project,first)
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    with Project(database) as project:
        with _launch(project,runtime,directory,generation=first['generation']) as debug:
            base=_runtime_base(debug)
            with pytest.raises(ValueError,match='predecessor'):
                debug.workspace_provenance_start('SAVE.DAT',mode='save')
            with pytest.raises(ValueError,match='hash'):
                debug.workspace_provenance_start('SAVE.DAT',mode='save',
                    predecessor={'artifact':first['artifact'],'sha256':'0'*64})
            reference={'artifact':first['artifact'],'sha256':first['sha256']}
            armed=debug.workspace_provenance_start('SAVE.DAT',mode='save',predecessor=reference)
            assert armed['native']['initial-exists'] is True
            assert bytes.fromhex(armed['native']['initial-payload-hex'])==b'AX!'
            _finish(debug,base,marker)
            second=debug.workspace_provenance_capture()
            assert second['generation']!=first['generation']
            assert debug.workspace_read('SAVE.DAT',second['generation'])['data']==b'AX!'
            assert _proof_doc(project,first)==old_doc
            doc=_proof_doc(project,second)
            assert doc['binding']['predecessor']==reference
            kept=debug.workspace_keep('SAVE.DAT',tmp_path/'verified.dat',second['generation'],
                       provenance={'artifact':second['artifact'],'sha256':second['sha256']})
            assert kept['guest_create_provenance'] is True and (tmp_path/'verified.dat').read_bytes()==b'AX!'
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'
    assert not (directory/'SAVE.DAT').exists()


@pytest.mark.parametrize('operation',['seek','rename'])
def test_checkpoint_mid_save_call_then_fdb_reopen(tmp_path,operation):
    runtime=_runtime();variant='cycles' if operation=='seek' else 'replace'
    directory,binary,source,marker=_setup(tmp_path,runtime,variant=variant)
    database=tmp_path/'project.fdb'
    with Project.create(database,binary,image='com') as project:
        generation=_initial_file_generation(project,runtime,directory) if operation=='rename' else None
        with _launch(project,runtime,directory,generation=generation) as debug:
            base=_runtime_base(debug)
            options={'mode':'save'}
            if operation=='rename':options['temporary_path']='TEMP.DAT'
            debug.workspace_provenance_start('SAVE.DAT',**options)
            _stop_at(debug,base+marker[operation])
            offset,segment=struct.unpack_from('<HH',debug._vectors_before,0x21*4)
            point=debug.breakpoint(segment*16+offset)
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            native=debug.workspace_provenance_status()['native']
            expected=0x42 if operation=='seek' else 0x56
            assert native['pending'] and native['pending-function']==expected
            saved=debug.save_state()
            resume_generation=saved['metadata']['workspace']['generation']['artifact']
    with Project(database) as project:
        with _launch(project,runtime,directory,generation=resume_generation) as debug:
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            native=debug.workspace_provenance_status()['native']
            assert native['pending'] and native['pending-function']==expected
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            _finish(debug,base,marker)
            proof=debug.workspace_provenance_capture();doc=_proof_doc(project,proof)
            events=[e for e in doc['native']['events'] if e['function']==expected]
            # Three 42h calls occur in the full cycles fixture; only one is
            # the saved first absolute seek. Rename occurs exactly once.
            if operation=='seek':
                assert len(events)==4 and sum(e['mode']==0 and e['seek-offset']==1 for e in events)==1
                assert debug.workspace_read('SAVE.DAT',proof['generation'])['data']==b'AX!'
            else:
                assert len(events)==1
                assert debug.workspace_read('SAVE.DAT',proof['generation'])['data']==b'NEW'
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


@pytest.mark.parametrize('variant',['gap','gap-zero','failed-seek','failed-rename','dup'])
def test_unsupported_or_failed_save_activity_cannot_grant_keep(tmp_path,variant):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant=variant)
    output=tmp_path/'keeps';output.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            with pytest.raises(ValueError,match='exists|protected'):
                debug.workspace_provenance_start('orig.dat',mode='save')
            options={'mode':'save'}
            if variant=='failed-rename':options['temporary_path']='TEMP.DAT'
            debug.workspace_keep_policy('SAVE.DAT',output,**options)
            _finish(debug,base,marker)
            native=debug.workspace_provenance_status()['native']
            assert not native['valid']
            with pytest.raises(ValueError):debug.workspace_provenance_capture()
            assert debug.workspace_seal(timeout_ms=60000)['keep_policy']['status']=='not-ready'
            assert list(output.iterdir())==[]
            debug.workspace_provenance_stop();assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'
