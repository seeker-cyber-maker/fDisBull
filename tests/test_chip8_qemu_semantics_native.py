"""Independent golden cases for the bounded real QEMU CHIP-8 target.

These use authored ROM words and explicit state expectations, not the pilot VM.
"""
from contextlib import contextmanager
import os
import pytest
from fdisbull.project import Project


def _inputs():
    binary, tool = os.environ.get('FDISBULL_CHIP8_QEMU'), os.environ.get('FDISBULL_CHIP8_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8') == '1':
            pytest.fail('CHIP-8 QEMU and qemu-img are required')
        pytest.skip('Set FDISBULL_CHIP8_QEMU and FDISBULL_CHIP8_QEMU_IMG')
    return binary, tool


@contextmanager
def _machine(tmp_path, words):
    binary, tool = _inputs()
    source = bytes.fromhex(words)
    rom = tmp_path / 'golden.ch8'; rom.write_bytes(source)
    with Project.create(tmp_path / 'golden.fdb', rom, arch='chip8', bits=16) as project:
        with project.debugger(binary, str(tmp_path), backend='qemu-chip8', qemu_checkpoint_tool=tool, boot_timeout_ms=10000) as debug:
            yield debug
    assert rom.read_bytes() == source


def _registers(debug):
    return {k:int(v,16) for k,v in debug.registers()['registers'].items()}


def _step(debug, pc, **expected):
    result = debug.step(timeout_ms=5000)
    assert result['outcome'] == 'step', result
    regs = _registers(debug)
    assert regs['pc'] == pc
    for key, value in expected.items():
        assert regs[key] == value, (key, regs, result)
    return regs


def _fault(result, code, pc, opcode):
    assert result['outcome'] == 'exception', result
    fault = result['fault']
    assert fault['faulted'] and fault['fault-code'] == code
    assert fault['fault-pc'] == pc and fault['fault-opcode'] == opcode
    assert fault['profile'] == 'chip8-classic-pilot-default-v1'


def test_golden_arithmetic_logic_shift_vy_and_vf_alias(tmp_path):
    # Explicit pilot-default quirks: logic clears VF, shifts source Vy.
    with _machine(tmp_path, '60ff 6102 8014 6203 8011 6305 8436 6380 843e 6f80 6103 8f14 6f81 8f16') as d:
        for pc, values in [
            (0x202, {'v0':255}), (0x204, {'v1':2}),
            (0x206, {'v0':1,'vf':1}), (0x208, {'v2':3}),
            (0x20a, {'v0':3,'vf':0}), (0x20c, {'v3':5}),
            (0x20e, {'v4':2,'vf':1}), (0x210, {'v3':128}),
            (0x212, {'v4':0,'vf':1}), (0x214, {'vf':128}),
            (0x216, {'v1':3}), (0x218, {'vf':0}),
            (0x21a, {'vf':129}), (0x21c, {'vf':1}),
        ]:
            _step(d, pc, **values)


def test_golden_call_skip_return_and_i_memory_roundtrip(tmp_path):
    # Taken skip bypasses 6109; call pushes continuation 0x208 and returns.
    with _machine(tmp_path, '6001 3001 6109 220e a300 f155 1214 6107 00ee 0000 1214') as d:
        _step(d,0x202,v0=1);_step(d,0x206,v0=1)
        _step(d,0x20e,sp=1,stack0=0x208)
        _step(d,0x210,v1=7);_step(d,0x208,sp=0)
        _step(d,0x20a,i=0x300);_step(d,0x20c,i=0x302)
        assert d.memory(0x300,length=2)['hex']=='0107'
        # Reload restores both registers and increments I under this profile.
        d.write_registers({'pc':{'expected':0x20c,'value':0x20c},
                           'i':{'expected':0x302,'value':0x300},
                           'v0':{'expected':1,'value':0},'v1':{'expected':7,'value':0}})
        d.write_memory(0x20c,'f165',expected_hex='1214')
        _step(d,0x20e,v0=1,v1=7,i=0x302)


def test_transfer_overrun_is_atomic_and_top_of_memory_is_allowed(tmp_path):
    with _machine(tmp_path, '60aa 61bb afff f155') as d:
        _step(d,0x202,v0=0xaa);_step(d,0x204,v1=0xbb);_step(d,0x206,i=0xfff)
        before=d.memory(0xfff,length=1)['hex'];regs=_registers(d)
        result=d.step(timeout_ms=5000)
        _fault(result,3,0x206,0xf155)
        assert _registers(d)==regs and d.memory(0xfff,length=1)['hex']==before
    # A single byte at FFF succeeds; I can become 1000, with no silent wrapping.
    other=tmp_path/'top';other.mkdir()
    with _machine(other, '60aa afff f055') as d:
        _step(d,0x202,v0=0xaa);_step(d,0x204,i=0xfff)
        _step(d,0x206,i=0x1000);assert d.memory(0xfff,length=1)['hex']=='aa'


@pytest.mark.parametrize('word,code', [('00ee',4),('ffff',1),('00e0',1)])
def test_underflow_unknown_and_device_operation_are_inspectable_exceptions(tmp_path,word,code):
    with _machine(tmp_path,word) as d:
        before=_registers(d); result=d.step(timeout_ms=5000)
        _fault(result,code,0x200,int(word,16))
        assert _registers(d)==before


def test_stack_overflow_and_odd_fetch_leave_state_unchanged(tmp_path):
    with _machine(tmp_path, '2200') as d:
        for depth in range(1,17):
            _step(d,0x200,sp=depth)
        before=_registers(d);result=d.step(timeout_ms=5000)
        _fault(result,5,0x200,0x2200)
        assert _registers(d)==before
    other=tmp_path/'odd';other.mkdir()
    with _machine(other, '1201') as d:
        _step(d,0x201)
        before=_registers(d);result=d.step(timeout_ms=5000)
        _fault(result,6,0x201,0)
        assert _registers(d)==before


def test_fetch_outside_ram_is_inspectable_and_checkpointed(tmp_path):
    with _machine(tmp_path, '6001') as d:
        d.write_registers({'pc':{'expected':0x200,'value':0x1000}})
        before=_registers(d);result=d.step(timeout_ms=5000)
        _fault(result,2,0x1000,0)
        assert _registers(d)==before
        checkpoint=d.save_state(timeout_ms=30000)
        old=d.vm.process
        d.load_state(checkpoint['artifact'],timeout_ms=30000)
        assert old.poll() is not None and _registers(d)==before
        restored=d.step(timeout_ms=5000)
        _fault(restored,2,0x1000,0)
        assert _registers(d)==before


def test_debugger_code_write_invalidates_translated_instruction(tmp_path):
    with _machine(tmp_path, '6001 1200') as d:
        _step(d,0x202,v0=1)
        d.write_memory(0x200,'6002',expected_hex='6001')
        _step(d,0x200)
        _step(d,0x202,v0=2)


def test_guarded_stack_retirement_zeroes_unused_slot_across_restore(tmp_path):
    with _machine(tmp_path, '2204 1202 00ee') as d:
        _step(d,0x204,sp=1,stack0=0x202)
        # QEMU's generic P handler replies OK even when the target rejects
        # an invalid register value: only actual readback proves rejection.
        before=_registers(d)
        assert d.vm.gdb.request('P12=11') == b'OK'  # SP is 8-bit reg 18.
        assert d.vm.gdb.request('P14=3412') == b'OK'  # Inactive stack1.
        assert _registers(d)==before
        d.write_registers({'sp':{'expected':1,'value':0}})
        retired=_registers(d)
        assert retired['sp']==0 and retired['stack0']==0
        checkpoint=d.save_state(timeout_ms=30000)
        old=d.vm.process
        d.load_state(checkpoint['artifact'],timeout_ms=30000)
        assert old.poll() is not None and _registers(d)==retired
