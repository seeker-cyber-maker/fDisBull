import base64
from copy import deepcopy

import pytest

from fdisbull import z_dos


def registers(mode='protected', cs='0x70', ip='0x4000', flags='0x202', esp='0x8000'):
    return {'cpu_mode': mode, 'segments': {'cs': cs}, 'instruction_pointer': ip,
            'flags': flags, 'general': {'esp': esp}}


class Session:
    def __init__(self, contexts=None, stops=None, initial_kind='pause'):
        self.contexts = contexts or [registers(), registers(cs='0x170', ip='0x123400')]
        self.stops = stops or []
        self.initial_kind = initial_kind
        self.events = []
        self.index = 0
        self.bad_read = False

    def call(self, method, params=None):
        self.events.append((method, params))
        if method == 'session.status':
            return {'state': 'stopped', 'stop_reason': {'kind': self.initial_kind}}
        assert method == 'memory.read'
        if self.bad_read:
            raise RuntimeError('unmapped linear probe')
        return {'data_base64': base64.b64encode(b'\x90'*params['length']).decode()}

    def registers(self):
        self.events.append(('registers', None))
        return deepcopy(self.contexts[min(self.index, len(self.contexts)-1)])

    def run(self, **params):
        self.events.append(('run', params))
        assert params['fast_forward'] is False and params['stop_on_hook'] is True
        self.index += 1
        if len(self.stops) >= self.index:
            return self.stops[self.index-1]
        return {'stop': {'trigger': 'guest_time'}, 'guest_elapsed_ms': params['guest_ms']+1,
                'session': {'stop_reason': {'kind': 'pause'}}}


def test_normal_probes_expose_contexts_and_keep_selectors_as_hypotheses():
    session = Session(contexts=[registers(), registers(mode='real', cs='0xC000', ip='0x42'),
                                registers(cs='0x170', ip='0x123400')])
    result = z_dos.sample_execution_contexts(session, probes=2)
    assert result['status'] == 'sampled' and result['completed_probes'] == 2
    assert [row['cpu_mode'] for row in result['observations']] == ['protected', 'real', 'protected']
    assert result['observations'][2]['ip'] == '0x123400'
    assert result['observations'][2]['observed_guest_ms'] == 2
    assert [c['selector'] for c in result['selector_candidates']] == ['0x70', '0x170']
    assert all(c['qualified'] is False for c in result['selector_candidates'])
    assert not any(op == 'memory.read' for op, _ in session.events)


@pytest.mark.parametrize('stop', [
    {'stop': {'trigger': 'breakpoint'}, 'session': {'stop_reason': {'kind': 'breakpoint', 'breakpoint_id': 'foreign'}}},
    {'stop': {'trigger': 'hook'}, 'hook_hits': [{'hook_id': 'foreign'}]},
    {'stop': {'trigger': 'guest_time'}, 'session': {'stop_reason': {'kind': 'breakpoint'}}},
    {'stop': {'trigger': 'trace_complete'}},
])
def test_foreign_stop_collects_context_but_is_never_resumed(stop):
    session = Session(stops=[stop])
    result = z_dos.sample_execution_contexts(session, probes=8)
    assert result['status'] == 'stopped' and result['completed_probes'] == 1
    assert len(result['observations']) == 2
    assert sum(op == 'run' for op, _ in session.events) == 1
    assert result['stop']['trigger'] == stop['stop']['trigger']


def test_existing_breakpoint_is_observed_without_any_resume():
    session = Session(initial_kind='breakpoint')
    result = z_dos.sample_execution_contexts(session)
    assert result['status'] == 'stopped' and result['completed_probes'] == 0
    assert len(result['observations']) == 1
    assert not any(op == 'run' for op, _ in session.events)


def test_optional_linear_bytes_are_explicitly_unqualified_and_read_failure_is_isolated():
    session = Session()
    session.bad_read = True
    result = z_dos.sample_execution_contexts(session, probes=2, linear_bytes=12)
    assert result['status'] == 'sampled' and result['completed_probes'] == 2
    assert all(row['linear_ip_probe']['status'] == 'unresolved' for row in result['observations'])
    assert all('unqualified' in row['linear_ip_probe']['mapping'] for row in result['observations'])
    session = Session()
    result = z_dos.sample_execution_contexts(session, probes=1, linear_bytes=12)
    assert result['observations'][1]['linear_ip_probe']['hex'] == '90'*12
    assert result['observations'][1]['linear_ip_probe']['address'] == '0x123400'
    assert not result['selector_candidates'][1]['qualified']


def test_virtual_8086_flag_does_not_create_protected_selector_candidate():
    session = Session(contexts=[registers(flags='0x20202')])
    result = z_dos.sample_execution_contexts(session, probes=1)
    assert result['selector_candidates'] == []


def test_required_register_failure_stops_without_discarding_earlier_context():
    session = Session()
    original = session.registers

    def read():
        if session.index:
            raise RuntimeError('register context unavailable')
        return original()

    session.registers = read
    result = z_dos.sample_execution_contexts(session, probes=8)
    assert result['status'] == 'error' and result['completed_probes'] == 1
    assert len(result['observations']) == 1
    assert result['errors'][0]['phase'] == 'registers'
    assert sum(op == 'run' for op, _ in session.events) == 1


def test_running_session_is_not_sampled_or_paused_implicitly():
    session = Session()
    session.call = lambda method: {'state': 'running'}
    result = z_dos.sample_execution_contexts(session)
    assert result['status'] == 'not_stopped' and not result['observations']
    assert session.events == []


def test_host_deadline_bounds_all_runs_and_retains_collected_observations(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(z_dos.time, 'monotonic', lambda: clock[0])
    session = Session()
    original = session.run

    def run(**params):
        reply = original(**params)
        clock[0] += 0.003
        return reply

    session.run = run
    result = z_dos.sample_execution_contexts(session, probes=10, timeout_ms=5)
    runs = [value for operation, value in session.events if operation == 'run']
    assert result['status'] == 'deadline'
    assert len(runs) == 2 and runs[0]['timeout_ms'] <= 5 and runs[1]['timeout_ms'] <= 2
    assert len(result['observations']) == 2  # Initial + first readback fit the deadline.


@pytest.mark.parametrize('options', [
    {'probes': 0}, {'probes': 65}, {'guest_ms': 0}, {'guest_ms': True},
    {'timeout_ms': 60001}, {'linear_bytes': 65},
])
def test_invalid_sampling_request_has_no_guest_effect(options):
    session = Session()
    with pytest.raises(ValueError):
        z_dos.sample_execution_contexts(session, **options)
    assert session.events == []

@pytest.mark.parametrize('kind,expected_probes', [('pause', 1), ('breakpoint', 0)])
def test_native_last_stop_shape_samples_pause_but_retains_breakpoint(kind, expected_probes):
    session = Session(initial_kind=kind)
    original = session.call
    def native_call(method, params=None):
        result = original(method, params)
        if method == 'session.status':
            result['last_stop'] = result.pop('stop_reason')
        return result
    session.call = native_call
    result = z_dos.sample_execution_contexts(session, probes=1)
    assert result['completed_probes'] == expected_probes
    assert sum(op == 'run' for op, _ in session.events) == expected_probes
