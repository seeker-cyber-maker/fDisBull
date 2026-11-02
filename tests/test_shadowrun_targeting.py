from pathlib import Path

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_targeting import SOURCE


def machine():
    return GameMachine(author_program(SOURCE.read_text()))


def captured(m):
    m.set_state({'shadowrun_camera_x': 1064 * 16, 'shadowrun_camera_y': 688 * 16,
        'shadowrun_target_x': [12620, 21248, 25216, 0, 0, 0, 0],
        'shadowrun_target_y': [8664, 13330, 5590, 0, 0, 0, 0],
        'shadowrun_target_index': [3, 4, 5, 0, 0, 0, 0],
        'shadowrun_target_flags': [0x25, 0x25, 0x25, 0, 0, 0, 0]})


def test_screen_admission_and_source_cycle_for_prepared_actor_geometry():
    m = machine(); captured(m)
    m.call('shadowrun_target_refresh'); before = m.snapshot()
    assert before['shadowrun_target_supported'] == 1
    assert before['shadowrun_target_contact'] == [0, 273, 0, 0, 0, 0, 0]
    m.call('shadowrun_target_cycle'); s = m.snapshot()
    assert s['shadowrun_target_selected'] == 1
    assert s['shadowrun_target_flags_low'][1] == 16
    assert s['shadowrun_target_marker'][1] == 0x8009
    assert s['shadowrun_target_backlink'][1] == 1


def test_cycle_preserves_source_guards_and_wrapping():
    m = machine(); captured(m)
    m.set_state({'shadowrun_target_contact': [111, 112, 113, 0, 0, 0, 0],
                 'shadowrun_target_flags_b0': [128, 0, 0, 0, 0, 0, 0]})
    m.call('shadowrun_target_cycle'); assert m.snapshot()['shadowrun_target_selected'] == 1
    m.call('shadowrun_target_cycle'); s = m.snapshot()
    assert s['shadowrun_target_selected'] == 2 and s['shadowrun_target_flags_low'][1] == 0
    m.call('shadowrun_target_cycle'); assert m.snapshot()['shadowrun_target_selected'] == 1


def test_unsupported_branches_refuse_without_changing_target():
    m = machine(); captured(m)
    m.set_state({'shadowrun_target_equipped_slot': 255, 'shadowrun_target_item': 4})
    m.call('shadowrun_target_cycle'); s = m.snapshot()
    assert s['shadowrun_target_supported'] == 0 and s['shadowrun_target_selected'] == 255
    m.set_state({'shadowrun_target_special_callback': [1, 0, 0, 0, 0, 0, 0]})
    m.call('shadowrun_target_refresh'); s = m.snapshot()
    assert s['shadowrun_target_supported'] == 0 and s['shadowrun_target_contact'] == [0]*7
