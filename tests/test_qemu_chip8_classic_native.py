"""Opt-in real QEMU RNG admission and checkpoint witness."""
import os
import pytest
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_CLASSIC_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_CLASSIC_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_CLASSIC')=='1':pytest.fail('CHIP-8 classic QEMU and qemu-img required')
        pytest.skip('Set FDISBULL_CHIP8_CLASSIC_QEMU and FDISBULL_CHIP8_CLASSIC_QEMU_IMG')
    return binary,tool


def test_seed_cas_and_checkpoint_restore_rng_without_hidden_cpu_execution(tmp_path):
    binary,tool=_inputs();rom=tmp_path/'rng.ch8';source=bytes.fromhex('c0ff c100 1200');rom.write_bytes(source)
    with Project.create(tmp_path/'rng.fdb',rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            assert debug.capabilities['rng']
            regs=debug.registers();before=debug.chip8_environment()
            ram=debug.memory(0,length=4096)['hex']
            assert (before['rng-seed'],before['rng-state'],before['rng-draws'])==(0,0,0)
            for seed,generation in ((123,before['state-generation']+1),(-1,before['state-generation']),
                                    (2**32,before['state-generation']),(True,before['state-generation'])):
                with pytest.raises(DebuggerError,match='QMP'):
                    debug.vm.qmp.call('x-chip8-seed-rng',{'seed':seed,'expected-generation':generation})
                assert debug.chip8_environment()==before and debug.registers()==regs
                assert debug.memory(0,length=4096)['hex']==ram
            seeded=debug.chip8_seed_rng(123);assert debug.registers()==regs
            assert (seeded['rng-seed'],seeded['rng-state'],seeded['rng-draws'])==(123,123,0)
            checkpoint=debug.save_state(timeout_ms=30000);old=debug.vm.process
            first=debug.step(timeout_ms=5000);first_env=debug.chip8_environment()
            expected=(1664525*123+1013904223)&0xffffffff
            assert int(first['registers']['registers']['v0'],16)==expected>>24
            assert (first_env['rng-state'],first_env['rng-draws'])==(expected,1)
            restored=debug.load_state(checkpoint['artifact'],timeout_ms=30000)
            assert old.poll() is not None and restored['environment']==seeded and debug.registers()==regs
            repeated=debug.step(timeout_ms=5000)
            assert repeated['registers']==first['registers']
            again=debug.chip8_environment()
            assert (again['rng-seed'],again['rng-state'],again['rng-draws'])==(123,expected,1)
    assert rom.read_bytes()==source


def test_classic_json_seed_route_keeps_cpu_stopped(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    binary,tool=_inputs();rom=tmp_path/'json.ch8';source=bytes.fromhex('c0ff 1200');rom.write_bytes(source)
    db=tmp_path/'json.fdb'
    with Project.create(db,rom,arch='chip8',bits=16):pass
    workspace=DebugWorkspace()
    def call(method,**params):
        return respond(dict(method=method,params=dict(project=str(db),**params)),debugger=workspace)
    launch=call('debug-launch',executable=binary,game_dir=str(tmp_path),backend='qemu-chip8',
                qemu_checkpoint_tool=tool,boot_timeout_ms=10000)
    assert launch['ok'],launch
    run=launch['result']['run'];process=workspace.sessions[run].rpc.process
    try:
        regs=call('debug-registers',run=run);env=call('debug-chip8-environment',run=run)
        assert regs['ok'] and env['ok'] and regs['result']['linear_pc']=='0x200'
        previous=env['result']
        for seed in (0,123):
            result=call('debug-chip8-seed-rng',run=run,seed=seed)
            assert result['ok'],result
            current=result['result']
            assert (current['rng-seed'],current['rng-state'],current['rng-draws'])==(seed,seed,0)
            assert current['state-generation']==previous['state-generation']+1
            assert all(current[key]==previous[key] for key in previous
                       if key not in ('rng-seed','rng-state','rng-draws','state-generation','key-wait-stop-owned'))
            assert call('debug-registers',run=run)==regs
            assert call('debug-chip8-environment',run=run)['result']==current
            previous=current
        step=call('debug-step',run=run,timeout_ms=5000)
        assert step['ok'] and step['result']['outcome']=='step'
        assert int(step['result']['registers']['registers']['v0'],16)==((1664525*123+1013904223)&0xffffffff)>>24
        stopped=call('debug-stop',run=run)
        assert stopped['ok'] and stopped['result']['process_reaped'] and process.poll() is not None
    finally:
        workspace.close()
    assert rom.read_bytes()==source
