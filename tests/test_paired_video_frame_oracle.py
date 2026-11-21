"""Hand-calculated counterexamples for the independent paired phase oracle.

These tests do not launch an emulator or assemble the fixture. They are authored
for a later separately admitted source test run; authoring is not execution.
"""
from fractions import Fraction
import json
import struct

import pytest

from support.paired_video_frame_oracle import (
    HEIGHT, Interval, TimingUnqualified, horizontal_interval, phase_predictions,
    parse_calibration, predict_rows, pulse_parameters, rgb_for_rows, unwrap_counts,
    vga_geometry,
)


def test_pit_mode2_unwrap_keeps_the_65536_transition_and_refuses_half_wrap():
    assert unwrap_counts([2, 0, 65535, 65530]) == [0, 2, 3, 8]
    with pytest.raises(TimingUnqualified, match='uniquely unwrapped'):
        unwrap_counts([60000, 10000])


def test_guest_mode13_register_bits_give_physical_lines_not_source_frame_ids():
    raw = bytes([0x63, 0x01, 0x5f, 0xbf, 0x1f, 0x41,
                 0x9c, 0x8e, 0x8f, 0x96, 0xb9, 0xa3])
    geometry = vga_geometry(raw)
    assert (geometry['vertical_total'], geometry['vsync_start'], geometry['display_lines']) == (449, 412, 400)
    bad = bytearray(raw)
    bad[5] = 0x40
    with pytest.raises(TimingUnqualified, match='400-line'):
        vga_geometry(bytes(bad))


def test_horizontal_oracle_counts_missed_edges_without_equating_them_to_lines():
    positions = list(range(0, 401, 2))  # Every OTHER physical line was observed.
    records = [{'generation': 0, 'edge': Interval(20 + line * 40 - 1, 20 + line * 40 + 1)}
               for line in positions]
    interval, receipt = horizontal_interval(records, Interval(39, 41))
    assert interval.lo <= 40 <= interval.hi
    assert interval.hi - interval.lo <= Fraction(1, 50)
    assert receipt['admitted_segments'][0]['line_positions'] == positions
    assert receipt['admitted_segments'][0]['physical_lines'] == 400
    assert receipt['vertical_period_division_used'] is False


def test_complete_counts_above_eight_keep_the_128_line_gate():
    positions = list(range(0, 133, 11))
    records = [{'generation': 0, 'edge': Interval(line * 40 - 1, line * 40 + 1)}
               for line in positions]
    with pytest.raises(TimingUnqualified, match='at least 128 lines'):
        horizontal_interval(records[:-1], Interval(39, 41))  # Only 121 lines.
    interval, receipt = horizontal_interval(records, Interval(39, 41))
    assert interval == Interval(40 - Fraction(1, 66), 40 + Fraction(1, 66))
    assert receipt['admitted_segments'] == [{
        'records': 13, 'physical_lines': 132, 'long_pair_constraints': 1,
        'line_positions': positions,
    }]
    assert receipt['excluded_gaps'] == []


def test_unique_fractional_count_has_no_arbitrary_upper_cutoff():
    records = [{'generation': 0, 'edge': Interval(time, time)}
               for time in (Fraction(0), Fraction(257, 3))]
    interval, receipt = horizontal_interval(records, Interval(Fraction(1, 3), Fraction(1, 3)))
    assert interval == Interval(Fraction(1, 3), Fraction(1, 3))
    assert receipt['admitted_segments'][0]['line_positions'] == [0, 257]


def test_eight_only_cutoff_cannot_hide_nine_line_ambiguity_in_a_long_span():
    # Adjacent deltas are [8.2, 8.6], compatible with both 8 and 9 lines.
    # Keeping only 8 previously formed a 128-line fit at the coarse upper edge.
    records = [{'generation': 0,
                'edge': Interval(index * Fraction(42, 5) - Fraction(1, 10),
                                 index * Fraction(42, 5) + Fraction(1, 10))}
               for index in range(17)]
    with pytest.raises(TimingUnqualified, match='uniquely counted'):
        horizontal_interval(records, Interval(Fraction(19, 20), Fraction(21, 20)))


@pytest.mark.parametrize(('coarse', 'delta', 'expected'), [
    ((Fraction(19, 20), Fraction(21, 20)), (Fraction(83, 10), Fraction(87, 10)),
     {'min': 8, 'max': 9}),
    ((Fraction(19, 20), Fraction(21, 20)), (Fraction(21, 2), Fraction(21, 2)),
     {'min': 10, 'max': 11}),
    ((Fraction(19, 20), Fraction(21, 20)), (Fraction(209, 20), Fraction(209, 20)),
     {'min': 10, 'max': 11}),
    ((Fraction(1, 3), Fraction(1, 3)), (Fraction(3), Fraction(10, 3)),
     {'min': 9, 'max': 10}),
    ((Fraction(1, 3), Fraction(1, 3)),
     (3 + Fraction(1, 10**30), Fraction(10, 3) - Fraction(1, 10**30)),
     {'min': 10, 'max': 9}),
    ((Fraction(1, 3), Fraction(1, 3)), (Fraction(-1, 3), Fraction(0)),
     {'min': 1, 'max': 0}),
    ((Fraction(1, 3), Fraction(1, 3)), (Fraction(-1, 3), Fraction(1)),
     {'min': 1, 'max': 3}),
])
def test_excluded_gap_bounds_preserve_closed_fractional_and_empty_ranges(coarse, delta, expected):
    # An independently exact 128-line prefix makes the excluded gap observable
    # in a successful receipt; that gap must not contribute to the fit.
    period = sum(coarse) / 2
    records = [{'generation': 0, 'edge': Interval(line * period, line * period)}
               for line in range(129)]
    records.append({'generation': 0,
                    'edge': Interval(128 * period + delta[0], 128 * period + delta[1])})
    interval, receipt = horizontal_interval(records, Interval(*coarse))
    assert interval == Interval(period, period)
    assert receipt['line_count_rule'] == 'complete-positive-integer-bounds-1'
    gap, = receipt['excluded_gaps']
    assert gap['after_record'] == 128
    assert gap['possible_line_count_bounds'] == expected
    assert gap['vertical_generation_changed'] is False
    assert gap['delta'] == Interval(*delta).json()


def test_half_wrap_safe_large_ambiguity_uses_bounded_receipt_fields():
    counters = [(60000 - line * 40, 60000 - line * 40, 0) for line in range(129)]
    for _ in range(2):
        previous_upper = counters[-1][1]
        counters.append(((previous_upper - 32767) & 0xffff,
                         (previous_upper - 65534) & 0xffff, 0))
    records = parse_calibration(b''.join(struct.pack('<HHH', *row) for row in counters),
                                len(counters))
    _, receipt = horizontal_interval(records, Interval(39, 41))
    assert len(receipt['excluded_gaps']) == 2
    gap = receipt['excluded_gaps'][-1]
    assert gap['delta'] == Interval(32765, 98303).json()
    assert gap['possible_line_count_bounds'] == {'min': 800, 'max': 2520}
    assert 'possible_line_counts' not in gap
    assert len(json.dumps(gap, sort_keys=True).encode('utf-8')) < 300


def test_complete_counts_still_intersect_every_long_pair():
    # Every adjacent gap uniquely counts 11 lines, but the two 132-line spans
    # constrain H near 40 and 41 respectively. Neither span may be discarded.
    times = [line * 40 for line in range(0, 133, 11)]
    times.extend(132 * 40 + line * 41 for line in range(11, 133, 11))
    records = [{'generation': 0, 'edge': Interval(time - 1, time + 1)} for time in times]
    with pytest.raises(TimingUnqualified, match='Empty device-time interval'):
        horizontal_interval(records, Interval(39, 41))


def test_ambiguous_edge_count_is_not_turned_into_an_expected_phase():
    records = [{'generation': 0, 'edge': Interval(line * 40, line * 40 + 1)} for line in range(200)]
    with pytest.raises(TimingUnqualified, match='uniquely counted'):
        horizontal_interval(records, Interval(20, 80))


def test_vertical_origin_jump_breaks_the_fit_instead_of_changing_horizontal_time():
    records = []
    for generation, offset in ((0, 0), (1, 9050)):
        records.extend({'generation': generation,
                        'edge': Interval(offset + line * 40 - 1, offset + line * 40 + 1)}
                       for line in range(201))
    interval, receipt = horizontal_interval(records, Interval(39, 41))
    assert interval.lo <= 40 <= interval.hi
    assert len(receipt['admitted_segments']) == 2
    gap, = receipt['excluded_gaps']
    assert gap['vertical_generation_changed'] is True
    assert gap['possible_line_count_bounds'] is None


def _manual_windows():
    # V=20000 ticks, H=40, Vstart=412. Source row100 is at11530
    # for phase0 and11570 for phase1. The B pulse is11550..11590.
    return {'ready': Interval(0, 2), 'write_b': Interval(11549, 11551),
            'write_c': Interval(11589, 11591), 'post_vsync': Interval(20000, 20000)}


def test_hand_computed_one_line_pulse_distinguishes_both_source_phases():
    phase0 = predict_rows(Interval(40, 40), 412, _manual_windows(), 0)
    phase1 = predict_rows(Interval(40, 40), 412, _manual_windows(), 1)
    assert phase0['colors'] == ['A'] * 101 + ['C'] * 99
    assert phase1['colors'] == ['A'] * 100 + ['B'] + ['C'] * 99
    offset = (100 * 320 + 10) * 3
    assert phase0['rgb'][offset:offset + 3] == bytes([4, 85, 170])
    assert phase1['rgb'][offset:offset + 3] == bytes([170, 85, 4])
    assert len(phase0['rgb']) == len(phase1['rgb']) == 192000
    assert phase0['rgb'] != phase1['rgb']
    assert all(value['rgb'] != rgb_for_rows(['C'] * HEIGHT) for value in (phase0, phase1))


def test_write_uncertainty_crossing_a_row_refuses_the_phase_prediction():
    windows = _manual_windows()
    windows['write_b'] = Interval(11529, 11532)
    with pytest.raises(TimingUnqualified, match='Row 100 phase 0'):
        predict_rows(Interval(40, 40), 412, windows, 0)


def test_expected_quiet_rgb_uses_legacy_nonendpoint_dac_and_all_four_sentinels():
    rgb = rgb_for_rows(['A'] * HEIGHT)
    assert rgb[3:6] == bytes([4, 85, 170])
    for (x, y), expected in (((0, 0), (255, 0, 0)), ((319, 0), (0, 255, 0)),
                              ((0, 199), (0, 0, 255)), ((319, 199), (255, 255, 255))):
        offset = (y * 320 + x) * 3
        assert rgb[offset:offset + 3] == bytes(expected)
    assert rgb != rgb_for_rows(['A'] * HEIGHT, wrong_qemu_dac=True)


def test_pulse_schedule_is_fixed_from_device_time_before_images_exist():
    params = pulse_parameters({'vertical_total': 449, 'vsync_start': 412}, Interval(40, 40))
    assert (params['delay_ticks'], params['width_ticks']) == (9510, 40)
    assert params['image_feedback'] is False


def test_full_raw_trial_keeps_next_vsync_and_both_quantized_write_windows():
    trial = {'number': 3, 'mode': 1, 'ready_lo': 60000, 'ready_hi': 59998,
             'b_before': 48451, 'b_after': 48449, 'c_before': 48411, 'c_after': 48409,
             'post_lo': 40001, 'post_hi': 39999, 'ready_status': 9, 'post_status': 9,
             'ready_generation': 5, 'post_generation': 6}
    predictions, windows = phase_predictions(Interval(40, 40), {'vsync_start': 412}, trial)
    assert predictions[0]['colors'][100] == 'A' and predictions[1]['colors'][100] == 'B'
    assert windows['write_b']['lo'] == [11548, 1] and windows['write_b']['hi'] == [11552, 1]
    trial['post_generation'] = 7
    with pytest.raises(TimingUnqualified, match='same raster'):
        phase_predictions(Interval(40, 40), {'vsync_start': 412}, trial)
