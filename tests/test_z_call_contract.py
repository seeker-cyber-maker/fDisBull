import base64
from copy import deepcopy
import hashlib
import struct
from types import SimpleNamespace

import pytest

from fdisbull import z_call_contract as module


CALL, ENTRY, STACK, STRING, SELECTOR = 0x12000, 0x11000, 0x8000, 0x4000, 0x150


class Session:
    def __init__(self):
        self.run_id, self.session_id = 'same-run-label', 'ses-1'
        self.memory = bytearray(0x40000)
        self.memory[ENTRY:ENTRY + 16] = bytes.fromhex('5589e553569090909090909090909090')
        self.memory[CALL:CALL + 5] = b'\xe8' + struct.pack('<i', ENTRY - CALL - 5)
        self.memory[CALL + 5:CALL + 10] = b'\x90\x90\x90\x90\x90'
        self.memory[STRING:STRING + 7] = b'SLOT_1\0'
        self.regs = {'cpu_mode': 'protected', 'flags': '0x202',
            'segments': {'cs': hex(SELECTOR), 'ds': '0x158', 'ss': '0x158'},
            'general': {k: hex(v) for k, v in dict(eax=STRING, ebx=2, ecx=3, edx=4,
                esi=5, edi=6, ebp=7, esp=STACK).items()}, 'instruction_pointer': hex(CALL)}
        self.events = []
        self.foreign = False
        self.changed_stack = False
        self.read_fail = None
        self.owned = False
        self.initial_stop = 'pause'
        self.qualify_foreign = False

    def registers(self):
        return deepcopy(self.regs)

    def call(self, method, params=None):
        self.events.append((method, deepcopy(params)))
        if method == 'memory.read':
            address = int(params['address']['offset'], 16)
            if address == self.read_fail:
                raise RuntimeError('unmapped pointer')
            return {'data_base64': base64.b64encode(self.memory[address:address + params['length']]).decode()}
        if method == 'memory.write':
            address = int(params['address']['offset'], 16)
            data = base64.b64decode(params['data_base64'])
            assert hashlib.sha256(self.memory[address:address + len(data)]).hexdigest() == params['expected_sha256']
            self.memory[address:address + len(data)] = data
            return {}
        if method == 'state.set_register':
            name, value = params['register'].lower(), hex(params['value'])
            if name == 'eip':
                # The installed backend exposes only a 16-bit EIP setter even
                # during protected32 execution. Capture/reentry must hop by
                # ordinary original-mode execution rather than rely on it.
                if params['value'] > 0xFFFF:
                    raise ValueError('EIP setter exceeds 16-bit backend range')
                self.regs['instruction_pointer'] = value
            elif name == 'flags': self.regs['flags'] = value
            else: self.regs['general'][name] = value
            return {}
        if method == 'breakpoints.create':
            address = params['address']
            assert address['segment'] == f'0x{SELECTOR:04X}'
            assert address['offset'] == f'0x{CALL:08X}'
            self.owned = True
            return {'breakpoint_id': 'capture-owned'}
        if method == 'breakpoints.delete':
            self.owned = False
            return {}
        if method == 'execution.step':
            self.regs['instruction_pointer'] = hex(int(self.regs['instruction_pointer'], 16) + 1)
            return {'stop_reason': {'kind': 'step'}}
        if method == 'session.status':
            return {'state': 'stopped', 'last_stop': {'kind': self.initial_stop}}
        raise AssertionError(method)

    def run(self, **params):
        self.events.append(('run', params))
        if self.qualify_foreign:
            return {'stop': {'trigger': 'breakpoint'}, 'session': {'stop_reason': {'breakpoint_id': 'foreign'}}}
        self.regs.update(cpu_mode='protected', flags='0x202', instruction_pointer='0x3000')
        self.regs['segments']['cs'] = hex(SELECTOR)
        return {'stop': {'trigger': 'guest_time'}, 'guest_elapsed_ms': params['guest_ms']}

    def reach(self, address, selector, **kwargs):
        self.events.append(('reach', {'address': address}))
        if self.foreign:
            raise RuntimeError('foreign stop retained')
        ip = int(self.regs['instruction_pointer'], 16)
        if self.memory[ip] == 0xE9:
            displacement = struct.unpack('<i', self.memory[ip + 1:ip + 5])[0]
            assert (ip + 5 + displacement) & 0xFFFFFFFF == address
            self.events.append(('executed-redirect', {'from': ip, 'to': address}))
            self.regs['instruction_pointer'] = hex(address)
            return {'registers': self.registers()}
        if address == CALL + 5:
            assert int(self.regs['instruction_pointer'], 16) == CALL
            # Model a near-returning serializer with intended global effects
            # and temporary writes within the declared stack window.
            self.memory[0x5000] = int(self.regs['general']['ebx'], 16)
            argument = int(self.regs['general']['eax'], 16)
            self.memory[0x5100:0x5107] = self.memory[argument:argument + 7]
            self.memory[STACK - 32:STACK] = b'X' * 32
            self.regs['general']['eax'] = '0x2a'
            self.regs['flags'] = '0x246'
            self.regs['general']['esp'] = hex(STACK)
            if self.changed_stack:
                self.regs['general']['esp'] = hex(STACK - 4)
        self.regs['instruction_pointer'] = hex(address)
        return {'registers': self.registers()}


def setup(monkeypatch):
    ctx = SimpleNamespace(d=Session(), state={})
    monkeypatch.setattr(module, 'reach_flat32_boundary', lambda d, a, s, **kw: d.reach(a, s, **kw))
    return ctx


def capture(ctx, **kwargs):
    return module.capture_native_call(ctx, 'serialize', CALL, SELECTOR, **kwargs)


def test_capture_extracts_original_call_context_arguments_and_near_return(monkeypatch):
    ctx = setup(monkeypatch)
    before = bytes(ctx.d.memory)
    result = capture(ctx)
    assert result['entry'] == ENTRY and result['return_address'] == CALL + 5
    assert result['arguments'][0]['pointer_hypothesis']['c_string'] == 'SLOT_1'
    assert result['entry_conditions']['registers']['general']['eax'] == hex(STRING)
    assert result['return_registers']['general']['eax'] == '0x2a'
    assert result['status'] == 'returned' and result['returned_stack_matches']
    assert result['entry_conditions']['stack']['bytes'] == 4112
    assert bytes(ctx.d.memory[CALL:CALL + 10]) == before[CALL:CALL + 10]
    assert not any(m == 'memory.write' for m, _ in ctx.d.events)
    assert ctx.state['native_call_contracts']['serialize'] is result
    assert 'native_capture_pending' not in ctx.state


def test_cpu_portal_replay_restores_interrupted_context_and_keeps_effects(monkeypatch):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d.regs['instruction_pointer'] = '0x23000'
    ctx.d.regs['general']['eax'] = '0x12'
    ctx.d.regs['general']['esp'] = '0xa000'
    current = ctx.d.registers()
    before = bytes(ctx.d.memory)
    result = module.invoke_captured_call(ctx, contract, args={'EBX': 99}, string_args={'EAX': 'SLOT_2'})
    assert result['ui_input'] is False and result['code_patched'] is True
    assert result['temporary_code_restored'] is True
    assert result['original_call_unchanged'] is True
    assert ctx.d.regs == current
    assert ctx.d.memory[0x5000] == 99
    assert ctx.d.memory[0x5100:0x5107] == b'SLOT_2\0'
    assert ctx.d.memory[STRING:STRING + 7] == b'SLOT_1\0'
    assert ctx.d.memory[STACK - 4096:STACK + 16] == before[STACK - 4096:STACK + 16]
    assert ctx.d.memory[CALL:CALL + 5] == before[CALL:CALL + 5]
    assert ctx.d.memory[CALL + 5:CALL + 10] == before[CALL + 5:CALL + 10]
    assert ctx.d.memory[0x23000:0x23005] == before[0x23000:0x23005]
    assert [params for method, params in ctx.d.events if method == 'executed-redirect'] == [
        {'from': 0x23000, 'to': CALL}, {'from': CALL + 5, 'to': 0x23000}]
    assert not any(method == 'state.set_register' and params['register'] == 'EIP'
                   for method, params in ctx.d.events)
    assert 'native_contract_pending' not in ctx.state


def test_same_provider_labels_do_not_allow_fresh_owner_reentry(monkeypatch):
    old = setup(monkeypatch)
    contract = capture(old)
    fresh = setup(monkeypatch)
    with pytest.raises(ValueError, match='different live runtime'):
        module.invoke_captured_call(fresh, contract)
    assert not fresh.d.events


def test_replacing_session_on_same_context_rejects_old_portal(monkeypatch):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d = Session()
    with pytest.raises(ValueError, match='different live runtime'):
        module.invoke_captured_call(ctx, contract)
    assert not ctx.d.events


@pytest.mark.parametrize('changed', ['call', 'signature', 'mode', 'segments'])
def test_replay_preflight_refuses_changed_code_or_cpu_without_writes(monkeypatch, changed):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    if changed == 'call': ctx.d.memory[CALL] = 0x90
    if changed == 'signature': ctx.d.memory[ENTRY] ^= 1
    if changed == 'mode': ctx.d.regs['flags'] = '0x20202'
    if changed == 'segments': ctx.d.regs['segments']['ds'] = '0x160'
    ctx.d.events.clear()
    with pytest.raises(ValueError): module.invoke_captured_call(ctx, contract, qualification_guest_ms=0)
    assert not any(m in ('memory.write', 'state.set_register', 'reach') for m, _ in ctx.d.events)


def test_foreign_stop_keeps_pending_recovery_and_does_not_restore_or_retry(monkeypatch):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d.regs['instruction_pointer'] = '0x3000'
    current = ctx.d.registers()
    ctx.d.foreign = True
    with pytest.raises(RuntimeError, match='foreign stop'):
        module.invoke_captured_call(ctx, contract)
    pending = ctx.state['native_contract_pending']
    assert pending['phase'] == 'string_arguments_installed'
    assert pending['redirect']['phase'] == 'installed'
    assert pending['redirect']['source'] == 0x3000
    assert pending['redirect']['target'] == CALL
    assert ctx.d.memory[0x3000:0x3005].hex() == pending['redirect']['jump_hex']
    assert pending['redirect']['original_hex'] == '0000000000'
    assert ctx.d.memory[CALL] == 0xE8
    assert pending['current_registers'] == current
    with pytest.raises(ValueError, match='needs recovery'):
        module.invoke_captured_call(ctx, contract)


def test_unmapped_argument_is_unknown_without_discarding_call_capture(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.read_fail = STRING
    result = capture(ctx, execute=False)
    assert result['status'] == 'inputs_observed'
    assert result['arguments'][0]['pointer_hypothesis'] is None
    assert 'unmapped pointer' in result['arguments'][0]['pointer_read_error']
    with pytest.raises(ValueError, match='observed near return'):
        module.invoke_captured_call(ctx, result)


def test_non_e8_and_nonmatching_near_returns_do_not_become_replayable(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.memory[CALL] = 0xFF
    with pytest.raises(ValueError, match='E8'):
        capture(ctx)
    assert ctx.state['native_capture_pending']['status'] == 'failed'
    ctx.d.memory[CALL] = 0xE8
    ctx.d.changed_stack = True
    result = capture(ctx)
    assert result['returned_stack_matches'] is False
    with pytest.raises(ValueError, match='observed near return'):
        module.invoke_captured_call(ctx, result)


def test_trigger_is_armed_before_event_and_accepts_only_exact_capture_stop(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.regs['instruction_pointer'] = '0x3000'
    def trigger():
        assert ctx.d.owned
        ctx.d.regs['instruction_pointer'] = hex(CALL)
        raise RuntimeError('mouse delivery interrupted by breakpoint')
    result = capture(ctx, trigger=trigger)
    assert result['status'] == 'returned' and not ctx.d.owned
    assert sum(m == 'breakpoints.create' for m, _ in ctx.d.events) == 1
    assert sum(m == 'breakpoints.delete' for m, _ in ctx.d.events) == 1


def test_other_trigger_error_leaves_stop_and_deletes_only_owned_id(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.regs['instruction_pointer'] = '0x3000'
    def trigger():
        ctx.d.regs['instruction_pointer'] = '0x3500'
        raise RuntimeError('foreign watchpoint')
    with pytest.raises(RuntimeError, match='foreign watchpoint'):
        capture(ctx, trigger=trigger)
    assert ctx.d.regs['instruction_pointer'] == '0x3500'
    assert not any(m == 'reach' for m, _ in ctx.d.events)
    assert [p for m, p in ctx.d.events if m == 'breakpoints.delete'] == [{'breakpoint_id': 'capture-owned'}]


def test_continuation_records_observed_instructions_and_replays_only_that_path(monkeypatch):
    ctx = setup(monkeypatch)
    contract = capture(ctx, continuation_steps=2)
    assert [r['instruction']['address'] for r in contract['continuation']] == [CALL + 5, CALL + 6]
    result = module.invoke_captured_call(ctx, contract, continuation_steps=2)
    assert len(result['continuation']) == 2
    assert ctx.d.regs['instruction_pointer'] == hex(CALL + 7)
    ctx.d.memory[CALL + 6] = 0xCC
    with pytest.raises(RuntimeError, match='diverged'):
        module.invoke_captured_call(ctx, contract, continuation_steps=2)
    assert ctx.state['native_contract_pending']['phase'] == 'callee_returned'


@pytest.mark.parametrize('kwargs', [
    {'string_args': {'EAX': 'TOO_LONG'}}, {'string_args': {'EAX': 'bad\0'}},
    {'string_args': {'EAX': 'é'}}, {'string_args': {'EBX': 'A'}},
    {'args': {'eax': 1}, 'string_args': {'EAX': 'SLOT_2'}},
    {'args': {'ESP': 1}}, {'args': {'eax': 1, 'EAX': 2}},
])
def test_bad_argument_overrides_have_no_mutations(monkeypatch, kwargs):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d.events.clear()
    with pytest.raises(ValueError): module.invoke_captured_call(ctx, contract, **kwargs)
    assert not any(m in ('memory.write', 'state.set_register', 'reach') for m, _ in ctx.d.events)


def test_stack_resident_string_override_restores_current_bytes_and_cpu(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.regs['general']['eax'] = hex(STACK)
    ctx.d.memory[STACK:STACK + 7] = b'SLOT_1\0'
    contract = capture(ctx)
    ctx.d.regs['instruction_pointer'] = '0x3000'
    ctx.d.memory[STACK:STACK + 7] = b'SLOT_9\0'
    before = bytes(ctx.d.memory[STACK - 4096:STACK + 16])
    cpu = ctx.d.registers()
    result = module.invoke_captured_call(ctx, contract, string_args={'EAX': 'SLOT_2'})
    assert ctx.d.memory[0x5100:0x5107] == b'SLOT_2\0'
    assert ctx.d.memory[STACK:STACK + 7] == b'SLOT_9\0'
    assert ctx.d.memory[STACK - 4096:STACK + 16] == before
    assert ctx.d.regs == cpu
    assert result['string_arguments_restored'] and result['stack_window_restored']


def test_replay_reacquires_captured_selector_from_v86_without_ui(monkeypatch):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d.regs.update(cpu_mode='v8086', flags='0x20202', instruction_pointer='0x100')
    ctx.d.regs['segments']['cs'] = '0xc000'
    ctx.d.events.clear()
    result = module.invoke_captured_call(ctx, contract)
    runs = [params for method, params in ctx.d.events if method == 'run']
    assert len(runs) == 1 and runs[0]['fast_forward'] is False
    assert runs[0]['stop_on_hook'] is True
    assert result['qualification_guest_ms'] == runs[0]['guest_ms']
    assert ctx.d.regs['instruction_pointer'] == '0x3000'
    assert ctx.d.regs['cpu_mode'] == 'protected'


@pytest.mark.parametrize('phase', ['initial', 'during_qualification'])
def test_replay_qualification_preserves_foreign_stops(monkeypatch, phase):
    ctx = setup(monkeypatch)
    contract = capture(ctx)
    ctx.d.regs.update(cpu_mode='v8086', flags='0x20202', instruction_pointer='0x100')
    ctx.d.regs['segments']['cs'] = '0xc000'
    if phase == 'initial': ctx.d.initial_stop = 'breakpoint'
    else: ctx.d.qualify_foreign = True
    ctx.d.events.clear()
    before = ctx.d.registers()
    with pytest.raises(RuntimeError, match='debugger stop'):
        module.invoke_captured_call(ctx, contract)
    assert ctx.d.regs == before
    assert not any(m in ('memory.write', 'state.set_register', 'reach') for m, _ in ctx.d.events)
    assert len([m for m, _ in ctx.d.events if m == 'run']) == (phase != 'initial')

@pytest.mark.parametrize('qualified', [True, False])
def test_trigger_capture_retains_initial_foreign_stop_without_input_or_run(monkeypatch, qualified):
    ctx = setup(monkeypatch)
    ctx.d.initial_stop = 'breakpoint'
    if not qualified:
        ctx.d.regs.update(cpu_mode='v8086', flags='0x20202', instruction_pointer='0x100')
        ctx.d.regs['segments']['cs'] = '0xc000'
    triggered = []
    with pytest.raises(RuntimeError, match='initial foreign'):
        capture(ctx, trigger=lambda: triggered.append(True))
    assert not triggered
    assert not any(method in ('run', 'memory.write', 'state.set_register') for method, _ in ctx.d.events)
