import base64
from copy import deepcopy
import struct
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.z_capture_watch import native_capture_watch


CALLS, ENTRY, CS = (0x12000, 0x13000), 0x11000, 0x150


class Session:
    def __init__(self):
        self.memory = bytearray(0x20000)
        for address in CALLS:
            self.memory[address:address + 5] = b'\xe8' + struct.pack('<i', ENTRY - address - 5)
        self.memory[ENTRY:ENTRY + 16] = b'\x90' * 16
        self.regs = {'cpu_mode': 'protected', 'flags': '0x202',
                     'instruction_pointer': '0x10000', 'segments': {'cs': hex(CS)}}
        self.stop = {'kind': 'pause'}
        self.breakpoints = {'foreign': 0x14000}
        self.events = []
        self.count = 0
        self.fail_create = None
        self.fail_delete = None
        self.qualify_foreign = False

    def registers(self):
        return deepcopy(self.regs)

    def call(self, method, params=None):
        self.events.append((method, deepcopy(params)))
        if method == 'session.status':
            return {'state': 'stopped', 'last_stop': deepcopy(self.stop)}
        if method == 'memory.read':
            start = int(params['address']['offset'], 16)
            return {'data_base64': base64.b64encode(self.memory[start:start + params['length']]).decode()}
        if method == 'breakpoints.create':
            self.count += 1
            if self.count == self.fail_create:
                raise DebuggerError('cannot arm second candidate')
            address = params['address']
            assert address['segment'] == f'0x{CS:04X}'
            assert address['offset'] in [f'0x{c:08X}' for c in CALLS]
            ident = f'owned-{self.count}'
            self.breakpoints[ident] = int(address['offset'], 16)
            return {'breakpoint_id': ident}
        if method == 'breakpoints.delete':
            ident = params['breakpoint_id']
            if ident == self.fail_delete:
                raise DebuggerError('transport failure during cleanup')
            if ident not in self.breakpoints:
                raise DebuggerError('Breakpoint no longer exists in the debugger (BREAKPOINT_NOT_FOUND)')
            del self.breakpoints[ident]
            return {}
        raise AssertionError(method)

    def run(self, **params):
        self.events.append(('run', params))
        if self.qualify_foreign:
            self.stop = {'kind': 'breakpoint', 'breakpoint_id': 'foreign'}
            return {'stop': {'trigger': 'breakpoint'}}
        self.regs.update(cpu_mode='protected', flags='0x202')
        self.regs['segments']['cs'] = hex(CS)
        return {'stop': {'trigger': 'guest_time'}, 'guest_elapsed_ms': params['guest_ms']}

    def hit(self, ident='owned-1'):
        address = self.breakpoints.pop(ident)
        self.regs['instruction_pointer'] = hex(address)
        self.stop = {'kind': 'breakpoint', 'breakpoint_id': ident}


def context():
    ctx = SimpleNamespace(d=Session(), state={}, captures=[])
    def capture(name, callsite, code_selector, **options):
        assert not any(ident.startswith('owned-') for ident in ctx.d.breakpoints)
        assert 'foreign' in ctx.d.breakpoints
        ctx.captures.append((name, callsite, code_selector, options))
        ctx.d.regs['instruction_pointer'] = hex(callsite + 5)
        ctx.d.stop = {'kind': 'step'}
        return {'name': name, 'status': 'returned', 'path': 'evidence/captured.json'}
    ctx.capture_native_call = capture
    return ctx


def arm(ctx, **options):
    return native_capture_watch(ctx, op='arm', name='save', callsites=list(CALLS), code_selector=CS, **options)


def test_watch_survives_trigger_error_and_finishes_the_actual_hit():
    ctx = context()
    result = arm(ctx, continuation_steps=2)
    assert result['phase'] == 'armed' and not result['candidate_hit']
    watch = ctx.state['native_capture_watch']
    # A separate UI request is interrupted by the armed event. The watch must
    # survive that request's exception rather than being cleaned in its finally.
    with pytest.raises(RuntimeError, match='input interrupted'):
        ctx.d.hit('owned-2')
        raise RuntimeError('input interrupted at debugger stop')
    ctx.d.events.clear()
    result = native_capture_watch(ctx)
    assert result['candidate_hit'] and result['hit_callsite'] == CALLS[1]
    assert ctx.state['native_capture_watch'] is watch
    assert not any(method == 'run' for method, _ in ctx.d.events)
    result = native_capture_watch(ctx, op='finish')
    assert result['watch']['phase'] == 'finished'
    assert ctx.captures == [('save', CALLS[1], CS, {'continuation_steps': 2})]
    assert ctx.d.breakpoints == {'foreign': 0x14000}


def test_finish_without_hit_preserves_watch_breakpoints_and_cpu():
    ctx = context()
    arm(ctx)
    before = deepcopy(ctx.d.breakpoints), deepcopy(ctx.d.regs)
    ctx.d.events.clear()
    with pytest.raises(RuntimeError, match='no owned candidate'):
        native_capture_watch(ctx, op='finish')
    assert (ctx.d.breakpoints, ctx.d.regs) == before
    assert ctx.state['native_capture_watch']['phase'] == 'armed'
    assert not any(m in ('run', 'breakpoints.delete') for m, _ in ctx.d.events)


def test_foreign_stop_at_candidate_is_not_consumed():
    ctx = context()
    arm(ctx)
    ctx.d.regs['instruction_pointer'] = hex(CALLS[0])
    ctx.d.stop = {'kind': 'breakpoint', 'breakpoint_id': 'foreign'}
    result = native_capture_watch(ctx)
    assert result['at_candidate'] and not result['candidate_hit']
    with pytest.raises(RuntimeError, match='no owned candidate'):
        native_capture_watch(ctx, op='finish')
    assert not ctx.captures
    native_capture_watch(ctx, op='cancel')
    assert ctx.d.breakpoints == {'foreign': 0x14000}


def test_cancel_removes_only_owned_ids_without_running_cpu():
    ctx = context()
    arm(ctx)
    ctx.d.events.clear()
    result = native_capture_watch(ctx, op='cancel')
    assert result['phase'] == 'cancelled' and not result['active']
    assert ctx.d.breakpoints == {'foreign': 0x14000}
    assert not any(m == 'run' for m, _ in ctx.d.events)


def test_partial_arm_failure_cleans_only_ids_created_so_far():
    ctx = context()
    ctx.d.fail_create = 2
    with pytest.raises(DebuggerError, match='second candidate'):
        arm(ctx)
    assert ctx.d.breakpoints == {'foreign': 0x14000}
    assert ctx.state['native_capture_watch']['phase'] == 'arm_failed'
    assert ctx.state['native_capture_watch']['breakpoints'] == []


def test_cleanup_failure_retains_remaining_owned_id_and_does_not_capture():
    ctx = context()
    arm(ctx)
    ctx.d.hit('owned-1')
    ctx.d.fail_delete = 'owned-2'
    with pytest.raises(RuntimeError, match='cleanup incomplete'):
        native_capture_watch(ctx, op='finish')
    watch = ctx.state['native_capture_watch']
    assert watch['phase'] == 'cleanup_failed'
    assert watch['breakpoints'] == [{'callsite': CALLS[1], 'breakpoint_id': 'owned-2'}]
    assert not ctx.captures
    ctx.d.fail_delete = None
    native_capture_watch(ctx, op='cancel')
    assert ctx.d.breakpoints == {'foreign': 0x14000}


def test_failed_capture_is_not_implicitly_finished_again():
    ctx = context()
    arm(ctx)
    ctx.d.hit()
    def fail(*args, **options):
        ctx.captures.append('attempted')
        raise RuntimeError('original return not reached')
    ctx.capture_native_call = fail
    with pytest.raises(RuntimeError, match='return not reached'):
        native_capture_watch(ctx, op='finish')
    assert ctx.state['native_capture_watch']['phase'] == 'finish_failed'
    with pytest.raises(ValueError, match='cannot finish in this phase'):
        native_capture_watch(ctx, op='finish')
    assert ctx.captures == ['attempted']


def test_new_runtime_does_not_reuse_old_breakpoint_ids():
    ctx = context()
    arm(ctx)
    ctx.d = Session()
    result = native_capture_watch(ctx)
    assert not result['runtime_matches']
    with pytest.raises(ValueError, match='another live owner'):
        native_capture_watch(ctx, op='cancel')
    assert ctx.d.breakpoints == {'foreign': 0x14000}


def test_normal_qualification_is_bounded_and_preserves_encountered_foreign_stop():
    ctx = context()
    ctx.d.regs.update(cpu_mode='v8086', flags='0x20202')
    result = arm(ctx)
    assert result['qualification_guest_ms'] > 0
    assert any(m == 'run' and not v['fast_forward'] for m, v in ctx.d.events)
    ctx = context()
    ctx.d.regs.update(cpu_mode='v8086', flags='0x20202')
    ctx.d.qualify_foreign = True
    with pytest.raises(RuntimeError, match='another debugger stop'):
        arm(ctx)
    assert len([m for m, _ in ctx.d.events if m == 'run']) == 1
    assert not any(m == 'breakpoints.create' for m, _ in ctx.d.events)


@pytest.mark.parametrize('bad', [[], [CALLS[0], CALLS[0]], [True], list(range(17))])
def test_invalid_candidates_are_rejected_before_breakpoint_or_run(bad):
    ctx = context()
    with pytest.raises(ValueError):
        native_capture_watch(ctx, op='arm', name='bad', callsites=bad, code_selector=CS)
    assert not ctx.d.events


def test_non_call_candidate_is_rejected_and_initial_foreign_stop_is_retained():
    ctx = context()
    ctx.d.memory[CALLS[1]] = 0x90
    with pytest.raises(ValueError, match='not an original E8'):
        arm(ctx)
    assert not any(m in ('breakpoints.create', 'run') for m, _ in ctx.d.events)
    ctx = context()
    ctx.d.stop = {'kind': 'breakpoint', 'breakpoint_id': 'foreign'}
    with pytest.raises(RuntimeError, match='initial foreign'):
        arm(ctx)
    assert not any(m in ('breakpoints.create', 'run') for m, _ in ctx.d.events)


@pytest.mark.parametrize('address', [CALLS[0], ENTRY])
def test_changed_watched_code_keeps_stop_and_watch_without_capture(address):
    ctx = context()
    arm(ctx)
    ctx.d.hit()
    ctx.d.memory[address] ^= 1
    ctx.d.events.clear()
    with pytest.raises(RuntimeError, match='changed'):
        native_capture_watch(ctx, op='finish')
    assert ctx.state['native_capture_watch']['phase'] == 'armed'
    assert not ctx.captures
    assert not any(m in ('breakpoints.delete', 'run') for m, _ in ctx.d.events)
