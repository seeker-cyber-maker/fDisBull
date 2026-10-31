"""Bounded AGI object effects, with explicit host-dependent continuations.

Semantics informed by ScummVM f7403b6 engines/agi/{op_cmd,view,checks,motion,text}.cpp;
this is a nominal model, not a claim of original-interpreter parity.
"""
from copy import deepcopy
import json
import re

from .interaction_il import ILInvalid, _fields, _require, _typed

CONTRACT = 'fdisbull.agi.object-resource.2.917.v1'
_SHA = re.compile(r'^[0-9a-fA-F]{64}$')
_VAR = re.compile(r'^\$[A-Za-z_][A-Za-z0-9_]*$')

def _spec(args, outputs=()):
    return {'args': dict(args), 'outputs': dict(outputs)}

SPECS = {
    'resource.load_view': _spec([('view', 'u8')]),
    'object.animate': _spec([('object', 'u8')]),
    'object.set_view': _spec([('object', 'u8'), ('view', 'u8')]),
    'object.position': _spec([('object', 'u8'), ('x', 'u8'), ('y', 'u8')]),
    'object.get_position': _spec([('object', 'u8')], [('x', 'u8'), ('y', 'u8')]),
    'object.distance': _spec([('first', 'u8'), ('second', 'u8')], [('distance', 'u8')]),
    'object.step_size': _spec([('object', 'u8'), ('size', 'u8')]),
    'object.follow_ego': _spec([('object', 'u8'), ('step', 'u8')], [('completion', 'bool')]),
    'ui.print': _spec([('message', 'u8'), ('output_mode', 'bool'), ('window_timer', 'u8')], [('output_mode', 'bool'), ('window_timer', 'u8')]),
}
for _action in ('ignore_horizon', 'land_only', 'stop_cycling', 'start_cycling',
                'stop_motion', 'start_motion', 'wander', 'normal_motion',
                'ignore_blocks', 'observe_blocks', 'draw', 'erase'):
    SPECS['object.' + _action] = _spec([('object', 'u8')])

def validate_block(block, variables):
    try:
        return _validate_block(block, variables)
    except (TypeError, KeyError, RecursionError, AttributeError) as exc:
        raise ILInvalid('invalid effect block') from exc

def _validate_block(block, variables):
    _fields(block, ('id', 'op', 'contract', 'action', 'args', 'outputs', 'binding'), ('evidence',))
    _require(isinstance(block['id'], str) and bool(block['id']), 'invalid effect id')
    _require(block['op'] == 'effect' and block['contract'] == CONTRACT, 'invalid effect contract')
    _require(isinstance(block['binding'], str) and bool(_SHA.fullmatch(block['binding'])), 'invalid logic binding')
    action = block['action']
    _require(isinstance(action, str) and action in SPECS, 'unknown effect action')
    spec = SPECS[action]
    _fields(block['args'], spec['args'])
    _require(isinstance(variables, dict), 'invalid variables')
    for key, typ in spec['args'].items():
        value = block['args'][key]
        if key in ('object', 'first', 'second', 'view', 'message'):
            _require(_typed(value, 'u8'), 'effect target must be a literal byte')
            if key=='message':_require(value>=1,'message ID must be one-based')
        if isinstance(value, dict):
            _fields(value, ('var',))
            _require(isinstance(value['var'], str) and value['var'] in variables and variables[value['var']]['type'] == typ, 'invalid effect argument variable')
        else:
            _require(_typed(value, typ), 'invalid effect argument')
    outputs = dict(spec['outputs'])
    if action in ('object.stop_motion', 'object.start_motion'):
        obj = block['args']['object']
        _require(type(obj) is int, 'motion object must be literal')
        if obj == 0: outputs['ego_direction'] = 'u8'
    _fields(block['outputs'], outputs)
    for port, typ in outputs.items():
        name = block['outputs'][port]
        _require(isinstance(name, str) and name in variables and variables[name]['type'] == typ, 'invalid effect output')

_DEFAULT = dict(x=0, y=0, prev_x=0, prev_y=0, width=0, height=0,
                prev_width=0, prev_height=0, view=0, loop=0, cel=0,
                loop_count=0, cel_count=0, direction=0, motion='normal',
                cycle='normal', step_size=1, follow_step=0, follow_flag=None,
                follow_count=0, view_replaced=False, flags=[])

def object_state(**overrides):
    _require(set(overrides) <= _DEFAULT.keys(), 'unknown object field')
    result = deepcopy(_DEFAULT); result.update(deepcopy(overrides))
    _validate_object(result)
    return result

def _validate_object(obj):
    _fields(obj, _DEFAULT)
    for k in ('x', 'y', 'prev_x', 'prev_y'):
        _require(_typed(obj[k], 'i16'), 'invalid object coordinate')
    for k in ('width', 'prev_width'):
        _require(type(obj[k]) is int and 0 <= obj[k] <= 160, 'invalid object width')
    for k in ('height', 'prev_height'):
        _require(type(obj[k]) is int and 0 <= obj[k] <= 168, 'invalid object height')
    for k in ('view', 'loop', 'cel', 'loop_count', 'cel_count', 'direction', 'step_size', 'follow_step', 'follow_count'):
        _require(_typed(obj[k], 'u8'), 'invalid object byte')
    _require(obj['motion'] in ('normal', 'follow', 'wander') and obj['cycle'] in ('normal', 'end', 'reverse', 'reverse_loop'), 'invalid motion or cycle')
    _require(obj['follow_flag'] is None or isinstance(obj['follow_flag'], str) and bool(_VAR.fullmatch(obj['follow_flag'])), 'invalid follow flag')
    _require(type(obj['view_replaced']) is bool and isinstance(obj['flags'], list) and all(isinstance(x, str) and bool(x) for x in obj['flags']) and len(set(obj['flags'])) == len(obj['flags']), 'invalid object flags')

def _key(k):
    return isinstance(k, str) and k.isascii() and k.isdecimal() and str(int(k)) == k and int(k) <= 255

def validate_context(context):
    try:
        return _validate_context(context)
    except (TypeError, KeyError, RecursionError, AttributeError, OverflowError) as exc:
        raise ILInvalid('invalid effect context') from exc

def _validate_context(context):
    try:
        encoded = json.dumps(context, ensure_ascii=False, allow_nan=False).encode('utf8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ILInvalid('context must be finite JSON') from exc
    _require(len(encoded) <= 1048576, 'context size budget exceeded')
    _fields(context, ('contract', 'horizon', 'player_control', 'objects', 'views', 'loaded_views', 'messages'))
    _require(context['contract'] == CONTRACT and type(context['horizon']) is int and 0 <= context['horizon'] <= 167 and type(context['player_control']) is bool, 'invalid context header')
    objects, views, loaded, messages = (context[k] for k in ('objects', 'views', 'loaded_views', 'messages'))
    _require(isinstance(objects, dict) and all(_key(k) for k in objects), 'invalid objects')
    for obj in objects.values(): _validate_object(obj)
    _require(isinstance(views, dict) and all(_key(k) for k in views), 'invalid views')
    for view in views.values():
        _fields(view, ('sha256', 'loops'))
        _require(isinstance(view['sha256'], str) and bool(_SHA.fullmatch(view['sha256'])), 'invalid view digest')
        _require(isinstance(view['loops'], list) and 1 <= len(view['loops']) <= 255, 'invalid view loops')
        for loop in view['loops']:
            _require(isinstance(loop, list) and 1 <= len(loop) <= 255, 'invalid view cels')
            for cel in loop:
                _fields(cel, ('width', 'height'))
                _require(type(cel['width']) is int and 1 <= cel['width'] <= 160 and type(cel['height']) is int and 1 <= cel['height'] <= 168, 'invalid cel dimensions')
    _require(isinstance(loaded, list) and all(_typed(v, 'u8') and str(v) in views for v in loaded) and len(set(loaded)) == len(loaded), 'invalid loaded views')
    _require(isinstance(messages, dict), 'invalid message tables')
    for binding, table in messages.items():
        _require(isinstance(binding, str) and bool(_SHA.fullmatch(binding)) and isinstance(table, dict) and all(_key(k) and int(k)>=1 and isinstance(v, str) for k, v in table.items()), 'invalid message table')
    return deepcopy(context)

def _flag(obj, flag, enabled):
    if enabled and flag not in obj['flags']: obj['flags'].append(flag)
    if not enabled and flag in obj['flags']: obj['flags'].remove(flag)

def _object(context, n):
    _require(str(n) in context['objects'], 'missing object snapshot')
    return context['objects'][str(n)]

def apply_effect(block, evaluated_args, context):
    action = block['action']; a = evaluated_args
    _fields(a, SPECS[action]['args'])
    _require(all(_typed(a[k], t) for k, t in SPECS[action]['args'].items()), 'invalid evaluated effect arguments')
    results, pending = {}, None
    if action == 'resource.load_view':
        _require(str(a['view']) in context['views'], 'missing view metadata')
        if a['view'] not in context['loaded_views']: context['loaded_views'].append(a['view'])
    elif action == 'ui.print':
        table = context['messages'].get(block['binding'], {})
        _require(str(a['message']) in table, 'missing bound message')
        pending = dict(kind='print', binding=block['binding'], message=table[str(a['message'])], output_mode=a['output_mode'], window_timer=a['window_timer'])
    elif action == 'object.distance':
        first, second = _object(context, a['first']), _object(context, a['second'])
        if 'drawn' in first['flags'] and 'drawn' in second['flags']:
            _require(all(-32768<=o['x']+o['width']//2<=32767 for o in (first,second)),
                     'distance center narrowing outside nominal model')
        results['distance'] = min(254, abs(first['x'] + first['width']//2 - second['x'] - second['width']//2) + abs(first['y']-second['y'])) if 'drawn' in first['flags'] and 'drawn' in second['flags'] else 255
    else:
        o = _object(context, a['object'])
        if action == 'object.animate':
            if 'animated' not in o['flags']:
                o['flags'] = ['animated', 'update', 'cycling']; o.update(motion='normal', cycle='normal', direction=0)
        elif action == 'object.set_view':
            v = a['view']; _require(v in context['loaded_views'] and str(v) in context['views'], 'view not loaded')
            loops = context['views'][str(v)]['loops']; loop = o['loop'] if o['loop'] < len(loops) else 0
            cels = loops[loop]; cel = o['cel'] if o['cel'] < len(cels) else 0
            o.update(view=v, loop=loop, cel=cel, loop_count=len(loops), cel_count=len(cels), width=cels[cel]['width'], height=cels[cel]['height'], view_replaced=True)
            if o['x'] + o['width'] > 160: o['x'] = 160-o['width']; _flag(o, 'update_pos', True)
            if o['y'] - o['height'] + 1 < 0: o['y'] = o['height']-1; _flag(o, 'update_pos', True)
            if o['y'] <= context['horizon'] and 'ignore_horizon' not in o['flags']: o['y'] = context['horizon']+1; _flag(o, 'update_pos', True)
        elif action == 'object.position': o.update(x=a['x'], y=a['y'], prev_x=a['x'], prev_y=a['y'])
        elif action == 'object.get_position': results = {'x': o['x'] & 255, 'y': o['y'] & 255}
        elif action in ('object.ignore_horizon', 'object.land_only', 'object.ignore_blocks', 'object.observe_blocks', 'object.stop_cycling', 'object.start_cycling'):
            flag, enabled = {'object.ignore_horizon': ('ignore_horizon', True), 'object.land_only': ('on_land', True), 'object.ignore_blocks': ('ignore_blocks', True), 'object.observe_blocks': ('ignore_blocks', False), 'object.stop_cycling': ('cycling', False), 'object.start_cycling': ('cycling', True)}[action]; _flag(o, flag, enabled)
        elif action == 'object.step_size': o['step_size'] = a['size']
        elif action in ('object.stop_motion', 'object.start_motion', 'object.normal_motion'):
            o['motion'] = 'normal'
            if action == 'object.stop_motion': o['direction'] = 0
            if action != 'object.normal_motion' and a['object'] == 0:
                results['ego_direction'] = 0; context['player_control'] = action == 'object.start_motion'
        elif action in ('object.follow_ego', 'object.wander'):
            _require(not ('cycling' in o['flags'] and o['cycle'] in ('end', 'reverse_loop')), 'overlapping motion and cycler unsupported')
            o['motion'] = 'follow' if action == 'object.follow_ego' else 'wander'; _flag(o, 'update', True)
            if action == 'object.follow_ego':
                o.update(follow_step=max(a['step'], o['step_size']), follow_flag=block['outputs']['completion'], follow_count=255); results['completion'] = False
            elif a['object'] == 0: context['player_control'] = False
        elif action == 'object.draw':
            if 'drawn' not in o['flags']:
                _require(o['width']>0 and o['height']>0 and o['view'] in context['loaded_views'],
                         'draw requires loaded view geometry')
                loops=context['views'][str(o['view'])]['loops']
                _require(o['loop']<len(loops) and o['cel']<len(loops[o['loop']]),'draw requires bound cel')
                _require(loops[o['loop']][o['cel']]=={'width':o['width'],'height':o['height']},
                         'draw snapshot geometry differs from bound cel')
                _flag(o, 'update', True); pending = dict(kind='draw', object=a['object'], binding=block['binding'])
        elif action == 'object.erase':
            if 'drawn' in o['flags']:
                _flag(o, 'drawn', False); pending = dict(kind='erase', object=a['object'], binding=block['binding'])
        else: raise ILInvalid('unknown effect action')
    return {'results': results, 'events': [], 'pending': pending}

def complete_effect(pending, result, context):
    _require(isinstance(pending, dict) and isinstance(result, dict), 'invalid effect completion')
    kind = pending.get('kind'); results = {}
    if kind == 'draw':
        _fields(pending, ('kind', 'object', 'binding')); _fields(result, ('x', 'y'))
        o = _object(context, pending['object']); x, y = result['x'], result['y']
        _require(type(x) is int and type(y) is int and 0 <= x < 160 and 0 <= y < 168 and x + o['width'] <= 160 and y - o['height'] + 1 >= 0 and ('ignore_horizon' in o['flags'] or y > context['horizon']), 'invalid host draw position')
        o.update(x=x, y=y, prev_x=x, prev_y=y, prev_width=o['width'], prev_height=o['height']); _flag(o, 'drawn', True); _flag(o, 'dont_update', False)
    elif kind == 'erase':
        _fields(pending, ('kind', 'object', 'binding')); _fields(result, ()); _object(context, pending['object'])
    elif kind == 'print':
        _fields(pending, ('kind', 'binding', 'message', 'output_mode', 'window_timer'))
        _fields(result, ('shown',) if pending['output_mode'] else ('dismissed',))
        _require(next(iter(result.values())) is True, 'message completion not acknowledged')
        results = {'output_mode': False, 'window_timer': pending['window_timer'] if pending['output_mode'] else 0}
    else: raise ILInvalid('invalid pending effect')
    return {'results': results, 'events': []}
