"""Public admission and guard composition for native checkpoint histories."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


def script(*steps, backend='qemu-dos'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def test_native_history_grammar_has_distinct_stopped_capture_and_step_routes():
    steps = [dict(op='rewind-start', max_steps=8, max_bytes=512 * 1024**2)]
    steps.extend([dict(op='rewind-record', advance='capture'),
                  dict(op='rewind', history='$root.history', node='$root.cursor', timeout_ms=1000)])
    assert validate_script(script(*steps)) == steps


@pytest.mark.parametrize('step', [dict(op='rewind-record', advance='replay'),
    dict(op='rewind-record', advance=True), dict(op='rewind-record', advance='capture', count=2),
    dict(op='rewind-start', max_bytes=1024**3 + 1),
    dict(op='rewind-start', max_steps=True), dict(op='rewind', count=0)])
def test_malformed_history_literals_reject_the_whole_script(step):
    with pytest.raises(ValueError):
        validate_script(script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'), step))


def test_raw_machine_does_not_advertise_process_history():
    with pytest.raises(ValueError, match='Unsupported operation'):
        validate_script(script(dict(op='rewind-start'), backend='qemu-machine'))


class RoutedHistorySession(MachineDebugSession):
    @property
    def script_operations(self):
        return super().script_operations | {'rewind-start', 'rewind-status', 'rewind-record', 'rewind'}

    def rewind_start(self, max_steps=16, max_bytes=512 * 1024**2, *, history=None, timeout_ms=60000):
        self.history_calls.append(('start', max_steps, max_bytes, history, timeout_ms))
        return dict(history='retained-history', cursor='root-node')

    def rewind_record(self, count=1, timeout_ms=60000, *, advance='step'):
        self.history_calls.append(('record', count, advance, timeout_ms))
        return dict(history='new-revision', cursor='child-node')

    def rewind(self, count=1, *, history=None, node=None, timeout_ms=60000):
        self.history_calls.append(('restore', count, history, node, timeout_ms))
        return dict(history=history, cursor=node)


def routed(project, tmp_path):
    session, peer = stopped_session(project, tmp_path)
    session.__class__ = RoutedHistorySession
    session.metadata['backend'] = 'qemu-dos'
    session.capabilities['rewind'] = True
    session.history_calls = []
    return session, peer


def test_json_restore_forwards_the_persistent_history_and_node(raw_project, tmp_path):
    session, peer = routed(raw_project, tmp_path)
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        result = respond(dict(method='debug-rewind', params=dict(project=str(raw_project.path),
            run=session.run_id, context='machine', history='retained-history', node='root-node',
            timeout_ms=400)), debugger=workspace)
        assert result['ok'], result
        assert result['result']['cursor'] == 'root-node'
        assert session.history_calls == [('restore', 1, 'retained-history', 'root-node', 400)]
        assert peer.calls == []
    finally:
        workspace.sessions.clear()
        session.close()


def test_saved_script_can_bind_and_restore_a_recorded_checkpoint(raw_project, tmp_path):
    session, peer = routed(raw_project, tmp_path)
    result = execute_script(session, script(
        dict(op='rewind-start', max_steps=4, max_bytes=512 * 1024**2, **{'as': 'root'}),
        dict(op='rewind-record', advance='capture'),
        dict(op='rewind', history='$root.history', node='$root.cursor')), timeout_ms=1000)
    assert result['ok'] and result['completed_steps'] == 3
    assert [call[0] for call in session.history_calls] == ['start', 'record', 'restore']
    assert session.history_calls[-1][2:4] == ('retained-history', 'root-node')
    assert peer.calls == []


def test_disabled_checkpoint_capability_refuses_before_an_earlier_script_write(raw_project, tmp_path):
    session, peer = routed(raw_project, tmp_path)
    session.capabilities['rewind'] = False
    with pytest.raises(ValueError, match='enabled full process checkpoints'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00,
            data_hex='90', expected_hex='00'), dict(op='rewind-start')))
    assert session.history_calls == [] and peer.calls == []


def test_detailed_history_guard_preserves_existing_native_guard(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    calls = []
    session.vm.operation_guard = lambda name: calls.append(('legacy', name))
    session.vm.history_operation_guard = lambda name, args, kwargs: calls.append(('history', name, args, kwargs))
    session.status()
    assert calls == [('legacy', 'status'), ('history', 'status', (), {})]
    assert peer.calls == [('query-status', None)]
    session.close()
