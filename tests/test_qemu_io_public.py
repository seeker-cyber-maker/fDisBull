"""Public QEMU clock/input/surface routes and whole-script admission.

Native execution is qualified separately. These tests keep real projects and
artifact/event persistence while supplying a small QMP/CPU boundary peer, so
they can detect routing and preflight defects without an installed emulator.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import uuid

from PIL import Image
import pytest

from fdisbull.cli import main, parser, respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace, stamp
from fdisbull.project import Project
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_machine import MachineContext, MachineDebugSession


@pytest.fixture
def raw_project(tmp_path):
    source = tmp_path / 'boot.img'
    source.write_bytes(bytes.fromhex('fa f4 ebfd').ljust(510, b'\0') + b'\x55\xaa')
    with Project.create(tmp_path / 'boot.fdb', source, arch='x86', bits=16,
                        base=0x7c00, entry=0x7c00) as project:
        yield project


@pytest.fixture
def com_project(tmp_path):
    source = tmp_path / 'tiny.com'
    source.write_bytes(bytes.fromhex('b8004c cd21'))
    with Project.create(tmp_path / 'tiny.fdb', source, image='com') as project:
        yield project


class StoppedQMP:
    def __init__(self):
        self.calls = []

    def call(self, command, arguments=None):
        self.calls.append((command, arguments))
        if command == 'query-status':
            return dict(running=False, status='paused')
        if command == 'query-replay':
            return dict(mode='none', icount=11)
        if command == 'screendump':
            Path(arguments['filename']).write_bytes(b'P6\n2 1\n255\n\xff\0\0\0\xff\0')
            return {}
        pytest.fail('Unexpected native dispatch: ' + command)


def stopped_session(project, tmp_path, profile='standard'):
    peer = StoppedQMP()
    vm = SimpleNamespace(qmp=peer, gdb=None, lock=threading.RLock(),
                         machine_stopped=True,
                         qmp_commands={'query-replay', 'screendump', 'input-send-event'},
                         machine_configuration=dict(cpus=1,
                             clock_profile=machine_clock_configuration(profile, 1)),
                         temporary=SimpleNamespace(name=str(tmp_path)))
    def close():
        vm.qmp = None
    vm.close = close
    session = MachineDebugSession.__new__(MachineDebugSession)
    MachineContext.__init__(session, vm)
    session.project, session.rpc = project, vm
    session.run_id = uuid.uuid4().hex
    session.version = project.version()
    session.metadata = {'backend': 'qemu-machine'}
    session.guest_profile = None
    session.closed = False
    session._stopped = lambda: None
    session.registers = lambda: dict(context='machine', registers={'eip': '0x7c00'},
                                    cpu_mode='real', linear_pc='0x7c00')
    vm.context = session
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                           (session.run_id, session.version['id'], stamp(), None,
                            'stopped', json.dumps(session.metadata)))
    return session, peer


@pytest.mark.parametrize('value', ['unknown', '', True, 7, ['instruction']])
def test_invalid_clock_option_is_rejected_before_native_constructor(
        com_project, tmp_path, monkeypatch, value):
    from fdisbull import qemu_dos_process
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession',
                        lambda *a, **kw: pytest.fail('Invalid profile launched a backend'))
    with pytest.raises(ValueError, match='qemu_clock'):
        com_project.debugger('/unused/qemu', tmp_path, backend='qemu-dos',
                             dos_boot_image=tmp_path / 'not-opened.img', qemu_clock=value)


@pytest.mark.parametrize('backend', [None, 'dosbox', 'dosbox-qemu', 'wine-qemu'])
def test_native_clock_option_cannot_be_ignored_by_another_backend(com_project, tmp_path, backend):
    with pytest.raises(ValueError, match='native QEMU'):
        com_project.debugger('/not-started', tmp_path, backend=backend, qemu_clock='standard')


@pytest.mark.parametrize('profile,expected', [(None, 'standard'), ('instruction', 'instruction')])
@pytest.mark.parametrize('route', ['raw-dos', 'com-dos', 'raw-machine', 'machine-python'])
def test_clock_profile_reaches_raw_and_com_factories(
        raw_project, com_project, tmp_path, monkeypatch, profile, expected, route):
    from fdisbull import qemu_dos, qemu_dos_process, qemu_machine
    captured = []
    sentinel = object()
    def create(*args, **options):
        captured.append((args, options))
        return sentinel
    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', create)
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession', create)
    monkeypatch.setattr(qemu_machine, 'MachineDebugSession', create)
    if route == 'machine-python':
        result = raw_project.machine('/qemu', boot_image=tmp_path / 'boot.img',
                                     clock_profile=expected)
    else:
        project = com_project if route == 'com-dos' else raw_project
        options = dict(backend='qemu-machine' if route == 'raw-machine' else 'qemu-dos',
                       qemu_clock=profile)
        if route == 'com-dos':
            options['dos_boot_image'] = tmp_path / 'separate-dos.img'
        result = project.debugger('/qemu', tmp_path, **options)
    assert result is sentinel and len(captured) == 1
    assert captured[0][1]['clock_profile'] == expected
    if route == 'com-dos':
        assert captured[0][1]['boot_image'] == tmp_path / 'separate-dos.img'


def test_cli_clock_choice_reaches_debug_server_launch(monkeypatch, raw_project):
    from fdisbull import cli
    calls = []
    monkeypatch.setattr(cli, 'serve', lambda project, launch: calls.append((project, launch)) or 0)
    assert main(['debug', str(raw_project.path), '--executable', '/qemu', '--game-dir', '.',
                 '--backend', 'qemu-dos', '--qemu-clock', 'instruction']) == 0
    assert calls[0][1]['qemu_clock'] == 'instruction'
    assert calls[0][1]['backend'] == 'qemu-dos'
    with pytest.raises(SystemExit) as error:
        parser().parse_args(['debug', str(raw_project.path), '--executable', '/qemu',
                             '--game-dir', '.', '--qemu-clock', 'invented'])
    assert error.value.code == 2


@pytest.mark.parametrize('profile', ['standard', 'instruction'])
def test_json_bridges_keep_clock_surface_and_input_evidence_distinct(raw_project, tmp_path, profile):
    session, peer = stopped_session(raw_project, tmp_path, profile)
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    def invoke(method, **params):
        response = respond({'id': 1, 'method': method,
                            'params': dict(project=str(raw_project.path), run=session.run_id, **params)},
                           debugger=workspace)
        assert response['ok'], response
        return response['result']
    try:
        clock = invoke('debug-clock-observe')
        assert clock['counter']['value'] == (11 if profile == 'instruction' else None)
        assert clock['counter']['state'] == ('observed' if profile == 'instruction' else 'unsupported')
        assert clock['virtual_ns'] is None and clock['guest_ms'] is None
        assert clock['host_monotonic_ns'] > 0
        key = invoke('debug-keyboard-down', key='a')
        movement = invoke('debug-mouse-move-relative', dx=1, dy=-1)
        button = invoke('debug-mouse-button-down', button='left')
        invoke('debug-mouse-button-up', lease=button['lease'])
        invoke('debug-keyboard-up', lease=key['lease'])
        assert movement['delivery'] == 'python_pending' and movement['guest_consumed'] is None
        assert invoke('debug-input-state')['pending_edges'] == 6
        assert invoke('debug-keyboard-state')['physical_state'] == 'not observed'
        surface = invoke('debug-capture-surface', name='bridge.png')
        metadata = surface['metadata']
        assert metadata['completed_guest_frame'] is None and metadata['guest_frame_id'] is None
        assert metadata['clock_stability'] == (
            'instruction_counter_unchanged' if profile == 'instruction' else 'not_observable')
        row = raw_project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                    (surface['artifact'],)).fetchone()
        with Image.open(io.BytesIO(bytes(row['data']))) as image:
            assert image.format == 'PNG' and image.size == (2, 1)
            assert image.tobytes() == b'\xff\0\0\0\xff\0'
        assert invoke('debug-input-cancel-pending')['cancelled_edges'] == 6
        state = invoke('debug-input-state')
        assert state['pending_edges'] == 0 and state['guest_consumed'] is None
        assert all(command != 'input-send-event' for command, _ in peer.calls)
        observed = raw_project.db.execute(
            "SELECT evidence FROM debug_events WHERE operation='machine-clock-observe'").fetchall()
        assert observed and all(json.loads(row['evidence'])['guest_ms'] is None for row in observed)
    finally:
        workspace.sessions.clear()
        session.close()


@pytest.mark.parametrize('step', [
    {'op': 'mouse.move-relative', 'dx': 0, 'dy': 0},
    {'op': 'mouse.move-relative', 'dx': True, 'dy': 1},
    {'op': 'mouse.move-relative', 'dx': 32768, 'dy': 1},
    {'op': 'mouse.button-down', 'button': 'side'},
    {'op': 'mouse.button-up', 'lease': ''},
    {'op': 'mouse.button-up', 'lease': 3},
])
def test_malformed_later_mouse_step_rejects_whole_script_before_any_operation(
        raw_project, tmp_path, step):
    session, peer = stopped_session(raw_project, tmp_path)
    session.step = lambda **kw: pytest.fail('Earlier CPU step escaped full preflight')
    session._artifact = lambda *a, **kw: pytest.fail('Malformed script persisted an artifact')
    route = {'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
             'steps': [{'op': 'step', 'timeout_ms': 100}, step]}
    try:
        with pytest.raises(ValueError):
            validate_script(route)
        with pytest.raises(ValueError):
            execute_script(session, route)
        assert peer.calls == []
    finally:
        session.close()


@pytest.mark.parametrize('step', [
    {'op': 'clock-observe'}, {'op': 'capture-surface'},
    {'op': 'keyboard.key-down', 'key': 'a'},
    {'op': 'mouse.move-relative', 'dx': 1, 'dy': 0},
    {'op': 'input-cancel-pending'},
])
def test_native_io_script_transaction_preflight_precedes_earlier_step(
        raw_project, tmp_path, step):
    session, peer = stopped_session(raw_project, tmp_path)
    session.step = lambda **kw: pytest.fail('Earlier CPU step escaped transaction preflight')
    session._artifact = lambda *a, **kw: pytest.fail('Transaction-bound script persisted an artifact')
    try:
        with raw_project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                execute_script(session, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
                                        'steps': [{'op': 'step', 'timeout_ms': 100}, step]})
            assert raw_project.db.in_transaction and peer.calls == []
    finally:
        session.close()


def test_timed_keyboard_script_is_refused_before_any_earlier_step(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.step = lambda **kw: pytest.fail('Earlier CPU step ran before timed-input refusal')
    session._artifact = lambda *a, **kw: pytest.fail('Unsupported timed route persisted an artifact')
    try:
        with pytest.raises(ValueError, match='guest clock|Unsupported operations'):
            execute_script(session, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
                                    'steps': [{'op': 'step', 'timeout_ms': 100},
                                              {'op': 'keyboard.press', 'key': 'a'}]})
        assert peer.calls == []
    finally:
        session.close()


def test_script_aliases_resolve_owned_leases_and_preserve_unknown_clock_time(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    route = {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': [
        {'op': 'clock-observe', 'as': 'clock'},
        {'op': 'assert', 'value': '$clock.guest_ms', 'equals': None},
        {'op': 'keyboard.key-down', 'key': 'a', 'as': 'key'},
        {'op': 'keyboard.key-up', 'lease': '$key.lease'},
        {'op': 'mouse.button-down', 'button': 'right', 'as': 'button'},
        {'op': 'mouse.button-up', 'lease': '$button.lease'},
        {'op': 'mouse.move-relative', 'dx': -1, 'dy': 0},
        {'op': 'input-state', 'as': 'pending'},
        {'op': 'assert', 'value': '$pending.pending_edges', 'equals': 5},
        {'op': 'input-cancel-pending'},
        {'op': 'capture-surface', 'name': 'script.png', 'as': 'surface'},
        {'op': 'assert', 'value': '$surface.metadata.completed_guest_frame', 'equals': None},
    ]}
    try:
        result = session.script(route)
        assert result['ok'] and result['completed_steps'] == len(route['steps']), result
        assert session.input_state()['pending_edges'] == 0
        assert all(command != 'input-send-event' for command, _ in peer.calls)
        stored = raw_project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (result['artifact'],)).fetchone()
        report = json.loads(bytes(stored['data']))
        assert report['steps'][0]['result']['counter']['state'] == 'unsupported'
        assert report['steps'][0]['result']['virtual_ns'] is None
    finally:
        session.close()


def test_script_cannot_hide_preexisting_pending_input_run_in_caller_transaction(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.keyboard_key_down('a')
    peer.calls.clear()
    session.step = lambda **kw: pytest.fail('Earlier step ran before pending-input transaction refusal')
    session._artifact = lambda *a, **kw: pytest.fail('Pending-input route persisted in caller transaction')
    try:
        with raw_project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                execute_script(session, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
                                        'steps': [{'op': 'step', 'timeout_ms': 100},
                                                  {'op': 'run', 'timeout_ms': 100}]})
            assert peer.calls == [] and raw_project.db.in_transaction
        assert session.input_state()['pending_edges'] == 1
    finally:
        session.close()
