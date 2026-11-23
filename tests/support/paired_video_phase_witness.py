"""Bounded alternative-phase rejection using only timing-qualified rows.

The historical paired gate still requires complete predictions for both phases.
This diagnostic can exclude an alternative with one independently determined
contradiction. It assigns no color to a row that overlaps a whole DAC write.
"""
from fractions import Fraction

from .paired_video_frame_oracle import HEIGHT, WIDTH, predict_rows, rgb_for_rows, trial_intervals


def _separated_rows(horizontal, vertical_start, windows, phase):
    vertical = windows['post_vsync']
    write_b, write_c = windows['write_b'], windows['write_c']
    for row in range(HEIGHT):
        offset = Fraction(2 * row + phase - vertical_start) + Fraction(1, 4)
        products = (offset * horizontal.lo, offset * horizontal.hi)
        lower = vertical.lo + min(products)
        upper = vertical.hi + max(products) + horizontal.hi / 8
        if upper < write_b.lo:
            yield 'A'
        elif write_b.hi < lower and upper < write_c.lo:
            yield 'B'
        elif write_c.hi < lower:
            yield 'C'
        else:
            yield None


def phase_witness(horizontal, vertical_start, trial, observed_rgb, *, expected_phase):
    """Require a complete expected-phase prediction, then compare exact RGB."""
    if type(observed_rgb) is not bytes or len(observed_rgb) != WIDTH * HEIGHT * 3:
        raise ValueError('Expected an exact RGB888 image for the authored raster')
    windows = trial_intervals(trial)
    expected = predict_rows(horizontal, vertical_start, windows, expected_phase)
    alternative = list(_separated_rows(horizontal, vertical_start, windows, 1 - expected_phase))
    # Unknown rows are excluded from every alternative comparison. Using a
    # full palette vector here retains the fixture's edge sentinel colors.
    alternative_rgb = rgb_for_rows([color or 'A' for color in alternative])
    stride = 3 * WIDTH
    rejected_rows = []
    for row, color in enumerate(alternative):
        window = slice(row * stride, (row + 1) * stride)
        if color is not None and observed_rgb[window] != alternative_rgb[window]:
            rejected_rows.append(row)
    return {
        'expected_phase': expected_phase,
        'full_rgb_matches_expected_phase': observed_rgb == expected['rgb'],
        'counterphase_unknown_rows': [row for row, color in enumerate(alternative) if color is None],
        'counterphase_rejected_rows': rejected_rows,
        'final_palette_only_rejected': observed_rgb != rgb_for_rows(['C'] * HEIGHT),
    }
