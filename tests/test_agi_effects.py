import pytest

from fdisbull.agi_effects import (CONTRACT, apply_effect, complete_effect,
                                 object_state, validate_block, validate_context)
from fdisbull.interaction_il import ILInvalid

SHA = 'a' * 64

def context():
    return validate_context({'contract': CONTRACT, 'horizon': 36, 'player_control': True,
        'objects': {'0': object_state(), '1': object_state()},
        'views': {'2': {'sha256': 'b' * 64, 'loops': [[{'width': 10, 'height': 20}]]}},
        'loaded_views': [], 'messages': {SHA: {'1': 'Hello'}}})

def block(action, args, outputs=None):
    return {'id': 'n', 'op': 'effect', 'contract': CONTRACT, 'binding': SHA,
            'action': action, 'args': args, 'outputs': outputs or {}}

def call(c, action, args, outputs=None):
    return apply_effect(block(action, args, outputs), args, c)

def test_geometry_and_query():
    c = context()
    call(c, 'resource.load_view', {'view': 2})
    call(c, 'object.position', {'object': 0, 'x': 159, 'y': 1})
    call(c, 'object.set_view', {'object': 0, 'view': 2})
    o = c['objects']['0']
    assert (o['x'], o['y'], o['prev_x'], o['prev_y']) == (150, 37, 159, 1)
    assert 'update_pos' in o['flags']
    assert call(c, 'object.get_position', {'object': 0})['results'] == {'x': 150, 'y': 37}
    assert call(c, 'object.distance', {'first': 0, 'second': 1})['results']['distance'] == 255
    o['flags'].append('drawn'); c['objects']['1'].update(x=0, y=0, width=2, flags=['drawn'])
    assert call(c, 'object.distance', {'first': 0, 'second': 1})['results']['distance'] == 191
    o['x'] = 32000
    assert call(c, 'object.distance', {'first': 0, 'second': 1})['results']['distance'] == 254

def test_animate_and_motion():
    c = context(); o = c['objects']['0']; o.update(flags=['custom', 'ignore_horizon'], direction=3)
    call(c, 'object.animate', {'object': 0})
    assert o['flags'] == ['animated', 'update', 'cycling'] and o['direction'] == 0
    o['flags'].append('custom'); call(c, 'object.animate', {'object': 0})
    assert 'custom' in o['flags']
    o['direction'] = 5
    assert call(c, 'object.stop_motion', {'object': 0}, {'ego_direction': '$dir'})['results'] == {'ego_direction': 0}
    assert o['direction'] == 0 and c['player_control'] is False
    o['direction'] = 4
    call(c, 'object.start_motion', {'object': 0}, {'ego_direction': '$dir'})
    assert o['direction'] == 4 and c['player_control'] is True
    r = call(c, 'object.follow_ego', {'object': 0, 'step': 0}, {'completion': '$done'})
    assert r['results'] == {'completion': False} and o['follow_flag'] == '$done' and o['follow_step'] == 1
    o['cycle'] = 'end'
    with pytest.raises(ILInvalid): call(c, 'object.wander', {'object': 0})

def test_draw_erase_and_print_are_pending():
    c = context(); call(c, 'resource.load_view', {'view': 2}); call(c, 'object.set_view', {'object': 0, 'view': 2})
    r = call(c, 'object.draw', {'object': 0}); assert r['pending']['kind'] == 'draw'
    assert 'drawn' not in c['objects']['0']['flags']
    with pytest.raises(ILInvalid): complete_effect(r['pending'], {'x': 159, 'y': 37}, c)
    complete_effect(r['pending'], {'x': 3, 'y': 40}, c)
    assert 'drawn' in c['objects']['0']['flags']
    r = call(c, 'object.erase', {'object': 0}); assert r['pending']['kind'] == 'erase'
    complete_effect(r['pending'], {}, c)
    r = call(c, 'ui.print', {'message': 1, 'output_mode': False, 'window_timer': 2})
    assert r['pending']['message'] == 'Hello'
    with pytest.raises(ILInvalid): complete_effect(r['pending'], {'shown': True}, c)
    assert complete_effect(r['pending'], {'dismissed': True}, c)['results'] == {'output_mode': False, 'window_timer': 0}
    r = call(c, 'ui.print', {'message': 1, 'output_mode': True, 'window_timer': 2})
    assert complete_effect(r['pending'], {'shown': True}, c)['results']['window_timer'] == 2

def test_validation_and_alias():
    c = context()
    c['objects']['0']['flags'].append('extra')
    assert validate_context(c) is not c
    del c['objects']['0']['x']
    with pytest.raises(ILInvalid): validate_context(c)
    variables = {'$p': {'type': 'u8', 'initial': 0}, '$d': {'type': 'u8', 'initial': 0}}
    b = block('object.get_position', {'object': 0}, {'x': '$p', 'y': '$p'})
    validate_block(b, variables)
    sample = context()
    sample['objects']['0'].update(x=7, y=9)
    r = call(sample, 'object.get_position', {'object': 0}, b['outputs'])
    state = {}
    for port, value in r['results'].items(): state[b['outputs'][port]] = value
    assert state == {'$p': 9}
    with pytest.raises(ILInvalid): validate_block(block('object.start_motion', {'object': 0}), variables)

def test_all_flags_and_literal_targets():
    c = context(); o = c['objects']['1']
    for action, flag, present in [('ignore_horizon', 'ignore_horizon', True),
            ('land_only', 'on_land', True), ('ignore_blocks', 'ignore_blocks', True),
            ('observe_blocks', 'ignore_blocks', False), ('start_cycling', 'cycling', True),
            ('stop_cycling', 'cycling', False)]:
        call(c, 'object.' + action, {'object': 1})
        assert (flag in o['flags']) is present
        call(c, 'object.' + action, {'object': 1})
        assert (flag in o['flags']) is present
    o['direction'] = 7; o['motion'] = 'wander'
    call(c, 'object.normal_motion', {'object': 1})
    assert o['motion'] == 'normal' and o['direction'] == 7
    call(c, 'object.step_size', {'object': 1, 'size': 8})
    call(c, 'object.follow_ego', {'object': 1, 'step': 3}, {'completion': '$done'})
    assert o['follow_step'] == 8 and o['follow_count'] == 255
    call(c, 'object.wander', {'object': 0})
    assert not c['player_control']
    v = {'$o': {'type': 'u8', 'initial': 0}}
    with pytest.raises(ILInvalid): validate_block(block('object.animate', {'object': {'var': '$o'}}), v)
    with pytest.raises(ILInvalid): validate_block(block('resource.load_view', {'view': {'var': '$o'}}), v)
    validate_block(block('object.position', {'object': 0, 'x': {'var': '$o'}, 'y': 255}), v)

def test_position_unclamped_and_set_view_retention():
    c = context(); c['views']['2']['loops'] = [[{'width': 3, 'height': 5}, {'width': 7, 'height': 8}], [{'width': 5, 'height': 6}]]
    o = c['objects']['0']; o.update(loop=0, cel=1, flags=['ignore_horizon'])
    call(c, 'object.position', {'object': 0, 'x': 255, 'y': 0})
    assert (o['x'], o['y']) == (255, 0)
    call(c, 'resource.load_view', {'view': 2}); call(c, 'object.set_view', {'object': 0, 'view': 2})
    assert (o['loop'], o['cel'], o['width'], o['height'], o['x'], o['y']) == (0, 1, 7, 8, 153, 7)
    o.update(loop=8, cel=9)
    call(c, 'object.set_view', {'object': 0, 'view': 2})
    assert (o['loop'], o['cel'], o['width']) == (0, 0, 3)
    o.update(flags=['drawn'], x=0, y=37, width=3)
    c['objects']['1'].update(flags=['drawn'], x=5, y=37, width=1)
    assert call(c, 'object.distance', {'first': 0, 'second': 1})['results']['distance'] == 4


@pytest.mark.parametrize('y,expected', [(50,50), (19,19), (18,51)])
def test_original_set_view_horizon_only_after_top_edge_repair(y,expected):
    # Native KQ1 set.view at logic103:10 left y=horizon=50 untouched.
    # A top edge exactly on row zero is valid; only a negative top repairs it.
    c=context(); c['horizon']=50; c['loaded_views']=[2]
    c['objects']['0']['y']=y
    call(c,'object.set_view',{'object':0,'view':2})
    assert c['objects']['0']['y']==expected

def test_invalid_context_shapes_refuse():
    c = context(); c['objects']['0']['cycle'] = []
    with pytest.raises(ILInvalid): validate_context(c)
    c = context(); c['objects']['0']['flags'] = [None]
    with pytest.raises(ILInvalid): validate_context(c)
    c = context(); c['loaded_views'] = [{}]
    with pytest.raises(ILInvalid): validate_context(c)
    with pytest.raises(ILInvalid): validate_context({'contract': float('nan')})

def test_draw_and_distance_do_not_guess_invalid_geometry():
    c=context()
    with pytest.raises(ILInvalid,match='loaded view geometry'):
        call(c,'object.draw',{'object':0})
    c['objects']['0'].update(x=32767,width=160,flags=['drawn'])
    c['objects']['1']['flags']=['drawn']
    with pytest.raises(ILInvalid,match='narrowing'):
        call(c,'object.distance',{'first':0,'second':1})
