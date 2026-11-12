"""Opt-in actual CHIP-8 TCG CPU smoke; no historical emulator claim."""
import os
from pathlib import Path
import pytest
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8')=='1':pytest.fail('CHIP-8 QEMU and qemu-img are required')
        pytest.skip('Set FDISBULL_CHIP8_QEMU and FDISBULL_CHIP8_QEMU_IMG for native smoke')
    return binary,tool


def test_native_chip8_register_ram_step_breakpoint_and_cold_restore(tmp_path):
    binary,tool=_inputs();rom=tmp_path/'probe.ch8'
    # V0=1; V0+=2; I=0x300; store V0; loop at 0x208.
    source=bytes.fromhex('6001 7002 a300 f055 1208');rom.write_bytes(source)
    db=tmp_path/'project.fdb'
    with Project.create(db,rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            assert debug.capabilities['frame'] is False
            assert debug.registers()['linear_pc']=='0x200'
            assert debug.step()['outcome']=='step'
            assert int(debug.registers()['registers']['v0'],16)==1
            assert debug.step()['outcome']=='step'
            assert int(debug.registers()['registers']['v0'],16)==3
            debug.step();debug.step()
            assert debug.memory(0x300,length=1)['hex']=='03'
            point=debug.breakpoint(0x208);result=debug.run(timeout_ms=5000)
            assert result['outcome']=='breakpoint' and result['session']['stop_reason']['breakpoint_ids']==[point['breakpoint_id']]
            debug.delete_breakpoint(point['breakpoint_id'])
            state=debug.save_state(timeout_ms=30000)
            before=debug.registers();debug.write_memory(0x300,'7f',expected_hex='03')
            old=debug.vm.process;restored=debug.load_state(state['artifact'],timeout_ms=30000)
            assert old.poll() is not None and debug.registers()==before
            assert debug.memory(0x300,length=1)['hex']=='03' and restored['host_files_restored'] is False
            artifact=state['artifact']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            old=debug.vm.process;debug.load_state(artifact,timeout_ms=30000)
            assert old.poll() is not None and debug.memory(0x300,length=1)['hex']=='03'
            assert int(debug.registers()['registers']['v0'],16)==3
    assert rom.read_bytes()==source


def test_native_chip8_json_workspace_launch_and_dispatch(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    binary,tool=_inputs();rom=tmp_path/'route.ch8';rom.write_bytes(bytes.fromhex('6001 1202'))
    db=tmp_path/'route.fdb'
    with Project.create(db,rom,arch='chip8',bits=16):pass
    workspace=DebugWorkspace()
    def call(method,**params):
        return respond(dict(method=method,params=dict(project=str(db),**params)),debugger=workspace)
    # CHIP-8 requires an explicit backend; its default cannot silently start DOS.
    default=call('debug-launch',executable=binary,game_dir=str(tmp_path))
    assert not default['ok']
    launched=call('debug-launch',executable=binary,game_dir=str(tmp_path),backend='qemu-chip8',
                  qemu_checkpoint_tool=tool,boot_timeout_ms=10000)
    assert launched['ok'],launched
    run=launched['result']['run'];process=workspace.sessions[run].rpc.process
    try:
        registers=call('debug-registers',run=run)
        assert registers['ok'] and registers['result']['linear_pc']=='0x200'
        step=call('debug-step',run=run)
        assert step['ok'] and step['result']['outcome']=='step'
        point=call('debug-breakpoint',run=run,address=0x202)
        assert point['ok'],point
        stopped=call('debug-run',run=run,timeout_ms=5000)
        assert stopped['ok'] and stopped['result']['outcome']=='breakpoint'
        status=call('debug-status',run=run)
        assert status['ok'] and status['result']['state']=='stopped'
        for method,kwargs in [('debug-hook',dict(address=0x200,actions=[])),
                              ('debug-layer-patch',dict(name='unsupported',address=0x200,
                                  expected_hex='60',data_hex='00'))]:
            denied=call(method,run=run,**kwargs)
            assert not denied['ok'] and denied['error']['type']=='ValueError'
        finished=call('debug-stop',run=run)
        assert finished['ok'] and finished['result']['process_reaped'] and process.poll() is not None
    finally:
        workspace.close()
