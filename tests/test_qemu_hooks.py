"""Paused hook control tests; these do not claim native-QEMU execution."""
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull.qemu_hooks import QemuHookSessionMixin


class Harness(QemuHookSessionMixin):
    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock(), gdb=None, qmp=None,
                                  operation_deadline=time.monotonic() + 30)
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False),
                                       debug_layer_info=lambda _: {'version': 1})
        self.version = {'id': 1}
        self.run_id = 'run'
        self.capabilities = {'code_layers': True}
        self.points = {}
        self.serial = 0
        self.events = []
        self.calls = []
        self.queue = []
        self.pc = 0x1000
        self.closed = False

    def _layer_epoch(self): return 1
    def _layer_spans(self, address, length, space, cs=None):
        value = int(address, 0) if isinstance(address, str) else address
        return value, value, [(value, length)], {'cpu_mode': 'real'}
    def breakpoint(self, address, *, access='x', length=1):
        self.serial += 1
        ident = 'bp-' + str(self.serial)
        self.points[ident] = address
        return {'breakpoint_id': ident}
    def delete_breakpoint(self, ident):
        del self.points[ident]
        return {'deleted': True}
    def _event(self, name, data): self.events.append((name, data))
    def registers(self): return {'linear_pc': hex(self.pc)}
    def layers(self, layers):
        self.calls.append(('layers', layers))
        return {'active': layers}
    def write_registers(self, registers):
        self.calls.append(('registers', registers))
        return {'ok': True}
    def _execute(self, command, timeout_ms):
        self.calls.append(('execute', command))
        return self.queue.pop(0)
    def close(self): self.closed = True


def _stop(outcome, *ids):
    return {'outcome': outcome, 'session': {'stop_reason': {
        'kind': outcome, 'breakpoint_ids': list(ids)}}}


def test_unique_one_shot_dispatch_and_collision_preserves_stop():
    session = Harness()
    hook = session.hook(0x1000, actions=[{'op': 'layers', 'layers': ['layer']}])
    ident = hook['breakpoint_id']
    collision = _stop('breakpoint', ident, 'unowned')
    assert session._dispatch_qemu_hook(collision) is None
    assert session.calls == [] and session.hooks()['hooks'][0]['hits'] == 0
    hit = session._dispatch_qemu_hook(_stop('breakpoint', ident))
    assert hit['hit'] == 1 and session.calls == [('layers', ['layer'])]
    assert session.hooks()['hooks'] == [] and session.points == {}
    assert [event[0] for event in session.events] == ['hook-create', 'hook-hit']


def test_repeat_hook_stops_then_steps_over_and_exhausts():
    session = Harness()
    hook = session.hook(0x1000, actions=[{'op': 'layers', 'layers': []}],
                        once=False, max_hits=2)
    session.queue = [_stop('breakpoint', hook['breakpoint_id'])]
    result = session._run_with_hooks(timeout_ms=1000, stop_on_hook=True)
    assert result['outcome'] == 'hook' and result['hook_hits'][0]['hit'] == 1
    assert not any(call == ('execute', 's') for call in session.calls)
    # Stepping once must happen before another continue. The replacement
    # breakpoint gets a fresh ID, then the second hit exhausts the hook.
    session.queue = [_stop('step'), _stop('breakpoint', 'bp-2'), _stop('guest_exit')]
    result = session._run_with_hooks(timeout_ms=1000, stop_on_hook=False)
    assert result['outcome'] == 'guest_exit' and result['hook_hits'][0]['hit'] == 2
    assert session.calls.index(('execute', 's')) < len(session.calls) - 1
    assert session.hooks()['hooks'] == []


def test_failed_action_closes_and_retains_original_native_stop():
    session = Harness()
    hook = session.hook(0x1000, actions=[{'op': 'registers', 'registers': {
        'eax': {'expected': 1, 'value': 2}}}])
    def fail(_): raise ValueError('guard differs')
    session.write_registers = fail
    stop = _stop('breakpoint', hook['breakpoint_id'])
    with pytest.raises(ValueError, match='guard differs') as caught:
        session._dispatch_qemu_hook(stop)
    assert caught.value.result is stop and session.closed
    assert session.events[-1][0] == 'hook-failed'


def test_invalid_hook_extent_refuses_before_breakpoint_creation():
    session = Harness()
    with pytest.raises(ValueError, match='extent'):
        session.hook(0x1000, actions=[{'op': 'layers', 'layers': []}], access='w', length=0)
    assert session.points == {} and session.events == []


def test_hook_owned_breakpoint_cannot_be_deleted_directly():
    from fdisbull.qemu_machine import MachineContext

    session = Harness()
    hook = session.hook(0x1000, actions=[{'op': 'layers', 'layers': []}])
    with pytest.raises(ValueError, match='Hook-owned'):
        MachineContext.delete_breakpoint.__wrapped__(session, hook['breakpoint_id'])
    assert session.hooks()['hooks'][0]['hook'] == hook['hook']
    assert session.delete_hook(hook['hook'])['deleted']
    assert session.hooks()['hooks'] == []
