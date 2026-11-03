"""Source title-controller boundaries; physical input and rendering are separate."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_menu import SOURCE


def machine():
    return GameMachine(author_program(SOURCE.read_text()), {})


def apply(m, keys):
    m.set_state({'menu_pressed': keys})
    m.call('shadowrun_snes_menu_control', 0)
    return m.snapshot()


def test_title_wraps_and_select_uses_down_branch():
    m = machine()
    assert [apply(m, 0x400)['menu_selection'] for _ in range(3)] == [1, 2, 0]
    assert apply(m, 0x800)['menu_selection'] == 2
    assert apply(m, 0x2000)['menu_selection'] == 0
    assert apply(m, 0x80)['menu_confirmed'] == 0


def test_confirm_precedes_direction_and_requires_explicit_continuation():
    for keys in (0x1000, 0x8000, 0x9400):
        m = machine()
        s = apply(m, keys)
        assert (s['menu_selection'], s['menu_confirmed'], s['menu_supported']) == (0, 1, 1)
        s = apply(m, 0x400)
        assert (s['menu_selection'], s['menu_confirmed'], s['menu_supported']) == (0, 1, 0)


def test_unobserved_disabled_entries_and_invalid_selection_fail_bounded():
    m = machine()
    m.set_state({'menu_disabled': [0, 1, 0]})
    assert apply(m, 0x400)['menu_selection'] == 2
    m.set_state({'menu_disabled': [1, 1, 1]})
    s = apply(m, 0x400)
    assert (s['menu_selection'], s['menu_supported']) == (2, 0)
    m.set_state({'menu_selection': 3})
    assert apply(m, 0)['menu_supported'] == 0
