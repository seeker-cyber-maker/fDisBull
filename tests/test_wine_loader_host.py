"""Host/broker early-loader contracts without a VM or simulated loader claim."""
from copy import deepcopy
import io
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest

from fixtures_formats import pe64
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.wine_arch import register_names
from fdisbull.wine_debugger import PEDebugSession
from test_wine_guest_bridge import broker_functions


@pytest.mark.parametrize('early', [False, True])
def test_broker_start_selects_early_agent_argument_only_when_explicit(tmp_path, early):
    scope = broker_functions()
    calls = []
    scope.update(process=None, Path=lambda *parts: tmp_path.joinpath(*parts[1:]),
                 open=lambda *args, **kwargs: open(tmp_path / 'wine.log', *args[1:], **kwargs),
                 stage_files=lambda params: (tmp_path, 'oracle.exe'))
    scope['subprocess'] = SimpleNamespace(DEVNULL=-3, PIPE=-1,
        run=lambda *args, **kwargs: None,
        Popen=lambda command, **kwargs: calls.append(command) or SimpleNamespace())
    scope['response'] = lambda timeout: {'started': True}
    params = {'entry_rva': 0x1000, 'bits': 64}
    if early:
        params['stop_before_loader'] = True
    assert scope['invoke']('session.start', params) == {'started': True}
    expected = ['wine', '/opt/fdisbull/agent.exe', 'Z:\\work\\game\\oracle.exe', '0x1000']
    assert calls == [expected + (['--stop-before-loader'] if early else [])]


@pytest.mark.parametrize('params', [
    {'stop_before_loader': 1}, {'stop_before_loader': 'true'},
    {'stop_before_loader': True, 'bits': 32}, {'stop_before_loader': True, 'profile': 'ne'},
])
def test_invalid_early_launch_options_refuse_before_staging_or_launch(params):
    scope = broker_functions()
    touched = []
    scope.update(process=None, stage_files=lambda params: touched.append('staged'))
    with pytest.raises(ValueError):
        scope['invoke']('session.start', params)
    assert touched == [] and scope['process'] is None


@pytest.mark.parametrize('method,params,expected', [
    ('loader-control', {'stop_on_load': True}, b'loader-control 1\n'),
    ('loader-control', {'stop_on_load': False}, b'loader-control 0\n'),
    ('loader-events', {}, b'loader-events 0 256\n'),
    ('loader-events', {'after': 2**64 - 1, 'limit': 1}, b'loader-events 18446744073709551615 1\n'),
    ('thread-info', {}, b'thread-info\n'),
])
def test_broker_loader_and_thread_commands_preserve_the_native_response(method, params, expected):
    scope = broker_functions()
    stream = io.BytesIO()
    reply = {'native': 'unchanged', 'lost_before': True}
    scope.update(process=SimpleNamespace(stdin=stream), response=lambda *args, **kwargs: reply)
    assert scope['invoke'](method, params) is reply
    assert stream.getvalue() == expected


@pytest.mark.parametrize('method,params', [
    ('loader-control', {'stop_on_load': 1}), ('loader-control', {'stop_on_load': True, 'resume': True}),
    ('loader-events', {'after': -1}), ('loader-events', {'after': True}),
    ('loader-events', {'after': 2**64}), ('loader-events', {'limit': 257}),
    ('loader-events', {'limit': 0}), ('loader-events', {'resume': True}),
])
def test_invalid_loader_commands_never_reach_the_native_channel(method, params):
    scope = broker_functions()
    stream = io.BytesIO()
    scope['process'] = SimpleNamespace(stdin=stream)
    with pytest.raises(ValueError):
        scope['invoke'](method, params)
    assert stream.getvalue() == b''


def _rpc(monkeypatch, *, native_early=True, corrupt=None, foreign=True):
    calls, instances = [], []
    pc = '0x6ffff0001000' if foreign else '0x140001000'
    context = {'rip': pc, 'rflags': '0x202', 'thread': 17,
               'general': {n: '0x0' for n in register_names(64) - {'rip', 'rflags'}}}
    state = {'state': 'stopped', 'stop_reason': {'kind': 'process-create' if native_early else 'entry',
              'address': pc, 'thread': 17}}
    if native_early:
        state['loader'] = {'profile': 'pe-before-loader', 'phase': 'before-entry',
                           'entry_reached': False, 'stop_on_load': True, 'event_sequence': 1}
    launched = {'image_base': '0x140000000', 'pid': 99, 'bits': 64, 'architecture': 'x86-64',
                'launch_profile': 'pe-before-loader' if native_early else 'pe-original', 'session': state}
    if corrupt:
        corrupt(launched)
    class RPC:
        def __init__(self, *args, **kwargs):
            self.lock = RLock()
            self.capabilities = {}
            self.inputs = {}
            self.hello = {key: 'authored-protocol-fixture' for key in
                          ('wine_version', 'guest_kernel', 'agent_binary_sha256', 'resources')}
            self.process = SimpleNamespace(pid=123, poll=lambda: 0)
            self.closed = False
            instances.append(self)
        def call(self, method, params=None, **kwargs):
            calls.append((method, params))
            if method == 'session.start':
                return deepcopy(launched)
            if method == 'registers':
                return deepcopy(context)
            if method == 'close':
                return {'state': 'closed'}
            raise AssertionError(method)
        def close(self):
            self.closed = True
    monkeypatch.setattr(PEDebugSession, 'rpc_type', RPC)
    return calls, instances, context


def test_process_create_launch_retains_actual_foreign_pc_and_native_stop(tmp_path, monkeypatch):
    source = tmp_path / 'loader.exe'
    source.write_bytes(pe64())
    calls, _, context = _rpc(monkeypatch)
    with Project.create(tmp_path / 'loader.fdb', source) as project:
        with project.debugger('qemu', tmp_path, kernel='kernel', initramfs='runtime', loader_mode='process-create') as debug:
            assert calls[0][1]['stop_before_loader'] is True
            assert debug.registers()['project_address'] is None
            assert debug.registers()['rip'] == context['rip']
            assert debug.metadata['runtime_profile'] == 'pe64-win32-debug-before-loader-1'
            assert debug.metadata['entry_observed_at_launch'] is False
            assert debug.metadata['initial_stop']['kind'] == 'process-create'
            assert debug.metadata['initial_registers']['project_address'] is None
            stored = json.loads(project.db.execute('SELECT metadata FROM debug_runs WHERE id=?', (debug.run_id,)).fetchone()[0])
            assert stored['loader_mode'] == 'process-create'
            assert stored['initial_stop'] == debug.metadata['initial_stop']


def test_default_entry_launch_keeps_original_payload_and_entry_requirement(tmp_path, monkeypatch):
    source = tmp_path / 'entry.exe'
    source.write_bytes(pe64())
    calls, _, _ = _rpc(monkeypatch, native_early=False, foreign=False)
    with Project.create(tmp_path / 'entry.fdb', source) as project:
        with project.debugger('qemu', tmp_path, kernel='kernel', initramfs='runtime') as debug:
            assert 'stop_before_loader' not in calls[0][1]
            assert debug.metadata['runtime_profile'] == 'pe64-win32-debug-2'
            assert debug.registers()['project_address'] == hex(project.meta['entry'])


@pytest.mark.parametrize('corrupt', [
    lambda r: r.update(launch_profile='pe-original'),
    lambda r: r['session']['loader'].update(entry_reached=True),
    lambda r: r['session']['stop_reason'].update(kind='entry'),
    lambda r: r['session']['stop_reason'].update(address='0x1234'),
    lambda r: r['session']['stop_reason'].update(thread=18),
])
def test_early_launch_requires_matching_native_stop_before_claiming_success(tmp_path, monkeypatch, corrupt):
    source = tmp_path / 'loader.exe'
    source.write_bytes(pe64())
    _, instances, _ = _rpc(monkeypatch, corrupt=corrupt)
    with Project.create(tmp_path / 'loader.fdb', source) as project:
        with pytest.raises(DebuggerError, match='process-create stop'):
            project.debugger('qemu', tmp_path, kernel='kernel', initramfs='runtime', loader_mode='process-create')
        assert instances[0].closed and project._live_debuggers == []
        assert project.db.execute('SELECT count(*) FROM debug_runs').fetchone()[0] == 0


def test_early_mode_refuses_saved_state_and_incompatible_backend_before_vm(tmp_path, monkeypatch):
    source = tmp_path / 'loader.exe'
    source.write_bytes(pe64())
    calls, instances, _ = _rpc(monkeypatch)
    with Project.create(tmp_path / 'loader.fdb', source) as project:
        with pytest.raises(ValueError, match='not qualified'):
            project.debugger('qemu', tmp_path, kernel='kernel', initramfs='runtime', loader_mode='process-create', state='old')
        with pytest.raises(ValueError, match='native PE64'):
            project.debugger('qemu', tmp_path, backend='ida-wine-qemu', loader_mode='process-create')
        with pytest.raises(ValueError, match='loader_mode'):
            project.debugger('qemu', tmp_path, loader_mode='pretend-entry')
    assert calls == [] and instances == []
    debug = PEDebugSession.__new__(PEDebugSession)
    debug.loader_mode = 'process-create'
    with pytest.raises(ValueError, match='not qualified'):
        debug._save_native_state()
    with pytest.raises(ValueError, match='not qualified'):
        debug._load_native_state('old')


def test_host_loader_wrappers_bound_requests_and_preserve_native_provenance():
    debug = PEDebugSession.__new__(PEDebugSession)
    debug.loader_mode = 'process-create'
    debug.rpc = SimpleNamespace(lock=RLock())
    calls, events = [], []
    response = {'teb_source': 'CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase', 'gs_base_register_observed': False}
    debug.call = lambda method, params=None: calls.append((method, params)) or response
    debug._event = lambda name, result: events.append((name, result))
    assert debug.thread_info() is response
    assert debug.loader_events(after=7, limit=2) is response
    assert debug.loader_control(stop_on_load=False) is response
    assert calls == [('thread-info', None), ('loader-events', {'after': 7, 'limit': 2}),
                     ('loader-control', {'stop_on_load': False})]
    assert events == [('loader-control', response)]
    before = len(calls)
    with pytest.raises(ValueError):
        debug.loader_events(after=True)
    with pytest.raises(ValueError):
        debug.loader_events(limit=257)
    with pytest.raises(ValueError):
        debug.loader_control(stop_on_load=1)
    debug.loader_mode = 'entry'
    with pytest.raises(ValueError, match='process-create'):
        debug.loader_control(stop_on_load=True)
    assert len(calls) == before
