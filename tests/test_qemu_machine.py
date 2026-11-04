"""A real PC boot fixture and the shared outer-machine debugger context."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.gdb_rpc import GDBRemote
from fdisbull.project import Project


def authored_qemu_identity(tmp_path, *, version='QEMU emulator version 9.2.4', delay=0):
    executable=tmp_path/'identity-qemu'
    executable.write_text(f'#!{sys.executable}\n'
                          'import sys,time\n'
                          'if sys.argv[1:] == ["--version"]:\n'
                          f'    time.sleep({delay!r});print({version!r})\n'
                          'else:\n'
                          '    time.sleep(60)\n')
    executable.chmod(0o700)
    image=tmp_path/'authored-boot.img';image.write_bytes(b'authored boot input')
    return executable,image


@pytest.mark.skipif(os.name!='posix',reason='Authored executable identity fixture requires a POSIX host')
def test_moderately_slow_qemu_identity_allows_machine_start(tmp_path,monkeypatch):
    from fdisbull import qemu_machine
    executable,image=authored_qemu_identity(tmp_path,delay=6)
    # The subprocess identity probe is real; no emulator or QMP is needed to
    # check whether successful identity dispatch reaches machine startup.
    monkeypatch.setattr(qemu_machine,'QemuControl',lambda *args:SimpleNamespace(close=lambda:None))
    spawned=[]
    machine=qemu_machine.QemuMachine(executable,boot_image=image,on_spawn=spawned.append)
    try:
        assert machine.inputs['qemu']['version']=='QEMU emulator version 9.2.4'
        assert spawned==[machine.process] and machine.process.poll() is None
    finally:machine.close()
    assert spawned[0].poll() is not None


@pytest.mark.skipif(os.name!='posix',reason='Authored executable identity fixture requires a POSIX host')
@pytest.mark.parametrize('version',['QEMU emulator version 8.2.0','unrecognized identity'])
def test_rejected_qemu_identity_never_spawns_machine(tmp_path,version):
    from fdisbull.qemu_machine import QemuMachine
    from fdisbull.dosbox_rpc import DebuggerError
    executable,image=authored_qemu_identity(tmp_path,version=version)
    spawned=[]
    with pytest.raises(DebuggerError,match='requires QEMU >= 9.1'):
        QemuMachine(executable,boot_image=image,on_spawn=spawned.append)
    assert spawned==[]


def test_qemu_identity_timeout_remains_bounded_and_never_spawns_machine(tmp_path,monkeypatch):
    from fdisbull import qemu_machine
    from fdisbull.dosbox_rpc import DebuggerError
    executable,image=authored_qemu_identity(tmp_path)
    probes=[]
    def timeout(command,**kwargs):
        probes.append(kwargs['timeout'])
        raise subprocess.TimeoutExpired(command,kwargs['timeout'])
    monkeypatch.setattr(qemu_machine.subprocess,'check_output',timeout)
    monkeypatch.setattr(qemu_machine.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('VM spawned after identity failure'))
    spawned=[]
    machine=qemu_machine.QemuMachine.__new__(qemu_machine.QemuMachine)
    with pytest.raises(DebuggerError,match='timed out'):
        machine.__init__(executable,boot_image=image,on_spawn=spawned.append)
    assert len(probes)==1 and 6<probes[0]<=30 and spawned==[]
    assert machine.process is None and machine.temporary is None


def boot_sector():
    # cli; DS/SS=0; SP=7c00; ES=b800; print FD; DS=0; counter=7;
    # inc word [5000]; nop; jmp back to inc.  No disk or OS dependency.
    code=bytes.fromhex('fa31c08ed88ed0bc007cb800b88ec031ffb8461fabb8441fab31c08ed8c70600500700')
    loop=len(code);code+=bytes.fromhex('ff06005090ebf9')
    return code+bytes(510-len(code))+b'\x55\xaa',loop


def qemu():
    value=os.environ.get('FDISBULL_MACHINE_QEMU')
    if not value:
        if os.environ.get('FDISBULL_REQUIRE_MACHINE')=='1':pytest.fail('Missing FDISBULL_MACHINE_QEMU')
        pytest.skip('Supply FDISBULL_MACHINE_QEMU for a real QEMU boot/session check')
    return value


def test_gdb_packet_checksum_failure_is_not_retried():
    left,right=socket.socketpair();client=GDBRemote.__new__(GDBRemote)
    client.socket=left;client.lock=threading.RLock();client.console=[];client._buffer=b'';client._cursor=0
    packets=[]
    def peer():
        try:packets.append(right.recv(4096));right.sendall(b'+$OK#00');assert right.recv(1)==b''
        finally:right.close()
    worker=threading.Thread(target=peer);worker.start()
    with pytest.raises(ValueError,match='checksum'):client.request('M100,1:90')
    worker.join(2)
    assert client.socket is None and len(packets)==1 and not worker.is_alive()


def test_gdb_run_length_and_escaped_bytes_are_decoded_from_wire():
    left,right=socket.socketpair();client=GDBRemote.__new__(GDBRemote)
    client.socket=left;client.lock=threading.RLock();client.console=[];client._buffer=b'';client._cursor=0
    # 0*<space> is four zeroes; }<03> is escaped '#'.
    payload=b'0* '+b'}\x03';right.sendall(b'+$'+payload+b'#'+f'{sum(payload)%256:02x}'.encode())
    try:assert client._packet(time.monotonic()+2)==b'0000#'
    finally:client.close();right.close()


def test_real_project_boot_breakpoint_registers_memory_trace_screenshot_restart_and_isolation(tmp_path):
    exe=qemu();image,loop=boot_sector();binary=tmp_path/'boot.img';binary.write_bytes(image)
    database=tmp_path/'boot.fdb'
    with Project.create(database,binary,arch='x86',bits=16,base=0x7c00,entry=0x7c00) as project:
        project.analyze(max_instructions=32)
        original=project.disassembly(address=0x7c00,lines=4)['instructions']
        with project.machine(exe,boot_image=binary) as debug:
            assert debug.status()['state']=='stopped'
            assert debug.registers()['cpu_mode']=='real'
            bp=debug.breakpoint(0x7c00)
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert debug.memory(0x7c00,length=32)['hex']==image[:32].hex()
            debug.delete_breakpoint(bp['breakpoint_id'])
            at=debug.breakpoint(0x7c00+loop)
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            assert debug.memory(0x5000,length=2)['hex']=='0700'
            debug.delete_breakpoint(at['breakpoint_id'])
            ax=debug.registers()['registers']['rax']
            debug.write_registers({'rax':{'expected':ax,'value':'0x1234'}})
            assert debug.registers()['registers']['rax']=='0x1234'
            debug.write_registers({'rax':{'expected':'0x1234','value':ax}})
            debug.write_memory(0x5000,'2900',expected_hex='0700')
            assert debug.memory(0x5000,length=2)['hex']=='2900'
            trace=debug.trace('machine-trace.json',count=3,timeout_ms=10000,bits=16)
            assert trace['metadata']['complete']
            assert debug.memory(0x5000,length=2)['hex']=='2a00'
            frame=debug.screenshot('machine-frame.png',grid=True,grid_step=8)
            stopped=debug.run(timeout_ms=100)
            assert stopped['outcome']=='timeout' and stopped['session']['state']=='stopped'
            assert debug.memory(0x7c00,length=32)['hex']==image[:32].hex()
            run=debug.run_id
        assert debug.rpc.process.poll() is not None
        assert project.disassembly(address=0x7c00,lines=4)['instructions']==original
        child=project.patch(0x7c00,'90')['version']
        assert project.debug_artifacts(version=child)['artifacts']==[]
    with Project(database) as reopened:
        output=tmp_path/'saved-trace.json';reopened.debug_export(trace['artifact'],output)
        saved=json.loads(output.read_text());assert [e['bytes'] for e in saved['events']]==['ff060050','90','ebf9']
        assert all(e['completion']=='confirmed native step' for e in saved['events'])
        picture=tmp_path/'saved.png';reopened.debug_export(frame['artifact'],picture)
        assert picture.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert reopened.debug_runs(version=1)['runs'][0]['state']=='exited'
        assert binary.read_bytes()==image
        evidence=os.environ.get('FDISBULL_MACHINE_EVIDENCE')
        if evidence:
            where=Path(evidence);where.mkdir(parents=True,exist_ok=True)
            reopened.debug_export(trace['artifact'],where/'boot-trace.json')
            reopened.debug_export(frame['artifact'],where/'boot-grid8.png')


@pytest.mark.parametrize('access',['r','w','rw'])
def test_real_machine_watchpoint_on_cpu_read_modify_write(tmp_path,access):
    exe=qemu();image,loop=boot_sector();binary=tmp_path/'boot.img';binary.write_bytes(image)
    with Project.create(tmp_path/'watch.fdb',binary,arch='x86',bits=16,base=0x7c00,entry=0x7c00) as project:
        with project.machine(exe,boot_image=binary) as debug:
            entry=debug.breakpoint(0x7c00+loop)
            assert debug.run(timeout_ms=15000)['outcome']=='breakpoint'
            debug.delete_breakpoint(entry['breakpoint_id'])
            watch=debug.breakpoint(0x5000,access=access,length=2)
            result=debug.run(timeout_ms=5000)
            assert result['outcome']=='watchpoint',result
            assert watch['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert debug.memory(0x5000,length=2)['hex'] in ('0700','0800')
            debug.delete_breakpoint(watch['breakpoint_id'])


def test_real_foreground_interface_uses_explicit_machine_context(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    exe=qemu();image,_=boot_sector();binary=tmp_path/'boot.img';binary.write_bytes(image)
    database=tmp_path/'rpc.fdb'
    with Project.create(database,binary,arch='x86',bits=16,base=0x7c00,entry=0x7c00):pass
    with_context=DebugWorkspace()
    def invoke(method,**params):
        return respond(dict(method=method,params=dict(project=str(database),**params)),debugger=with_context)
    try:
        start=invoke('debug-launch',executable=exe,game_dir=str(tmp_path),backend='qemu-machine')
        assert start['ok'],start
        run=start['result']['run']
        assert invoke('debug-contexts',run=run)['result']['selected']=='machine'
        bp=invoke('debug-breakpoint',run=run,context='machine',address=0x7c00)
        assert bp['ok'],bp
        assert invoke('debug-run',run=run,context='machine',timeout_ms=15000)['result']['outcome']=='breakpoint'
        assert invoke('debug-registers',run=run,context='machine')['result']['cpu_mode']=='real'
        stopped=invoke('debug-stop',run=run)
        assert stopped['ok'] and stopped['result']['process_reaped']
    finally:with_context.close()
