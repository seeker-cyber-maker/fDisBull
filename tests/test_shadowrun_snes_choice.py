from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_choice import SOURCE as CHOICE
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT


def machine(mask, held=0):
    m = GameMachine(author_program(SCRIPT.read_text() + '\n' + CHOICE.read_text()), {})
    shared = [0] * 65536
    shared[0x1e8:0x1ea] = [held & 255, held >> 8]
    m.set_state({'task_shared': shared, 'choice_mask': mask})
    m.call('shadowrun_snes_choice_begin', 0)
    return m


def word(s, addr):
    return s['task_shared'][addr] | s['task_shared'][addr + 1] << 8


def poll(m, held):
    m.set_state({'choice_input': held})
    m.call('shadowrun_snes_choice_poll', 0)
    return m.snapshot()


def test_order_and_source_labels():
    s = machine(0x0480).snapshot()
    assert s['choice_status'] == 1
    assert s['choice_count'] == 3
    assert [word(s, 0x1fb4 + i * 2) for i in range(3)] == [0, 0x80, 0x400]
    assert [word(s, 0x1f86 + i * 2) for i in range(4)] == [0x70c8, 0x7117, 0x712f, 0]
    assert [word(s, 0x1f9e + i * 2) for i in range(3)] == [0, 0x20, 0x10]


def test_opening_button_is_not_a_new_edge_and_final_poll_is_separate():
    m = machine(0x480, held=0x8000)
    assert poll(m, 0x8000)['choice_status'] == 1
    assert poll(m, 0)['choice_status'] == 1
    assert word(poll(m, 0x400), 0x1db3) == 2
    poll(m, 0)
    s = poll(m, 0x8000)
    assert (s['choice_status'], s['choice_event'], word(s, 0x1ea)) == (2, 0x80, 0x8000)
    m.set_state({'choice_input': 0})
    m.call('shadowrun_snes_choice_finish', 0)
    s = m.snapshot()
    assert (s['choice_status'], word(s, 0x1ea), word(s, 0x1e6)) == (3, 0, 0)


def test_repeat_boundary_and_cancel_precedes_confirm():
    m = machine(0x480)
    assert word(poll(m, 0x400), 0x1db3) == 2
    for _ in range(18):
        assert word(poll(m, 0x400), 0x1db3) == 2
    assert word(poll(m, 0x400), 0x1db3) == 4
    poll(m, 0)
    assert poll(m, 0xa000)['choice_status'] == 2
    m.call('shadowrun_snes_choice_finish', 0)
    assert m.snapshot()['choice_status'] == 4


def test_refuses_unmodeled_scroll_and_reset_chord():
    assert machine(0x67f2).snapshot()['choice_status'] == 0
    m = machine(0x480)
    before = m.snapshot()['task_shared']
    assert poll(m, 0x3030)['choice_status'] == 0
    assert m.snapshot()['task_shared'] == before


def test_hotkey_and_combined_option():
    m = machine(0x680)
    s = m.snapshot()
    assert [word(s, 0x1fb4 + i * 2) for i in range(3)] == [0, 0x80, 0x600]
    s = poll(m, 0x20)
    assert (s['choice_status'], s['choice_event'], word(s, 0x1db3)) == (2, 0x80, 2)


def test_no_action_does_not_terminate_option_table_or_clear_override():
    m = GameMachine(author_program(SCRIPT.read_text() + '\n' + CHOICE.read_text()), {})
    shared = [0] * 65536
    shared[0x1f88:0x1f8a] = [0x34, 0x12]
    m.set_state({'task_shared': shared, 'choice_mask': 0})
    m.call('shadowrun_snes_choice_begin', 0)
    s = m.snapshot()
    assert s['choice_status'] == 5
    assert word(s, 0x1f88) == 0x1234
