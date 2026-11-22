"""Explicit stereo capture ownership at real QMP and public API boundaries.

The authored PCM below proves host byte/frame handling only; native device
production and paired tone expectations are qualified by separate VM tests.
"""
from copy import deepcopy
import hashlib
import io
import json
import struct
import wave

import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_audio import AUDIO_COMMANDS, machine_audio_configuration
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from fdisbull.qemu_instrumented_checkpoint import COMMANDS, FORMAT, PREFIX, restore
from fdisbull.qemu_machine import MachineContext
from test_qemu_audio import AudioWire
from test_qemu_io_deadlines import observation


FORMAT_COMMAND = 'x-fdisbull-start-audio-format'
MONO = dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1)
STEREO = dict(rate=32000, channels=2, sample_format='s16', bytes_per_frame=4)
PCM = struct.pack('<hhhh', 32767, -32768, -1234, 5678)


class FormatWire(AudioWire):
    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command in ('x-fdisbull-start-audio', FORMAT_COMMAND):
            self.calls.append((command, args))
            self.budgets.append(self.timeout)
            stereo = args.get('capture-format', 'u8-mono') == 's16-stereo'
            self.audio.update(state='capturing', token=args['token'], frames=0,
                chunks=[], channels=2 if stereo else 1, format='s16' if stereo else 'u8',
                **{'start-ns': self.receipt['virtual-ns'], 'max-frames': args['max-frames'],
                   'virtual-ns': self.receipt['virtual-ns'], 'dropped-frames': 0})
            self.audio.pop('stop-ns', None)
            self.pcm = b''
            self.reply(request, self.mutate(deepcopy(self.audio)))
        elif command == PREFIX + 'checkpoint-import':
            self.calls.append((command, args))
            self.imported = json.loads(args['state'])
            self.imported['source-epoch'] = 2
            self.imported['clock']['info']['epoch'] = 2
            self.receipt = deepcopy(self.imported['clock']['info'])
            self.audio = self.imported['audio']['info']
            self.audio.update(epoch=2, token='restored-audio-owner')
            self.imported['display']['info']['epoch'] = 2
            self.import_result = {'new-epoch': 2, 'virtual-ns': self.receipt['virtual-ns'],
                                  'audio-token': self.audio['token']}
            self.reply(request, self.import_result)
        elif command == PREFIX + 'checkpoint-status':
            self.calls.append((command, args))
            self.reply(request, self.import_result)
        elif command == PREFIX + 'checkpoint-export':
            self.calls.append((command, args))
            self.reply(request, envelope(self.imported))
        elif command == 'x-fdisbull-query-display':
            self.calls.append((command, args))
            self.reply(request, self.imported['display']['info'])
        else:
            super().sendall(data)

    def reply(self, request, value):
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency


@pytest.fixture
def formatted_audio(observation):
    o = observation
    o.qmp.socket = o.wire = FormatWire(o.clock)
    o.vm.machine_configuration.update(
        clock_profile=machine_clock_configuration('virtual', 1),
        audio_profile=machine_audio_configuration('sb16-opl', 'virtual'))
    o.vm.qmp_commands = AUDIO_COMMANDS | VIRTUAL_CLOCK_COMMANDS | COMMANDS | {FORMAT_COMMAND}
    o.session.capabilities.update(audio_capture=True, audio_stereo_capture=True,
                                  virtual_clock_budget=True)
    return o


def frames(o, count=2, pcm=PCM):
    o.wire.audio.update(frames=count, chunks=[
        {'first-frame': 0, 'frames': count, 'virtual-ns': 1000}])
    o.wire.pcm = pcm


def script(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-machine', steps=list(steps))


def envelope(state):
    data = json.dumps(state, sort_keys=True, separators=(',', ':'))
    return dict(state=data, sha256=hashlib.sha256(data.encode()).hexdigest(), icount=41)


def checkpoint(o, *, stereo=True):
    info = deepcopy(o.wire.audio)
    info.update(state='capturing', token='saved-audio-owner', channels=2 if stereo else 1,
                format='s16' if stereo else 'u8', **{'max-frames': 8, 'start-ns': 1000})
    return dict(format=FORMAT, **{'source-epoch': 1, 'virtual-ns': 1000},
        clock=dict(info=deepcopy(o.wire.receipt)), audio=dict(info=info), retrace={},
        display=dict(info={'api-version': 1, 'epoch': 1, 'state': 'idle',
                          'virtual-ns': 1000, 'period-ns': 0, 'updates': 0}))


@pytest.mark.parametrize('explicit', [False, True])
def test_default_and_explicit_mono_keep_the_original_command_on_old_binaries(formatted_audio, explicit):
    o = formatted_audio
    o.vm.qmp_commands -= {FORMAT_COMMAND}
    options = {'capture_format': 'u8-mono'} if explicit else {}
    result = o.session.audio_start(max_frames=8, **options)
    assert result['sample_format'] == MONO
    calls = [(name, args) for name, args in o.wire.calls if name.startswith('x-fdisbull-start-audio')]
    assert calls == [('x-fdisbull-start-audio', {'token': result['window'], 'max-frames': 8})]
    assert not o.vm.closed


def test_stereo_start_binds_requested_format_and_logical_frame_capacity(formatted_audio):
    o = formatted_audio
    result = o.session.audio_start(max_frames=1920000, capture_format='s16-stereo')
    assert result['sample_format'] == STEREO
    assert result['max_frames'] == 1920000 and result['frames'] == 0
    assert (FORMAT_COMMAND, {'token': result['window'], 'max-frames': 1920000,
                            'capture-format': 's16-stereo'}) in o.wire.calls
    assert o.session.audio_observe()['sample_format'] == STEREO


def test_stereo_wav_retains_signed_little_endian_channels_and_frame_counts(formatted_audio):
    o = formatted_audio
    o.session.audio_start(capture_format='s16-stereo')
    frames(o)
    artifact = o.session.capture_audio('stereo.wav')
    metadata = artifact['metadata']
    assert metadata['sample_format'] == STEREO
    assert metadata['frames'] == 2 and metadata['sample_duration_ns'] == 62500
    assert metadata['pcm_sha256'] == hashlib.sha256(PCM).hexdigest()
    data = o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                               (artifact['artifact'],)).fetchone()[0]
    with wave.open(io.BytesIO(data), 'rb') as stream:
        assert (stream.getframerate(), stream.getnchannels(), stream.getsampwidth(),
                stream.getnframes()) == (32000, 2, 2, 2)
        assert stream.readframes(2) == PCM
    o.wire.audio['frames'] = 3
    o.wire.audio['chunks'].append({'first-frame': 2, 'frames': 1, 'virtual-ns': 1000})
    o.wire.pcm += struct.pack('<hh', 45, -67)
    assert o.session.capture_audio('stereo-extended.wav')['metadata']['frames'] == 3
    assert not o.vm.closed and not list(o.directory.glob('audio-*.pcm'))


@pytest.mark.parametrize('pcm', [PCM[:-1], PCM + b'\0', PCM[:2]])
def test_stereo_export_requires_exact_whole_frame_byte_extent(formatted_audio, pcm):
    o = formatted_audio
    o.session.audio_start(capture_format='s16-stereo')
    frames(o, pcm=pcm)
    with pytest.raises(DebuggerError, match='length'):
        o.session.capture_audio()
    assert o.vm.closed and not list(o.directory.glob('audio-*.pcm'))
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='audio'").fetchone()[0] == 0


def test_stereo_prefix_integrity_includes_every_channel_byte(formatted_audio):
    o = formatted_audio
    o.session.audio_start(capture_format='s16-stereo')
    frames(o)
    o.session.capture_audio()
    o.wire.pcm = PCM[:-1] + bytes([PCM[-1] ^ 1])
    with pytest.raises(DebuggerError, match='PCM changed'):
        o.session.capture_audio()
    assert o.vm.closed


@pytest.mark.parametrize('mutation', [dict(channels=1, format='u8'), dict(rate=48000),
                                      dict(channels=True), dict(format='s16be')])
def test_stereo_start_refuses_native_geometry_other_than_requested(formatted_audio, mutation):
    o = formatted_audio
    o.wire.mutate = lambda value: dict(value, **mutation) if value['state'] != 'idle' else value
    with pytest.raises(DebuggerError, match='audio receipt'):
        o.session.audio_start(capture_format='s16-stereo')
    assert o.vm.closed


def test_owned_stereo_geometry_cannot_change_mid_window(formatted_audio):
    o = formatted_audio
    o.session.audio_start(capture_format='s16-stereo')
    o.wire.audio.update(channels=1, format='u8')
    with pytest.raises(DebuggerError, match='audio receipt'):
        o.session.audio_observe()
    assert o.vm.closed


def test_format_can_change_only_by_starting_a_new_stopped_window(formatted_audio):
    o = formatted_audio
    first = o.session.audio_start(capture_format='s16-stereo')
    assert o.session.audio_stop()['sample_format'] == STEREO
    second = o.session.audio_start()
    assert second['sample_format'] == MONO and first['window'] != second['window']
    assert o.session.audio_observe()['sample_format'] == MONO


@pytest.mark.parametrize('capture_format', [None, True, [], {}, 's16', 'stereo', pytest.param('', id='empty')])
def test_invalid_format_refuses_before_any_native_request(formatted_audio, capture_format):
    o = formatted_audio
    with pytest.raises(ValueError, match='capture_format'):
        o.session.audio_start(capture_format=capture_format)
    assert o.wire.calls == [] and not o.vm.closed


@pytest.mark.parametrize('profile,command', [('sb16-opl', False), ('pc-speaker', True), ('sb16', True)])
def test_stereo_capability_is_scoped_and_refuses_before_mutation(formatted_audio, profile, command):
    o = formatted_audio
    o.vm.machine_configuration['audio_profile'] = machine_audio_configuration(profile, 'virtual')
    if not command:
        o.vm.qmp_commands -= {FORMAT_COMMAND}
    assert MachineContext(o.vm).capabilities['audio_stereo_capture'] is False
    with pytest.raises(ValueError, match='stereo'):
        o.session.audio_start(capture_format='s16-stereo')
    assert o.wire.calls == [] and not o.vm.closed


def test_stereo_capability_requires_explicit_virtual_combined_profile(formatted_audio):
    o = formatted_audio
    assert MachineContext(o.vm).capabilities['audio_stereo_capture'] is True
    o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('instruction', 1)
    assert MachineContext(o.vm).capabilities['audio_stereo_capture'] is False


@pytest.mark.parametrize('capture_format,capability', [('unknown', True), ('s16-stereo', False)])
def test_saved_script_stereo_admission_precedes_earlier_mutation(formatted_audio, capture_format, capability):
    o = formatted_audio
    o.session.capabilities['audio_stereo_capture'] = capability
    writes = []
    o.session.write_memory = lambda **kwargs: writes.append(kwargs)
    value = script(dict(op='write-memory', address='0x1000', data_hex='01'),
                   dict(op='audio-start', capture_format=capture_format))
    with pytest.raises(ValueError, match='capture_format|stereo'):
        validate_script(value, session=o.session)
    with pytest.raises(ValueError, match='capture_format|stereo'):
        execute_script(o.session, value)
    assert writes == [] and o.wire.calls == [] and not o.vm.closed


@pytest.mark.parametrize('route', ['json', 'saved-script'])
def test_public_routes_preserve_explicit_stereo_selection(formatted_audio, route):
    o = formatted_audio
    if route == 'json':
        workspace = DebugWorkspace()
        workspace.sessions[o.session.run_id] = o.session
        try:
            response = respond(dict(id=12, method='debug-audio-start', params=dict(
                project=str(o.project.path), run=o.session.run_id,
                capture_format='s16-stereo', max_frames=8)), debugger=workspace)
        finally:
            workspace.sessions.clear()
        assert response['ok'], response
        result = response['result']
    else:
        response = execute_script(o.session, script(dict(op='audio-start',
            capture_format='s16-stereo', max_frames=8)))
        assert response['ok'], response
        result = response['steps'][0]['result']
    assert result['sample_format'] == STEREO and result['max_frames'] == 8
    assert sum(name == FORMAT_COMMAND for name, _ in o.wire.calls) == 1


@pytest.mark.parametrize('stereo', [False, True])
def test_checkpoint_restore_binds_saved_geometry_before_adopting_new_owner(formatted_audio, stereo):
    o = formatted_audio
    saved = checkpoint(o, stereo=stereo)
    if not stereo:
        o.vm.qmp_commands -= {FORMAT_COMMAND}
    o.vm._audio_capture_format = 'u8-mono' if stereo else 's16-stereo'
    o.vm._audio_export = dict(token='old', frames=1, bytes=4, sha256='old')
    result = restore(o.vm, envelope(saved))
    assert result['windows']['audio'] == dict(old='saved-audio-owner', new='restored-audio-owner')
    assert o.session.audio_observe()['sample_format'] == (STEREO if stereo else MONO)
    assert not hasattr(o.vm, '_audio_export') and not o.vm.closed


@pytest.mark.parametrize('mutation', [dict(channels=1, format='s16'), dict(channels=True),
                                      dict(rate=48000), dict(format='s16be')])
def test_checkpoint_invalid_geometry_refuses_before_native_import(formatted_audio, mutation):
    o = formatted_audio
    saved = checkpoint(o)
    saved['audio']['info'].update(mutation)
    with pytest.raises(ValueError, match='audio.*format'):
        restore(o.vm, envelope(saved))
    assert o.wire.calls == [] and not o.vm.closed


@pytest.mark.parametrize('profile,command', [('sb16-opl', False), ('pc-speaker', True), ('sb16', True)])
def test_stereo_checkpoint_requires_capability_before_native_import(formatted_audio, profile, command):
    o = formatted_audio
    saved = checkpoint(o)
    o.vm.machine_configuration['audio_profile'] = machine_audio_configuration(profile, 'virtual')
    if not command:
        o.vm.qmp_commands -= {FORMAT_COMMAND}
    with pytest.raises(ValueError, match='stereo'):
        restore(o.vm, envelope(saved))
    assert o.wire.calls == [] and not o.vm.closed


def test_restored_native_geometry_must_match_checkpoint_not_startup(formatted_audio):
    o = formatted_audio
    saved = checkpoint(o)
    o.wire.mutate = lambda value: dict(value, channels=1, format='u8')
    with pytest.raises(DebuggerError, match='audio receipt'):
        restore(o.vm, envelope(saved))
    assert any(name == PREFIX + 'checkpoint-import' for name, _ in o.wire.calls)
    assert o.vm.closed
