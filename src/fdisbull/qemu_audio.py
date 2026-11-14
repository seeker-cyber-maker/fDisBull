"""Bounded native audio output windows, independent of guest or host pacing.

The optional PC-speaker profile captures QEMU mixer output. A sample callback
is a real output boundary, but its timestamp is not the onset time of each
sample. Inactive intervals are not filled with invented silence. A stopped
read never invokes the mixer, flushes a device or advances the machine.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
from pathlib import Path
import uuid
import wave

from .dosbox_rpc import DebuggerError


AUDIO_COMMANDS = frozenset({
    'x-fdisbull-query-audio', 'x-fdisbull-start-audio',
    'x-fdisbull-stop-audio', 'x-fdisbull-export-audio',
})
AUDIO_RATE = 32000
MAX_AUDIO_FRAMES = AUDIO_RATE * 60
_FORMAT = dict(rate=AUDIO_RATE, channels=1, sample_format='u8', bytes_per_frame=1)


def machine_audio_configuration(profile, clock_profile):
    if profile not in ('off', 'pc-speaker'):
        raise ValueError('QEMU audio profile must be off or pc-speaker')
    if profile == 'pc-speaker' and clock_profile != 'virtual':
        raise ValueError('PC-speaker capture requires the explicit QEMU virtual clock profile')
    return dict(profile=profile, devices=['pc-speaker'] if profile != 'off' else [],
                host_playback=False, capture_format=deepcopy(_FORMAT) if profile != 'off' else None)


def validate_audio_capacity(max_frames):
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_AUDIO_FRAMES:
        raise ValueError('Audio max_frames must be an integer in 1..1920000')


def _invalid(vm, message):
    vm.close()
    raise DebuggerError(message)


def _native_audio(vm, value, clock, *, token=None):
    def integer(item, maximum=(1 << 63) - 1):
        return type(item) is int and 0 <= item <= maximum

    native_clock = clock['virtual_clock']['native']
    required = {'api-version', 'epoch', 'state', 'virtual-ns', 'max-frames',
                'frames', 'dropped-frames', 'rate', 'channels', 'format', 'enabled', 'chunks'}
    if (not isinstance(value, dict) or not required <= value.keys()
            or type(value['api-version']) is not int or value['api-version'] != 1
            or not integer(value['epoch'], (1 << 64) - 1)
            or value['epoch'] != native_clock['epoch']
            or not integer(value['virtual-ns']) or value['virtual-ns'] != clock['virtual_ns']
            or value['state'] not in ('idle', 'capturing', 'stopped', 'overflow')
            or type(value['rate']) is not int or value['rate'] != AUDIO_RATE
            or type(value['channels']) is not int or value['channels'] != 1
            or value['format'] != 'u8' or type(value['enabled']) is not bool
            or not integer(value['max-frames'], MAX_AUDIO_FRAMES)
            or not integer(value['frames'], value['max-frames'])
            or not integer(value['dropped-frames'], (1 << 64) - 1)
            or not isinstance(value['chunks'], list) or len(value['chunks']) > 8192):
        _invalid(vm, 'Invalid native QEMU audio receipt')
    if value['state'] == 'idle':
        if (any(key in value for key in ('token', 'start-ns', 'stop-ns'))
                or value['max-frames'] or value['frames'] or value['dropped-frames']
                or value['chunks'] or token is not None):
            _invalid(vm, 'Idle native audio unexpectedly retains a window')
    else:
        if (token is None or not isinstance(value.get('token'), str) or not 1 <= len(value['token']) <= 128
                or value['token'] != token
                or not integer(value.get('start-ns'))
                or value['start-ns'] > value['virtual-ns'] or value['max-frames'] == 0
                or 'stop-ns' in value and (not integer(value['stop-ns']) or
                    not value['start-ns'] <= value['stop-ns'] <= value['virtual-ns'])
                or value['state'] == 'stopped' and 'stop-ns' not in value
                or value['state'] == 'capturing' and 'stop-ns' in value
                or (value['state'] == 'overflow') != (value['dropped-frames'] > 0)):
            _invalid(vm, 'Native audio window identity or interval is invalid')
    total, previous = 0, value.get('start-ns', value['virtual-ns'])
    for chunk in value['chunks']:
        if (not isinstance(chunk, dict) or not integer(chunk.get('first-frame'))
                or chunk['first-frame'] != total or not integer(chunk.get('frames'))
                or chunk['frames'] == 0 or not integer(chunk.get('virtual-ns'))
                or not previous <= chunk['virtual-ns'] <= value.get('stop-ns', value['virtual-ns'])):
            _invalid(vm, 'Native audio callback boundaries are invalid')
        total += chunk['frames']
        previous = chunk['virtual-ns']
    if total != value['frames']:
        _invalid(vm, 'Native audio callbacks do not cover the retained samples')
    prior = getattr(vm, '_audio_last', None)
    if prior is not None and prior.get('token') == value.get('token'):
        if (value['frames'] < prior['frames'] or value['dropped-frames'] < prior['dropped-frames']
                or value['chunks'][:len(prior['chunks'])] != prior['chunks']
                or value.get('start-ns') != prior.get('start-ns')
                or value['max-frames'] != prior['max-frames']
                or 'stop-ns' in prior and value.get('stop-ns') != prior['stop-ns']):
            _invalid(vm, 'Native audio window regressed or changed identity')
        if 'stop-ns' in prior and any(value.get(key) != item for key, item in prior.items() if key != 'virtual-ns'):
            _invalid(vm, 'Stopped native audio changed after capture detachment')
    vm._audio_last = deepcopy(value)
    return deepcopy(value)


def admit_audio(vm):
    if not AUDIO_COMMANDS <= vm.qmp_commands:
        raise ValueError('PC-speaker capture requires the fDisBull audio extension API 1')
    clock = dict(virtual_ns=vm.native_clock_admission['virtual-ns'],
                 virtual_clock=dict(native=vm.native_clock_admission))
    value = _native_audio(vm, vm.qmp.call('x-fdisbull-query-audio'), clock)
    if value['state'] != 'idle':
        _invalid(vm, 'New QEMU machine already has an audio capture window')
    return value


class QemuAudioMixin:
    def _audio_context(self):
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Audio capture requires a project outside a caller-owned transaction')
        if self.vm.machine_configuration.get('audio_profile', {}).get('profile') != 'pc-speaker':
            raise ValueError('Audio capture requires the explicit QEMU pc-speaker audio profile')
        if self.vm.machine_configuration['audio_profile'] != machine_audio_configuration('pc-speaker', 'virtual'):
            _invalid(self.vm, 'Owned-machine audio profile changed within its observation epoch')
        self._stopped()
        return self.clock_observe()

    def _audio_read(self, clock):
        return _native_audio(self.vm, self.vm.qmp.call('x-fdisbull-query-audio'), clock,
                             token=getattr(self.vm, '_audio_token', None))

    def _audio_receipt(self, native, clock):
        return dict(format='fdisbull-audio-window-1', context='machine', run=self.run_id,
                    epoch=clock['epoch'], window=native.get('token'), state=native['state'],
                    observed_ns=native['virtual-ns'], start_ns=native.get('start-ns'),
                    stop_ns=native.get('stop-ns'), clock_domain='QEMU_CLOCK_VIRTUAL',
                    frames=native['frames'], max_frames=native['max-frames'],
                    dropped_frames=native['dropped-frames'], sample_format=deepcopy(_FORMAT),
                    sample_duration_ns=native['frames'] * 31250,
                    clock=deepcopy(clock), native=deepcopy(native),
                    guest_audio_complete=None, device_queue_drained=None,
                    scope=('Complete mixer-output PCM frames with callback delivery timestamps; '
                           'inactive intervals are not synthesized. Sample duration describes '
                           'the concatenated PCM, not elapsed guest time or audible playback.'))

    def audio_observe(self):
        clock = self._audio_context()
        result = self._audio_receipt(self._audio_read(clock), clock)
        self._event('machine-audio-observe', result)
        return result

    def audio_start(self, *, max_frames=320000):
        validate_audio_capacity(max_frames)
        clock = self._audio_context()
        prior = self._audio_read(clock)
        if prior['state'] != 'idle' and 'stop-ns' not in prior:
            raise ValueError('Stop the current audio capture window before starting another')
        token = uuid.uuid4().hex
        try:
            native = _native_audio(self.vm, self.vm.qmp.call('x-fdisbull-start-audio',
                {'token': token, 'max-frames': max_frames}), clock, token=token)
            if (native['state'] != 'capturing' or native['frames'] != 0
                    or native['start-ns'] != clock['virtual_ns']
                    or native['max-frames'] != max_frames):
                _invalid(self.vm, 'Native audio start differs from the requested window')
            self.vm._audio_token = token
            result = self._audio_receipt(native, clock)
            self._event('machine-audio-start', result)
            return result
        except BaseException:
            self.vm.close()
            raise

    def audio_stop(self):
        clock = self._audio_context()
        prior = self._audio_read(clock)
        if prior['state'] == 'idle':
            raise ValueError('No owned audio capture window has been started')
        try:
            native = _native_audio(self.vm, self.vm.qmp.call('x-fdisbull-stop-audio',
                {'token': prior['token']}), clock, token=prior['token'])
            if (native['frames'] != prior['frames'] or native['chunks'] != prior['chunks']
                    or native.get('stop-ns') != prior.get('stop-ns', clock['virtual_ns'])):
                _invalid(self.vm, 'Native audio stop changed the retained samples')
            result = self._audio_receipt(native, clock)
            self._event('machine-audio-stop', result)
            return result
        except BaseException:
            self.vm.close()
            raise

    def capture_audio(self, name='machine-audio.wav'):
        from .debugger import _file_name

        _file_name(name)
        clock = self._audio_context()
        prior = self._audio_read(clock)
        if prior['state'] == 'idle':
            raise ValueError('No owned audio capture window has been started')
        if prior['state'] == 'overflow':
            raise ValueError('Audio capture overflowed; stop it and start a new bounded window')
        path = Path(self.vm.temporary.name) / ('audio-' + uuid.uuid4().hex + '.pcm')
        try:
            native = _native_audio(self.vm, self.vm.qmp.call('x-fdisbull-export-audio',
                {'token': prior['token'], 'filename': str(path)}), clock, token=prior['token'])
            if native != prior:
                _invalid(self.vm, 'Native audio changed across its stopped export')
            if not path.is_file() or path.stat().st_size != native['frames']:
                _invalid(self.vm, 'Native audio export length differs from its sample receipt')
            pcm = path.read_bytes()
            if len(pcm) != native['frames']:
                _invalid(self.vm, 'Native PCM changed length during its stopped read')
            previous = getattr(self.vm, '_audio_export', None)
            if previous is not None and previous['token'] == native['token']:
                if (len(pcm) < previous['frames'] or
                        hashlib.sha256(pcm[:previous['frames']]).hexdigest() != previous['sha256']):
                    _invalid(self.vm, 'Retained native PCM changed within the same audio window')
            self.vm._audio_export = dict(token=native['token'], frames=len(pcm),
                                         sha256=hashlib.sha256(pcm).hexdigest())
            after = self.clock_observe()
            if (clock['epoch'] != after['epoch'] or clock['counter'] != after['counter']
                    or clock['virtual_ns'] != after['virtual_ns']):
                _invalid(self.vm, 'Machine clock changed across the stopped audio export')
        except BaseException:
            self.vm.close()
            raise
        finally:
            path.unlink(missing_ok=True)
        output = io.BytesIO()
        with wave.open(output, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(1)
            stream.setframerate(AUDIO_RATE)
            stream.writeframes(pcm)
        data = output.getvalue()
        metadata = self._audio_receipt(native, clock)
        metadata.update(source='qemu_audio_capture_callback', stopped=True,
                        pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                        sha256=hashlib.sha256(data).hexdigest(),
                        clocks=dict(before=clock, after=after))
        artifact = self._artifact(name, 'audio', data, metadata)
        self._event('machine-capture-audio', dict(artifact=artifact['artifact'],
                    window=native['token'], frames=native['frames'], sha256=metadata['sha256']))
        return artifact
