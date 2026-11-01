import pytest

from fdisbull.shadowrun_city import project_city, SOURCE_SHA256
from fdisbull.shadowrun_z import assisted_teleport, observe_city


def state():
    return {'source_sha256': SOURCE_SHA256, 'scene_id': 2, 'revision': 'r1',
            'player_x': 320 << 4, 'player_y': 480 << 4,
            'camera_x': 100 << 4, 'camera_y': 200 << 4,
            'bounds': [0, 2048, 0, 1408], 'terrain': bytes(2816)}


class Runtime:
    def __init__(self):
        self.state = state()
        self.calls = []

    def snapshot(self):
        return self.state

    def assisted_teleport(self, **kwargs):
        self.calls.append(kwargs)
        return {'status': 'refused', 'complete': True, 'reason': 'unqualified collision'}


def test_projection_uses_runtime_state_and_preserves_unknowns():
    runtime = Runtime()
    city = observe_city(runtime, radius_x=1, radius_y=1)
    assert city['terrain_grid'] == [64, 44]
    assert city['player']['cell'] == [10, 15]
    assert len(city['local_cells']) == 9
    assert city['local_cells'][4]['id'] == 'shadowrun.scene.02.cell.10.15'
    assert city['local_cells'][4]['walkability'] == 'unknown'
    assert len(city['regions']) == 48
    assert sum(r['contains_player'] for r in city['regions']) == 1
    runtime.state['player_x'] = 352 << 4
    assert observe_city(runtime, radius_x=1, radius_y=1)['player']['cell'] == [11, 15]


def test_snapshot_validation_and_region_clipping():
    s = state(); s['bounds'] = [320, 384, 480, 512]
    city = project_city(s)
    assert [r['id'] for r in city['regions']] == ['shadowrun.scene.02.region.01.01']
    for field, bad in [('scene_id', True), ('revision', ''), ('terrain', bytes(1)),
                       ('bounds', [0, 2049, 0, 1408]), ('player_x', -1)]:
        s = state(); s[field] = bad
        with pytest.raises(ValueError): project_city(s)


def test_teleport_requires_assisted_policy_current_revision_and_same_scene():
    r = Runtime()
    common = dict(scene_id=2, x=320 << 4, y=480 << 4, revision='r1')
    for changes in ({'policy': 'physical'}, {'policy': 'story'},
                    {'policy': 'assisted', 'scene_id': 3},
                    {'policy': 'assisted', 'revision': 'stale'},
                    {'policy': 'assisted', 'x': -1},
                    {'policy': 'assisted', 'x': 2048 << 4}):
        request = {'policy': 'assisted', **common, **changes}
        assert assisted_teleport(r, **request)['status'] == 'refused'
    assert not r.calls
    assert assisted_teleport(r, policy='assisted', **common)['reason'] == 'unqualified collision'
    assert r.calls == [{'policy': 'assisted', **common}]


def test_teleport_refuses_if_runtime_has_no_qualified_placement():
    class ReadOnly:
        def snapshot(self): return state()
    result = assisted_teleport(ReadOnly(), policy='assisted', scene_id=2,
                               x=320 << 4, y=480 << 4, revision='r1')
    assert result['status'] == 'refused'
    assert result['reason'] == 'qualified runtime placement unavailable'


def test_symbolic_map_retains_raw_categories_and_bounds():
    from fdisbull.shadowrun_city import terrain_symbols, render_city_text
    s = state(); terrain = bytearray(s['terrain'])
    terrain[15 * 64 + 9:15 * 64 + 13] = bytes([0, 127, 3, 255])
    s['terrain'] = bytes(terrain); s['bounds'] = [288, 384, 480, 512]
    symbols = terrain_symbols(s)
    assert len(symbols) == 2816
    assert list(symbols[15 * 64 + 8:15 * 64 + 13]) == [0, 1, 2, 3, 0]
    text = render_city_text(s, radius_x=2, radius_y=1)
    assert '?.@+?' in text
    assert 'not walkability' in text


def test_shared_model_movement_teleport_and_player_protocol(monkeypatch):
    from io import StringIO
    import json
    from pathlib import Path
    from fdisbull.game_il import GameMachine, author_program
    from fdisbull.shadowrun_z import ShadowrunRuntime, ShadowrunZBackend
    from fdisbull.text_projection import serve_stream
    source = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources'
    collision = (source / 'shadowrun_collision.c').read_text() + (source / 'shadowrun_collision_resolve.c').read_text()
    code = collision + '''
        u16 shadowrun_player_x, shadowrun_player_y, shadowrun_camera_x, shadowrun_camera_y;
        u8 shadowrun_player_flags, shadowrun_opening_status;
        u16 shadowrun_camera_min_x, shadowrun_camera_max_x, shadowrun_camera_min_y, shadowrun_camera_max_y;
        u16 shadowrun_camera_scroll_ax, shadowrun_camera_scroll_bx, shadowrun_camera_scroll_ay, shadowrun_camera_scroll_by;
        u16 shadowrun_camera_stream_x, shadowrun_camera_stream_y;
        u16 shadowrun_camera_freeze_a, shadowrun_camera_freeze_b, shadowrun_camera_freeze_c;
        u8 shadowrun_camera_mode, shadowrun_camera_previous_x, shadowrun_camera_previous_y;
        u8 shadowrun_camera_request_x, shadowrun_camera_request_y;
        u16 rom16(u8 region,u32 offset) { return 0; }
        void shadowrun_play_frame(u8 pad) { shadowrun_player_x += pad; shadowrun_opening_status = 1; }
    '''
    import hashlib
    import fdisbull.shadowrun_city as city_module
    import fdisbull.shadowrun_world as world_module
    fake_rom = b'authored fixture'
    digest = hashlib.sha256(fake_rom).hexdigest()
    monkeypatch.setattr(city_module, 'SOURCE_SHA256', digest)
    monkeypatch.setattr(world_module, 'SOURCE_SHA256', digest)
    code += (source / 'shadowrun_debug_place.c').read_text()
    machine = GameMachine(author_program(code, [{'id': 0, 'length': len(fake_rom), 'sha256': digest}]), {0: fake_rom})
    machine.set_state({'shadowrun_player_x': 320 << 4, 'shadowrun_player_y': 480 << 4,
                       'shadowrun_camera_x': 256 << 4, 'shadowrun_camera_y': 400 << 4,
                       'shadowrun_x_max': 2048, 'shadowrun_y_max': 1408,
                       'shadowrun_player_flags': 4, 'shadowrun_camera_max_x': 1600 << 4,
                       'shadowrun_camera_max_y': 1100 << 4})
    runtime = ShadowrunRuntime(machine)
    backend = ShadowrunZBackend(runtime, policy='assisted')
    initial = backend.observe(); token = initial['context']['token']
    result = backend.act({'verb':'go', 'target':'direction.east', 'item':None, 'context_token':token})
    assert result['status'] == 'success' and runtime.snapshot()['player_x'] == (320 << 4) + 8
    assert backend.act({'verb':'go', 'target':'direction.east', 'item':None, 'context_token':token})['status'] == 'rejected'
    s = runtime.snapshot(); camera = (s['camera_x'], s['camera_y'])
    moved = assisted_teleport(runtime, policy='assisted', scene_id=2,
                               x=336 << 4, y=496 << 4, revision=s['revision'])
    assert moved['status'] == 'placed'
    assert (runtime.snapshot()['camera_x'], runtime.snapshot()['camera_y']) == camera
    s = runtime.snapshot(); terrain = list(s['terrain']); terrain[15*64+10] = 127
    runtime.machine.set_state({'shadowrun_terrain_map': terrain})
    refused = assisted_teleport(runtime, policy='assisted', scene_id=2,
                                 x=336 << 4, y=496 << 4, revision=s['revision'])
    assert refused['status'] == 'refused' and runtime.snapshot()['player_x'] == 336 << 4
    s = runtime.snapshot(); before = runtime.machine.snapshot()
    moved = assisted_teleport(runtime, policy='assisted', scene_id=2, x=1000 << 4,
                              y=800 << 4, revision=s['revision'], recenter=True)
    assert moved['status'] == 'placed' and moved['camera_recentered']
    after = runtime.machine.snapshot()
    assert after['shadowrun_camera_x'] == 864 << 4
    assert after['shadowrun_camera_y'] == 688 << 4
    assert after['shadowrun_camera_scroll_ax'] == (before['shadowrun_camera_scroll_ax'] - 608) & 65535
    assert after['shadowrun_camera_scroll_ay'] == (before['shadowrun_camera_scroll_ay'] + 288) & 65535
    assert after['shadowrun_camera_stream_x'] == (after['shadowrun_camera_x'] & 0xff80)
    assert after['shadowrun_camera_request_x'] == 1
    stale = runtime.machine.snapshot()
    result = assisted_teleport(runtime, policy='assisted', scene_id=2, x=1000 << 4,
                                y=800 << 4, revision=s['revision'], recenter=True)
    assert result['status'] == 'refused' and runtime.machine.snapshot() == stale
    stream = StringIO(); serve_stream(backend, StringIO('{"op":"observe"}\n'), stream)
    observed = json.loads(stream.getvalue())
    assert observed['context']['id'] == 'shadowrun.scene.02'
    assert 'Scene regions' in observed['context']['description']
    target = next(o for o in observed['objects'] if o['id'] == 'teleport.2048.2048')
    assert target['verbs'] == ['teleport-recenter']
    command = {'op':'act', 'action':{'verb':'teleport-recenter', 'target':target['id'],
                                    'item':None, 'context_token':observed['context']['token']}}
    stream = StringIO(); serve_stream(backend, StringIO(json.dumps(command) + '\n'), stream)
    assert json.loads(stream.getvalue())['status'] == 'success'
    assert runtime.snapshot()['player_x'] == 2048
    current = backend.observe()
    direct = backend.act({'verb':'teleport-recenter', 'target':'teleport.2096.2096',
                          'item':None, 'context_token':current['context']['token']})
    assert direct['status'] == 'success' and runtime.snapshot()['player_x'] == 2096
    obs = backend.observe()
    wait = backend.act({'verb':'wait', 'target':'wait.10', 'item':None,
                        'context_token':obs['context']['token']})
    assert wait['status'] == 'success' and wait['detail']['frames_executed'] == 10


def test_captured_stacks_and_visibility_are_preserved():
    s = state(); s['camera_y'] = 300 << 4
    s['captured_entities'] = [
        {'id': 'one', 'x': 320 << 4, 'y': 480 << 4},
        {'id': 'two', 'x': 321 << 4, 'y': 481 << 4},
        {'id': 'away', 'x': 1200 << 4, 'y': 900 << 4},
    ]
    city = project_city(s, radius_x=1, radius_y=1)
    center = next(c for c in city['local_cells'] if c['contains_player'])
    assert center['captured_entity_ids'] == ['one', 'two']
    assert [a['visibility'] for a in city['captured_entities']] == ['unknown'] * 3
    assert [a['inside_camera_rectangle'] for a in city['captured_entities']] == [True, True, False]


def test_captured_player_uses_live_position_without_losing_capture():
    s = state()
    s['captured_entities'] = [
        {'id':'player','slot_address':0xff0100,'x':100<<4,'y':200<<4,'current_position':'unknown'},
        {'id':'npc','slot_address':0xff0400,'x':100<<4,'y':200<<4,'current_position':'unknown'},
    ]
    city=project_city(s, radius_x=1, radius_y=1)
    player,npc=city['captured_entities']
    assert (player['x'],player['y'])==(s['player_x'],s['player_y'])
    assert player['captured_position']=={'x':100<<4,'y':200<<4}
    assert player['current_position']=='shared model'
    assert npc['current_position']=='unknown' and (npc['x'],npc['y'])==(100<<4,200<<4)
    assert next(c for c in city['local_cells'] if c['contains_player'])['captured_entity_ids']==['player']


def test_inventory_view_preserves_empty_unknown_and_equipment():
    from fdisbull.shadowrun_z import inventory_view
    assert inventory_view({})['status'] == 'unknown'
    state = {f'shadowrun_inventory_cell{i}': n for i,n in enumerate([2,44,14,16,0,0,0,0])}
    state.update({'shadowrun_play_weapon_slot':0, 'shadowrun_play_weapon_item':2,
                  'shadowrun_play_ammo':12, 'shadowrun_inventory_equipped_armor':1})
    inventory = inventory_view(state)
    assert [x['state'] for x in inventory['slots']] == ['occupied']*4 + ['empty']*4
    assert inventory['slots'][0]['weapon_equipped'] is True
    assert inventory['slots'][1]['weapon_equipped'] is False
    assert inventory['weapon'] == {'slot_raw':0,'item_code':2}
    assert inventory['ammo'] == 12 and inventory['armor'] == 1
    assert inventory['ammo_units'] == 'rounds'
    del state['shadowrun_play_weapon_slot']
    assert inventory_view(state)['weapon'] is None
    assert inventory_view(state)['slots'][0]['weapon_equipped'] is None


def test_actor_model_hp_is_live_and_captured_hp_is_preserved():
    s=state(); s['captured_entities']=[{'id':'npc','slot_address':0xff0500,'x':1,'y':2,'hp_byte_4c':10}]
    assert project_city(s)['captured_entities'][0]['hp_current'] is None
    s['model_actor_hp']=[10,6,10,0,0,0,0]
    actor=project_city(s)['captured_entities'][0]
    assert actor['hp_byte_4c']==10 and actor['hp_current']==6
    assert actor['hp_current_status']=='shared model'
    s['model_actor_hp']=[10]
    assert project_city(s)['captured_entities'][0]['hp_current_status']=='unknown'
