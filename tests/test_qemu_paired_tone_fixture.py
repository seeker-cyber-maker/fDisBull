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


def _signed_stereo_lanes():
    # An integer number of both source periods gives independent DC/RMS oracles.
    # Distinct offsets and amplitudes remain in the raw WAV, without gain fitting.
    count = SOURCE_RATE // 10
    return (
        [round(256 + 6000 * math.sin(2 * math.pi * 500 * n / SOURCE_RATE))
         for n in range(count)],
        [round(-768 + 2000 * math.sin(2 * math.pi * 800 * n / SOURCE_RATE))
         for n in range(count)],
    )


def test_explicit_s16_stereo_oracle_retains_raw_levels_and_separate_lanes(tmp_path):
    left, right = _signed_stereo_lanes()
    path = tmp_path / 'signed-stereo.wav'
    _wav(path, 2, SOURCE_RATE, [value for pair in zip(left, right) for value in pair], 2)
    report = analyze_wav(path, 'S', 'qemu', capture_format='s16-stereo')
    assert (report['rate'], report['channels'], report['width']) == (32000, 2, 2)
    assert report['frames'] == len(left) and report['pcm_bytes'] == len(left) * 4
    assert report['pcm_encoding'] == 's16le'
    assert report['channel_order'] == ['left', 'right']
    assert report['whole_record_untrimmed'] is True
    assert report['gain_or_time_fit'] is False
    for index, (dc, amplitude) in enumerate(((256, 6000), (-768, 2000))):
        actual = report['channels_analysis'][index]
        assert actual['dc_mean'] == pytest.approx(dc / 32768, abs=1e-12)
        assert actual['rms_including_dc'] == pytest.approx(
            math.sqrt(dc * dc + amplitude * amplitude / 2) / 32768, rel=0.0003)
        assert actual['ac_rms'] == pytest.approx(amplitude / math.sqrt(2) / 32768, rel=0.0003)
        assert (actual['minimum_code'], actual['maximum_code']) == (dc - amplitude, dc + amplitude)
        assert actual['lower_rail_samples'] == actual['upper_rail_samples'] == 0
    assert report['frequencies'][0]['left']['measured_hz'] == 500
    assert report['frequencies'][1]['right']['measured_hz'] == 800


@pytest.mark.parametrize('fault', ['swapped', 'duplicated-mix', 'duplicated-left', 'duplicated-right'])
def test_explicit_s16_stereo_oracle_rejects_swapped_and_duplicated_mono(tmp_path, fault):
    left, right = _signed_stereo_lanes()
    if fault == 'swapped':
        left, right = right, left
    else:
        mono = ([round((a + b) / 2) for a, b in zip(left, right)]
                if fault == 'duplicated-mix' else left if fault == 'duplicated-left' else right)
        left = right = mono
    path = tmp_path / f'{fault}.wav'
    _wav(path, 2, SOURCE_RATE, [value for pair in zip(left, right) for value in pair], 2)
    with pytest.raises(AssertionError):
        analyze_wav(path, 'S', 'qemu', capture_format='s16-stereo')


@pytest.mark.parametrize('channels,width', [(1, 2), (2, 1)])
def test_explicit_s16_stereo_oracle_rejects_legacy_capture_geometry(tmp_path, channels, width):
    left, _ = _signed_stereo_lanes()
    values = (left if channels == 1 else list(source_stereo()))
    path = tmp_path / 'wrong-geometry.wav'
    _wav(path, channels, SOURCE_RATE, values, width)
    with pytest.raises(AssertionError):
        analyze_wav(path, 'S', 'qemu', capture_format='s16-stereo')


def test_explicit_s16_stereo_oracle_reports_each_raw_lane_rail_without_trimming(tmp_path):
    left, right = _signed_stereo_lanes()
    left[0], left[-1] = -32768, 32767
    right[0], right[-1] = 32767, -32768
    path = tmp_path / 'rails.wav'
    _wav(path, 2, SOURCE_RATE, [value for pair in zip(left, right) for value in pair], 2)
    report = analyze_wav(path, 'S', 'qemu', capture_format='s16-stereo')
    assert report['frames'] == len(left)
    for lane in report['channels_analysis']:
        assert (lane['minimum_code'], lane['maximum_code']) == (-32768, 32767)
        assert lane['lower_rail_samples'] == lane['upper_rail_samples'] == 1
