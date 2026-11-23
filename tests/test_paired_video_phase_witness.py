from fractions import Fraction

import pytest

from support.paired_video_frame_oracle import HEIGHT, Interval, TimingUnqualified, rgb_for_rows
from support.paired_video_phase_witness import phase_witness


HORIZONTAL = Interval(Fraction(2236, 59), Fraction(13391, 353))
VERTICAL_START = 412
# PIT counts from the authored translated-pulse fixture.
PHASE_ONE_RGB = rgb_for_rows(['A'] * 100 + ['B'] + ['C'] * 99)
PULSE_THREE = dict(mode=1, ready_status=8, post_status=8, ready_generation=6, post_generation=7,
    ready_lo=40000, ready_hi=39991, b_before=30974, b_after=30968, c_before=30932,
    c_after=30926, post_lo=22965, post_hi=22955)
PULSE_FOUR = dict(mode=1, ready_status=8, post_status=8, ready_generation=8, post_generation=9,
    ready_lo=5925, ready_hi=5915, b_before=62434, b_after=62428, c_before=62392,
    c_after=62386, post_lo=54430, post_hi=54420)


def test_unknown_alternative_row_cannot_exclude_other_phase():
    observed = phase_witness(HORIZONTAL, VERTICAL_START, PULSE_THREE, PHASE_ONE_RGB, expected_phase=1)
    assert observed == dict(expected_phase=1, full_rgb_matches_expected_phase=True,
        counterphase_unknown_rows=[100], counterphase_rejected_rows=[], final_palette_only_rejected=True)


def test_independent_row_rejects_alternative_despite_other_unknown_row():
    observed = phase_witness(HORIZONTAL, VERTICAL_START, PULSE_FOUR, PHASE_ONE_RGB, expected_phase=1)
    assert observed == dict(expected_phase=1, full_rgb_matches_expected_phase=True,
        counterphase_unknown_rows=[101], counterphase_rejected_rows=[100], final_palette_only_rejected=True)


def test_expected_phase_still_requires_complete_timing_prediction():
    with pytest.raises(TimingUnqualified, match='Row 100 phase 0'):
        phase_witness(HORIZONTAL, VERTICAL_START, PULSE_THREE, PHASE_ONE_RGB, expected_phase=0)


def test_incompatible_image_does_not_qualify_expected_phase():
    result = phase_witness(HORIZONTAL, VERTICAL_START, PULSE_THREE,
                           rgb_for_rows(['C'] * HEIGHT), expected_phase=1)
    assert result['full_rgb_matches_expected_phase'] is False
    assert result['final_palette_only_rejected'] is False
