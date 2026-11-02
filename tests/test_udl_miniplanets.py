"""Authored logical vectors; original level bytes remain external."""
import hashlib
import os
from pathlib import Path

import pytest

from fdisbull.interaction_il import execute_il, validate_il
from fdisbull.udl_miniplanets import ROM_SHA256, _program, _tables, lift_level


def authored_model():
    world = [0] * 256
    world[1] = world[17] = 1
    world[2], world[3] = 3, 4
    collision = [0] * 35
    collision[1], collision[3] = 1, 2
    joy = [255] * 16
    for raw, angle in ((8, 0), (9, 1), (1, 2), (4, 4), (2, 6)):
        joy[raw] = angle
    # Authored diagonal value differs from the original game's constant.
    distance = [256, 180, 0, -180, -256, -180, 0, 180, 256, 180]
    return _program(_tables(world, collision, joy, distance), 0, 96)


def step(program, **changes):
    state = {name: spec['initial'] for name, spec in program['variables'].items()}
    state.update({'$jump': 0})
    state.update({'$'+name: value for name, value in changes.items()})
    result = execute_il(program, state)
    assert result['complete'], result
    return result['state']


def test_source_identity_is_required():
    for rom in (b'', bytes(0x80000), 'not bytes'):
        with pytest.raises(ValueError, match='ROM identity'):
            lift_level(rom)


def test_authored_table_profile_and_cardinal_movement():
    program = authored_model()
    assert validate_il(program)
    assert len(program['variables']) <= 32
    assert all(t['type'] == 'u8' and len(t['values']) == 256 for t in program['tables'].values())
    right = step(program, buttons=1)
    left = step(program, buttons=2)
    assert (right['$x'], right['$y'], right['$angle'], right['$action']) == (1, 0, 0, 1)
    assert (left['$x'], left['$y']) == (255, 0)


def test_wall_stop_and_corrected_horizontal_position_for_vertical_slide():
    program = authored_model()
    blocked = step(program, x=15, buttons=1)
    assert blocked['$x'] == 15 and blocked['$blocked_x'] == 1
    # Diagonal NE hits wall at (16,16), then slides north at corrected X=15.
    slid = step(program, x=15, y=16, phase=1, buttons=5)
    assert (slid['$x'], slid['$y']) == (15, 15)
    assert (slid['$blocked_x'], slid['$blocked_y']) == (1, 0)


@pytest.mark.parametrize('phase,expected', [(0, (100, 99)), (1, (101, 99)), (3, (101, 100))])
def test_diagonal_subpixel_classes_with_bit_reversed_phase(phase, expected):
    state = step(authored_model(), x=100, y=100, phase=phase, buttons=5)
    assert (state['$x'], state['$y']) == expected


def test_grounded_water_death_and_jump_landing_boundary():
    program = authored_model()
    dead = step(program, x=31, buttons=1)
    assert (dead['$x'], dead['$dead'], dead['$action'], dead['$angle']) == (32, 1, 6, 255)
    airborne = step(program, x=31, jump=2, buttons=1)
    assert (airborne['$x'], airborne['$jump'], airborne['$dead'], airborne['$action']) == (32, 1, 0, 2)
    landed = execute_il(program, airborne)['state']
    assert landed['$jump'] == 0 and landed['$dead'] == 1


def test_new_button_jump_holding_and_first_frame_key_collision():
    program = authored_model()
    jumped = step(program, buttons=16)
    assert jumped['$jump'] == 48 and jumped['$action'] == 0
    held = execute_il(program, jumped)['state']
    assert held['$jump'] == 47 and held['$action'] == 2
    grabbed = step(program, y=96, buttons=16)
    assert (grabbed['$jump'], grabbed['$keys'], grabbed['$key_active']) == (48, 0, 0)
    too_high = step(program, y=96, jump=20)
    assert (too_high['$keys'], too_high['$key_active']) == (1, 1)


def test_wrapped_key_radius_goal_gate_and_authored_terminal_reset():
    program = authored_model()
    grabbed = step(program, x=255, y=96)
    assert (grabbed['$keys'], grabbed['$key_active']) == (0, 0)
    assert step(program, x=48)['$win'] == 0
    won = step(program, x=48, keys=0, key_active=0)
    assert won['$win'] == 1
    won['$buttons'] = 1
    frozen = execute_il(program, won)['state']
    assert frozen['$x'] == 48 and frozen['$phase'] == won['$phase']
    frozen['$buttons'] = 64
    reset = execute_il(program, frozen)['state']
    assert (reset['$x'], reset['$y'], reset['$jump'], reset['$keys'], reset['$win']) == (0, 0, 16, 1, 0)


def test_optional_actual_rom_source_regions():
    path = os.environ.get('FDISBULL_MINIPLANETS_ROM')
    if not path:
        pytest.skip('set FDISBULL_MINIPLANETS_ROM to the external official ROM')
    rom = Path(path).read_bytes()
    assert hashlib.sha256(rom).hexdigest() == ROM_SHA256
    recovered = lift_level(rom)
    assert recovered['provenance']['source_sha256'] == ROM_SHA256
    for region in recovered['provenance']['regions'].values():
        start = region['offset']
        assert hashlib.sha256(rom[start:start+region['length']]).hexdigest() == region['sha256']
    with pytest.raises(ValueError, match='Stage'):
        lift_level(rom, stage=1)
