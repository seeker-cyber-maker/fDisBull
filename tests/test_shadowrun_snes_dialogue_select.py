from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_dialogue_select import SOURCE


PRELUDE = '''
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 task_shared[65536];
u16 scene_read(u16 a) {return (u16)task_shared[a]|((u16)task_shared[a+1U]<<8);}
void scene_write(u16 a,u16 v) {task_shared[a]=(u8)v;task_shared[a+1U]=(u8)(v>>8);}
'''


def machine(count=3, rows=3, previous=0):
    m = GameMachine(author_program(PRELUDE + SOURCE.read_text()), {})
    shared = [0] * 65536
    shared[0x1e8:0x1ea] = [previous & 255, previous >> 8]
    m.set_state({'task_shared': shared, 'dialogue_select_count': count,
                 'dialogue_select_rows': rows, 'dialogue_select_column': 2,
                 'dialogue_select_row': 4})
    m.call('shadowrun_snes_dialogue_select_begin', 0)
    return m


def poll(m, held):
    m.set_state({'dialogue_select_input': held})
    m.call('shadowrun_snes_dialogue_select_poll', 0)
    return m.snapshot()


def test_primary_selector_ignores_opening_button_until_repressed():
    m = machine(previous=0x8000)
    assert poll(m, 0x8000)['dialogue_select_status'] == 1
    poll(m, 0)
    s = poll(m, 0x400)
    assert s['dialogue_select_moved'] == 1 and s['task_shared'][0x1db3] == 2
    poll(m, 0)
    s = poll(m, 0x8000)
    assert (s['dialogue_select_status'], s['dialogue_select_index']) == (2, 1)
    m.set_state({'dialogue_select_input': 0})
    m.call('shadowrun_snes_dialogue_select_finish', 0)
    s = m.snapshot()
    assert s['dialogue_select_status'] == 3 and s['task_shared'][0x1ea] == 0


def test_cancel_precedes_confirmation_and_final_poll_uses_new_input():
    m = machine()
    s = poll(m, 0xa000)
    assert (s['dialogue_select_status'], s['dialogue_select_index']) == (2, 0xffff)
    m.set_state({'dialogue_select_input': 0})
    m.call('shadowrun_snes_dialogue_select_finish', 0)
    s = m.snapshot()
    assert s['dialogue_select_status'] == 4 and s['task_shared'][0x1e6:0x1ec] == [0] * 6


def test_selector_refuses_scroll_and_unmodeled_page_keys():
    assert machine(10, 9).snapshot()['dialogue_select_status'] == 0
    m = machine()
    before = m.snapshot()['task_shared']
    assert poll(m, 0x10)['dialogue_select_status'] == 0
    assert m.snapshot()['task_shared'] == before
