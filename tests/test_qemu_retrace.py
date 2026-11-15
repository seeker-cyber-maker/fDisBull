"""Host retrace admission and evidence at the production QMP envelope.

This deterministic peer proves protocol validation and host deadlines only.
Independent authored native fixtures establish the VGA model and guest reads.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_retrace import (
    RETRACE_COMMANDS, RETRACE_MODEL, admit_retrace,
    machine_retrace_arguments, machine_retrace_configuration,
)
from test_qemu_clock_budget import NativeWire, owned


RAW = {'msr': 1, 'sr1': 0, 'cr00': 95, 'cr04': 80, 'cr05': 9,
       'cr06': 98, 'cr07': 0, 'cr10': 80, 'cr11': 9, 'vbe-enable': 0}
# Authored model-v1 tuple: 100 characters/line, 100 lines/period, 317 ns/char.
# The inclusive horizontal/vertical windows both contain positions 80..90.
TIMING = {'ticks-per-char': 317, 'total-chars': 10_000, 'htotal': 100,
          'hstart': 80, 'hend': 90, 'vstart': 80, 'vend': 90, 'freq': 0}


class RetraceWire(NativeWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.retrace = {
            'api-version': 1, 'model': RETRACE_MODEL, 'epoch': 1, 'virtual-ns': 1000,
            'device': '/machine/unattached/device[0]', 'device-type': 'VGA',
            'console': 0, 'head': 0, 'timing-generation': 1, 'phase-supported': False,
            'unsupported-reason': 'uninitialized', 'raw': deepcopy(RAW),
            'timing': {key: 0 for key in TIMING},
        }
        self.mutate = lambda value: value
        self.after_query = lambda: None
        self.reject_query = False

    def initialized(self, generation=2):
        self.retrace.update({'raw': deepcopy(RAW), 'timing': deepcopy(TIMING),
                             'timing-generation': generation, 'phase-supported': True})
        self.retrace.pop('unsupported-reason', None)

    def value(self):
        value = deepcopy(self.retrace)
        value['virtual-ns'] = self.receipt['virtual-ns']
        if value['phase-supported']:
            timing = value['timing']
            period = timing['ticks-per-char'] * timing['total-chars']
            phase_ns = value['virtual-ns'] % period
            character = phase_ns // timing['ticks-per-char']
            line, horizontal = divmod(character, timing['htotal'])
            vertical_retrace = timing['vstart'] <= line <= timing['vend']
            horizontal_retrace = timing['hstart'] <= horizontal <= timing['hend']
            value['phase'] = {
                'period-ns': period, 'phase-ns': phase_ns, 'character': character,
                'line': line, 'line-character': horizontal,
                'vertical-retrace': vertical_retrace, 'horizontal-retrace': horizontal_retrace,
                'status1-timing-bits': (8 if vertical_retrace else 0) | (1 if vertical_retrace or horizontal_retrace else 0),
            }
        return self.mutate(value)

    def sendall(self, data):
        request = json.loads(data)
        if request['execute'] != 'x-fdisbull-query-retrace':
            return super().sendall(data)
        assert request.get('arguments', {}) == {}
        self.calls.append((request['execute'], request.get('arguments', {})))
        self.budgets.append(self.timeout)
        answer = ({'error': {'class': 'GenericError', 'desc': 'Native VGA ownership invalidated'}}
                  if self.reject_query else {'return': self.value()})
        self.buffer.extend(json.dumps(dict(id=request['id'], **answer)).encode() + b'\n')
        self.delay = self.latency
        self.after_query()


@pytest.fixture
def retrace(owned):
    o = owned
    o.wire = RetraceWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= RETRACE_COMMANDS
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    o.vm.native_clock_admission = deepcopy(o.wire.receipt)
    o.vm.machine_configuration['native_retrace_admission'] = admit_retrace(o.vm)
    o.context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    o.context.run_id = 'owned-retrace-run'
    o.context.capabilities['retrace_observation'] = True
    o.journal = []
    o.context._event = lambda name, value: o.journal.append((name, deepcopy(value)))
    o.wire.calls.clear(); o.wire.budgets.clear()
    return o


def initialized(retrace):
    retrace.wire.initialized()
    return retrace


def change(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


def test_standard_profile_keeps_default_arguments_and_precise_is_explicit():
    assert machine_retrace_arguments('standard') == []
    assert machine_retrace_arguments('precise') == [
        '-vga', 'std,retrace=precise', '-global', 'VGA.x-fdisbull-retrace=on']
    standard = machine_retrace_configuration('standard', 'standard')
    assert standard['adapter'] is standard['model'] is standard['retrace'] is None
    precise = machine_retrace_configuration('precise', 'virtual')
    assert precise['model'] == RETRACE_MODEL and precise['host_synchronization'] is False
    for profile in (None, True, 'adaptive', 'dumb'):
        with pytest.raises(ValueError):
            machine_retrace_configuration(profile, 'virtual')
    for profile in ('standard', 'instruction'):
        with pytest.raises(ValueError, match='virtual'):
            machine_retrace_configuration('precise', profile)


def test_uninitialized_admission_and_observation_do_not_invent_phase(retrace):
    o = retrace
    assert o.vm.native_retrace_admission['unsupported-reason'] == 'uninitialized'
    result = o.context.retrace_observe(timeout_ms=250)
    assert result['phase_supported'] is False and result['phase'] is None
    assert result['unsupported_reason'] == 'uninitialized'
    assert result['completed_renderer_update'] is result['completed_guest_frame'] is result['guest_frame_id'] is None
    assert result['run'] == 'owned-retrace-run'
    assert result['native_epoch'] == 1 and result['observed_ns'] == 1000
    assert [command for command, _ in o.wire.calls] == [
        'query-status', 'query-replay', 'x-fdisbull-query-clock',
        'x-fdisbull-query-retrace', 'query-status', 'query-replay', 'x-fdisbull-query-clock']
    assert [name for name, _ in o.journal] == ['machine-retrace-observe']
    assert not o.executions and not o.vm.closed


def test_phase_receipt_shares_clock_epoch_without_extra_clock_journals(retrace):
    o = initialized(retrace)
    before = o.context.clock_observe()
    result = o.context.retrace_observe()
    after = o.context.clock_observe()
    assert result['epoch'] == before['epoch'] == after['epoch']
    assert [before['sequence'], result['clocks']['before']['sequence'],
            result['clocks']['after']['sequence'], after['sequence']] == [1, 2, 3, 4]
    assert result['phase'] == {'period-ns': 3_170_000, 'phase-ns': 1000,
        'character': 3, 'line': 0, 'line-character': 3,
        'vertical-retrace': False, 'horizontal-retrace': False, 'status1-timing-bits': 0}
    assert result['raw'] == RAW and result['timing'] == TIMING
    assert [name for name, _ in o.journal] == [
        'machine-clock-observe', 'machine-retrace-observe', 'machine-clock-observe']
    result['raw']['cr10'] = 99
    assert o.journal[1][1]['raw']['cr10'] == o.vm._retrace_last['raw']['cr10'] == 80


@pytest.mark.parametrize('line,character,bits', [
    (0, 79, 0), (0, 80, 1), (0, 90, 1), (0, 91, 0),
    (79, 0, 0), (80, 0, 9), (90, 0, 9), (91, 0, 0), (80, 80, 9),
])
def test_inclusive_model_windows_and_period_wrap(retrace, line, character, bits):
    o = initialized(retrace)
    o.wire.receipt['virtual-ns'] = 3_170_000 + (line * 100 + character) * 317
    result = o.context.retrace_observe()
    assert result['phase']['line'] == line and result['phase']['line-character'] == character
    assert result['phase']['status1-timing-bits'] == bits


@pytest.mark.parametrize('msr,ticks', [(0, 357), (1, 317), (4, 317), (5, 282),
                                       (8, 357), (9, 317), (12, 357), (13, 317)])
def test_declared_character_clock_uses_msr_bit_zero_and_integer_double_floor(retrace, msr, ticks):
    o = initialized(retrace)
    o.wire.retrace['raw']['msr'] = msr
    o.wire.retrace['timing']['ticks-per-char'] = ticks
    result = o.context.retrace_observe()
    assert result['timing']['ticks-per-char'] == ticks
    assert result['phase']['period-ns'] == ticks * 10_000


def test_raw_overflow_bits_and_effective_sequencer_width_are_not_lost(retrace):
    o = initialized(retrace)
    o.wire.retrace['raw'].update(msr=5, sr1=8, cr05=0x69, cr07=0xa5)
    o.wire.retrace['timing'] = {
        'ticks-per-char': 282, 'htotal': 200, 'total-chars': 173_600,
        'hstart': 83, 'hend': 93, 'vstart': 848, 'vend': 858, 'freq': 0,
    }
    result = o.context.retrace_observe()
    assert result['phase']['period-ns'] == 48_955_200
    assert result['timing']['total-chars'] // result['timing']['htotal'] == 868


@pytest.mark.parametrize('path,value', [
    (('api-version',), True), (('model',), 'qemu-vga-precise'), (('epoch',), 2),
    (('epoch',), True), (('virtual-ns',), 1001), (('device',), 'not-canonical'),
    (('device',), '/bad\npath'), (('device',), '/bad\ud800'),
    (('device',), '/' + '\u00e9' * 256),
    (('device-type',), 'isa-vga'), (('console',), True), (('head',), 1),
    (('timing-generation',), 0), (('timing-generation',), True),
    (('timing-generation',), 1 << 64), (('phase-supported',), 1),
    (('raw', 'cr10'), True), (('raw', 'msr'), 256), (('raw', 'vbe-enable'), 65536),
    (('raw', 'extra'), 0), (('timing', 'ticks-per-char'), 318),
    (('timing', 'freq'), 60), (('timing', 'htotal'), True),
    (('phase', 'phase-ns'), 1001), (('phase', 'period-ns'), 3_170_001),
    (('phase', 'character'), 4), (('phase', 'line'), 1),
    (('phase', 'line-character'), 4), (('phase', 'vertical-retrace'), True),
    (('phase', 'horizontal-retrace'), True), (('phase', 'status1-timing-bits'), 8),
    (('phase', 'line'), False), (('phase', 'extra'), 1), (('guest-frame-id',), 1),
])
def test_malformed_or_contradictory_native_receipt_closes_owner(retrace, path, value):
    o = initialized(retrace)
    o.wire.mutate = lambda receipt: change(receipt, path, value)
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed and not o.executions and not o.journal


def test_unsupported_vbe_or_wrapped_timing_is_normal_and_generation_qualified(retrace):
    o = initialized(retrace)
    first = o.context.retrace_observe()
    o.wire.retrace['raw']['vbe-enable'] = 1
    o.wire.retrace.update({'phase-supported': False, 'unsupported-reason': 'vbe-enabled',
                           'timing-generation': 3})
    vbe = o.context.retrace_observe()
    assert vbe['phase'] is None and vbe['unsupported_reason'] == 'vbe-enabled'
    o.wire.initialized(generation=4)
    o.wire.retrace['raw']['cr11'] = 15
    o.wire.retrace['raw']['cr10'] = o.wire.retrace['timing']['vstart'] = 95
    o.wire.retrace['timing']['vend'] = 111
    o.wire.retrace.update({'phase-supported': False, 'unsupported-reason': 'invalid-timing'})
    invalid = o.context.retrace_observe()
    assert invalid['unsupported_reason'] == 'invalid-timing' and invalid['phase'] is None
    assert first['timing_generation'] < vbe['timing_generation'] < invalid['timing_generation']
    assert not o.vm.closed


def test_unsupported_reason_and_phase_fields_have_exact_state_shape(retrace):
    o = retrace
    o.wire.mutate = lambda value: dict(value, phase={})
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed


@pytest.mark.parametrize('mutation', ['reason', 'support', 'cached-model'])
def test_uninitialized_cannot_be_relabelled_or_populated_incoherently(retrace, mutation):
    o = retrace
    if mutation == 'reason':
        o.wire.mutate = lambda value: dict(value, **{'unsupported-reason': 'vbe-enabled'})
    elif mutation == 'support':
        o.wire.mutate = lambda value: dict(value, **{'phase-supported': True})
    else:
        o.wire.mutate = lambda value: change(value, ('timing', 'htotal'), 100)
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed


@pytest.mark.parametrize('mutation', ['device', 'generation', 'raw', 'support'])
def test_owned_identity_and_same_generation_configuration_are_immutable(retrace, mutation):
    o = initialized(retrace)
    o.context.retrace_observe()
    if mutation == 'device':
        o.wire.retrace['device'] = '/machine/unattached/device[1]'
    elif mutation == 'generation':
        o.wire.retrace['timing-generation'] = 1
    elif mutation == 'raw':
        o.wire.retrace['raw']['cr10'] = 81
        o.wire.retrace['timing'].update(vstart=81, vend=91)
    else:
        o.wire.retrace['raw']['vbe-enable'] = 1
        o.wire.retrace.update({'phase-supported': False, 'unsupported-reason': 'vbe-enabled'})
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed and len(o.journal) == 1


def test_generation_jump_preserves_unobserved_change_and_restore(retrace):
    o = initialized(retrace)
    first = o.context.retrace_observe()
    o.wire.retrace['timing-generation'] = 4  # Native A -> B -> A between queries.
    restored = o.context.retrace_observe()
    assert restored['raw'] == first['raw'] and restored['timing'] == first['timing']
    assert restored['timing_generation'] == first['timing_generation'] + 2
    assert not o.vm.closed


@pytest.mark.parametrize('field', ['time', 'counter', 'epoch'])
def test_stopped_bracket_drift_never_publishes_a_qualified_phase(retrace, field):
    o = initialized(retrace)
    def drift():
        if field == 'time':
            o.wire.receipt['virtual-ns'] += 1
        elif field == 'counter':
            o.wire.counter += 1
        else:
            o.wire.receipt['epoch'] += 1
    o.wire.after_query = drift
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed and not o.journal and not o.executions


def test_native_model_query_error_is_terminal_without_retry(retrace):
    o = retrace
    o.wire.reject_query = True
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed
    assert sum(command == 'x-fdisbull-query-retrace' for command, _ in o.wire.calls) == 1


def test_direct_observation_uses_one_shrinking_deadline_through_all_qmp_reads(retrace):
    o = initialized(retrace)
    o.wire.latency = .01
    o.context.retrace_observe(timeout_ms=100)
    assert o.wire.budgets == pytest.approx([.10, .09, .08, .07, .06, .05, .04])
    assert o.clock.now == pytest.approx(100.07)
    assert o.vm.operation_deadline is o.qmp.operation_deadline is o.remote.operation_deadline is None
    assert o.context._deadline is None


def test_expired_read_closes_uncertain_channel_and_restores_incoming_bounds(retrace):
    o = initialized(retrace)
    o.wire.latency = .03
    o.vm.operation_deadline = 101.0
    o.qmp.operation_deadline = 100.08
    o.remote.operation_deadline = 102.0
    with pytest.raises(TimeoutError):
        o.context.retrace_observe(timeout_ms=500)
    assert o.clock.now == pytest.approx(100.08)
    assert o.vm.closed and not o.journal
    assert o.vm.operation_deadline == 101.0 and o.qmp.operation_deadline == 100.08
    assert o.remote.operation_deadline == 102.0


@pytest.mark.parametrize('kind', ['failure', 'late'])
def test_observed_result_survives_failed_or_late_evidence_persistence(retrace, kind):
    o = initialized(retrace)
    def journal(name, value):
        if kind == 'failure':
            raise OSError('Authored evidence failure')
        o.journal.append((name, deepcopy(value)))
        o.clock.now += .2
    o.context._event = journal
    with pytest.raises(OSError if kind == 'failure' else TimeoutError) as caught:
        o.context.retrace_observe(timeout_ms=100)
    result = caught.value.result
    assert result['phase_supported'] and result['native']['model'] == RETRACE_MODEL
    assert result['clocks']['before']['virtual_ns'] == result['clocks']['after']['virtual_ns'] == 1000
    assert not o.vm.closed and not o.executions


def test_caller_transaction_refuses_before_native_read(retrace):
    o = retrace
    o.context.project.db.in_transaction = True
    with pytest.raises(ValueError, match='transaction'):
        o.context.retrace_observe()
    assert not o.wire.calls and not o.vm.closed


@pytest.mark.parametrize('field,value', [
    ('retrace_profile', {'profile': 'standard'}), ('retrace_profile', 'precise'),
    ('clock_profile', 'virtual'), ('cpus', True),
])
def test_admitted_profile_loss_closes_before_any_native_query(retrace, field, value):
    o = retrace
    o.vm.machine_configuration[field] = value
    with pytest.raises(DebuggerError):
        o.context.retrace_observe()
    assert o.vm.closed and not o.wire.calls
