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


def test_task_private_routes_forward_json_arguments(tmp_path):
    project = (tmp_path / 'task.fdb').resolve()
    workspace = DebugWorkspace()
    calls = []

    def capture(operation):
        def call(**kwargs):
            calls.append((operation, kwargs))
            return {'operation': operation}
        return call

    names = {
        'debug-dos-task-switching': ('dos_task_switching', {}),
        'debug-dos-task-register': ('dos_task_register',
                                    {'cookie': 161, 'incarnation': 1, 'pages': [0x110000]}),
        'debug-dos-task-layer-patch': ('dos_task_layer_patch',
            {'name': 'private', 'address': '0x110100', 'expected_hex': '00', 'data_hex': '01',
             'kind': 'ram', 'task': 'task-a', 'activate': False}),
        'debug-dos-task-layers': ('dos_task_layers',
                                   {'active': ['layer-a'], 'task': 'task-a', 'conflict': 'stop'}),
        'debug-dos-task-memory': ('dos_task_memory',
                                   {'address': '0x110100', 'length': 1, 'task': 'task-a', 'view': 'base'}),
        'debug-dos-task-retire': ('dos_task_retire', {'task': 'task-a'}),
    }
    session = SimpleNamespace(project=SimpleNamespace(path=project), metadata={'backend': 'qemu-dos'})
    for operation, _ in names.values():
        setattr(session, operation, capture(operation))
    workspace.sessions['run-1'] = session
    for route, (operation, arguments) in names.items():
        reply = respond({'method': route, 'params': {'run': 'run-1', **arguments}},
                        default_project=str(project), debugger=workspace)
        assert reply == {'id': None, 'ok': True, 'result': {'operation': operation}}
        assert route in METHODS
    assert calls == list(names.values())
