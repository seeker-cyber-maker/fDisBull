"""The ordinary DOS project API through Linux/QEMU, including native state IO."""
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_dos_loader import mz_file


def inputs():
    names=('FDISBULL_MACHINE_QEMU','FDISBULL_DOS_KERNEL','FDISBULL_DOS_INITRAMFS')
    if any(not os.environ.get(n) for n in names):
        if os.environ.get('FDISBULL_REQUIRE_DOS_QEMU')=='1':pytest.fail('Missing DOS/QEMU acceptance inputs')
        pytest.skip('Supply FDISBULL_MACHINE_QEMU, FDISBULL_DOS_KERNEL and FDISBULL_DOS_INITRAMFS')
    return [os.environ[n] for n in names]


def test_dos_qemu_preflight_rejects_implicit_private_assets_before_launch(tmp_path):
    binary=tmp_path/'GAME.EXE';binary.write_bytes(mz_file())
    with Project.create(tmp_path/'game.fdb',binary) as project:
        with pytest.raises(ValueError,match='requires kernel'):
            project.debugger('missing',tmp_path,backend='dosbox-qemu')
        secret=tmp_path/'private.sav';secret.write_bytes(b'private')
        with pytest.raises(ValueError,match='databases or saved states'):
            project.debugger('missing',tmp_path,backend='dosbox-qemu',kernel='k',initramfs='i',files=['GAME.EXE','private.sav'])
        assert project.debug_runs()['runs']==[]


def test_real_dos_qemu_same_api_layers_watches_states_grid_click_machine_context_and_restart(tmp_path):
    qemu,kernel,runtime=inputs()
    # Mode 13h; DS=CS; AX immediate; BX reads that immediate as data;
    # store BX; poll mouse, increment counter when left held, store x/y.
    code=bytes.fromhex('b81300cd100e1fb811118b1e0800891e000190b80300cd33f7c301007404ff060001890e020189160401ebe7')
    binary=tmp_path/'DOS.EXE';binary.write_bytes(mz_file(code+bytes(512-len(code)),ss=0,sp=0x200))
    database=tmp_path/'dos.fdb'
    with Project.create(database,binary) as project:
        project.analyze(max_instructions=64)
        original=project.disassembly(address='1000:0007',lines=1)['instructions']
        with project.debugger(qemu,tmp_path,backend='dosbox-qemu',kernel=kernel,initramfs=runtime) as debug:
            assert [c['id'] for c in debug.contexts()['contexts']]==['dos-cpu','machine']
            overlay=debug.layer_patch('fetch immediate','1000:0008',expected_hex='1111',data_hex='2222',kind='execute')
            bp=debug.breakpoint('1000:0012')
            assert debug.run(timeout_ms=10000)['outcome']=='breakpoint'
            regs=debug.registers()['general']
            assert int(regs['eax'],16)==0x2222 and int(regs['ebx'],16)==0x1111
            assert debug.memory('1000:0007',length=3)['hex']=='b81111'
            debug.delete_breakpoint(bp['breakpoint_id'])
            debug.run(guest_ms=100,timeout_ms=10000,fast_forward=True)
            snapshot=debug.save_state('private-dos.sav')
            ram=debug.layer_patch('RAM marker','1000:0120',expected_hex='00',data_hex='29',kind='ram')
            assert debug.memory('1000:0120',length=1)['hex']=='29'
            debug.layers([overlay['layer']])
            assert debug.memory('1000:0120',length=1)['hex']=='00'
            debug.load_state(snapshot['artifact'])
            with pytest.raises(ValueError,match='No complete framebuffer'):
                debug.screenshot('invalidated-frame.png')
            assert debug.rpc.process.poll() is None
            debug.run(guest_ms=50,timeout_ms=10000,fast_forward=True)
            frame=debug.screenshot('dos-grid8.png',grid=True,grid_step=8)
            assert (frame['metadata']['width'],frame['metadata']['height'])==(320,200)
            click=debug.click_frame(80,80,name='dos-click.png',grid_step=8,hold_ms=30)
            assert click['frame']['metadata']['coordinate_grid']['target']==[80,80]
            watch=debug.breakpoint('1000:0100',access='w',length=2)
            stopped=debug.run(timeout_ms=10000,fast_forward=True)
            assert stopped['outcome']=='breakpoint' and stopped['session']['stop_reason'].get('data_access'),stopped
            for item in watch['breakpoints']:debug.delete_breakpoint(item['breakpoint_id'])
            assert int.from_bytes(bytes.fromhex(debug.memory('1000:0100',length=2)['hex']),'little')>0x1111
            debug.run(guest_ms=100,timeout_ms=10000,fast_forward=True)
            trace=debug.trace('dos-trace.json',count=96,timeout_ms=10000)
            assert trace['metadata']['complete']
            debug.machine.pause()
            assert debug.machine.registers()['cpu_mode']=='long'
            assert debug.machine.memory(0x5000,length=16)['space']=='physical'
            with pytest.raises(ValueError,match='Resume the machine'):
                debug.registers()
            debug.machine.resume()
            assert debug.registers()['cpu_mode']=='real'
            debug.load_state(snapshot['artifact'])
            assert debug.memory('1000:0100',length=2)['hex']=='1111'
            run=debug.run_id
        assert debug.rpc.process.poll() is not None
        assert project.disassembly(address='1000:0007',version=1,lines=1)['instructions']==original
        child=project.patch('1000:0007','90')['version']
        assert project.debug_artifacts(version=child)['artifacts']==[]
    with Project(database) as project:
        output=tmp_path/'trace-export.json';project.debug_export(trace['artifact'],output)
        assert len(json.loads(output.read_text())['events'])==96
        image=tmp_path/'frame.png';project.debug_export(frame['artifact'],image)
        assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        evidence=os.environ.get('FDISBULL_DOS_QEMU_EVIDENCE')
        if evidence:
            where=Path(evidence);where.mkdir(parents=True,exist_ok=True)
            for artifact in project.debug_artifacts(version=1,run=run)['artifacts']:
                if artifact['kind']!='state':project.debug_export(artifact['id'],where/artifact['name'])
        # Native DOS state remains usable after a whole owned VM is replaced.
        with project.debugger(qemu,tmp_path,backend='dosbox-qemu',kernel=kernel,initramfs=runtime,version=1) as debug:
            debug.load_state(snapshot['artifact'])
            assert debug.memory('1000:0100',length=2)['hex']=='1111'


def test_real_remote_disconnect_during_qemu_boot_reaps_pending_machine(tmp_path):
    import socket,threading,time
    from fdisbull.ida_dosbox import Endpoint,DOSRemoteDebugger
    qemu,kernel,runtime=inputs()
    binary=tmp_path/'WAIT.EXE';binary.write_bytes(mz_file(bytes.fromhex('ebfe')+bytes(510),ss=0,sp=0x200))
    database=tmp_path/'wait.fdb'
    with Project.create(database,binary):pass
    endpoint=Endpoint(database,qemu,tmp_path,backend='dosbox-qemu',kernel=kernel,initramfs=runtime)
    failures=[]
    with endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=3))
        def launch():
            try:client.start(binary.name,bits=16)
            except (OSError,ValueError,AttributeError) as error:failures.append(type(error).__name__)
        thread=threading.Thread(target=launch);thread.start()
        deadline=time.monotonic()+15
        while endpoint._spawned is None and time.monotonic()<deadline:time.sleep(.02)
        assert endpoint._spawned is not None
        client.close()
    thread.join(5)
    assert not thread.is_alive() and not endpoint.thread.is_alive()
    assert endpoint._spawned.poll() is not None and failures
