"""Explicit raw hardware readings for the source-bound SNES RNG consumer.

Recordings contain only bytes read at the distinct NMI-counter/PPU read sites.
The source seed and the resulting random value are always computed by UIL.
A seeded source is a reproducible local-play policy, not a recovered SNES clock.
"""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_hardware.c'
INPUT_CAPACITY = 128
MODES = {'disabled': 0, 'recorded': 1, 'seeded': 2}
CALLERS = {'ambient': 1, 'bounded': 2, 'native-63': 3}
_RECORD_FIELDS = ('caller', 'context', 'nmi_low', 'nmi_high', 'beam_h', 'beam_v')
_ARRAYS = ('hardware_callers', 'hardware_contexts', 'hardware_nmi_lows',
           'hardware_nmi_highs', 'hardware_beam_hs', 'hardware_beam_vs')


def configuration(mode='disabled', seed=1):
    """Choose the hardware policy before the title-seeded runtime starts."""
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError('hardware mode must be disabled, recorded or seeded')
    if type(seed) is not int or not 1 <= seed <= 0xffffffff:
        raise ValueError('hardware seed must be a nonzero 32-bit integer')
    return {'hardware_mode': MODES[mode], 'hardware_prng_state': seed}


def input_batch(records, *, ordinal):
    """Encode one finite, ordered input transaction without game-state outputs.

    Supply a fresh batch before every recorded-mode public update, including an
    empty batch. A wrong caller, task, ordinal, missing or unused row causes the
    containing native update to roll back. Never include result/seed metadata in
    these consumable records; retain it separately as comparison evidence.
    """
    if type(ordinal) is not int or not 0 <= ordinal <= 0xffffffff:
        raise ValueError('hardware ordinal must be a 32-bit integer')
    if not isinstance(records, (list, tuple)) or len(records) > INPUT_CAPACITY:
        raise ValueError('hardware batch must contain at most 128 records')
    if ordinal + len(records) > 0xffffffff:
        raise ValueError('hardware batch would overflow the source-call ordinal')
    columns = [[] for _ in _ARRAYS]
    for record in records:
        if not isinstance(record, dict) or set(record) != set(_RECORD_FIELDS):
            raise ValueError('hardware records require only caller/context and four raw bytes')
        values = [record[name] for name in _RECORD_FIELDS]
        if any(type(value) is not int for value in values):
            raise ValueError('hardware record fields must be integers')
        caller, context, *readings = values
        if caller not in (1, 2, 3) or not 0 <= context <= 0xffff:
            raise ValueError('invalid hardware caller or context')
        if ((caller in (1, 2) and context != 0xffff) or
                (caller == 3 and (context >= 96 or context & 1))):
            raise ValueError('hardware context must identify the source caller')
        if any(not 0 <= value <= 255 for value in readings):
            raise ValueError('hardware readings must be bytes')
        for column, value in zip(columns, values):
            column.append(value)
    return {'hardware_input_count': len(records), 'hardware_input_index': 0,
            'hardware_input_ordinal': ordinal} | {
                name: column + [0] * (INPUT_CAPACITY - len(column))
                for name, column in zip(_ARRAYS, columns)}
