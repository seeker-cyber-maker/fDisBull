"""Independent device-journal oracle for a finite paired mode-13h experiment.

This module accepts guest PIT/VGA observations, never frame receipts or pixels.
The candidate image is compared only after both phase predictions are frozen.
All time arithmetic is exact rational PIT ticks; host time is only a deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import ceil, floor
import struct


WIDTH, HEIGHT = 320, 200
PIT_HZ = 1_193_182
MAX_CALIBRATION_EDGES = 512
MAX_RETRACES = 12
RAW_FIELDS = ('misc', 'seq1', 'cr00', 'cr06', 'cr07', 'cr09', 'cr10',
              'cr11', 'cr12', 'cr15', 'cr16', 'cr17')
PALETTES = {'A': (1, 21, 42), 'B': (42, 21, 1), 'C': (21, 42, 1)}
SENTINELS = {(0, 0): (255, 0, 0), (319, 0): (0, 255, 0),
             (0, 199): (0, 0, 255), (319, 199): (255, 255, 255)}
SOURCE_PHASE = {'qemu': 0, 'dosbox': 1}


class TimingUnqualified(ValueError):
    """The independent journal cannot distinguish the frozen phase models."""


@dataclass(frozen=True)
class Interval:
    lo: Fraction
    hi: Fraction

    def __post_init__(self):
        object.__setattr__(self, 'lo', Fraction(self.lo))
        object.__setattr__(self, 'hi', Fraction(self.hi))
        if self.lo > self.hi:
            raise TimingUnqualified('Empty device-time interval')

    def json(self):
        return {'lo': [self.lo.numerator, self.lo.denominator],
                'hi': [self.hi.numerator, self.hi.denominator], 'unit': 'PIT ticks'}


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid authored ' + name)


def unwrap_counts(values):
    """Unwrap a descending channel-2 count with an explicit half-wrap rule."""
    result = []
    previous = None
    elapsed = 0
    for value in values:
        _integer(value, 0, 65535, 'PIT count')
        if previous is not None:
            difference = (previous - value) & 0xffff
            if difference >= 32768:
                raise TimingUnqualified('PIT journal gap is not uniquely unwrapped')
            elapsed += difference
        result.append(elapsed)
        previous = value
    return result


def vga_geometry(raw):
    if not isinstance(raw, bytes) or len(raw) != len(RAW_FIELDS):
        raise ValueError('Expected the exact guest-read VGA register journal')
    registers = dict(zip(RAW_FIELDS, raw, strict=True))
    overflow = registers['cr07']
    vertical = registers['cr06'] | ((overflow & 1) << 8) | ((overflow & 32) << 4)
    display = registers['cr12'] | ((overflow & 2) << 7) | ((overflow & 64) << 3)
    sync = registers['cr10'] | ((overflow & 4) << 6) | ((overflow & 128) << 2)
    blank = registers['cr15'] | ((overflow & 8) << 5) | ((registers['cr09'] & 32) << 4)
    vertical += 2
    display += 1
    if (display != 400 or registers['cr09'] & 31 != 1 or
            not 400 <= blank < vertical or not 400 < sync < vertical or
            registers['seq1'] & 8 or registers['cr09'] & 128):
        raise TimingUnqualified('Guest mode does not have the admitted 400-line mode-13 timing')
    # This deliberately coarse VGA clock band only disambiguates missed-edge
    # integer counts. Measured edge intervals, not this nominal value or a
    # candidate frame period, establish the final H bounds.
    dot_hz = (25_175_000, 28_322_000, 25_175_000, 25_175_000)[(registers['misc'] >> 2) & 3]
    dots = 8 if registers['seq1'] & 1 else 9
    nominal = Fraction((registers['cr00'] + 5) * dots * PIT_HZ, dot_hz)
    coarse = Interval(nominal * Fraction(95, 100), nominal * Fraction(105, 100))
    return {'raw': registers, 'vertical_total': vertical, 'vsync_start': sync,
            'display_lines': display, 'horizontal_coarse': coarse}


def parse_calibration(data, count):
    """Records are (lower count, upper count, vertical-edge generation)."""
    _integer(count, 0, MAX_CALIBRATION_EDGES, 'calibration edge count')
    if not isinstance(data, bytes) or len(data) != count * 6:
        raise ValueError('Calibration journal has the wrong length')
    raw = list(struct.iter_unpack('<HHH', data))
    counts = unwrap_counts([counter for lo, hi, _ in raw for counter in (lo, hi)])
    records = []
    for index, (lo, hi, generation) in enumerate(raw):
        _integer(generation, 0, MAX_RETRACES, 'vertical generation')
        # The two latch values bracket the status transition. One tick on each
        # side also covers counter quantization; no sub-tick precision is made up.
        interval = Interval(counts[index * 2] - 1, counts[index * 2 + 1] + 1)
        records.append({'raw': (lo, hi), 'generation': generation, 'edge': interval})
    return records


def horizontal_interval(records, coarse):
    """Fit H only across uniquely counted same-polarity horizontal edges.

    Vertical gaps and ambiguous physical-line counts terminate a segment and
    remain in the receipt. They are never silently counted as one scanline.
    At least one independently counted span of 128 physical lines is required.
    Long-span constraints retain correlation, avoiding period/Vtotal estimates.
    """
    if not isinstance(coarse, Interval) or coarse.lo <= 0:
        raise ValueError('Expected a positive coarse horizontal interval')
    lower, upper = coarse.lo, coarse.hi
    segments, gaps, current = [], [], []
    for record in records:
        if not current:
            current = [(0, record)]
            continue
        position, previous = current[-1]
        left, right = previous['edge'], record['edge']
        delta = Interval(right.lo - left.hi, right.hi - left.lo)
        generation_changed = previous['generation'] != record['generation']
        bounds = None
        if not generation_changed:
            # Closed overlap with n * coarse is equivalent to these bounds.
            # Keep every positive integer candidate without enumerating them.
            bounds = {'min': max(1, ceil(delta.lo / coarse.hi)),
                      'max': floor(delta.hi / coarse.lo)}
        if bounds is None or bounds['min'] != bounds['max']:
            gaps.append({'after_record': sum(len(segment) for segment in segments) + len(current) - 1,
                         'possible_line_count_bounds': bounds, 'delta': delta.json(),
                         'vertical_generation_changed': generation_changed})
            segments.append(current)
            current = [(0, record)]
        else:
            current.append((position + bounds['min'], record))
    if current:
        segments.append(current)
    admitted = []
    for segment in segments:
        if len(segment) < 2 or segment[-1][0] < 128:
            continue
        # Every long pair, not an image-selected pair or best-looking edge.
        constraints = 0
        for index, (line_a, first) in enumerate(segment):
            for line_b, last in segment[index + 1:]:
                lines = line_b - line_a
                if lines < 128:
                    continue
                lo = (last['edge'].lo - first['edge'].hi) / lines
                hi = (last['edge'].hi - first['edge'].lo) / lines
                lower, upper = max(lower, lo), min(upper, hi)
                constraints += 1
        admitted.append({'records': len(segment), 'physical_lines': segment[-1][0],
                         'long_pair_constraints': constraints,
                         'line_positions': [line for line, _ in segment]})
    if not admitted:
        raise TimingUnqualified('No uniquely counted horizontal span of at least 128 lines')
    interval = Interval(lower, upper)
    return interval, {'horizontal': interval.json(), 'coarse': coarse.json(),
                      'line_count_rule': 'complete-positive-integer-bounds-1',
                      'admitted_segments': admitted, 'excluded_gaps': gaps,
                      'vertical_period_division_used': False}


def pulse_parameters(geometry, horizontal):
    """One predeclared schedule, chosen before any pulse image is available."""
    midpoint = (horizontal.lo + horizontal.hi) / 2
    target_lines = geometry['vertical_total'] - geometry['vsync_start'] + Fraction(803, 4)
    delay = int(target_lines * midpoint)
    width = int(midpoint)
    _integer(delay, 1, 30000, 'pulse delay')
    _integer(width, 1, 1000, 'pulse width')
    if delay + width >= 32768:
        raise TimingUnqualified('Authored pulse crosses the unwrapping bound')
    return {'delay_ticks': delay, 'width_ticks': width,
            'rule': 'previous-vsync upper latch + (Vtotal-VsyncStart+200.75)*midpoint(H); width=floor(midpoint(H))',
            'image_feedback': False}


def parse_trial(data):
    """Fixed 28-byte control journal, captured at ready and after post-vsync."""
    if not isinstance(data, bytes) or len(data) != 28:
        raise ValueError('Expected the exact authored trial journal')
    names = ('number', 'mode', 'ready_lo', 'ready_hi', 'b_before', 'b_after',
             'c_before', 'c_after', 'post_lo', 'post_hi', 'ready_status',
             'post_status', 'ready_generation', 'post_generation')
    result = dict(zip(names, struct.unpack('<14H', data), strict=True))
    _integer(result['number'], 1, 4, 'trial number')
    _integer(result['mode'], 0, 1, 'trial mode')
    for name in ('ready_generation', 'post_generation'):
        _integer(result[name], 0, MAX_RETRACES, name)
    return result


def trial_intervals(trial):
    if trial['mode'] != 1 or not trial['ready_status'] & 8 or not trial['post_status'] & 8:
        raise TimingUnqualified('Pulse lacks its surrounding vertical-sync witnesses')
    if trial['post_generation'] != trial['ready_generation'] + 1:
        raise TimingUnqualified('Pulse does not end at the same raster next vertical sync')
    names = ('ready_lo', 'ready_hi', 'b_before', 'b_after', 'c_before', 'c_after', 'post_lo', 'post_hi')
    times = unwrap_counts([trial[name] for name in names])
    pairs = [Interval(times[index] - 1, times[index + 1] + 1) for index in (0, 2, 4, 6)]
    if not pairs[0].hi < pairs[1].lo < pairs[1].hi < pairs[2].lo < pairs[2].hi < pairs[3].lo:
        raise TimingUnqualified('Pulse write and vertical-sync intervals are not separated')
    return dict(zip(('ready', 'write_b', 'write_c', 'post_vsync'), pairs, strict=True))


def rgb_for_rows(colors, *, wrong_qemu_dac=False):
    if len(colors) != HEIGHT or any(color not in PALETTES for color in colors):
        raise ValueError('Expected one declared palette name per source row')
    expand = ((lambda value: (value << 2) | ((value & 1) * 3)) if wrong_qemu_dac else
              (lambda value: (value << 2) | (value >> 4)))
    palette = {name: bytes(expand(value) for value in channels) for name, channels in PALETTES.items()}
    pixels = bytearray(b''.join(palette[color] * WIDTH for color in colors))
    for (x, y), rgb in SENTINELS.items():
        offset = (y * WIDTH + x) * 3
        pixels[offset:offset + 3] = bytes(rgb)
    return bytes(pixels)


def predict_rows(horizontal, vertical_start, windows, phase):
    """Freeze one complete prediction, or refuse any overlapping uncertainty.

    Rows use the same-frame post-display vsync: V+(2*r+phase+.25-Vstart)*H.
    Keeping that relation intact avoids adding origin/H uncertainty twice.
    The declared phase witness allows only H/8 callback lateness. This is a
    stricter experimental gate than the unchanged native v1's H admission.
    """
    _integer(phase, 0, 1, 'source phase')
    vsync, first, second = (windows[name] for name in ('post_vsync', 'write_b', 'write_c'))
    colors, ranges = [], []
    for row in range(HEIGHT):
        multiplier = Fraction(2 * row + phase - vertical_start) + Fraction(1, 4)
        products = (multiplier * horizontal.lo, multiplier * horizontal.hi)
        lower = vsync.lo + min(products)
        upper = vsync.hi + max(products) + horizontal.hi / 8
        sampled = Interval(lower, upper)
        if sampled.hi < first.lo:
            color = 'A'
        elif first.hi < sampled.lo and sampled.hi < second.lo:
            color = 'B'
        elif second.hi < sampled.lo:
            color = 'C'
        else:
            raise TimingUnqualified(f'Row {row} phase {phase} intersects a DAC write uncertainty window')
        colors.append(color)
        ranges.append(sampled.json())
    return {'phase': phase, 'colors': colors, 'row_intervals': ranges,
            'rgb': rgb_for_rows(colors), 'lateness_allowance': 'H/8',
            'image_or_native_frame_time_input': False}


def phase_predictions(horizontal, geometry, trial):
    windows = trial_intervals(trial)
    predictions = {phase: predict_rows(horizontal, geometry['vsync_start'], windows, phase)
                   for phase in (0, 1)}
    if predictions[0]['rgb'] == predictions[1]['rgb']:
        raise TimingUnqualified('The authored pulse does not distinguish both phase predictions')
    return predictions, {name: interval.json() for name, interval in windows.items()}
