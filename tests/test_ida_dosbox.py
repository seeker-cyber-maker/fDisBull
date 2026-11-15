"""One common binary client drives a real DOSBox CPU, without IDA installed."""
import json
import os
from pathlib import Path
import socket

import pytest

from fdisbull.ida_dosbox import Endpoint,DOSRemoteDebugger
from fdisbull.project import Project
from test_debugger import game,emulator,access_game
from test_code_layers import layered_game
from test_dos_loader import mz_file


def test_real_dos_endpoint_breakpoints_registers_memory_trace_layers_state_and_restart(game,emulator,tmp_path):
    path,binary=game
    original=binary.read_bytes()
    with Endpoint(path,emulator,binary.parent) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3), password=Path(endpoint.password_file).read_text().strip())
        try:
            started=client.start(binary.name,bits=16)
            base=started['module']['base']
            code=client.read(base,12)
            assert code==bytes.fromhex('b83412bb7856ff060001ebfa')
            bp=client.breakpoint(base+3)
            assert client.read(base,12,logical=False)==code  # No INT3 bytes.
            stopped=client.run(2000)
            assert stopped['stop_reason']['kind']=='breakpoint',stopped
            assert client.registers()['eax']==0x1234
            assert client.registers()['eip']==3
            client.delete_breakpoint(bp)
            assert client.step(2000)['stop_reason']['kind']=='step'
            assert client.registers()['ebx']==0x5678
            client.set_register('eax',0xabcdef01)
            assert client.registers()['eax']==0xabcdef01
            client.set_register('ds',client.registers()['cs'])
            client.write(base+0x100,b'\x29\0')
            assert client.read(base+0x100,2)==b'\x29\0'
            watch=client.breakpoint(base+0x101,access='w')
            stopped=client.run(2000)
            assert stopped['stop_reason']['kind']=='watchpoint',stopped
            assert stopped['stop_reason']['before_access'] is False
            assert client.read(base+0x100,2)==b'\x2a\0'
            client.delete_breakpoint(watch)
            trace=client.extension('trace',name='remote-dos-trace.json',count=6,timeout_ms=2000)
            assert trace['metadata']['complete']
            client.extension('run',guest_ms=100,timeout_ms=2000,fast_forward=True)
            frame=client.extension('screenshot',name='remote-dos-grid.png',grid=True,grid_step=8)
            state=client.extension('save-state',name='private-checkpoint.sav')
            before=client.registers()['eax']
            client.set_register('eax',0x99)
            client.extension('load-state',artifact=state['artifact'])
            assert client.registers()['eax']==before
            layer=client.extension('layer-patch',name='temporary',address='1000:0000',
                                   expected_hex='b83412',data_hex='b87856',kind='ram')
            assert client.read(base,3)==bytes.fromhex('b87856')
            client.extension('layers',active=[])
            assert client.read(base,3)==bytes.fromhex('b83412')
            pid=endpoint.debug.rpc.process.pid
        finally:
            client.close()
    assert not endpoint.thread.is_alive()
    assert endpoint.debug.rpc.process.poll() is not None
    assert binary.read_bytes()==original
    with Project(path) as project:
        assert project.disassembly(address='1000:0000',version=1,lines=1)['instructions'][0]['bytes']=='b83412'
        image=tmp_path/'restored-grid.png'
        project.debug_export(frame['artifact'],image)
        assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        trace_path=tmp_path/'trace.json'
        project.debug_export(trace['artifact'],trace_path)
        saved=json.loads(trace_path.read_text())
        assert saved['complete'] and len(saved['events'])==6
        assert saved['events'][0]['project_address']=='0x1000a'
        child=project.patch('1000:0000','90')['version']
        assert project.debug_artifacts(version=child)['artifacts']==[]


def test_real_disconnect_while_cpu_runs_reaps_only_owned_emulator(game,emulator):
    path,binary=game
    with Endpoint(path,emulator,binary.parent) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3), password=Path(endpoint.password_file).read_text().strip())
        client.start(binary.name,bits=16)
        client.continue_event()
        client.close()
    assert not endpoint.thread.is_alive()
    assert endpoint.debug.rpc.process.poll() is not None


@pytest.mark.parametrize('access,expected_ip',[('r',11),('rw',8)])
def test_real_dos_wire_read_and_read_write_watch_modes(access_game,emulator,access,expected_ip):
    path,binary=access_game
    with Endpoint(path,emulator,binary.parent) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3), password=Path(endpoint.password_file).read_text().strip())
        try:
            base=client.start(binary.name,bits=16)['module']['base']
            entry=client.breakpoint(base+5)
            assert client.run(2000)['stop_reason']['kind']=='breakpoint'
            client.delete_breakpoint(entry)
            watch=client.breakpoint(base+0x101,access=access)
            hit=client.run(2000)
            assert hit['stop_reason']['kind']=='watchpoint',hit
            assert hit['stop_reason']['before_access'] is False
            assert client.registers()['eip']==expected_ip
            assert client.read(base+0x100,2)==bytes.fromhex('3412')
            client.delete_breakpoint(watch)
        finally:
            client.close()
    assert endpoint.debug.rpc.process.poll() is not None


def test_real_dos_remote_execution_layer_changes_fetch_but_guest_reads_original(layered_game,emulator):
    path,binary=layered_game
    with Endpoint(path,emulator,binary.parent) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3), password=Path(endpoint.password_file).read_text().strip())
        try:
            base=client.start(binary.name,bits=16)['module']['base']
            layer=client.extension('layer-patch',name='fetch only',address='1000:0003',
                                   expected_hex='1111',data_hex='2222',kind='execute')
            bp=client.breakpoint(base+9)
            assert client.read(base+2,3,logical=False)==bytes.fromhex('b81111')
            assert client.run(2000)['stop_reason']['kind']=='breakpoint'
            registers=client.registers()
            assert registers['eax']==0x2222  # CPU fetched the alternate immediate.
            assert registers['ebx']==0x1111  # Guest MOV read the original RAM.
            client.delete_breakpoint(bp)
            client.extension('layers',active=[])
            assert client.read(base+2,3,logical=False)==bytes.fromhex('b81111')
        finally:
            client.close()
    assert endpoint.debug.rpc.process.poll() is not None


def test_real_dos_remote_grid8_click_frame_and_timeout(tmp_path,emulator):
    binary=tmp_path/'GRID.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('b81300cd10ebfe')+bytes(505),ss=0,sp=0x200))
    path=tmp_path/'grid.fdb'
    with Project.create(path,binary) as project:project.analyze(max_instructions=10)
    with Endpoint(path,emulator,tmp_path) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3), password=Path(endpoint.password_file).read_text().strip())
        try:
            client.start(binary.name,bits=16)
            result=client.extension('run',guest_ms=100,timeout_ms=2000,fast_forward=True)
            assert result['outcome']=='guest_time'
            clicked=client.extension('click-frame',x=160,y=160,name='click.png',grid_step=8)
            assert clicked['frame']['metadata']['coordinate_grid']['target']==[160,160]
            assert clicked['frame']['metadata']['width']==320
            stopped=client.run(30)
            assert stopped['stop_reason']['kind']=='timeout'
            assert client.registers()['eip']==5
        finally:
            client.close()
    assert endpoint.debug.rpc.process.poll() is not None
