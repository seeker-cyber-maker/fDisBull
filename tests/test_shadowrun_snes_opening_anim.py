"""Sprite allocator determines whether animation sort metadata is installed."""
import hashlib
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_opening_anim import source_fragment

PREFIX = '''typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 rom8(u8 region,u32 offset); u8 task_shared[65536],scene_7f[65536];
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 value) {task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
'''


def make_machine():
    rom = bytearray(1048576)
    at = (27 << 15) + 0x100
    rom[at - 1] = 5
    rom[at] = 1
    rom[at + 8] = 1
    data = bytes(rom)
    region = {'id': 0, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    m = GameMachine(author_program(PREFIX + source_fragment(), [region]), {0: data})
    m.call('opening_animation_metadata_reset')
    return m


def word(data, at):
    return data[at] | data[at + 1] << 8


def test_sprite_allocation_metadata_and_release():
    m = make_machine()
    m.call('opening_animation_metadata', 0x4c, 0x0100)
    s = m.snapshot()
    assert (s['opening_anim_supported'], s['opening_anim_deferred']) == (1, 0)
    data = s['task_shared']
    assert (word(data, 0xd38), word(data, 0xd3a)) == (63, 4)
    assert (word(data, 0x1308), word(data, 0x1360)) == (1, 2)
    assert (word(data, 0xff0), word(data, 0x1048)) == (0x8001, 20)
    m.call('opening_animation_metadata_cleanup', 0x4c)
    s = m.snapshot()
    assert s['opening_anim_supported'] == 1
    assert (word(s['task_shared'], 0xd38), word(s['task_shared'], 0xd3a)) == (64, 2)
    assert word(s['task_shared'], 0x1308) == 0


def test_over_budget_defers_without_changing_allocator():
    m = make_machine()
    before = m.snapshot()
    data = before['task_shared'][:]
    data[0x82:0x84] = [0x4e, 0]
    m.set_state({'task_shared': data})
    m.call('opening_animation_metadata', 0x4c, 0x0100)
    s = m.snapshot()
    assert (s['opening_anim_supported'], s['opening_anim_deferred']) == (1, 1)
    assert word(s['task_shared'], 0x115c + 0x4c) == 0x0100
    assert s['task_shared'][0xd38:0xd3c] == data[0xd38:0xd3c]
    assert s['task_shared'][0xff0:0xff2] == data[0xff0:0xff2]
