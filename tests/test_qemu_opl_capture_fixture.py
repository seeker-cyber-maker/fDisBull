"""Host signal-format checks for the native OPL witnesses; no VM evidence."""
import math
import struct

import pytest

from test_qemu_opl_native import _assert_keyoff, _pcm_lanes, _pitches


MONO = dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1)
STEREO = dict(rate=32000, channels=2, sample_format='s16', bytes_per_frame=4)


def test_checkpoint_pcm_decoder_preserves_legacy_mono_and_signed_lane_order():
    assert _pcm_lanes(bytes([0, 128, 255]), MONO) == [[0, 128, 255]]
    raw = struct.pack('<4h', -32768, 32767, 123, -456)
    assert _pcm_lanes(raw, STEREO) == [[-32768, 123], [32767, -456]]
    assert _pcm_lanes(b'', STEREO) == [[], []]


@pytest.mark.parametrize('raw,format_override', [
    (b'\x00\x00\x00', {}),
    (b'\x00' * 4, dict(channels=1)),
    (b'\x00' * 4, dict(bytes_per_frame=2)),
    (b'\x00' * 4, dict(rate=48000)),
])
def test_checkpoint_pcm_decoder_refuses_inconsistent_geometry(raw, format_override):
    with pytest.raises(AssertionError):
        _pcm_lanes(raw, {**STEREO, **format_override})


def test_checkpoint_pitch_oracle_checks_each_signed_channel_without_byte_or_lane_mixup():
    frames = 6400
    left = [round(300 + 5000 * math.sin(2 * math.pi * 440 * n / 32000)) for n in range(frames)]
    right = [round(-200 + 3000 * math.sin(2 * math.pi * 880 * n / 32000)) for n in range(frames)]
    raw = struct.pack('<' + 'h' * (2 * frames), *(value for pair in zip(left, right) for value in pair))
    assert _pitches(raw, STEREO) == pytest.approx([440, 880], rel=0.015)


def test_checkpoint_keyoff_requires_both_signed_lanes_to_be_silent():
    _assert_keyoff(bytes([128]) * 4096, MONO)
    _assert_keyoff(bytes(4096 * 4), STEREO)
    raw = struct.pack('<' + 'h' * (4096 * 2), *(value for _ in range(4096) for value in (0, 1000)))
    with pytest.raises(AssertionError):
        _assert_keyoff(raw, STEREO)
