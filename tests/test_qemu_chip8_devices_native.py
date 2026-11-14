"""Opt-in actual QEMU CHIP-8 device and stop-ownership witnesses."""
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from test_chip8_devices_semantics_native import _inputs


def test_wait_restore_breakpoint_and_key_admission_never_replay_old_stop(tmp_path):
    binary,tool=_inputs();rom=tmp_path/'wait.ch8';source=bytes.fromhex('f00a 6001 1200');rom.write_bytes(source)
    with Project.create(tmp_path/'wait.fdb',rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            assert debug.capabilities['frame'] and debug.capabilities['input'] and debug.capabilities['timers']
            stopped=debug.step(timeout_ms=5000)
            assert stopped['outcome']=='key_wait' and stopped['registers']['linear_pc']=='0x200'
            before=debug.registers();env=debug.chip8_environment()
            assert env['key-wait'] and env['key-wait-stop-owned'] and env['key-mask']==0
            snapshot=debug.save_state(timeout_ms=30000);old=debug.vm.process
            restored=debug.load_state(snapshot['artifact'],timeout_ms=30000)
            assert old.poll() is not None and debug.registers()==before
            assert restored['environment']['key-wait'] and not restored['environment']['key-wait-stop-owned']
            point=debug.breakpoint(0x200)
            collision=debug.run(timeout_ms=5000)
            assert collision['outcome']=='breakpoint'
            assert collision['session']['stop_reason']['breakpoint_ids']==[point['breakpoint_id']]
            assert collision['environment']['key-wait'] and not collision['environment']['key-wait-stop-owned']
            debug.delete_breakpoint(point['breakpoint_id'])
            pre=debug.registers();keyed=debug.chip8_keypad([5,2])
            assert keyed['key-mask']==(1<<5)|(1<<2) and keyed['key-wait']
            assert debug.registers()==pre
            consumed=debug.step(timeout_ms=5000)
            assert consumed['outcome']=='step' and consumed['registers']['linear_pc']=='0x202'
            assert consumed['registers']['registers']['v0']=='0x2'
            assert not consumed['environment']['key-wait']
    assert rom.read_bytes()==source


def test_native_qmp_admission_rejects_stale_and_invalid_inputs_atomically(tmp_path):
    binary,tool=_inputs();rom=tmp_path/'guards.ch8';source=bytes.fromhex('6001 1200');rom.write_bytes(source)
    with Project.create(tmp_path/'guards.fdb',rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            environment=debug.chip8_environment();registers=debug.registers()
            memory=debug.memory(0,length=4096)['hex']
            generation=environment['state-generation']
            calls=(
                ('x-chip8-set-keys',{'key-mask':1,'expected-generation':generation+1}),
                ('x-chip8-debug-ticks',{'count':1,'expected-generation':generation+1}),
                ('x-chip8-set-keys',{'key-mask':65536,'expected-generation':generation}),
                ('x-chip8-debug-ticks',{'count':0,'expected-generation':generation}),
                ('x-chip8-debug-ticks',{'count':65536,'expected-generation':generation}),
            )
            for command,arguments in calls:
                with pytest.raises(DebuggerError,match='QMP'):
                    debug.vm.qmp.call(command,arguments,timeout_ms=5000)
                assert debug.chip8_environment()==environment
                assert debug.registers()==registers
                assert debug.memory(0,length=4096)['hex']==memory
    assert rom.read_bytes()==source
