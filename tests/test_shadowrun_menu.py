"""Original menu input precedence, wrap, and explicit continuation boundaries."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_menu import SOURCE, MAIN_LABELS, ARCHETYPE_LABELS


def machine():
    return GameMachine(author_program(SOURCE.read_text()))


def step(m, pressed):
    m.set_state({'shadowrun_menu_pressed': pressed})
    m.call('shadowrun_menu_tick')
    return m.snapshot()


def test_main_and_archetype_cursor_wrap_and_confirm():
    assert MAIN_LABELS == ('New Game', 'Load Game')
    assert ARCHETYPE_LABELS == ('Samurai', 'Decker', 'Gator Shaman')
    m = machine()
    assert step(m, 0x8000)['shadowrun_menu_phase'] == 0  # Start alone is not confirm.
    assert step(m, 0x0200)['shadowrun_menu_cursor'] == 1
    assert step(m, 0x0200)['shadowrun_menu_cursor'] == 0
    assert step(m, 0x4000)['shadowrun_menu_phase'] == 1
    s = step(m, 0x0100); assert (s['shadowrun_menu_cursor'], s['shadowrun_menu_preview']) == (2, 2)
    assert step(m, 0x0200)['shadowrun_menu_cursor'] == 0
    s = step(m, 0x4000); assert (s['shadowrun_menu_phase'], s['shadowrun_menu_archetype']) == (2, 0)
    s = step(m, 0); assert not s['shadowrun_menu_supported'] and s['shadowrun_menu_phase'] == 2


def test_input_priority_and_load_boundary():
    m = machine(); s = step(m, 0x0300)
    assert s['shadowrun_menu_cursor'] == 1  # Up is tested before Down.
    s = step(m, 0x1000); assert s['shadowrun_menu_phase'] == 3
    assert not step(m, 0)['shadowrun_menu_supported']


def test_inconsistent_archetype_preview_refuses_before_transition():
    m = machine()
    m.set_state({'shadowrun_menu_phase': 1, 'shadowrun_menu_cursor': 2,
                 'shadowrun_menu_preview': 0, 'shadowrun_menu_pressed': 0x4000})
    m.call('shadowrun_menu_tick'); s = m.snapshot()
    assert not s['shadowrun_menu_supported']
    assert (s['shadowrun_menu_phase'], s['shadowrun_menu_cursor'], s['shadowrun_menu_preview']) == (1, 2, 0)
