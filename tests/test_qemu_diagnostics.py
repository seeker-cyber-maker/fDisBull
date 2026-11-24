"""Host-only byte-cursor contracts for owned QEMU stderr logs."""
from types import SimpleNamespace
import threading

import pytest

from fdisbull.qemu_chip8 import Chip8DebugSession
from fdisbull.qemu_machine import MachineContext


@pytest.fixture(params=['dos', 'chip8'])
def debug(request, tmp_path):
    path = tmp_path / 'qemu.log'
    path.write_bytes(b'A\xff\xe2\x82\xacZ')
    serial = tmp_path / 'boot.log'
    serial.write_bytes(b'guest serial is not QEMU stderr')
    vm = SimpleNamespace(lock=threading.RLock(), process=SimpleNamespace(poll=lambda: None),
                         qemu_log_path=path, log_path=serial,
                         _diagnostic_id='a' * 32)
    vm.test_log_path = path
    cls = MachineContext if request.param == 'dos' else Chip8DebugSession
    session = cls.__new__(cls)
    session.vm = vm
    session.closed = False
    session.capabilities = {}
    return session


def test_cursor_reads_raw_bytes_and_tracks_growth(debug):
    first = debug.diagnostics(limit=3)
    assert first == {'cursor': 0, 'next_cursor': 3, 'size': 6,
                     'hex': '41ffe2', 'native_exit_code': None, 'identity': 'a' * 32}
    with debug.vm.test_log_path.open('ab') as stream:
        stream.write(b'!')
    debug.vm.process.poll = lambda: -9
    second = debug.diagnostics(cursor=first['next_cursor'], limit=16, identity=first['identity'])
    assert second == {'cursor': 3, 'next_cursor': 7, 'size': 7,
                      'hex': '82ac5a21', 'native_exit_code': -9, 'identity': 'a' * 32}
    assert debug.diagnostics(cursor=7, identity=first['identity'])['hex'] == ''


@pytest.mark.parametrize('kwargs', [
    {'cursor': -1}, {'cursor': True}, {'cursor': 7}, {'cursor': 0.0},
    {'limit': 0}, {'limit': 16385}, {'limit': True}, {'limit': 1.0},
])
def test_invalid_cursor_or_limit_rejected(debug, kwargs):
    with pytest.raises(ValueError):
        debug.diagnostics(**kwargs)


def test_missing_log_does_not_report_empty_success(debug):
    debug.vm.test_log_path.unlink()
    with pytest.raises((OSError, ValueError)):
        debug.diagnostics()


def test_cursor_is_bound_to_owner_identity(debug):
    first = debug.diagnostics(limit=1)
    with pytest.raises(ValueError):
        debug.diagnostics(cursor=1)
    with pytest.raises(ValueError):
        debug.diagnostics(identity='b' * 32)
    debug.vm._diagnostic_id = 'b' * 32  # replacement owner
    with pytest.raises(ValueError):
        debug.diagnostics(cursor=first['next_cursor'], identity=first['identity'])
    assert debug.diagnostics()['identity'] == 'b' * 32


def test_json_route_returns_owned_bytes(debug, tmp_path):
    from fdisbull.cli import METHODS, respond
    from fdisbull.debugger import DebugWorkspace

    debug.project = SimpleNamespace(path=tmp_path.resolve())
    debug.run_id = 'owned-run'
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    assert 'debug-diagnostics' in METHODS
    response = respond({'id': 1, 'method': 'debug-diagnostics', 'params': {
        'project': str(tmp_path), 'run': debug.run_id, 'limit': 2}}, debugger=workspace)
    assert response['ok'], response
    assert response['result']['hex'] == '41ff'
    assert response['result']['next_cursor'] == 2
    assert response['result']['identity'] == 'a' * 32


def test_cpu_inventory_public_route_preserves_target_specific_fields(debug, tmp_path):
    from fdisbull.cli import METHODS, respond
    from fdisbull.debugger import DebugWorkspace

    chip8 = isinstance(debug, Chip8DebugSession)
    arch = 'chip8' if chip8 else 'x86_64'
    debug.vm.inspection_target = arch
    if chip8:
        debug.vm.inspection_qom_cpu_type = 'chip8-cpu'
    enum_values = ['x86_64']  # Older CHIP-8 producer cannot encode chip8.
    schema = [
        {'name': 'SysEmuTarget', 'meta-type': 'enum', 'values': enum_values},
        {'name': 'TargetInfo', 'meta-type': 'object', 'members': [{'name': 'arch', 'type': 'SysEmuTarget'}]},
        {'name': 'CpuInfo', 'meta-type': 'object', 'members': [{'name': 'target', 'type': 'SysEmuTarget'}]},
        {'name': 'CpuList', 'meta-type': 'array', 'element-type': 'CpuInfo'},
        {'name': 'QomList', 'meta-type': 'array', 'element-type': 'str'},
        {'name': 'StatusInfo', 'meta-type': 'object', 'members': []},
    ] + [{'name': name, 'meta-type': 'command', 'ret-type': result} for name, result in (
        ('query-target', 'TargetInfo'), ('query-cpus-fast', 'CpuList'),
        ('qom-list', 'QomList'), ('query-status', 'StatusInfo'))]
    # QMP introspection emits numeric type IDs, not C/QAPI type names.
    type_ids = {'SysEmuTarget': '10', 'TargetInfo': '11', 'CpuInfo': '12',
                'CpuList': '13', 'QomList': '14', 'StatusInfo': '15'}
    def numeric_types(value):
        if isinstance(value, dict):
            return {key: numeric_types(item) for key, item in value.items()}
        if isinstance(value, list):
            return [numeric_types(item) for item in value]
        return type_ids.get(value, value) if isinstance(value, str) else value
    schema = numeric_types(schema)
    calls = []
    values = {'query-qmp-schema': schema, 'query-target': {'arch': arch},
              'query-cpus-fast': [{'cpu-index': 0, 'qom-path': '/machine/unattached/device[0]'}],
              'qom-list': [{'name': 'device[0]', 'type': 'child<chip8-cpu>'}],
              'query-status': {'running': False, 'status': 'paused'}}
    def call(command, arguments=None, *, timeout_ms, max_reply_bytes):
        calls.append((command, timeout_ms))
        if chip8 and command in ('query-target', 'query-cpus-fast'):
            pytest.fail('unsafe query dispatched to older CHIP-8')
        if command == 'qom-list':
            assert arguments == {'path': '/machine/unattached'}
        return values[command]
    debug.vm.qmp = SimpleNamespace(call=call)
    debug.project = SimpleNamespace(path=tmp_path.resolve())
    debug.run_id = 'owned-run'
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    assert 'debug-cpu-inventory' in METHODS
    response = respond({'id': 2, 'method': 'debug-cpu-inventory', 'params': {
        'project': str(tmp_path), 'run': debug.run_id, 'timeout_ms': 5000}}, debugger=workspace)
    assert response['ok'], response
    result = response['result']
    assert result['format'] == 'fdisbull-native-cpu-inventory-2'
    assert result['expected_target'] == arch
    assert result['expected_target_source'] == 'caller-declared'
    assert result['status'] == values['query-status'] and result['status_source'] == 'qmp'
    if chip8:
        assert result['target'] is None and result['target_source'] is None
        assert result['cpus'] is None and result['cpu_source'] == 'qom-list'
        assert result['expected_cpu_type'] == 'chip8-cpu'
        assert result['qom_cpu_children'] == [{'qom_path': '/machine/unattached/device[0]',
                                               'property': values['qom-list'][0]}]
        expected_calls = ['query-qmp-schema', 'qom-list', 'query-status']
    else:
        assert result['target'] == values['query-target'] and result['target_source'] == 'qmp'
        assert result['cpus'] == values['query-cpus-fast'] and result['cpu_source'] == 'query-cpus-fast'
        expected_calls = ['query-qmp-schema', 'query-target', 'query-cpus-fast', 'query-status']
    assert result['cpu_paths'] == ['/machine/unattached/device[0]']
    assert [command for command, _ in calls] == expected_calls
    assert all(0 < timeout <= 5000 for _, timeout in calls)


@pytest.mark.parametrize('method', ['diagnostics', 'cpu_inventory'])
def test_inspection_lock_timeout_is_bounded(debug, method):
    class BusyLock:
        def acquire(self, *, timeout):
            assert 0 < timeout <= 0.01
            return False
        def release(self):
            pytest.fail('unacquired lock released')
    debug.vm.lock = BusyLock()
    with pytest.raises(TimeoutError, match='lock deadline'):
        getattr(debug, method)(timeout_ms=10)


@pytest.mark.parametrize('method', ['diagnostics', 'cpu_inventory'])
@pytest.mark.parametrize('closed_object', ['session', 'owner'])
def test_closed_inspection_owner_rejected(debug, method, closed_object):
    setattr(debug if closed_object == 'session' else debug.vm, 'closed', True)
    with pytest.raises(ValueError, match='closed'):
        getattr(debug, method)()


@pytest.mark.parametrize('method', ['diagnostics', 'cpu_inventory'])
def test_replaced_owner_while_waiting_for_lock_is_rejected(debug, method):
    class ReplacedLock:
        def acquire(self, *, timeout):
            debug.vm = SimpleNamespace()
            return True
        def release(self):
            pass
    debug.vm.lock = ReplacedLock()
    with pytest.raises(ValueError, match='owner changed'):
        getattr(debug, method)()


@pytest.mark.parametrize('method', ['diagnostics', 'cpu_inventory'])
def test_replaced_owner_during_operation_is_rejected(debug, method, monkeypatch):
    import fdisbull.qemu_diagnostics as diagnostics
    import fdisbull.native_cpu as native_cpu
    def replace(*args, **kwargs):
        debug.vm = SimpleNamespace()
        return {}
    if method == 'diagnostics':
        monkeypatch.setattr(diagnostics, 'read_diagnostics', replace)
    else:
        debug.vm.qmp = object()
        debug.vm.inspection_target = 'chip8'
        monkeypatch.setattr(native_cpu, 'inspect_native_cpu', replace)
    with pytest.raises(ValueError, match='owner changed'):
        getattr(debug, method)()


@pytest.mark.parametrize('available', [True, False])
def test_inventory_capability_is_observed_and_resets_for_replaced_owner(debug, monkeypatch, available):
    import fdisbull.native_cpu as native_cpu
    debug.capabilities['native_cpu_inventory'] = None
    debug.vm.qmp = object()
    debug.vm.inspection_target = 'chip8'
    monkeypatch.setattr(native_cpu, 'inspect_native_cpu', lambda *args, **kwargs: {
        'cpu_source': 'qom-list' if available else 'unavailable',
        'cpu_paths': ['/machine/unattached/device[0]'] if available else [],
        'status': {'running': False}})
    debug.cpu_inventory()
    assert debug.capabilities['native_cpu_inventory'] is available
    debug.vm = SimpleNamespace()
    debug._refresh_inspection_capability()
    assert debug.capabilities['native_cpu_inventory'] is None
