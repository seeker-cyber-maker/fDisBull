"""Deterministic checks for test-only native fixture preparation."""
import base64
import copy
import hashlib

import pytest

from native_fixture import prepare_native_fixture


class Keyboard:
    def state(self):
        return {'keyboard': {'pending_events': 0, 'owned_keys': 0,
                             'queued_guest_ms': 0, 'frame_keys': [], 'frame_edge_capacity': 12}}


class SyntheticDebug:
    def __init__(self, corrupt=False):
        self.mem = bytearray(0x20000)
        self.mem[0x10000:0x10200] = bytes(range(256)) * 2
        self.regs = {'cpu_mode': 'real', 'general': {k: '0x00000000' for k in
                     ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp')},
                     'segments': {k: '0x1000' for k in ('cs', 'ds', 'es', 'ss', 'fs', 'gs')},
                     'instruction_pointer': '0x0000', 'flags': '0x0202'}
        self.regs['general']['esp'] = '0x00000400'
        self.keyboard = Keyboard()
        self.elapsed = 0
        self.corrupt = corrupt
        self.breakpoint = False

    def registers(self):
        return copy.deepcopy(self.regs)

    def call(self, method, args):
        if method == 'breakpoints.create':
            self.breakpoint = True
            return {'breakpoint_id': 'test-loop'}
        if method == 'state.set_register':
            name = args['register'].lower()
            target = self.regs['general'] if name in self.regs['general'] else self.regs['segments']
            if name == 'eip':
                self.regs['instruction_pointer'] = hex(args['value'])
            elif name == 'flags':
                self.regs['flags'] = hex(args['value'])
            else:
                target[name] = hex(args['value'])
            return {}
        address = args['address']
        at = int(address['segment'], 16) * 16 + int(address['offset'], 16)
        if method == 'memory.read':
            data = bytes(self.mem[at:at + args['length']])
            return {'address': address, 'sha256': hashlib.sha256(data).hexdigest(),
                    'data_base64': base64.b64encode(data).decode()}
        assert method == 'memory.write'
        data = base64.b64decode(args['data_base64'])
        assert hashlib.sha256(self.mem[at:at + len(data)]).hexdigest() == args['expected_sha256']
        self.mem[at:at + len(data)] = data
        return {}

    def delete_breakpoint(self, breakpoint_id):
        assert breakpoint_id == 'test-loop'
        self.breakpoint = False

    def run(self, *, guest_ms=None, timeout_ms, fast_forward):
        assert self.mem[0x10000:0x10002] == b'\xeb\xfe'
        assert int(self.regs['flags'], 16) & 0x200
        if self.breakpoint:
            return {'outcome': 'breakpoint'}
        self.elapsed += guest_ms
        if self.corrupt:
            self.mem[0x10020] ^= 1
        return {'outcome': 'guest_time'}


def test_fixture_preparation_restores_program_and_keeps_interrupts_enabled():
    debug = SyntheticDebug()
    program = bytes(debug.mem[0x10000:0x10200])
    prepare_native_fixture(debug)
    assert bytes(debug.mem[0x10000:0x10200]) == program
    assert int(debug.regs['flags'], 16) == 0x202
    assert debug.elapsed == 300


def test_fixture_preparation_detects_unexpected_program_mutation():
    with pytest.raises(AssertionError):
        prepare_native_fixture(SyntheticDebug(corrupt=True))
