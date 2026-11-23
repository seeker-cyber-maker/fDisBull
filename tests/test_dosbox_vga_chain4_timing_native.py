"""Independent native DOSBox timing for the frozen four-raster guest."""
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import struct
import sys

import pytest

from support.dos_process_fixture import digest
from support.paired_video_frame_fixture import TRIAL_BYTES
from support.paired_video_frame_oracle import HEIGHT, PALETTES, PIT_HZ, parse_trial, rgb_for_rows
from test_paired_video_frame_native import PROFILE, _calibration, _owner, _write_json, paired_video_program


COM_SHA256 = 'c2ddebd5affa489302f22c9139d354be1cb31b38d5edbe58b5e491c90ed3cb1d'


def _ns(stamp):
    assert stamp['ticks'] >= 0 and stamp['tick_cycles'] >= 0 and stamp['cycles_per_tick'] > 0
    return 1000000 * (stamp['ticks'] + Fraction(stamp['tick_cycles'], stamp['cycles_per_tick']))


def _timing_predictions(timing, geometry, horizontal, *, pulse):
    assert timing['model'] == 'dosbox-vga-chain4-row-timing-v1'
    assert timing['palette_index'] == 1 and timing['physical_phase'] == 1
    h = timing['line_period_ns']
    h_ticks = Fraction(h * PIT_HZ, 1000000000)
    assert horizontal.lo <= h_ticks <= horizontal.hi
    frame = timing['frame_scheduled_ns']
    first = timing['first_callback_scheduled_ns']
    vstart = geometry['vsync_start']
    assert abs((first - frame) * 4 - h) <= 6
    assert abs(timing['retrace_scheduled_ns'] - frame - vstart * h) <= (vstart + 2) / 2
    assert timing['initial_rgb6'] == list(PALETTES['A'])
    commits = timing['dac_commits']
    assert [entry['rgb6'] for entry in commits] == (
        [list(PALETTES[name]) for name in ('B', 'C')] if pulse else [])
    change = [_ns(entry['actual']) for entry in commits]
    assert not pulse or frame < change[0] < change[1] < timing['retrace_scheduled_ns']
    rows = timing['rows']
    assert [entry['physical_line'] for entry in rows] == list(range(1, 400, 2))
    actual = [_ns(entry['actual']) for entry in rows]
    latency = []
    for entry, sampled in zip(rows, actual, strict=True):
        physical = entry['physical_line']
        scheduled = entry['scheduled_ns']
        assert abs(scheduled - first - physical * h) <= Fraction(physical + 2, 2)
        latency.append(sampled - scheduled)
    assert min(latency) >= -Fraction(1, 2) and max(latency) < Fraction(h, 8)

    def color(lower, upper):
        # Producer DAC events and scheduler timestamps are independent of RGB.
        # The endpoints conservatively account for rounded scheduler time and
        # allowed lateness. An intersecting candidate row stays unknown.
        if not pulse or upper < change[0]:
            return 'A'
        if change[0] < lower and upper < change[1]:
            return 'B'
        if change[1] < lower:
            return 'C'
        return None

    measured = [color(instant, instant) for instant in actual]
    assert all(measured)
    predictions = {}
    for phase in (0, 1):
        colors = []
        for row in range(HEIGHT):
            line = 2 * row + phase
            scheduled = first + line * h
            rounding = Fraction(line + 2, 2)
            colors.append(color(scheduled - rounding, scheduled + rounding + Fraction(h, 8)))
        predictions[str(phase)] = colors
    return {'measured': measured, 'phase_predictions': predictions,
            'maximum_actual_lateness_ns': [max(latency).numerator, max(latency).denominator]}


def test_native_dosbox_chain4_callback_phase_precedes_rgb_read(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_CHAIN4_TIMING') != '1':
        pytest.skip('Select the exact DOSBox-X diagnostic producer')
    executable = Path(os.environ['FDISBULL_DOSBOX_CHAIN4_TIMING']).resolve(strict=True)
    executable_sha = os.environ['FDISBULL_DOSBOX_CHAIN4_TIMING_SHA256']
    assert digest(executable) == executable_sha
    assert not any((directory / '.git').exists() for directory in
                   (tmp_path.resolve(), *tmp_path.resolve().parents))
    code, offsets = paired_video_program(tmp_path, os.environ['NASM'])
    assert hashlib.sha256(code).hexdigest() == COM_SHA256
    wrapper = tmp_path / 'timing-dosbox'
    arguments = [part for setting in PROFILE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
        "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
        f'os.execv({str(executable)!r}, [{str(executable)!r}, *sys.argv[1:], *{arguments!r}])\n')
    wrapper.chmod(0o700)
    work = tmp_path / 'dosbox'
    work.mkdir()
    evidence = {'producer_sha256': executable_sha, 'fixture_sha256': COM_SHA256, 'frames': []}
    try:
        with _owner('dosbox', work, code, offsets, {'wrapper': wrapper}, evidence) as adapter:
            geometry, horizontal, parameters = _calibration(adapter, evidence)
            # Same previously declared pulse translation as the paired run.
            base_delay = parameters['delay_ticks'] - 1
            base_width = parameters['width_ticks'] + 3
            evidence['declared_pulses'] = [[base_delay, base_width], [base_delay, base_width - 4]]
            request = {'points': [], 'source_timing_palette_index': 1}
            arm = adapter.call('video.probe', request)
            assert arm['source_timing_available'] is False
            for number in range(1, 5):
                pulse = number > 2
                if pulse:
                    delay, width = evidence['declared_pulses'][number - 3]
                    adapter.write('delay_ticks', struct.pack('<H', delay))
                    adapter.write('width_ticks', struct.pack('<H', width))
                adapter.write('pulse_mode', bytes([pulse]))
                adapter.write('command', b'\x01')
                adapter.park('trial_ready')
                ready = parse_trial(adapter.read(offsets['trial'], TRIAL_BYTES))
                assert (ready['number'], ready['mode']) == (number, pulse)
                advance = adapter.advance(adapter.before_frame())
                raw_trial = adapter.read(offsets['trial'], TRIAL_BYTES)
                assert parse_trial(raw_trial)['post_generation'] == 0
                identity = {name: advance[name] for name in ('frame_id', 'mode_id')}
                probe = adapter.call('video.probe', dict(request, **identity))
                assert {name: probe[name] for name in identity} == identity
                assert probe['samples'] == [] and 'frame_source' not in probe
                assert probe['source_timing_available'] is True, probe
                timing = probe['source_timing']
                record = {'trial': number, 'identity': identity, 'source_timing': timing}
                evidence['frames'].append(record)
                predictions = _timing_predictions(timing, geometry, horizontal, pulse=pulse)
                record.update(predictions=predictions, prediction_preceded_rgb_read=True)
                _write_json(work / f'frame-{number}-timing-before-image.json', record)

                rgb, _ = adapter.capture(number, advance)
                record['rgb_sha256'] = hashlib.sha256(rgb).hexdigest()
                record['rgb_matches_actual_callback_colors'] = rgb == rgb_for_rows(predictions['measured'])
                assert record['rgb_matches_actual_callback_colors']
                if pulse:
                    colors = predictions['phase_predictions']
                    record['counterphase_unknown_rows'] = [row for row, color in enumerate(colors['0']) if color is None]
                    record['expected_phase_unknown_rows'] = [row for row, color in enumerate(colors['1']) if color is None]
                    record['strict_both_phase_predictions'] = (
                        all(colors['0']) and all(colors['1']) and colors['0'] != colors['1']
                        and rgb == rgb_for_rows(colors['1']) and rgb != rgb_for_rows(colors['0']))
                    assert rgb != rgb_for_rows(['C'] * HEIGHT)
                adapter.park('trial_done')
                post = parse_trial(adapter.read(offsets['trial'], TRIAL_BYTES))
                assert post['post_generation'] == ready['ready_generation'] + 1
                record['guest_post_vsync'] = post
            evidence['strict_both_pulses'] = all(frame['strict_both_phase_predictions'] for frame in evidence['frames'][2:])
    finally:
        evidence['producer_unchanged'] = digest(executable) == executable_sha
        _write_json(tmp_path / 'chain4-timing-receipt.json', evidence)
    assert evidence['producer_unchanged'] and evidence['reaped'] and evidence['returncode'] == 0
