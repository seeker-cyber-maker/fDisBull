"""Public routing and whole-script admission for native periodic rules."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS
from test_qemu_io_public import raw_project, stopped_session


def _script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def _native(project, tmp_path):
    session, peer = stopped_session(project, tmp_path, profile='virtual')
    session.vm.qmp_commands.update(VIRTUAL_CLOCK_COMMANDS)
    return session, peer


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_native_rule_script_grammar_preserves_existing_parameters(backend):
    step = dict(op='memory-rule-run', rule='$saved.artifact', ticks=3,
                interval_ms=10, timeout_ms=200)
    assert validate_script(_script(step, backend=backend)) == [step]


def test_native_rule_json_route_forwards_without_implicit_execution(raw_project, tmp_path):
    session, peer = _native(raw_project, tmp_path)
    calls = []
    def run(rule, *, ticks, interval_ms=100, timeout_ms=10000):
        calls.append(dict(rule=rule, ticks=ticks, interval_ms=interval_ms, timeout_ms=timeout_ms))
        return dict(complete=True, clock_domain='qemu-virtual-ns')
    session.memory_rule_run = run
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        result = respond(dict(method='debug-memory-rule-run', params=dict(
            project=str(raw_project.path), run=session.run_id, context='machine',
            rule='rule-1', ticks=3, interval_ms=10, timeout_ms=200)), debugger=workspace)
        assert result['ok'], result
        assert result['result'] == dict(complete=True, clock_domain='qemu-virtual-ns')
        assert calls == [dict(rule='rule-1', ticks=3, interval_ms=10, timeout_ms=200)]
        assert peer.calls == []
    finally:
        workspace.sessions.clear()
        session.close()


def test_native_rule_script_forwards_one_remaining_budget(raw_project, tmp_path):
    session, peer = _native(raw_project, tmp_path)
    calls = []
    def run(rule, *, ticks, interval_ms=100, timeout_ms=10000):
        calls.append((rule, ticks, interval_ms, timeout_ms, session._rpc_deadline))
        return dict(complete=True, completed_ticks=ticks)
    session.memory_rule_run = run
    execute_script(session, _script(dict(op='memory-rule-run', rule='rule-1',
        ticks=3, interval_ms=10, timeout_ms=500)), timeout_ms=200)
    assert len(calls) == 1 and calls[0][:3] == ('rule-1', 3, 10)
    assert 1 <= calls[0][3] <= 200 and calls[0][4] is not None
    assert peer.calls == []


@pytest.mark.parametrize('guard', ['standard', 'transaction'])
def test_native_rule_script_rejects_before_an_earlier_write(raw_project, tmp_path, guard):
    session, peer = (stopped_session(raw_project, tmp_path) if guard == 'standard'
                     else _native(raw_project, tmp_path))
    if guard == 'transaction':
        raw_project.db.execute('BEGIN')
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    try:
        with pytest.raises(ValueError, match='virtual|hooks|task|transaction'):
            execute_script(session, _script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                dict(op='memory-rule-run', rule='rule-1', ticks=2)))
        assert writes == [] and peer.calls == [] and not session.closed
    finally:
        if raw_project.db.in_transaction:
            raw_project.db.rollback()


@pytest.mark.parametrize('options', [dict(ticks=0), dict(ticks=True), dict(interval_ms=0),
    dict(interval_ms=60001), dict(timeout_ms=False), dict(timeout_ms=60001),
    dict(rule='$saved.artifact', ticks='$saved.count', interval_ms=-1)])
def test_native_rule_malformed_literals_refuse_whole_script(raw_project, tmp_path, options):
    session, peer = _native(raw_project, tmp_path)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    step = dict(op='memory-rule-run', rule='rule-1', ticks=2)
    step.update(options)
    with pytest.raises(ValueError):
        execute_script(session, _script(dict(op='write-memory', address=0x7c00, data_hex='90'), step))
    assert writes == [] and peer.calls == []


@pytest.mark.parametrize('owner', ['native hooks', 'task-private', 'layers'])
def test_native_script_admission_defers_context_specific_checks(raw_project, tmp_path, owner):
    session, peer = _native(raw_project, tmp_path)
    if owner == 'native hooks': session._qemu_hooks = {'h': {'active': True}}
    elif owner == 'task-private': session._dos_task_views = {'task': {}}
    else: session._layer_active = ['layer']
    step = dict(op='memory-rule-run', rule='rule-1', ticks=2)
    assert validate_script(_script(step), session=session) == [step]
    assert peer.calls == []
