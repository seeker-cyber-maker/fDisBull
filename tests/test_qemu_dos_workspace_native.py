"""Native FreeDOS private-workspace checkpoints with authored COM/MZ probes."""
import hashlib
import os
from pathlib import Path
import struct

import pytest
from fdisbull.project import Project
from fdisbull.dos_workspace_guest import observe_guest_files
from support.dos_workspace_fixture import workspace_probe


def _inputs():
    result={key:os.environ.get(key) for key in (
        'FDISBULL_FREEDOS_RUNTIME','FDISBULL_QEMU_DOS_FIRMWARE',
        'FDISBULL_QEMU_DOS_MCOPY','FDISBULL_QEMU_IMG','NASM')}
    result['qemu']=os.environ.get('FDISBULL_QEMU_LAYERS') or os.environ.get('FDISBULL_QEMU_DOS')
    missing=[key for key,value in result.items() if not value]
    if missing:
        if any(os.environ.get(key)=='1' for key in ('FDISBULL_REQUIRE_QEMU_DOS_OS','FDISBULL_REQUIRE_QEMU_LAYERS')):
            pytest.fail('Missing native workspace inputs: '+', '.join(missing))
        pytest.skip('Supply native workspace inputs: '+', '.join(missing))
    return result


def _mz(com):
    module=b'\0'*256+com
    total=64+len(module);header=bytearray(64)
    # Original COM uses ORG 100h, so enter at CS:0100 with the same addresses.
    struct.pack_into('<14H',header,0,0x5a4d,total%512,(total+511)//512,0,4,
                     0x200,0xffff,0x100,0x1000,0,0x100,0,0x1c,0)
    return bytes(header)+module


def _launch(project, runtime, directory, *, generation=None, root=None):
    return project.debugger(runtime['qemu'],directory,backend='qemu-dos',
        freedos_runtime=runtime['FDISBULL_FREEDOS_RUNTIME'],
        dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],qemu_transport='pipe',
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'],dos_generation=generation,
        dos_directory=root,
        boot_timeout_ms=60000)


def _word(debug,address):
    return int.from_bytes(bytes.fromhex(debug.memory(address,length=2)['hex']),'little')


def _runtime_base(debug):
    value=debug.registers()['linear_pc']
    return int(value,0) if isinstance(value,str) else value


def _open(debug):
    ready=debug._ready
    return observe_guest_files(debug._read,ready['list_of_lists_segment'],
                               ready['list_of_lists_offset'],ready['child_psp'])


@pytest.mark.parametrize('kind',['com','mz'])
def test_workspace_open_handle_checkpoint_and_crud(tmp_path,kind):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    com,markers=workspace_probe(build,runtime['NASM']);source=_mz(com) if kind=='mz' else com
    binary=directory/('PROBE.EXE' if kind=='mz' else 'PROBE.COM');binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    with Project.create(tmp_path/'project.fdb',binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            point=debug.breakpoint(base+markers['open_ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            open_state=_open(debug)
            opened=[x for x in open_state['handles'] if x['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2 and opened[0]['size']==4
            saved=debug.save_state()
            assert saved['metadata']['workspace_state_present'] is True
            debug.delete_breakpoint(point['breakpoint_id'])
            finish=debug.breakpoint(base+markers['done'])
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert _word(debug,base+markers['status'])==0xbeef
            assert debug.memory(base+markers['second_read'],length=2)['hex']=='4344'
            debug.delete_breakpoint(finish['breakpoint_id'])
            sealed=debug.workspace_seal(timeout_ms=60000)
            generation=sealed['workspace']['generation']['artifact']
            assert debug.workspace_read('RENAMED.DAT',generation)['data']==bytes.fromhex('1000ff41')
            names={x['dos_path'] for x in debug.workspace_files(generation)['entries']}
            assert 'EXIST.BIN' in names and 'RENAMED.DAT' in names and 'GONE.BIN' not in names
            exported = tmp_path / 'kept-output.dat'
            receipt = debug.workspace_export('RENAMED.DAT', exported, generation)
            assert receipt['durable'] and exported.read_bytes() == bytes.fromhex('1000ff41')
            with pytest.raises(ValueError, match='witnessed new'):
                debug.workspace_keep('RENAMED.DAT', tmp_path / 'unproven.dat', generation)
            with pytest.raises((ValueError, FileExistsError)):
                debug.workspace_export('RENAMED.DAT', directory / 'EXIST.BIN', generation)
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            assert exported.read_bytes() == bytes.fromhex('1000ff41')
            assert 'RENAMED.DAT' not in {x['dos_path'] for x in debug.workspace_files()['entries']}
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            reopened=[x for x in _open(debug)['handles'] if x['dos_name']=='EXIST.BIN']
            assert len(reopened)==1 and reopened[0]['position']==2
            finish=debug.breakpoint(base+markers['done'])
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert debug.memory(base+markers['second_read'],length=2)['hex']=='4344'
            assert _word(debug,base+markers['status'])==0xbeef
            debug.delete_breakpoint(finish['breakpoint_id'])
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}==original


def test_workspace_cold_restore_keeps_open_position_without_original_root(tmp_path):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    source,markers=workspace_probe(build,runtime['NASM']);binary=directory/'PROBE.COM';binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    database=tmp_path/'project.fdb'
    with Project.create(database,binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);point=debug.breakpoint(base+markers['open_ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            saved=debug.save_state();generation=saved['metadata']['workspace']['generation']['artifact']
    # Preserve the authored original tree but make its admitted path unavailable.
    directory.rename(tmp_path/'preserved-input')
    with Project(database) as project:
        with _launch(project,runtime,directory,generation=generation) as debug:
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            reopened=[x for x in _open(debug)['handles'] if x['dos_name']=='EXIST.BIN']
            assert len(reopened)==1 and reopened[0]['position']==2
            finish=debug.breakpoint(base+markers['done'])
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert debug.memory(base+markers['second_read'],length=2)['hex']=='4344'
            assert _word(debug,base+markers['status'])==0xbeef
            debug.delete_breakpoint(finish['breakpoint_id'])
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert (tmp_path/'preserved-input'/'EXIST.BIN').read_bytes()==b'ABCD'


def test_workspace_staged_write_cold_boot_uses_generation(tmp_path):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    source,markers=workspace_probe(build,runtime['NASM']);binary=directory/'PROBE.COM';binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    database=tmp_path/'project.fdb'
    with Project.create(database,binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=debug.workspace_status()['generation']['artifact']
            staged=debug.workspace_edit(base,'write',path='EXIST.BIN',data=b'WXYZ',
                         expected_sha256=hashlib.sha256(b'ABCD').hexdigest())
            assert staged['active'] is False
            assert debug.workspace_status()['generation']['artifact']==base
            assert debug.workspace_read('EXIST.BIN',staged['generation']['artifact'])['data']==b'WXYZ'
            generation=staged['generation']['artifact']
    with Project(database) as project:
        with _launch(project,runtime,directory,generation=generation) as debug:
            base=_runtime_base(debug);point=debug.breakpoint(base+markers['done'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            assert _word(debug,base+markers['status'])==0xbeef
            assert debug.memory(base+markers['second_read'],length=2)['hex']=='595a'
            debug.delete_breakpoint(point['breakpoint_id'])
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert (directory/'EXIST.BIN').read_bytes()==b'ABCD'


def test_workspace_subdirectory_override_sets_relative_asset_directory(tmp_path):
    runtime = _inputs()
    build = tmp_path / 'build'; build.mkdir()
    root = tmp_path / 'input'; root.mkdir()
    directory = root / 'Long game directory'; directory.mkdir()
    source, markers = workspace_probe(build, runtime['NASM'])
    binary = directory / 'PROBE.COM'; binary.write_bytes(source)
    (directory / 'EXIST.BIN').write_bytes(b'ABCD')
    (directory / 'GONE.BIN').write_bytes(b'original')
    with Project.create(tmp_path / 'nested.fdb', binary, image='com') as project:
        with _launch(project, runtime, directory, root=root) as debug:
            status = debug.workspace_status()
            assert '\\' in status['source_dospath']
            base = _runtime_base(debug)
            finish = debug.breakpoint(base + markers['done'])
            assert debug.run(timeout_ms=20000)['outcome'] == 'breakpoint'
            assert _word(debug, base + markers['status']) == 0xbeef
            debug.delete_breakpoint(finish['breakpoint_id'])
            sealed = debug.workspace_seal()
            parent = status['source_dospath'].rpartition('\\')[0]
            assert debug.workspace_read(parent + '\\RENAMED.DAT')['data'] == bytes.fromhex('1000ff41')
            assert sealed['workspace']['generation']['artifact']
    assert (directory / 'EXIST.BIN').read_bytes() == b'ABCD'
    assert (directory / 'GONE.BIN').read_bytes() == b'original'


def _dirty_search_probe(directory,nasm):
    from support.dos_process_fixture import assemble
    code=assemble(directory,'workspace-dirty-search',r'''
bits 16
org 100h
    push cs
    pop ds
    mov dx, filename
    mov ax, 3d02h
    int 21h
    jc failed
    mov [handle],ax
    mov bx,ax
    mov dx,payload
    mov cx,2
    mov ah,40h
    int 21h
    jc failed
    cmp ax,2
    jne failed
    mov dx,dta
    mov ah,1ah
    int 21h
    mov dx,pattern
    xor cx,cx
    mov ah,4eh
    int 21h
    jc failed
    mov word [status],0a11ah
ready:
    nop
    mov ah,4fh
    int 21h
    jc failed
    mov si,dta+30
    mov di,second_name
    mov cx,13
    push ds
    pop es
    rep movsb
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
filename: db 'EXIST.BIN',0
pattern: db '*.BIN',0
payload: db 0ah,0bh
second_name: times 13 db 0
dta: times 43 db 0
    db 'FDSH'
    dw ready-100h,done-100h,status-100h,second_name-100h,dta-100h
''',nasm)
    if code[-14:-10]!=b'FDSH': raise ValueError('Dirty-search marker missing')
    return code,dict(zip(('ready','done','status','second_name','dta'),struct.unpack_from('<5H',code,len(code)-10)))


def test_workspace_dirty_handle_and_findnext_cursor_restore(tmp_path):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    source,marker=_dirty_search_probe(build,runtime['NASM']);binary=directory/'PROBE.COM';binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);point=debug.breakpoint(base+marker['ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xa11a
            opened=[entry for entry in _open(debug)['handles'] if entry['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2 and opened[0]['access']=='read-write'
            saved=debug.save_state()
            debug.delete_breakpoint(point['breakpoint_id'])
            finish=debug.breakpoint(base+marker['done'])
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xbeef
            first_name=debug.memory(base+marker['second_name'],length=13)['hex']
            assert bytes.fromhex(first_name).split(b'\0',1)[0].upper() in (b'EXIST.BIN',b'GONE.BIN')
            debug.delete_breakpoint(finish['breakpoint_id'])
            sealed=debug.workspace_seal(timeout_ms=60000)
            assert debug.workspace_read('EXIST.BIN',sealed['workspace']['generation']['artifact'])['data']==b'\x0a\x0bCD'
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            opened=[entry for entry in _open(debug)['handles'] if entry['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2
            finish=debug.breakpoint(base+marker['done'])
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xbeef
            assert debug.memory(base+marker['second_name'],length=13)['hex']==first_name
            debug.delete_breakpoint(finish['breakpoint_id'])
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert (directory/'EXIST.BIN').read_bytes()==b'ABCD'
