"""Public tracking lifecycle with a deterministic per-stop observation seam."""

import json
import pytest
from test_qemu_dos_source_admission import owned as owned

from test_qemu_dos_le_trace import active_le as active_le


@pytest.fixture
def paged(active_le, monkeypatch):  # noqa: F811
    o, s = active_le, active_le.session
    import fdisbull.qemu_le_translation as translation
    import fdisbull.qemu_paged_le_capture as capture
    import fdisbull.qemu_paged_le_observation as observation

    monkeypatch.setattr(translation, 'parse_hmp', lambda value: {'stable': True})
    monkeypatch.setattr(
        capture, '_cpu', lambda registers, context: {'ip': int(registers['instruction_pointer'], 0)}
    )

    def sample(image, version, cpu, context, physical, virtual):
        ip = cpu['ip']
        valid = ip != 0x50042
        q = dict(
            qualified=valid,
            reason=None if valid else 'unknown',
            instruction_size=2 if valid else None,
            execution_bytes='6a00' if valid else '',
            source_instruction_sha256='a' * 64 if valid else None,
            source_location={'offset': ip} if valid else None,
            context={} if valid else None,
        )
        return dict(
            qualification=q,
            mapping_identity={'ip': ip} if valid else None,
            witness={'ip': ip} if valid else None,
        )

    monkeypatch.setattr(observation, 'observe', sample)
    first = s.dos_source_bind(tracking='paged')
    return o, first


def test_paged_binding_steps_and_trace_never_reuse_unknown_mapping(paged):
    o, first = paged
    s = o.session
    assert first['live'] and first['tracking'] == 'paged'
    result = s.trace(count=3, bits=32)
    row = o.project.db.execute(
        'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
    ).fetchone()
    doc = json.loads(bytes(row['data']))
    assert doc['format'] == 'fdisbull-paged-le-trace-1'
    assert [e['qualification']['qualified'] for e in doc['events']] == [True, False, True]
    assert [e['mapping_identity'] for e in doc['events']] == [{'ip': 0x50040}, None, {'ip': 0x50044}]
    assert doc['events'][1]['witness'] is None
    assert len(o.intervals) == 3
    assert s.dos_source_binding()['live']
    s._le_source_retire('restore')
    second = s.dos_source_bind(tracking='paged')
    assert second['binding_id'] != first['binding_id']


def test_paged_budget_refuses_without_retiring_or_guest_io(paged):
    o, first = paged
    before = (len(o.peer.reads), len(o.peer.qmp_calls))
    with pytest.raises(ValueError, match='default comparison'):
        o.session.dos_source_bind(tracking='paged', max_compare_bytes=1)
    assert before == (len(o.peer.reads), len(o.peer.qmp_calls))
    assert o.session.dos_source_binding()['binding_id'] == first['binding_id']
    assert o.session.dos_source_binding()['mapping_identity'] == {'ip': 0x50040}


def test_paged_breakpoint_prevents_step_and_retains_stop(paged):
    o, _ = paged
    s = o.session
    s.breakpoints[12] = dict(access='x', address=0x50040)
    result = s.trace(count=2)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert not o.intervals and doc['outcome'] == 'foreign_stop'
    assert doc['current_stop']['breakpoint_ids'] == [12] and doc['attempted_steps'] == 0


def test_paged_step_unknown_withdraws_mapping_then_recovers(paged):
    o, _ = paged
    s = o.session
    assert s.step(timeout_ms=1000)['outcome'] == 'step'
    status = s.dos_source_binding()
    assert not status['live'] and status['mapping_identity'] is None
    assert s.step(timeout_ms=1000)['outcome'] == 'step'
    assert s.dos_source_binding()['mapping_identity'] == {'ip': 0x50044}
    s._le_source_retire('test')
    assert s.dos_source_binding()['mapping_identity'] is None


def test_paged_trace_preserves_arrived_foreign_stop(paged, monkeypatch):
    o, _ = paged
    s = o.session
    stop = dict(outcome='breakpoint', session={'stop_reason': {'native_reply': 'T05'}})
    monkeypatch.setattr(s, 'step', lambda **kwargs: stop)
    result = s.trace(count=2)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert doc['outcome'] == 'foreign_stop' and doc['current_stop'] == stop
    assert doc['attempted_steps'] == 1 and len(doc['events']) == 1


def test_paged_legacy_checkpoint_and_history_refuse(paged):
    o, _ = paged
    with pytest.raises(ValueError, match='save_machine_state'):
        o.session.save_le_source_state()
    with pytest.raises(ValueError, match='does not support LE source history'):
        o.session.le_rewind_start()


def test_paged_trace_retains_exact_stop_after_control_error(paged, monkeypatch):
    o, _ = paged
    s = o.session
    s.vm.machine_stopped = True
    stop = dict(outcome='step', session={'stop_reason': {'native_reply': 'T05'}})

    def failure(**kwargs):
        error = RuntimeError('publication failed after stop')
        error.result = stop
        raise error

    monkeypatch.setattr(s, 'step', failure)
    result = s.trace(count=2)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert doc['outcome'] == 'error' and doc['current_stop'] == stop
    assert doc['attempted_steps'] == 1 and len(doc['events']) == 1
    assert doc['error']['message'] == 'publication failed after stop'


def test_paged_timeout_records_single_attempt_without_retry(paged, monkeypatch):
    o, _ = paged
    s = o.session
    s.vm.machine_stopped = True
    calls = []

    def timed_out(**kwargs):
        calls.append(1)
        raise TimeoutError('native stop timed out')

    monkeypatch.setattr(s, 'step', timed_out)
    result = s.trace(count=3)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert calls == [1] and doc['outcome'] == 'timeout'
    assert doc['attempted_steps'] == 1 and len(doc['events']) == 1


def test_transport_failure_during_observation_stops_trace(paged, monkeypatch):
    from fdisbull.dosbox_rpc import DebuggerError
    import fdisbull.qemu_paged_le_observation as observation

    o, _ = paged
    o.session.vm.machine_stopped = True

    def failure(*args):
        raise DebuggerError('lost native channel')

    monkeypatch.setattr(observation, 'observe', failure)
    result = o.session.trace(count=2)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert doc['outcome'] == 'error' and doc['error']['message'] == 'lost native channel'
    assert doc['attempted_steps'] == 0 and not o.intervals
    assert not o.session.dos_source_binding()['live']
    assert o.session.dos_source_binding()['mapping_identity'] is None


def test_context_change_during_observation_stops_trace(paged, monkeypatch):
    import fdisbull.qemu_le_translation as translation

    o, _ = paged
    o.session.vm.machine_stopped = True
    calls = []

    def changing(value):
        calls.append(1)
        return {'stable': len(calls) == 1}

    monkeypatch.setattr(translation, 'parse_hmp', changing)
    result = o.session.trace(count=2)
    doc = json.loads(
        bytes(
            o.project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)
            ).fetchone()['data']
        )
    )
    assert doc['outcome'] == 'error' and 'context changed' in doc['error']['message']
    assert doc['attempted_steps'] == 0 and not o.intervals
    assert o.session.dos_source_binding()['mapping_identity'] is None
