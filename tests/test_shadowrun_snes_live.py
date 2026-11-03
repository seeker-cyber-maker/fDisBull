from pathlib import Path

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_live import SOURCE


def test_rebuild_inserts_rectangles_in_source_order_and_refuses_invalid_slot():
    m = GameMachine(author_program(Path(SOURCE).read_text()), {})
    z = [0] * 44
    x = z.copy(); y = z.copy(); height = z.copy(); flags = z.copy()
    left = z.copy(); right = z.copy(); top = z.copy(); bottom = z.copy()
    # Two actors share one cell. The source walks the list backwards and
    # prepends each record, so the first listed actor ends at the head.
    x[1], y[1], height[1], flags[1] = 40, 80, 8, 0x100
    x[2], y[2], height[2], flags[2] = 44, 84, 10, 0x100
    m.set_state({'live_order': [2, 4] + [0] * 42, 'live_order_count': 2,
                 'live_first_node': 0, 'live_x': x, 'live_y': y,
                 'live_height': height, 'live_flags': flags,
                 'live_left': left, 'live_right': right,
                 'live_top': top, 'live_bottom': bottom})
    m.call('shadowrun_snes_rebuild')
    s = m.snapshot()
    assert s['live_status'] == 1
    assert s['live_records'][:12] == [11, 21, 0, 11, 21, 10, 10, 20, 0, 10, 20, 8]
    assert s['live_heads'][0] == 2
    assert s['live_node_record'][:2] == [0xa74, 0xa80]
    assert s['live_node_next'][:2] == [0xffff, 0]
    assert s['live_owners'][0xa74 >> 2] == 4
    assert s['live_owners'][0xa80 >> 2] == 2

    m.set_state({'live_order': [3, 4] + [0] * 42})
    before = m.snapshot()
    m.call('shadowrun_snes_rebuild')
    after = m.snapshot()
    assert after['live_status'] == 0
    for name in ('live_heads', 'live_records', 'live_node_record', 'live_node_next', 'live_owners'):
        assert after[name] == before[name]


def test_sort_adjusts_depth_preserves_ties_and_refuses_unknown_jump():
    m = GameMachine(author_program(Path(SOURCE).read_text()), {})
    depth = [0] * 44; mode = [0] * 44; delta = [0] * 44
    x = [0] * 44; y = [0] * 44
    depth[1], depth[2] = 100, 90
    mode[2], delta[2] = 0x8001, 20
    y[1], y[2] = 10, 20
    m.set_state({'live_order': [2, 4] + [0] * 42, 'live_order_count': 2,
                 'live_depth': depth, 'live_sort_mode': mode,
                 'live_sort_delta': delta, 'live_x': x, 'live_y': y})
    m.call('shadowrun_snes_sort')
    assert m.snapshot()['live_order'][:2] == [4, 2]
    # A comparison with equal depth must retain its existing order.
    mode[2] = 0; depth[2] = 100
    m.set_state({'live_order': [2, 4] + [0] * 42,
                 'live_sort_mode': mode, 'live_depth': depth})
    m.call('shadowrun_snes_sort')
    assert m.snapshot()['live_order'][:2] == [2, 4]
    mode[2] = 0x8005
    m.set_state({'live_sort_mode': mode})
    before = m.snapshot()['live_order']
    m.call('shadowrun_snes_sort')
    assert m.snapshot()['live_sort_supported'] == 0
    assert m.snapshot()['live_order'] == before
