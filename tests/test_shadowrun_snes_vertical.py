from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_vertical import SOURCE


PRELUDE = '''
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 task_shared[65536],scene_7f[65536];
u16 scene_read(u16 a) {return (u16)task_shared[a]|((u16)task_shared[a+1U]<<8);}
void scene_write(u16 a,u16 v) {task_shared[a]=(u8)v;task_shared[a+1U]=(u8)(v>>8);}
'''


def word(buffer, address, value):
    buffer[address:address + 2] = [value & 255, (value >> 8) & 255]


def machine():
    m = GameMachine(author_program(PRELUDE + SOURCE.read_text()), {})
    shared, bank = [0] * 65536, [0] * 65536
    for i in range(0, 512, 2):
        word(shared, 0xde88 + i, 0xffff)
        word(shared, 0xe088 + i, 0xffff)
    actor = 0x56
    for base, value in ((0x421c, 0xfffe), (0x4274, 2), (0x42cc, 0xfffe),
                        (0x4324, 2), (0x437c, 10)):
        word(shared, base + actor, value)
    word(shared, 0x0cde, actor)
    m.set_state({'task_shared': shared, 'scene_7f': bank, 'vertical_actor': actor,
                 'vertical_x': 400, 'vertical_y': 400, 'vertical_z': 400,
                 'vertical_geometry_known': 1, 'vertical_flags_known': 1})
    return m


def add_record(m, dynamic, owner):
    s = m.snapshot()
    shared, bank = s['task_shared'], s['scene_7f']
    cell = ((98 & 0x3c0) >> 5) | ((102 & 0x3c0) >> 1)
    word(shared, (0xe088 if dynamic else 0xde88) + cell, 0)
    word(shared, 0xef18, 12)
    word(shared, 0xf778, 0xffff)
    for i, value in enumerate((98, 98, 90, 102, 102, 105)):
        word(shared, 0xe288 + 12 + i * 2, value)
    word(bank, 0xe214 + (12 >> 2), owner)
    m.set_state({'task_shared': shared, 'scene_7f': bank})


def test_empty_grid_and_solid_floor_have_source_carry_semantics():
    m = machine()
    m.call('shadowrun_snes_vertical_collision', 0)
    assert (m.snapshot()['vertical_supported'], m.snapshot()['vertical_blocked']) == (1, 0)
    add_record(m, False, 0)
    m.call('shadowrun_snes_vertical_collision', 0)
    s = m.snapshot()
    assert (s['vertical_supported'], s['vertical_blocked'], s['vertical_hit']) == (1, 1, 5)
    assert s['task_shared'][0x68:0x6a] == [12, 0]


def test_source_static_special_owner_needs_qualified_flag_bits():
    m = machine()
    add_record(m, False, 1)
    m.set_state({'vertical_flags_known': 0})
    before = m.snapshot()['task_shared']
    m.call('shadowrun_snes_vertical_collision', 0)
    assert m.snapshot()['vertical_supported'] == 0 and m.snapshot()['task_shared'] == before
    m.set_state({'vertical_flags_known': 1, 'vertical_flags': 3})
    m.call('shadowrun_snes_vertical_collision', 0)
    assert (m.snapshot()['vertical_blocked'], m.snapshot()['vertical_hit']) == (1, 64)


def test_dynamic_self_is_ignored_but_another_actor_blocks():
    m = machine()
    add_record(m, True, 0x56)
    m.call('shadowrun_snes_vertical_collision', 0)
    assert (m.snapshot()['vertical_supported'], m.snapshot()['vertical_blocked']) == (1, 0)
    add_record(m, True, 0x44)
    m.call('shadowrun_snes_vertical_collision', 0)
    assert (m.snapshot()['vertical_blocked'], m.snapshot()['vertical_hit']) == (1, 5)


def test_invalid_node_and_misaligned_record_refuse_before_shared_writes():
    m = machine()
    shared = m.snapshot()['task_shared']
    cell = ((98 & 0x3c0) >> 5) | ((102 & 0x3c0) >> 1)
    word(shared, 0xde88 + cell, 0x860)
    m.set_state({'task_shared': shared})
    m.call('shadowrun_snes_vertical_collision', 0)
    assert m.snapshot()['vertical_supported'] == 0 and m.snapshot()['task_shared'] == shared
    word(shared, 0xde88 + cell, 0)
    word(shared, 0xef18, 4)
    m.set_state({'task_shared': shared})
    m.call('shadowrun_snes_vertical_collision', 0)
    assert m.snapshot()['vertical_supported'] == 0 and m.snapshot()['task_shared'] == shared
