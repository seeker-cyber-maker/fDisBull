"""Actual guest faults and REP progress must not acquire retirement claims.

Supply FDISBULL_QEMU_DOS and optionally FDISBULL_QEMU_DOS_FIRMWARE.
These authored boot witnesses need no DOS image, assembler or game.
"""
import json
import os
import struct

import pytest

from fdisbull.project import Project
from fdisbull.qemu_step_policy import observe_step_policy
from support.qemu_trace_fixture import fault_and_rep_boot


@pytest.fixture
def machine(tmp_path):
    executable = os.environ.get('FDISBULL_QEMU_DOS')
    if not executable:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS') == '1':
            pytest.fail('Missing FDISBULL_QEMU_DOS for the native step-boundary witnesses')
        pytest.skip('Supply FDISBULL_QEMU_DOS for actual native step-boundary witnesses')
    image, symbols = fault_and_rep_boot()
    binary = tmp_path / 'trace-probe.img'
    binary.write_bytes(image)
    with Project.create(tmp_path / 'trace.fdb', binary, arch='x86', bits=32,
                        base=0x7c00, entry=0x7c00) as project:
        with project.debugger(executable, tmp_path, backend='qemu-dos',
                qemu_transport='pipe',
                qemu_firmware=os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE')) as debug:
            yield project, debug, symbols
        assert debug.vm.process.poll() is not None
    assert binary.read_bytes() == image


def park(debug, address):
    point = debug.breakpoint(address)
    result = debug.run(timeout_ms=15000)
    assert result['outcome'] == 'breakpoint', result
    assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
    debug.delete_breakpoint(point['breakpoint_id'])
    return debug.registers()


def word(registers, name):
    for candidate in ('r' + name, 'e' + name, name):
        if candidate in registers['registers']:
            return int(registers['registers'][candidate], 16) & 0xffff
    raise AssertionError('Missing native register ' + name)


def read(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space='physical')['hex'])


def trace_document(project, debug, tmp_path):
    artifact = debug.trace('boundary.json', count=1, timeout_ms=3000)
    project.debug_export(artifact['artifact'], tmp_path / 'boundary.json')
    value = json.loads((tmp_path / 'boundary.json').read_text())
    assert value['complete'] is True
    assert value['single_step_policy']['status'] == 'observed'
    assert value['single_step_policy']['mask'] == 7
    assert value['single_step_policy']['interrupts_masked'] is True
    assert value['single_step_policy']['timers_masked'] is True
    assert len(value['events']) == 1
    assert value['events'][0]['observation']['instruction_completed'] is None
    assert 'unknown' in value['events'][0]['completion']
    assert value['session']['session']['stop_reason']['native_reply'].startswith('T05')
    return value


def test_native_div_fault_stops_at_handler_without_claiming_completion(machine, tmp_path):
    project, debug, symbols = machine
    before = park(debug, symbols['fault_at'])
    assert read(debug, symbols['fault_at'], 2) == b'\xf6\xf3'
    assert word(before, 'bx') & 0xff == 0
    assert word(before, 'ax') == 0x1234
    document = trace_document(project, debug, tmp_path)
    after = debug.registers()
    assert document['events'][0]['bytes'] == 'f6f3'
    assert int(after['linear_pc'], 16) == symbols['fault_handler']
    assert word(after, 'ax') == 0x1234
    assert word(after, 'sp') == word(before, 'sp') - 6
    # The CPU-created frame points to the faulting DIV, not its successor.
    saved_ip, saved_cs, _ = struct.unpack('<HHH', read(debug, word(after, 'sp'), 6))
    assert saved_ip == symbols['fault_at'] and saved_cs == 0


def test_native_rep_progress_is_observed_while_instruction_remains_active(machine, tmp_path):
    project, debug, symbols = machine
    before = park(debug, symbols['rep_at'])
    assert read(debug, symbols['rep_at'], 2) == b'\xf3\xa4'
    assert word(before, 'cx') == 3
    assert read(debug, symbols['source'], 3) == b'ABC'
    assert read(debug, symbols['destination'], 3) == b'\0\0\0'
    document = trace_document(project, debug, tmp_path)
    after = debug.registers()
    assert document['events'][0]['bytes'] == 'f3a4'
    assert int(after['linear_pc'], 16) == symbols['rep_at']
    assert word(after, 'cx') == 2
    assert word(after, 'si') == word(before, 'si') + 1
    assert word(after, 'di') == word(before, 'di') + 1
    assert read(debug, symbols['destination'], 3) == b'A\0\0'


def test_native_step_policy_observer_reads_actual_mask_and_preserves_it(machine):
    _, debug, symbols = machine
    park(debug, symbols['fault_at'])
    remote = debug.vm.debugger()
    original = remote.request('qqemu.sstep')
    assert original == b'0x7'
    # A caller may deliberately configure another policy. Observation must
    # report it and leave it untouched, then this test restores its own change.
    try:
        assert remote.request('Qqemu.sstep=0x5') == b'OK'
        policy = observe_step_policy(remote)
        assert policy['bits'] == {'ENABLE': 1, 'NOIRQ': 2, 'NOTIMER': 4}
        assert policy['status'] == 'observed' and policy['mask'] == 5
        assert policy['enabled'] and policy['timers_masked']
        assert policy['interrupts_masked'] is False and policy['changed'] is False
        assert remote.request('qqemu.sstep') == b'0x5'
    finally:
        assert remote.request('Qqemu.sstep=' + original.decode()) == b'OK'
    assert remote.request('qqemu.sstep') == original
