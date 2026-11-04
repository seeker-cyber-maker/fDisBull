import base64
from copy import deepcopy
import hashlib
import struct
from types import SimpleNamespace

import pytest

from fdisbull import z_native


ENTRY, BOUNDARY, STACK, SELECTOR = 0x1000, 0x2000, 0x6000, 0x150
SIGNATURE = bytes.fromhex('5589e583ec085356')


class NativeSession:
    def __init__(self):
        self.memory = bytearray(0x8000)
        self.memory[ENTRY:ENTRY + len(SIGNATURE)] = SIGNATURE
        self.memory[BOUNDARY:BOUNDARY + 32] = b'\x90' * 32
        self.memory[STACK - 4096:STACK + 16] = bytes(range(256)) * 16 + b'0123456789abcdef'
        self.regs = {'cpu_mode': 'protected', 'flags': '0x202',
                     'segments': {'cs': '0x0150', 'ss': '0x0158', 'ds': '0x0158'},
                     'instruction_pointer': hex(BOUNDARY),
                     'general': {key: hex(value) for key, value in {
                         'eax': 1, 'ebx': 2, 'ecx': 3, 'edx': 4, 'esi': 5,
                         'edi': 6, 'ebp': 7, 'esp': STACK}.items()}}
        self.events = []
        self.stops = []
        self.fail_at = None
        self.changed_stack = False

    def call(self, method, params):
        self.events.append((method, params))
        if method == 'state.set_register':
            name = params['register'].lower()
            if name == 'flags':
                self.regs['flags'] = hex(params['value'])
            else:
                self.regs['general'][name] = hex(params['value'])
            return {}
        start = int(params['address']['offset'], 16)
        if method == 'memory.read':
            return {'data_base64': base64.b64encode(self.memory[start:start + params['length']]).decode()}
        assert method == 'memory.write'
        data = base64.b64decode(params['data_base64'])
        assert hashlib.sha256(self.memory[start:start + len(data)]).hexdigest() == params['expected_sha256']
        self.memory[start:start + len(data)] = data
        return {}

    def reach(self, address, selector, **options):
        self.stops.append((address, selector, options))
        if address == self.fail_at:
            raise RuntimeError('foreign stop retained')
        if address == BOUNDARY + 5:
            # A tiny model of the original callee: consumes the installed args,
            # modifies persistent state and its temporary stack, returns EAX.
            assert self.memory[BOUNDARY] == 0xE8
            displacement = struct.unpack('<I', self.memory[BOUNDARY + 1:BOUNDARY + 5])[0]
            assert (BOUNDARY + 5 + displacement) & 0xFFFFFFFF == ENTRY
            self.memory[0x3000] = int(self.regs['general']['ebx'], 16)
            self.memory[STACK - 32:STACK] = b'X' * 32
            self.regs['general']['eax'] = '0x2a'
            self.regs['flags'] = '0x246'
            if self.changed_stack:
                self.regs['general']['esp'] = hex(STACK - 4)
        self.regs['instruction_pointer'] = hex(address)
        return {'registers': deepcopy(self.regs)}


def setup(monkeypatch):
    session = NativeSession()
    monkeypatch.setattr(z_native, 'reach_flat32_boundary', lambda d, a, s, **kw: d.reach(a, s, **kw))
    return SimpleNamespace(d=session, state={})


def invoke(ctx, **extra):
    return z_native.invoke_native(ctx, ENTRY, BOUNDARY, SELECTOR, SIGNATURE.hex(), **extra)


def test_call_preserves_intended_effect_and_restores_temporary_context(monkeypatch):
    ctx = setup(monkeypatch)
    original = bytes(ctx.d.memory)
    regs = deepcopy(ctx.d.regs)
    result = invoke(ctx, directory='SLOT_2', args={'ebx': 83})
    assert result['returned_eax'] == '0x2a' and result['ui_input'] is False
    assert result['callee_effects'].startswith('retained')
    assert ctx.d.memory[0x3000] == 83
    assert ctx.d.memory[BOUNDARY:BOUNDARY + 32] == original[BOUNDARY:BOUNDARY + 32]
    assert ctx.d.memory[STACK - 4096:STACK + 16] == original[STACK - 4096:STACK + 16]
    assert ctx.d.regs == regs and not ctx.state
    assert [a for a, _, _ in ctx.d.stops] == [BOUNDARY, BOUNDARY + 5, BOUNDARY]


@pytest.mark.parametrize('kwargs', [
    {'args': {'esp': 42}}, {'args': {'EAX': 1, 'eax': 2}},
    {'args': {'ebx': -1}}, {'args': {'edx': True}},
    {'directory': 'too-long-for-slot-name'}, {'directory': 'bad\0name'},
    {'directory': 'SLOT', 'args': {'eax': 1}}, {'directory': 'é'},
])
def test_bad_contract_arguments_have_no_guest_effect(monkeypatch, kwargs):
    ctx = setup(monkeypatch)
    with pytest.raises(ValueError):
        invoke(ctx, **kwargs)
    assert not ctx.d.events and not ctx.d.stops and not ctx.state


def test_signature_mismatch_fails_before_code_or_register_mutation(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.memory[ENTRY] = 0xCC
    with pytest.raises(ValueError, match='signature differs'):
        invoke(ctx)
    assert [method for method, _ in ctx.d.events] == ['memory.read']
    assert not ctx.state


def test_foreign_stop_during_callee_is_preserved_and_retry_is_refused(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.fail_at = BOUNDARY + 5
    with pytest.raises(RuntimeError, match='foreign stop'):
        invoke(ctx, args={'ecx': 21})
    pending = ctx.state['native_call_pending']
    assert pending['phase'] == 'arguments_installed'
    assert bytes.fromhex(pending['original_hex']) == b'\x90' * 32
    assert ctx.d.memory[BOUNDARY] == 0xE8
    events = deepcopy(ctx.d.events)
    stops = deepcopy(ctx.d.stops)
    with pytest.raises(ValueError, match='needs recovery'):
        invoke(ctx)
    assert ctx.d.events == events and ctx.d.stops == stops


def test_changed_stack_cannot_be_reported_as_success(monkeypatch):
    ctx = setup(monkeypatch)
    ctx.d.changed_stack = True
    with pytest.raises(RuntimeError, match='changed stack'):
        invoke(ctx)
    assert ctx.state['native_call_pending']['phase'] == 'callee_returned'
    assert [a for a, _, _ in ctx.d.stops] == [BOUNDARY, BOUNDARY + 5]


def test_interruption_during_return_does_not_restore_code_over_foreign_stop(monkeypatch):
    ctx = setup(monkeypatch)
    old_reach = ctx.d.reach

    def fail_on_return(address, selector, **options):
        if len(ctx.d.stops) == 2:
            raise RuntimeError('foreign stop retained')
        return old_reach(address, selector, **options)

    ctx.d.reach = fail_on_return
    with pytest.raises(RuntimeError, match='foreign stop'):
        invoke(ctx)
    assert ctx.state['native_call_pending']['phase'] == 'registers_restored'
    assert ctx.d.memory[BOUNDARY] == 0xE8
