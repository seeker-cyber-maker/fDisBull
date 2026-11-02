"""Authored range/branch tests for the reviewed Shadowrun components."""
import hashlib
from pathlib import Path

import pytest
from fdisbull.game_il import GameMachine, author_program

SOURCES = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources'


def program(names, region=None):
    units = []
    seen = set()
    for name in names:
        lines = []
        for line in (SOURCES / name).read_text().splitlines():
            if line.startswith('typedef '):
                if line in seen:
                    continue
                seen.add(line)
            lines.append(line)
        units.append('\n'.join(lines))
    regions = [] if region is None else [{'id': 0, 'length': len(region),
                                         'sha256': hashlib.sha256(region).hexdigest()}]
    return author_program('\n'.join(units), regions)


def test_four_corner_probe_keeps_all_raw_samples_and_wall_override():
    machine = GameMachine(program(['shadowrun_collision.c']))
    x, y = 100, 100
    offset = lambda px, py: ((py * 2) & 0xffc0) + (px >> 5)
    corners = [offset(x-12,y-7), offset(x+12,y-7), offset(x-12,y+7), offset(x+12,y+7)]
    data = [0] * 2816
    for location, value in zip(corners, [3, 20, 127, 240]):
        data[location] = value
    # Depending on tile boundaries corners can alias; compute expected from
    # the actual authored memory rather than assuming distinct addresses.
    values = [data[i] for i in corners]
    machine.set_state({'shadowrun_terrain_map': data, 'shadowrun_probe_x':x,
                       'shadowrun_probe_y':y, 'shadowrun_probe_flags':4})
    machine.call('shadowrun_probe_terrain')
    state = machine.snapshot()
    assert state['shadowrun_probe_corners'] == values
    assert state['shadowrun_probe_result'] == (127 if 127 in values else max(values))
    assert state['shadowrun_probe_map_offset'] == corners[max(i for i, value in enumerate(values) if value == max(values))]


def test_terrain_map_access_outside_declared_slice_fails_closed():
    machine = GameMachine(program(['shadowrun_collision.c']))
    machine.set_state({'shadowrun_probe_x':65535, 'shadowrun_probe_y':65535,
                       'shadowrun_probe_flags':4})
    with pytest.raises(ValueError, match='bounds'):
        machine.call('shadowrun_probe_terrain')


def test_normal_player_proposal_refuses_unknown_table_selection():
    rom = bytes(0xbf00)
    machine = GameMachine(program(['shadowrun_player_move.c'], rom), {0:rom})
    machine.set_state({'shadowrun_player_kind':13, 'shadowrun_player_flags':15,
                       'shadowrun_player_contact':1, 'shadowrun_player_x':123,
                       'shadowrun_player_proposed_x':987})
    machine.call('shadowrun_player_propose')
    state = machine.snapshot()
    assert state['shadowrun_player_proposal_supported'] == 0
    assert state['shadowrun_player_x'] == 123
    assert state['shadowrun_player_proposed_x'] == 987
