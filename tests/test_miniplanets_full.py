"""Authored fixture tests for source-rule and target-flow regression boundaries.

The fixture is newly authored data, not original ROM bytes. Original precision
is checked separately by check_miniplanets_common_native.py with private inputs.
"""
from pathlib import Path

import pytest

pytest.importorskip('pycparser')
from fdisbull.game_il import GameMachine, author_program


@pytest.fixture(scope='module')
def profile():
    root = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources'
    source = '\n'.join((root / name).read_text() for name in
                       ('miniplanets_full.c', 'miniplanets_actors.c'))
    raw = bytearray(0x66000)
    for index in range(55):
        base, header = 0x60000 + index * 258, 0x655CA + index * 8
        raw[header:header + 4] = base.to_bytes(4, 'big')
        name = ((index // 9 + 1) << 4) | (index % 9 + 1) if index < 45 else (
            0x60 if index == 45 else 0x71 + index - 46)
        raw[header + 4:header + 6] = bytes((name, 1))
        raw[base + 256] = 255
    raw[0x4131A:0x4131F] = bytes((0x15, 0x30, 0x45, 0x60, 0x75))
    for index in range(5):
        raw[0x41320 + index * 4:0x41324 + index * 4] = (0x10000).to_bytes(4, 'big')
    # Newly authored password points to a synthetic stage header.
    raw[0x48FDC:0x48FE0] = bytes((0x12, 0x34, 1, 2))
    raw[0x4912C] = 255
    return author_program(source), bytes(raw)


@pytest.fixture
def game(profile):
    program, rom = profile
    return GameMachine(program, {0: rom}, environment={'hv16': [0], 'sound_busy': [0]})


def test_score_awards_one_life_per_call_and_caps_bcd(game):
    game.set_state({'score': 0, 'next_life': 0x10000, 'lives': 5, 'life_setting': 0})
    game.call('add_score', 0x35000)
    state = game.snapshot()
    assert (state['score'], state['next_life'], state['lives']) == (0x35000, 0x20000, 6)
    game.call('add_score', 0)
    assert (game.snapshot()['next_life'], game.snapshot()['lives']) == (0x30000, 7)
    game.set_state({'score': 0x999999, 'lives': 0x99, 'next_life': 0})
    game.call('add_score', 1)
    assert (game.snapshot()['score'], game.snapshot()['lives']) == (0x999999, 0x99)


def test_zero_seconds_borrow_preserves_zero_and_starts_death(game):
    game.set_state({'time_secs': 0, 'time_frames': 1, 'timer_ok': 255})
    game.call('update_level_timer')
    state = game.snapshot()
    assert (state['time_secs'], state['time_frames'], state['player_die']) == (0, 60, 1)
    assert state['player_action'] == 5


def test_pause_freezes_logic_but_render_side_shake_still_counts(game):
    game.set_state({'mode': 1, 'ingame_status': 1, 'shake_timer': 10,
                    'time_secs': 0x45, 'time_frames': 60, 'timer_ok': 255})
    game.call('game_frame')
    state = game.snapshot()
    assert (state['anim'], state['time_frames'], state['shake_timer']) == (0, 60, 9)
    game.set_state({'input_buttons': 64})
    game.call('game_frame')
    state = game.snapshot()
    assert (state['ingame_status'], state['anim'], state['time_frames'], state['shake_timer']) == (0, 1, 59, 8)
    assert state['player_action'] == 3


def test_clear_phase_retains_original_timer_store_order(game):
    game.set_state({'clear_phase': 1, 'clear_timer': 239, 'stage_bonus': 0})
    game.call('update_clear_all')
    assert (game.snapshot()['clear_phase'], game.snapshot()['clear_timer']) == (2, 240)


def test_password_dial_helper_accepts_without_target_screen_transition(game):
    game.set_state({'entered_password': 0x01020304, 'joy_press': 128, 'mode': 5})
    game.call('update_password_dial')
    state = game.snapshot()
    assert (state['password_quit'], state['stage'], state['muteki'], state['mode']) == (1, 2, 1, 5)


def test_credits_branch_unlocks_hidden_world_only_for_invict(game):
    game.set_state({'stage': 45, 'invict': 255})
    game.call('enter_credits')
    assert (game.snapshot()['stage'], game.snapshot()['mode']) == (46, 8)
    game.set_state({'stage': 45, 'invict': 0})
    game.call('enter_credits')
    assert (game.snapshot()['stage'], game.snapshot()['mode']) == (45, 7)


def test_title_boot_and_start_during_zoom_only_opens_menu(game):
    game.call('game_boot')
    assert (game.snapshot()['mode'], game.snapshot()['title_show_menu']) == (0, 0)
    game.set_state({'input_buttons': 64})
    game.call('game_frame')
    assert (game.snapshot()['mode'], game.snapshot()['title_show_menu']) == (0, 255)
    game.set_state({'input_buttons': 0})
    game.call('game_frame')
    game.set_state({'input_buttons': 64})
    game.call('game_frame')
    assert (game.snapshot()['mode'], game.snapshot()['lives'], game.snapshot()['invict']) == (8, 5, 255)


def test_full_object_pool_records_fault_without_overwriting_actor_data(game):
    pool = [1, 2, 3, 4] * 48
    game.set_state({'objects': pool, 'keys_left': 48})
    result = game.call('add_object', 27, 10, 20, 8)
    assert result['result'] == 255
    assert game.snapshot()['objects'] == pool
    assert game.snapshot()['keys_left'] == 48
    assert game.snapshot()['actor_capacity_fault'] == 1
