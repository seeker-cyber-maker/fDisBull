"""Host checks for the independent paired-tone signal oracle, not VM evidence."""
import math
import struct
import wave

import pytest

from support.qemu_paired_tone_fixture import (
    DSP_REQUEST_SAMPLES, REQUESTED_STEREO_FRAMES, LEFT_PERIOD, RIGHT_PERIOD,
    SOURCE_BYTES, SOURCE_FRAMES, SOURCE_RATE,
    expected_frequencies, source_stereo,
)
from test_qemu_paired_tone_native import analyze_wav


def _wav(path, channels, rate, values, width):
    raw = bytes(values) if width == 1 else struct.pack('<' + 'h' * len(values), *values)
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((channels, width, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(raw)


def test_authored_stereo_input_has_independent_periods_and_bounded_asymmetry():
    source = source_stereo()
    left, right = source[::2], source[1::2]
    assert len(source) == SOURCE_BYTES == SOURCE_FRAMES * 2
    assert left[LEFT_PERIOD:] == left[:-LEFT_PERIOD]
    assert right[RIGHT_PERIOD:] == right[:-RIGHT_PERIOD]
    assert max(left) - min(left) == 64 and max(right) - min(right) == 24
    assert expected_frequencies()['left'] == SOURCE_RATE / LEFT_PERIOD == 500
    assert expected_frequencies()['right'] == SOURCE_RATE / RIGHT_PERIOD == 800


def test_whole_record_oracle_distinguishes_stereo_from_mono_with_dc_retained(tmp_path):
    stereo = tmp_path / 'stereo.wav'
    _wav(stereo, 2, SOURCE_RATE, source_stereo(), 1)
    report = analyze_wav(stereo, 'S', 'dosbox')
    assert report['whole_record_untrimmed'] and report['gain_or_time_fit'] is False
    mono = tmp_path / 'mono.wav'
    data = source_stereo()
    _wav(mono, 1, SOURCE_RATE,
         [data[2 * n] + data[2 * n + 1] - 127 for n in range(SOURCE_FRAMES)], 1)
    report = analyze_wav(mono, 'S', 'qemu')
    assert report['channels'] == 1 and report['channels_analysis'][0]['dc_mean'] > 0
    assert report['channels_analysis'][0]['rms_including_dc'] > report['channels_analysis'][0]['ac_rms']


def test_oracle_rejects_missing_right_frequency_and_checks_full_s16_pitch(tmp_path):
    missing = tmp_path / 'missing.wav'
    _wav(missing, 1, SOURCE_RATE, source_stereo()[::2], 1)
    with pytest.raises(AssertionError):
        analyze_wav(missing, 'S', 'qemu')
    tone = tmp_path / 'tone.wav'
    frequency, rate = expected_frequencies()['opl'], 48000
    values = [round(400 + 5000 * math.sin(2 * math.pi * frequency * n / rate)) for n in range(rate // 3)]
    _wav(tone, 2, rate, [v for value in values for v in (value, value)], 2)
    report = analyze_wav(tone, 'O', 'dosbox')
    assert report['frames'] == len(values) and report['channels_analysis'][0]['dc_mean'] > 0


def test_opl_oracle_rejects_weak_expected_residual_under_wrong_dominant_tone(tmp_path):
    frequency, rate = expected_frequencies()['opl'], 48000
    values = [round(7000 * math.sin(2 * math.pi * 880 * n / rate)
                    + 70 * math.sin(2 * math.pi * frequency * n / rate))
              for n in range(rate // 3)]
    path = tmp_path / 'wrong-dominant-tone.wav'
    _wav(path, 1, rate, values, 2)
    with pytest.raises(AssertionError):
        analyze_wav(path, 'O', 'qemu')


def test_dsp_c0_length_counts_eight_bit_channel_samples_not_stereo_frames():
    # Creative Hardware Programming Guide6-24: Cxh length is8-bit samples-1.
    assert DSP_REQUEST_SAMPLES == 4096 and DSP_REQUEST_SAMPLES - 1 == 0x0fff
    assert REQUESTED_STEREO_FRAMES == 2048
    assert SOURCE_FRAMES == 4096 and SOURCE_BYTES == 8192
    assert DSP_REQUEST_SAMPLES * 1 == 4096  # Bytes, independent of stereo framing.
    assert SOURCE_BYTES - DSP_REQUEST_SAMPLES - 1 == 4095
