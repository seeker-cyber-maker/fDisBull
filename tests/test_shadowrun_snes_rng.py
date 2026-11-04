import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_rng import SOURCE


def machine():
    rom = bytearray(0x465d)
    rom[0x455d:0x465d] = bytes(range(256))
    rom = bytes(rom)
    return GameMachine(author_program(SOURCE.read_text(),
                       [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}]), {0: rom})


def test_transform_uses_latched_bytes_and_counter_without_hidden_state():
    m = machine()
    m.set_state({'rng_seed': 5, 'rng_nmi_low': 0x34, 'rng_nmi_high': 0x12, 'rng_beam_h': 0x56, 'rng_beam_v': 0x78})
    m.call('shadowrun_snes_rng_transform', 0)
    s = m.snapshot()
    assert (s['rng_supported'], s['rng_result'], s['rng_next_seed']) == (1, 0x7531, 0x0d)
    assert (s['rng_seed'], s['rng_nmi_low'], s['rng_nmi_high'], s['rng_beam_h'], s['rng_beam_v']) == (5, 0x34, 0x12, 0x56, 0x78)


def test_transform_increments_a_repeated_seed_with_byte_wrap():
    m = machine()
    m.set_state({'rng_seed': 0, 'rng_nmi_low': 0, 'rng_nmi_high': 0, 'rng_beam_h': 0, 'rng_beam_v': 0})
    m.call('shadowrun_snes_rng_transform', 0)
    assert (m.snapshot()['rng_result'], m.snapshot()['rng_next_seed']) == (0, 1)
    m.set_state({'rng_seed': 255})
    m.call('shadowrun_snes_rng_transform', 0)
    assert (m.snapshot()['rng_result'], m.snapshot()['rng_next_seed']) == (0xffff, 0)


def test_counter_bytes_can_come_from_opposite_sides_of_nmi_carry():
    m = machine()
    m.set_state({'rng_seed': 0, 'rng_nmi_low': 0xff, 'rng_nmi_high': 1,
                 'rng_beam_h': 0, 'rng_beam_v': 0})
    m.call('shadowrun_snes_rng_transform', 0)
    assert (m.snapshot()['rng_result'], m.snapshot()['rng_next_seed']) == (0xfeff, 0xfe)
