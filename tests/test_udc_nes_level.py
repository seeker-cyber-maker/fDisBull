"""The level adapter preserves the UIL contract and declares its display scope."""
import copy
import hashlib
from importlib.resources import files
import json

import pytest

from fdisbull.console_udc import compile_console_rom
from fdisbull.roms import inspect_rom


def fixture():
    variables = {name: {'type': 'u8', 'initial': 0} for name in
                 ('$buttons', '$x', '$y', '$jump', '$dead', '$win', '$key_active', '$index', '$value')}
    variables['$key_active']['initial'] = 1
    tiles = [0] * 256
    tiles[1], tiles[2], tiles[3] = 1, 3, 4
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {}, 'variables': variables,
               'tables': {'map': {'type': 'u8', 'values': tiles},
                          'collision': {'type': 'u8', 'values': [0,1,1,2,0] + [0] * 251},
                          'sample': {'type': 'u8', 'values': [(i * 73 + 19) & 255 for i in range(256)]}},
               'body': [{'id': 'sample', 'op': 'lookup', 'var': '$value', 'table': 'sample', 'index': {'var': '$index'}},
                        {'id': 'step', 'op': 'add', 'var': '$index', 'value': 1}]}
    scene = {'format': 'fdisbull-console-scene-1', 'width': 16, 'height': 16,
             'tile_values': tiles, 'collision_values': [0, 1, 1, 2, 0],
             'player_x': '$x', 'player_y': '$y', 'jump': '$jump', 'dead': '$dead',
             'win': '$win', 'key_active': '$key_active', 'key_x': 0, 'key_y': 96}
    return program, scene


def test_emits_structurally_valid_native_cartridge_with_published_state():
    program, scene = fixture()
    result = compile_console_rom(program, target='nes', scene=scene)
    manifest = result['manifest']
    assert inspect_rom(result['rom'])['valid']
    assert len(result['rom']) == 16 + 32768 + 8192
    assert manifest['executed'] is False
    assert manifest['profile']['published_snapshot'] is True
    assert manifest['profile']['logic_cycles_upper_bound'] <= 20000
    assert manifest['profile']['max_logic_cycles'] == 20000
    for name, binding in manifest['variables'].items():
        assert manifest['profile']['working_variables'][name]['address'] == binding['address'] + 0x100


def test_scene_map_must_match_declared_uil_data():
    program, scene = fixture()
    scene = copy.deepcopy(scene)
    scene['tile_values'][4] = 1
    with pytest.raises(ValueError, match='scene map differs'):
        compile_console_rom(program, target='nes', scene=scene)


def test_scene_collision_styles_must_match_declared_uil_data():
    program, scene = fixture()
    scene = copy.deepcopy(scene)
    scene['collision_values'][1] = 0
    with pytest.raises(ValueError, match='scene collisions differ'):
        compile_console_rom(program, target='nes', scene=scene)


@pytest.mark.parametrize('change', [
    {'width': 15}, {'tile_values': [0] * 255}, {'player_x': '$missing'},
    {'key_y': 256}, {'collision_values': [0, 3]}, {'title': 'UNSUPPORTED? FONT'},
])
def test_rejects_unsupported_or_ambiguous_scenes(change):
    program, scene = fixture()
    with pytest.raises(ValueError):
        compile_console_rom(program, target='nes', scene={**scene, **change})


@pytest.mark.parametrize('table', [{'type': 'u8', 'values': [0] * 255},
                                  {'type': 'u16', 'values': [0] * 256}])
def test_native_lookup_refuses_unqualified_table_shapes(table):
    program, scene = fixture()
    program['tables']['sample'] = table
    if table['type'] == 'u16':
        program['variables']['$value']['type'] = 'u16'
    with pytest.raises(ValueError, match='256'):
        compile_console_rom(program, target='nes', scene=scene)


def test_scene_requires_nes_and_uses_its_own_display_bindings():
    program, scene = fixture()
    with pytest.raises(ValueError, match='Genesis|genesis'):
        compile_console_rom(program, target='genesis', scene=scene)
    with pytest.raises(ValueError, match='display bindings'):
        compile_console_rom(program, target='nes', scene=scene, display_variable='$x')


def test_large_accepted_uil_is_refused_when_it_exceeds_native_frame_budget():
    program, scene = fixture()
    program['variables']['$wide'] = {'type': 'u16', 'initial': 0}
    program['body'] = [{'id': f'add{i}', 'op': 'add', 'var': '$wide', 'value': 1} for i in range(1024)]
    with pytest.raises(ValueError, match='logic cycle budget'):
        compile_console_rom(program, target='nes', scene=scene)


def test_publication_copy_is_bounded_even_for_mixed_width_state():
    program, scene = fixture()
    for index in range(55):
        program['variables'][f'$z{index:02d}'] = {'type': 'u16', 'initial': 0}
    with pytest.raises(ValueError, match='publication exceeds'):
        compile_console_rom(program, target='nes', scene=scene)


def test_shared_logic_refactor_keeps_qualified_classic_rom_bytes():
    program = json.loads(files('fdisbull').joinpath('data/console-udc-demo.json').read_text())
    result = compile_console_rom(program, target='nes', display_variable='$x')
    assert hashlib.sha256(result['rom']).hexdigest() == '69fc25c972c9206d0df535598b187a272210e1887b03f1cd13cae775f3806c61'
