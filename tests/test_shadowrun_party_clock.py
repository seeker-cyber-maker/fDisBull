"""Normal party clock retains source signed-word arithmetic and refusal."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_party_clock import ANIMATION, SOURCE


def clock_machine():
    rom = bytearray(0x10000)
    rom[0x62b8:0x62bc] = (0x200).to_bytes(4, 'big')
    rom[0x200:0x204] = (0x300).to_bytes(4, 'big')
    rom[0x300:0x302] = (4).to_bytes(2, 'big')
    m = GameMachine(author_program(ANIMATION.read_text() + '\n' + SOURCE.read_text()), {0: bytes(rom)})
    m.set_state({'shadowrun_party_kind': 3, 'shadowrun_party_callback': 0xb45c,
                 'shadowrun_anim_threshold': 4096, 'shadowrun_anim_increment': 0xfff0,
                 'shadowrun_anim_accumulator': 0, 'shadowrun_anim_index': 0,
                 'shadowrun_party_speed': 16})
    return m


def test_negative_increment_uses_signed_source_comparison():
    m = clock_machine()
    m.call('shadowrun_party_clock_tick'); s = m.snapshot()
    assert s['shadowrun_party_clock_supported'] == 1
    assert (s['shadowrun_anim_accumulator'], s['shadowrun_anim_index'],
            s['shadowrun_anim_increment']) == (0xfff0, 0, 448)


def test_unknown_callback_refuses_before_advancing_clock():
    m = clock_machine(); m.set_state({'shadowrun_party_callback': 0xb07e})
    before = m.snapshot(); m.call('shadowrun_party_clock_tick'); after = m.snapshot()
    assert after['shadowrun_party_clock_supported'] == 0
    for k in ('shadowrun_anim_accumulator', 'shadowrun_anim_increment', 'shadowrun_anim_index'):
        assert after[k] == before[k]
