"""JSON dispatch for the native DOS cooperating-task APIs, without a guest."""
from types import SimpleNamespace

from fdisbull.cli import METHODS, respond
from fdisbull.debugger import DebugWorkspace


def test_task_methods_are_discoverable_and_dispatch_arguments(tmp_path):
    project = (tmp_path / 'task.fdb').resolve()
    workspace = DebugWorkspace()
    calls = []
    def bind(*, anchor_address, expected_monitor):
        calls.append((anchor_address, expected_monitor))
        return {'binding': 'current'}
    def observe():
        calls.append('observe')
        return {'matches_binding': True}
    workspace.sessions['run-1'] = SimpleNamespace(
        project=SimpleNamespace(path=project), metadata={'backend': 'qemu-dos'},
        dos_task_bind=bind, dos_task_observe=observe,
    )
    monitor = '00112233445566778899aabbccddeeff'
    bind_reply = respond({'id': 1, 'method': 'debug-dos-task-bind', 'params': {
        'run': 'run-1', 'anchor_address': '0x150000', 'expected_monitor': monitor,
    }}, default_project=str(project), debugger=workspace)
    assert bind_reply == {'id': 1, 'ok': True, 'result': {'binding': 'current'}}
    observe_reply = respond({'id': 2, 'method': 'debug-dos-task-observe', 'params': {
        'run': 'run-1',
    }}, default_project=str(project), debugger=workspace)
    assert observe_reply == {'id': 2, 'ok': True, 'result': {'matches_binding': True}}
    assert calls == [('0x150000', monitor), 'observe']
    assert all(name in METHODS for name in ('debug-dos-task-bind', 'debug-dos-task-observe'))
