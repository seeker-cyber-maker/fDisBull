"""Opening collision adapter uses mutable banks and refuses unknown actors."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_opening_collision import source_fragment

PREFIX = '''
typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 task_shared[65536],scene_7f[65536];
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 value) {task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
'''


def test_rebuild_uses_mutable_banks_and_refuses_other_dynamic_actor():
    shared, upper = bytearray(65536), bytearray(65536)
    shared[0xde88:0xe088] = b'\xff' * 512
    def word(at, value):
        shared[at:at + 2] = value.to_bytes(2, 'little')
    word(0x0cde, 0x42)
    word(0x14cc, 2)
    word(0x14ce, 0x42)
    word(0x14d0, 0x40)
    for actor in (0x42, 0x40):
        word(0x0e44 + actor, 400)
        word(0x0e9c + actor, 400)
        word(0x0ef4 + actor, 256)
        word(0x1474 + actor, 0x100)
        word(0x4274 + actor, 4)
        word(0x4324 + actor, 4)
        word(0x437c + actor, 4)
    machine = GameMachine(author_program(PREFIX + source_fragment()), {})
    machine.set_state({'task_shared': list(shared), 'scene_7f': list(upper)})
    machine.call('opening_rebuild')
    state = machine.snapshot()
    assert state['opening_rebuild_supported'] == 1
    assert state['scene_7f'][0xe214 + (0xa74 >> 2)] == 0x40
    machine.call('opening_collision_at', 0x42, 400, 400, 0)
    assert machine.snapshot()['opening_collision_supported'] == 0
    machine.call('opening_collision_at', 0x40, 400, 400, 0)
    assert machine.snapshot()['opening_collision_supported'] == 0
    before = machine.snapshot()
    malformed = before['task_shared'][:]
    malformed[0x14cc:0x14ce] = [0xff, 0xff]
    machine.set_state({'task_shared': malformed})
    machine.call('opening_rebuild')
    after = machine.snapshot()
    assert after['opening_rebuild_supported'] == 0
    assert after['task_shared'] == malformed
    assert after['scene_7f'] == before['scene_7f']
