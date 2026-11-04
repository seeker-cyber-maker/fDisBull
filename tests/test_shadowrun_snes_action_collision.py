import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_action_collision import SOURCE


PRELUDE = '''
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 task_shared[65536],scene_7f[65536];
u16 scene_read(u16 a) { return (u16)task_shared[a]|((u16)task_shared[a+1U]<<8); }
void scene_write(u16 a,u16 v) { task_shared[a]=(u8)v;task_shared[a+1U]=(u8)(v>>8); }
'''


def machine():
    rom = bytearray(0x70000)
    rom[0x66d8a + 0x18 * 2:0x66d8c + 0x18 * 2] = bytes([0xe6, 0x93])
    rom[0x613e6:0x613e8] = bytes([0xf6, 0x93])
    rom[0x613f9:0x613fe] = bytes([0xf2, 0, 0, 2, 32])
    rom = bytes(rom)
    program = author_program(PRELUDE + SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                            'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    shared, bank = [0] * 65536, [0] * 65536

    def word(buf, at, value):
        buf[at:at + 2] = [value & 255, value >> 8]

    for base, value in ((0x3f04, 0x18), (0x0e44, 463 * 4), (0x0e9c, 479 * 4),
                        (0x0ef4, 64 * 4), (0x1474, 0x304)):
        word(shared, base + 0x4e, value)
    word(shared, 0x0cde, 0x42)
    word(shared, 0xe088 + 0xee, 0xf4)
    word(shared, 0xef18 + 0xf4, 0xab0)
    word(shared, 0xf778 + 0xf4, 0xee)
    word(shared, 0xef18 + 0xee, 0xa98)
    word(shared, 0xf778 + 0xee, 0xffff)
    for record, values in ((0xab0, [449, 465, 64, 465, 481, 96]),
                           (0xa98, [456, 473, 64, 462, 479, 88])):
        for i, value in enumerate(values):
            word(shared, 0xe288 + record + i * 2, value)
    word(bank, 0xe214 + (0xab0 >> 2), 0x4e)
    word(bank, 0xe214 + (0xa98 >> 2), 0x42)
    m.set_state({'task_shared': shared, 'scene_7f': bank, 'action_collision_actor': 0x4e,
                 'action_collision_action': 0, 'action_collision_flags_known': 1})
    return m


def test_other_actor_blocks_prospective_action_and_source_scratch_matches():
    m = machine()
    m.call('shadowrun_snes_action_collision', 0)
    s = m.snapshot()
    assert (s['action_collision_supported'], s['action_collision_result']) == (1, 0xffff)
    assert s['task_shared'][0x3b:0x3d] == [24, 0]
    assert s['task_shared'][:2] == [255, 255]


def test_qualified_low_flag_bits_can_exclude_player():
    m = machine()
    s = m.snapshot()['task_shared']
    s[0x1474 + 0x4e] |= 3
    m.set_state({'task_shared': s})
    m.call('shadowrun_snes_action_collision', 0)
    assert (m.snapshot()['action_collision_supported'], m.snapshot()['action_collision_result']) == (1, 0)


def test_unknown_low_flag_bits_refuse_without_shared_writes():
    m = machine()
    m.set_state({'action_collision_flags_known': 0})
    before = m.snapshot()['task_shared']
    m.call('shadowrun_snes_action_collision', 0)
    s = m.snapshot()
    assert s['action_collision_supported'] == 0 and s['task_shared'] == before
