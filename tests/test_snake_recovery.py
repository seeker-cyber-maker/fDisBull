"""Authored-model contracts; original bytes are qualified in the private study."""
from examples.recovery.snake_model import (
    FRAME, INPUT, STATE, initial_words, make_program, core_state,
)
from fdisbull.udc_web_memory import execute_memory_uil, validate_memory_uil


def run(program, function, words):
    result = execute_memory_uil(program, function, words)
    assert result['status'] == 'complete'
    return result['words']


def initial(program):
    return run(program, 'reset', initial_words(bytes(2048)))


def event(program, words, *, kind=0, ascii=0, scan=0, x=0, y=0, buttons=0, clock=0):
    words = list(words)
    for key, value in dict(kind=kind, ascii=ascii, scan=scan, x=x, y=y, buttons=buttons, clock=clock).items():
        words[INPUT[key]] = value
    return run(program, 'action', words)


def test_udl_uil_retain_same_complete_nodes_and_source_context():
    udl, uil = make_program('udl'), make_program('uil')
    validate_memory_uil(udl); validate_memory_uil(uil)
    udl['role'] = 'uil'
    assert udl == uil
    for name, function in uil['functions'].items():
        ids = []
        def walk(nodes):
            for node in nodes:
                ids.append(node['id'])
                assert node['evidence'] == ['source_' + name]
                for key in ('body', 'then', 'else'):
                    if key in node: walk(node[key])
        walk(function['body'])
        assert len(ids) == len(set(ids))


def test_queued_turn_then_second_turn_and_reverse_do_not_create_shortcuts():
    p = make_program(); words = initial(p)
    words = event(p, words, kind=1, ascii=119, scan=17)
    words = event(p, words, kind=1, ascii=97, scan=30)
    assert words[STATE['pending_direction']] == 0
    words = event(p, words, kind=1, ascii=110, scan=49)
    assert core_state(words)['cells'] == [278, 308, 307]
    assert words[STATE['direction']] == 0
    words = event(p, words, kind=1, scan=80)
    assert words[STATE['pending_direction']] == 0


def test_keyboard_dispatch_matches_original_first_match_order():
    p = make_program(); words = initial(p)
    # Deliberately contradictory BIOS pair: original W branch precedes left scan.
    words = event(p, words, kind=1, ascii=119, scan=75)
    assert words[STATE['pending_direction']] == 0
    # Escape precedes a direction scan and requests quit without moving.
    words = event(p, words, kind=1, ascii=27, scan=77)
    assert words[STATE['quit_requested']] == 1
    assert words[STATE['tick_count']] == 0


def test_mouse_press_edge_and_release_are_distinct_from_poll_repetition():
    p = make_program(); words = initial(p)
    words = event(p, words, kind=2, x=280, y=154, buttons=1)
    assert core_state(words)['cells'] == [309, 308, 307]
    assert words[STATE['mouse_events']] == 1
    words = event(p, words, kind=2, x=280, y=154, buttons=1)
    assert words[STATE['tick_count']] == 1
    words = event(p, words, kind=2, x=280, y=154, buttons=0)
    words = event(p, words, kind=2, x=280, y=154, buttons=1)
    assert core_state(words)['cells'] == [310, 309, 308]
    assert words[STATE['mouse_events']] == 2


def test_clock_has_one_step_per_observation_and_handles_low_word_wrap():
    p = make_program(); words = initial(p)
    words = event(p, words, kind=1, ascii=112, clock=65534)
    assert words[STATE['paused']] == 0
    words = event(p, words, clock=1)
    assert words[STATE['tick_count']] == 0
    words = event(p, words, clock=2)
    assert words[STATE['tick_count']] == 1
    words = event(p, words, clock=1000)
    assert words[STATE['tick_count']] == 2


def test_reset_repeats_game_but_retains_driver_and_pointer_lifetime():
    p = make_program(); words = initial(p)
    words = event(p, words, kind=2, x=290, y=50, buttons=1)
    words = event(p, words, kind=1, ascii=114, clock=50)
    assert core_state(words)['cells'] == [308, 307, 306]
    assert words[STATE['mouse_present']] == 1
    assert words[STATE['mouse_buttons']] == 1
    assert words[STATE['mouse_x']] == 290
    assert words[STATE['key_events']] == 0
    assert words[STATE['mouse_events']] == 0
    assert words[STATE['last_tick']] == 50


def test_raster_owns_only_frame_diagnostics_and_decimal_scratch():
    p = make_program(); words = initial(p); before = list(words)
    words = run(p, 'render', words)
    expected = {(72, 104): 10, (64, 104): 2, (56, 104): 2,
                (104, 104): 12, (6, 22): 8, (8, 24): 0}
    for (x, y), color in expected.items(): assert words[FRAME + y * 320 + x] == color
    assert set(words[FRAME:FRAME + 64000]) <= {0, 1, 2, 8, 10, 12, 15}
    changed = {i for i, (a, b) in enumerate(zip(before, words)) if a != b}
    allowed = set(range(FRAME, FRAME + 64000)) | set(range(760, 773)) | {STATE['frame_count'], STATE['needs_render']}
    assert changed <= allowed
    assert words[STATE['frame_count']] == 1 and words[STATE['needs_render']] == 0
    assert words[1024:3072] == before[1024:3072]
    assert words[3072:4096] == before[3072:4096]
