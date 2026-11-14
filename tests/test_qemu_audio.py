"""Public routing and hostile native audio receipts at the real QMP envelope.

This peer supplies transport/protocol evidence only. Actual audio production
and PIT tone expectations live in test_qemu_audio_native.py.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fdisbull.cli import main, parser
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_audio import AUDIO_COMMANDS, machine_audio_configuration
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from test_qemu_clock_budget import NativeWire
from test_qemu_io_deadlines import observation
from test_qemu_io_public import raw_project, com_project


class AudioWire(NativeWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.audio = {'api-version': 1, 'epoch': 1, 'state': 'idle', 'virtual-ns': 1000,
                      'max-frames': 0, 'frames': 0, 'dropped-frames': 0, 'rate': 32000,
                      'channels': 1, 'format': 'u8', 'enabled': False, 'chunks': []}
        self.mutate = lambda value: value
        self.pcm = b''

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in AUDIO_COMMANDS:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-start-audio':
            self.audio.update(state='capturing', token=args['token'], **{
                'start-ns': self.receipt['virtual-ns'], 'max-frames': args['max-frames']})
        elif command == 'x-fdisbull-stop-audio':
            self.audio.update(state='stopped', **{'stop-ns': self.receipt['virtual-ns']})
        elif command == 'x-fdisbull-export-audio':
            Path(args['filename']).write_bytes(self.pcm)
        self.audio['virtual-ns'] = self.receipt['virtual-ns']
        value = self.mutate(deepcopy(self.audio))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency


@pytest.fixture
def audio(observation):
    o = observation
    wire = AudioWire(o.clock)
    o.qmp.socket = wire
    o.wire = wire
    o.vm.machine_configuration.update(
        clock_profile=machine_clock_configuration('virtual', 1),
        audio_profile=machine_audio_configuration('pc-speaker', 'virtual'))
    o.vm.qmp_commands = AUDIO_COMMANDS | VIRTUAL_CLOCK_COMMANDS
    o.session.capabilities.update(audio_capture=True, virtual_clock_budget=True)
    return o


@pytest.mark.parametrize('route', ['raw-dos', 'com-dos', 'raw-machine', 'machine-python'])
def test_audio_profile_reaches_every_native_factory(raw_project, com_project, tmp_path, monkeypatch, route):
    from fdisbull import qemu_dos, qemu_dos_process, qemu_machine
    seen = []
    def create(*args, **kwargs):
        seen.append(kwargs)
        return 'selected'
    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', create)
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession', create)
    monkeypatch.setattr(qemu_machine, 'MachineDebugSession', create)
    if route == 'machine-python':
        result = raw_project.machine('/qemu', boot_image=tmp_path / 'boot.img',
                                     clock_profile='virtual', audio_profile='pc-speaker')
    else:
        project = com_project if route == 'com-dos' else raw_project
        options = dict(backend='qemu-machine' if route == 'raw-machine' else 'qemu-dos',
                       qemu_clock='virtual', qemu_audio='pc-speaker')
        if route == 'com-dos':
            options['dos_boot_image'] = tmp_path / 'dos.img'
        result = project.debugger('/qemu', tmp_path, **options)
    assert result == 'selected' and len(seen) == 1
    assert seen[0]['audio_profile'] == 'pc-speaker' and seen[0]['clock_profile'] == 'virtual'


def test_cli_audio_selector_and_wrong_backend_or_clock_are_not_ignored(raw_project, com_project, tmp_path, monkeypatch):
    from fdisbull import cli
    seen = []
    monkeypatch.setattr(cli, 'serve', lambda project, launch: seen.append(launch) or 0)
    assert main(['debug', str(raw_project.path), '--executable', '/qemu', '--game-dir', '.',
                 '--backend', 'qemu-dos', '--qemu-clock', 'virtual', '--qemu-audio', 'pc-speaker']) == 0
    assert seen[0]['qemu_audio'] == 'pc-speaker'
    with pytest.raises(SystemExit):
        parser().parse_args(['debug', 'p.fdb', '--executable', '/qemu', '--game-dir', '.',
                             '--qemu-audio', 'unknown'])
    for backend, clock in [('dosbox', 'virtual'), ('qemu-dos', 'instruction')]:
        with pytest.raises(ValueError):
            com_project.debugger('/not-started', tmp_path, backend=backend,
                                 qemu_clock=clock, qemu_audio='pc-speaker')


@pytest.mark.parametrize('mutation', [
    {'api-version': True}, {'epoch': 2}, {'virtual-ns': 1001}, {'frames': True},
    {'rate': 44100}, {'channels': 2}, {'format': 's16'}, {'state': 'invalidated'},
    {'frames': 1}, {'dropped-frames': 1}, {'token': 'unowned'},
])
def test_malformed_audio_receipt_closes_owner_without_artifact(audio, mutation):
    o = audio
    o.wire.mutate = lambda value: dict(value, **mutation)
    with pytest.raises(DebuggerError):
        o.session.audio_observe()
    assert o.vm.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='audio'").fetchone()[0] == 0


@pytest.mark.parametrize('chunk', [
    {'first-frame': 1, 'frames': 4, 'virtual-ns': 1000},
    {'first-frame': 0, 'frames': 3, 'virtual-ns': 1000},
    {'first-frame': 0, 'frames': 4, 'virtual-ns': 999},
    {'first-frame': 0, 'frames': 4, 'virtual-ns': 1001},
])
def test_callback_receipt_must_cover_exact_pcm_prefix(audio, chunk):
    o = audio
    o.session.audio_start()
    o.wire.audio.update(frames=4, chunks=[chunk])
    with pytest.raises(DebuggerError, match='callback'):
        o.session.audio_observe()
    assert o.vm.closed


def test_export_length_mismatch_cannot_store_audio(audio):
    o = audio
    o.session.audio_start()
    o.wire.audio.update(frames=4, chunks=[{'first-frame': 0, 'frames': 4, 'virtual-ns': 1000}])
    o.wire.pcm = b'bad'
    with pytest.raises(DebuggerError, match='length'):
        o.session.capture_audio()
    assert o.vm.closed and not list(o.directory.glob('audio-*.pcm'))
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='audio'").fetchone()[0] == 0


def test_audio_window_cannot_regress_or_change_its_owned_token(audio):
    o = audio
    o.session.audio_start()
    o.wire.audio.update(frames=4, chunks=[{'first-frame': 0, 'frames': 4, 'virtual-ns': 1000}])
    assert o.session.audio_observe()['frames'] == 4
    o.wire.audio.update(token='another-window')
    with pytest.raises(DebuggerError, match='identity'):
        o.session.audio_observe()
    assert o.vm.closed


def test_whole_script_audio_admission_precedes_earlier_input_mutation(audio):
    o = audio
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='keyboard.key-down', key='a'),
        dict(op='audio-start', max_frames=0)])
    with pytest.raises(ValueError, match='max_frames'):
        validate_script(script, session=o.session)
    assert o.wire.calls == []
    script['steps'][1]['max_frames'] = 10
    o.session.capabilities['audio_capture'] = False
    with pytest.raises(ValueError, match='audio profile'):
        validate_script(script, session=o.session)
    assert o.wire.calls == []


def test_audio_script_uses_one_deadline_through_real_qmp_envelopes(audio):
    o = audio
    o.wire.latency = .03
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[dict(op='audio-start')])
    result = execute_script(o.session, script, timeout_ms=50)
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    assert [command for command, _ in o.wire.calls] == ['query-status', 'query-replay']
    assert o.wire.budgets == pytest.approx([.05, .02])
    assert o.vm.closed and o.wire.socket_closed


def test_audio_transaction_refusal_precedes_every_native_request(audio):
    o = audio
    with o.project.transaction(True):
        for operation in (o.session.audio_start, o.session.audio_observe,
                          o.session.audio_stop, o.session.capture_audio):
            with pytest.raises(ValueError, match='transaction'):
                operation()
    assert o.wire.calls == []


def test_unowned_native_audio_window_is_not_adopted(audio):
    o = audio
    o.wire.audio.update(state='capturing', token='not-python-owned',
                        **{'start-ns': 1000, 'max-frames': 32000})
    with pytest.raises(DebuggerError, match='identity'):
        o.session.audio_observe()
    assert o.vm.closed


def test_stopped_audio_cannot_keep_growing(audio):
    o = audio
    o.session.audio_start()
    o.session.audio_stop()
    o.wire.audio.update(frames=4, chunks=[{'first-frame': 0, 'frames': 4, 'virtual-ns': 1000}])
    with pytest.raises(DebuggerError, match='Stopped native audio'):
        o.session.audio_observe()
    assert o.vm.closed


def test_retained_pcm_prefix_cannot_change_after_an_export(audio):
    o = audio
    o.session.audio_start()
    o.wire.audio.update(frames=4, chunks=[{'first-frame': 0, 'frames': 4, 'virtual-ns': 1000}])
    o.wire.pcm = bytes((32, 224, 32, 224))
    o.session.capture_audio()
    o.wire.pcm = bytes((224, 32, 224, 32))
    with pytest.raises(DebuggerError, match='PCM changed'):
        o.session.capture_audio()
    assert o.vm.closed
