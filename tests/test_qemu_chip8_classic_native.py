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
            assert (before['rng-seed'],before['rng-state'],before['rng-draws'])==(0,0,0)
            with pytest.raises(DebuggerError,match='QMP'):
                debug.vm.qmp.call('x-chip8-seed-rng',{'seed':123,'expected-generation':before['state-generation']+1})
            assert debug.chip8_environment()==before and debug.registers()==regs
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
