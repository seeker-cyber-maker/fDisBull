"""Passive software-voice gain readback; no gain or channel-law changes."""
from __future__ import annotations

from copy import deepcopy

from .qemu_audio import _invalid


MIXER_COMMAND = 'x-fdisbull-query-mixer'
GAIN_SCALE = 1 << 32


def _native_mixer(vm, value, profile):
    def require(condition):
        if not condition:
            _invalid(vm, 'Invalid native QEMU mixer gain receipt')

    def integer(item, lower, upper):
        return type(item) is int and lower <= item <= upper

    def name(item):
        if not isinstance(item, str) or not item or '\0' in item:
            return False
        try:
            return len(item.encode('utf-8')) <= 128
        except UnicodeEncodeError:
            return False

    def pcm(item):
        require(isinstance(item, dict))
        require(integer(item.get('rate'), 1, 192000)
                and type(item.get('channels')) is int and item['channels'] in (1, 2)
                and type(item.get('bits')) is int and item['bits'] in (8, 16, 32)
                and type(item.get('is-signed')) is bool
                and type(item.get('swap-endianness')) is bool)
        frame = item['channels'] * item['bits'] // 8
        require(type(item.get('bytes-per-frame')) is int and item['bytes-per-frame'] == frame
                and type(item.get('bytes-per-second')) is int
                and item['bytes-per-second'] == frame * item['rate'])

    require(isinstance(value, dict) and type(value.get('api-version')) is int
            and value['api-version'] == 1
            and type(value.get('gain-scale')) is int and value['gain-scale'] == GAIN_SCALE
            and value.get('mono-input') == 'duplicate-to-left-right'
            and value.get('mono-output') == 'sum-then-clip'
            and value.get('stereo-output') == 'clip-left-right'
            and isinstance(value.get('audiodevs'), list) and len(value['audiodevs']) <= 8)
    card_total = voice_total = capture_total = 0
    identities = []
    for device in value['audiodevs']:
        require(isinstance(device, dict) and name(device.get('audiodev-id'))
                and name(device.get('driver')) and type(device.get('mixing-engine')) is bool
                and isinstance(device.get('cards'), list)
                and isinstance(device.get('voices'), list)
                and isinstance(device.get('captures'), list))
        identities.append(device['audiodev-id'])
        cards = device['cards']
        card_total += len(cards)
        voice_total += len(device['voices'])
        capture_total += len(device['captures'])
        require(card_total <= 32 and voice_total <= 32 and capture_total <= 32
                and all(name(card) for card in cards)
                and cards == sorted(set(cards)))
        voices = []
        for voice in device['voices']:
            require(isinstance(voice, dict) and name(voice.get('card-id'))
                    and name(voice.get('voice-id')) and voice['card-id'] in cards
                    and all(type(voice.get(key)) is bool for key in (
                        'active', 'software-volume-applied', 'hardware-enabled',
                        'hardware-pending-disable')))
            require(not voice['software-volume-applied'] or device['mixing-engine'])
            voices.append((voice['card-id'], voice['voice-id']))
            gain = voice.get('gain')
            require(isinstance(gain, dict) and type(gain.get('mute')) is bool
                    and integer(gain.get('left'), 0, GAIN_SCALE)
                    and integer(gain.get('right'), 0, GAIN_SCALE))
            pcm(voice.get('format'))
            pcm(voice.get('hardware-format'))
        require(voices == sorted(set(voices)))
        captures = []
        for capture in device['captures']:
            require(isinstance(capture, dict) and type(capture.get('enabled')) is bool)
            pcm(capture.get('format'))
            captures.append(tuple(capture['format'][key] for key in (
                'rate', 'channels', 'bits', 'is-signed', 'swap-endianness')))
        require(captures == sorted(set(captures)))
    require(identities == sorted(set(identities)))
    expected = 'fdisbull-pc' if profile == 'pc-speaker' else 'fdisbull-' + profile
    require(identities == [expected] and value['audiodevs'][0]['driver'] == 'none'
            and value['audiodevs'][0]['mixing-engine'] is True)
    return deepcopy(value)


class QemuMixerMixin:
    def mixer_observe(self):
        if MIXER_COMMAND not in self.vm.qmp_commands:
            raise ValueError('Mixer gain readback requires the optional native mixer extension API 1')
        before = self._audio_context()
        profile = self.vm.machine_configuration['audio_profile']['profile']
        native = _native_mixer(self.vm, self.vm.qmp.call(MIXER_COMMAND), profile)
        after = self.clock_observe()
        if (before['epoch'] != after['epoch'] or before['counter'] != after['counter']
                or before['virtual_ns'] != after['virtual_ns']):
            _invalid(self.vm, 'Machine clock changed across the stopped mixer readback')
        result = dict(format='fdisbull-machine-mixer-1', context='machine', run=self.run_id,
            epoch=before['epoch'], observed_ns=before['virtual_ns'], clock=deepcopy(before),
            clocks=dict(before=before, after=after), native=native,
            scope=('Actual software-voice Q32 gains and current graph formats; mute is separate. '
                   'No invented master gain, guest SB-register gain application, calibrated '
                   'loudness or physical output is implied. Readback never runs or flushes audio.'))
        self._event('machine-mixer-observe', result)
        return result
