"""Public trace routing and bounded LE collection; native peers are separate."""
from copy import deepcopy
import json

import pytest

from fdisbull import qemu_dos_trace as collector
from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.execution_trace import ExecutionTraceError
from test_qemu_dos_source_admission import owned


@pytest.fixture
def routed(owned, monkeypatch):
    owned.bound = False
    owned.collections = []
    owned.session._le_source_bound = lambda: owned.bound
    owned.session._le_source_trace_binding = lambda: pytest.fail('Routing attempted a hidden source bind')

    def collect(session, **options):
        assert session is owned.session
        owned.collections.append(deepcopy(options))
        return dict(trace=dict(artifact='routed-trace', source_view=options['source_view']),
                    outcome='predicate', complete=True, matched=True, exact_stop=True)

    monkeypatch.setattr(collector, '_collect', collect)
    return owned


@pytest.mark.parametrize('installed,explicit,bits,expected', [
    (False, None, 16, 'initial-dos'),
    (True, None, 32, 'embedded-le'),
    (True, 'embedded-le', None, 'embedded-le'),
    (True, 'initial-dos', 16, 'initial-dos'),
])
def test_count_trace_selects_only_the_installed_or_explicit_view(routed, installed, explicit, bits, expected):
    routed.bound = installed
    result = routed.session.trace(count=2, bits=bits, source_view=explicit)
    assert result['source_view'] == expected
    assert routed.collections == [dict(name='machine-trace.json', count=2, max_steps=2,
                                        timeout_ms=10000, source_view=expected)]
    assert routed.peer.reads == routed.peer.qmp_calls == []


def test_explicit_le_without_handle_refuses_without_hidden_binding(routed):
    with pytest.raises(ValueError, match='explicitly bound'):
        routed.session.trace(bits=32, source_view='embedded-le')
    with pytest.raises(ValueError, match='explicitly bound'):
        routed.session.trace_until(dict(kind='register', register='eax', equals=1),
                                   source_view='embedded-le')
    assert not routed.collections and not routed.peer.reads and not routed.peer.qmp_calls


@pytest.mark.parametrize('installed,bits', [(False, 32), (True, 16), (True, True)])
def test_source_view_width_mismatch_refuses_before_collection(routed, installed, bits):
    routed.bound = installed
    with pytest.raises(ValueError, match='mode'):
        routed.session.trace(bits=bits)
    assert not routed.collections and not routed.peer.reads and not routed.peer.qmp_calls


@pytest.mark.parametrize('view', ['le', 1, True, [], {}, '$binding'])
@pytest.mark.parametrize('operation', ['trace', 'trace-until'])
def test_invalid_saved_view_refuses_before_an_earlier_write(routed, view, operation):
    step = dict(op=operation, source_view=view)
    if operation == 'trace-until':
        step['until'] = dict(kind='register', register='eax', equals=1)
    route = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-registers', registers={'rax': dict(expected=0, value=1)}), step])
    routed.session.write_registers = lambda *a, **kw: pytest.fail('Invalid later trace allowed an earlier write')
    with pytest.raises(ValueError, match='source_view'):
        execute_script(routed.session, route)
    assert not routed.collections and not routed.peer.reads and not routed.peer.qmp_calls


def test_saved_le_predicate_view_is_validated_without_leaking_into_generic_descriptor(routed):
    routed.bound = True
    until = dict(kind='register', register='eax', equals=7)
    route = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='trace-until', until=until, source_view='embedded-le', max_steps=2)])
    assert validate_script(route, session=routed.session)[0]['source_view'] == 'embedded-le'
    assert validate_script(route)[0]['source_view'] == 'embedded-le'
    result = routed.session.trace_until(until, source_view='embedded-le', max_steps=2)
    assert result['matched'] and routed.collections[0]['source_view'] == 'embedded-le'
    routed.bound = False
    with pytest.raises(ValueError, match='explicitly bound'):
        validate_script(route, session=routed.session)


def test_public_json_trace_preserves_explicit_view_and_initial_dos_override(routed):
    routed.bound = True
    workspace = DebugWorkspace()
    workspace.sessions[routed.session.run_id] = routed.session
    for method, params, view in [
        ('debug-trace', dict(count=2, bits=32), 'embedded-le'),
        ('debug-trace', dict(count=2, bits=16, source_view='initial-dos'), 'initial-dos'),
        ('debug-trace-until', dict(until=dict(kind='register', register='eax', equals=7),
                                  max_steps=2, source_view='embedded-le'), 'embedded-le'),
    ]:
        reply = respond(dict(method=method, params=dict(run=routed.session.run_id, **params)),
                        default_project=str(routed.project.path), debugger=workspace)
        assert reply['ok'], reply
        assert routed.collections[-1]['source_view'] == view
    assert not routed.peer.reads and not routed.peer.qmp_calls


@pytest.fixture
def active_le(owned):
    """Use production source admission/binding/observation and public GDB steps."""
    s, peer = owned.session, owned.peer
    # Production QMP and GDB have independent transport deadline state.
    from types import SimpleNamespace
    s.vm.qmp = SimpleNamespace(call=peer.call, operation_deadline=None)
    s.metadata.update(process=deepcopy(s._process),
                      machine_configuration=deepcopy(s.vm.machine_configuration))
    s.breakpoints, s.next_bp, s._return_breakpoint = {}, 1, None
    s._launching = False
    owned.intervals, owned.requests = [], []
    owned.after_step = None
    owned.step_failure = None

    def request(command, **options):
        owned.requests.append(command)
        if command == 'qqemu.sstepbits':
            return b'ENABLE=1,NOIRQ=2,NOTIMER=4'
        if command == 'qqemu.sstep':
            return b'0x7'
        pytest.fail('Unexpected native control: '+command)

    def execute(command, timeout_ms, *, after_send=None):
        # The authored runtime at 50040 is a sequence of two-byte PUSH imm8.
        assert command == 's' and after_send is None and 0 < timeout_ms <= 10000
        owned.intervals.append((command, timeout_ms))
        if owned.step_failure is not None:
            raise owned.step_failure
        peer.cpu['ip'] += 2
        if owned.after_step is not None:
            owned.after_step(owned)
        return b'T05', False

    peer.request, peer.execute = request, execute
    owned.original_mapping = deepcopy(s._process)
    owned.binding = s.dos_source_bind(expected_source_sha256=owned.project.meta['source_sha256'])
    assert owned.binding['live'] is True
    return owned


def stored_trace(o, artifact):
    row = o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
    return json.loads(bytes(row['data']))


def test_actual_bound_count_trace_uses_gdb_steps_and_keeps_le_namespace(active_le):
    o, s = active_le, active_le.session
    result = s.trace(count=2, bits=32)
    doc = stored_trace(o, result['artifact'])
    assert len(o.intervals) == 2 and o.peer.cpu['ip'] == 0x50044
    assert o.requests == ['qqemu.sstepbits', 'qqemu.sstep']
    assert doc['native_process_capture']['format'] == 'fdisbull-qemu-dos-le-capture-1'
    assert doc['native_process_capture']['source_scope'] == 'owned-revalidated-LE-stop-sequence'
    assert doc['native_process_capture']['binding_id'] == o.binding['binding_id']
    assert doc['mapping']['protected_source_binding']['binding_id'] == o.binding['binding_id']
    assert doc['mapping']['protected_source_binding_artifact']['artifact'] == o.binding['artifact']['artifact']
    assert doc['mapping']['protected_source_binding_material']['gdt_hex'] == o.peer.table.hex()
    assert doc['regions'] == [] and doc['complete'] and doc['window']['closed']
    assert [e['identity']['source_location']['object_offset'] for e in doc['events']] == [64, 66]
    assert all(e['project_address'] is e['task_id'] is None for e in doc['events'])
    assert all(e['observation']['instruction_completed'] is None for e in doc['events'])
    assert all('gdt_hex' not in e['le_source_witness'] for e in doc['events'])
    assert s._process == o.original_mapping


def test_actual_bound_json_predicate_stops_at_exact_source_boundary(active_le):
    o, s = active_le, active_le.session
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    reply = respond(dict(method='debug-trace-until', params=dict(run=s.run_id,
        until=dict(kind='register', register='eip', equals=0x50044), max_steps=4,
        source_view='embedded-le')), default_project=str(o.project.path), debugger=workspace)
    assert reply['ok'], reply
    result = reply['result']
    assert result['outcome'] == 'predicate' and result['matched'] and result['exact_stop']
    assert result['steps'] == result['attempted_steps'] == len(o.intervals) == 2
    assert result['matched_event']['site']['space'] == 'embedded-le'
    assert result['matched_event']['pc']['project'] is None
    doc = stored_trace(o, result['trace_artifact'])
    assert [e['identity']['source_location']['object_offset'] for e in doc['events']] == [64, 66, 68]
    assert [e['observation']['instruction_completed'] for e in doc['events']] == [None, None, False]
    assert doc['window']['closed'] and s._process == o.original_mapping


def test_unqualified_le_endpoint_cannot_match_predicate_or_execute_again(active_le):
    o, s = active_le, active_le.session
    o.after_step = lambda current: current.peer.cpu.update(ip=0x90000)
    result = s.trace_until(dict(kind='register', register='eip', equals=0x90000),
                           max_steps=4)
    assert result['outcome'] == 'source_boundary'
    assert not result['matched'] and not result['exact_stop'] and not result['source_window_closed']
    assert result['steps'] == result['attempted_steps'] == len(o.intervals) == 1
    doc = stored_trace(o, result['trace_artifact'])
    assert len(doc['events']) == 2 and not doc['window']['closed']
    terminal = doc['events'][-1]
    assert not terminal['source_qualification']['qualified']
    assert terminal['identity'].get('source_location') is None
    assert terminal['identity'].get('context') is terminal['identity'].get('source_instruction_sha256') is None
    assert terminal['observation']['instruction_completed'] is False


def test_le_foreign_breakpoint_stops_before_native_dispatch(active_le):
    o, s = active_le, active_le.session
    s.breakpoints['authored-user-point'] = dict(access='x', address=0x50040)
    result = s.trace_until(dict(kind='register', register='eip', equals=0x50044), max_steps=3)
    assert result['outcome'] == 'foreign_stop' and not result['source_window_closed']
    assert result['foreign_stop']['breakpoint_ids'] == ['authored-user-point']
    assert not o.intervals and result['attempted_steps'] == 0
    assert s.breakpoints['authored-user-point']['address'] == 0x50040


def test_le_linear_region_predicate_and_project_region_refusal(active_le):
    o, s = active_le, active_le.session
    with pytest.raises(ValueError, match='linear regions'):
        s.trace_until(dict(kind='region-change'), regions=[
            dict(id='mz-is-not-le', space='project', start=0, end=0x100000)], max_steps=3)
    assert not o.intervals
    result = s.trace_until(dict(kind='region-change'), regions=[
        dict(id='first', space='linear', start=0x50040, end=0x50044),
        dict(id='second', space='linear', start=0x50044, end=0x50050)], max_steps=3)
    assert result['outcome'] == 'predicate' and result['matched_event']['region']['id'] == 'second'
    assert len(o.intervals) == result['steps'] == 2


def test_le_step_error_preserves_arrived_native_receipt_and_never_replays(active_le):
    o, s = active_le, active_le.session
    failure = OSError('authored protected stop publication failure')
    failure.result = dict(outcome='step', timed_out=False,
        session=dict(state='stopped', stop_reason=dict(native_reply='T05', kind='step')))
    o.step_failure = failure
    result = s.trace_until(dict(kind='register', register='eip', equals=0x50044), max_steps=3)
    assert result['outcome'] == 'error' and result['error']['type'] == 'OSError'
    assert result['attempted_steps'] == len(o.intervals) == 1 and result['steps'] == 0
    assert result['current_stop'] == failure.result
    doc = stored_trace(o, result['trace_artifact'])
    assert not doc['window']['closed'] and len(doc['events']) == 1
    assert doc['events'][0]['observation']['instruction_completed'] is None


def test_le_persistence_error_retains_completed_observations_without_replay(active_le):
    o, s = active_le, active_le.session
    def unavailable(*args, **kwargs):
        raise OSError('authored trace storage failure')
    s._artifact = unavailable
    with pytest.raises(ExecutionTraceError) as caught:
        s.trace_until(dict(kind='register', register='eip', equals=0x50044), max_steps=3)
    result = caught.value.result
    assert result['steps'] == result['attempted_steps'] == len(o.intervals) == 2
    assert result['current_stop']['registers']['instruction_pointer'] == '0x50044'
    assert result['persistence_error']['type'] == 'OSError'


def test_le_step_budget_then_saved_script_preserves_exact_source_predicate(active_le):
    o, s = active_le, active_le.session
    budget = s.trace_until(dict(kind='register', register='eip', equals=0x50044), max_steps=1)
    assert budget['outcome'] == 'step_budget' and not budget['matched'] and not budget['complete']
    assert budget['source_window_closed'] and budget['steps'] == budget['attempted_steps'] == 1
    assert len(stored_trace(o, budget['trace_artifact'])['events']) == 2
    result = s.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='trace-until', until=dict(kind='register', register='eip', equals=0x50046),
             source_view='embedded-le', max_steps=3, **{'as':'matched'}),
        dict(op='assert', value='$matched.exact_stop', equals=True),
    ]), timeout_ms=5000)
    assert result['ok'] and result['completed_steps'] == 2
    match = result['steps'][0]['result']
    assert match['outcome'] == 'predicate' and match['steps'] == 2
    assert match['matched_event']['site']['space'] == 'embedded-le'
    assert match['matched_event']['pc']['project'] is None
    assert len(o.intervals) == 3 and s._process == o.original_mapping
