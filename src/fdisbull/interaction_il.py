"""A small, shared, block-shaped interaction language.

UDL and UIL are roles on the same document. Host events are plans: this module
never claims that a graphic, sound, or click has happened. Evidence is retained
as supplied, not independently verified.
"""
from copy import deepcopy
import json
import re

_TYPES = {f'{s}{n}' for s in 'ui' for n in (8, 16, 32, 64)} | {'bool'}
_CAP = {'load_graphic': 'graphics', 'play_sound': 'audio', 'click': 'input'}

class ILInvalid(ValueError):
    pass

def _require(ok, message):
    if not ok:
        raise ILInvalid(message)

def _fields(obj, required, optional=()):
    _require(isinstance(obj, dict), 'expected object')
    _require(set(required) <= obj.keys() and obj.keys() <= set(required) | set(optional), 'invalid fields')

def _typed(value, typ):
    if typ == 'bool':
        return type(value) is bool
    bits = int(typ[1:])
    lo, hi = (0, 2**bits - 1) if typ[0] == 'u' else (-2**(bits-1), 2**(bits-1)-1)
    return type(value) is int and lo <= value <= hi

def validate_il(document):
    """Validate the entire program, raising ILInvalid on any invalid input."""
    try:
        raw = json.dumps(document, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ILInvalid('document must be finite JSON') from exc
    _require(len(raw) <= 65536, 'document size budget exceeded')
    _fields(document, ('format', 'role', 'variables', 'resources', 'body'), ('evidence', 'tables'))
    _require(document['format'] == 'fdisbull-il-1' and document['role'] in ('udl', 'uil'), 'invalid format or role')
    variables, resources = document['variables'], document['resources']
    tables = document.get('tables', {})
    _require(isinstance(tables, dict) and len(tables) <= 16, 'invalid table declarations')
    total = 0
    for name, table in tables.items():
        _require(isinstance(name, str) and bool(name), 'invalid table name')
        _fields(table, ('type', 'values'))
        _require(table['type'] in ('u8', 'u16') and isinstance(table['values'], list)
                 and bool(table['values']) and all(_typed(v, table['type']) for v in table['values']),
                 'invalid immutable table')
        total += len(table['values'])
    _require(total <= 4096, 'immutable table budget exceeded')
    _require(isinstance(variables, dict) and isinstance(resources, dict), 'invalid declarations')
    for name, decl in variables.items():
        _require(isinstance(name, str) and re.fullmatch(r'\$[A-Za-z_][A-Za-z0-9_]*', name), 'invalid variable name')
        _fields(decl, ('type', 'initial'))
        _require(decl['type'] in _TYPES and _typed(decl['initial'], decl['type']), 'invalid initial value')
    for name, resource in resources.items():
        _require(isinstance(name, str) and bool(name), 'invalid resource name')
        _fields(resource, ('kind',), ('text', 'uri'))
        _require(resource['kind'] in ('text', 'graphic', 'sound'), 'invalid resource kind')
        if resource['kind'] == 'text':
            _require(set(resource) == {'kind', 'text'} and isinstance(resource['text'], str), 'invalid text resource')
        else:
            _require(set(resource) == {'kind', 'uri'} and isinstance(resource['uri'], str) and bool(resource['uri']), 'invalid media resource')
    evidence = document.get('evidence', {})
    _require(isinstance(evidence, dict), 'invalid evidence')
    for key, item in evidence.items():
        _require(isinstance(key, str) and bool(key) and isinstance(item, dict), 'invalid evidence item')
        if 'sha256' in item:
            _require(isinstance(item['sha256'], str) and re.fullmatch(r'[0-9a-fA-F]{64}', item['sha256']), 'invalid evidence digest')
        if 'range' in item:
            value = item['range']
            _require(isinstance(value, list) and len(value) == 2 and all(type(x) is int for x in value) and 0 <= value[0] <= value[1], 'invalid evidence range')
    ids, count = set(), [0]
    def value(v):
        if isinstance(v, dict):
            _fields(v, ('var',))
            _require(v['var'] in variables, 'unknown variable')
            return variables[v['var']]['type']
        _require(type(v) in (int, bool), 'invalid value')
        return 'bool' if type(v) is bool else 'integer'
    def condition(c, depth):
        count[0] += 1
        _require(count[0] <= 1024, 'node budget exceeded')
        _require(depth <= 32, 'depth budget exceeded')
        _require(isinstance(c, dict), 'invalid condition')
        op = c.get('op')
        if op == 'eq':
            _fields(c, ('op', 'left', 'right'))
            a, b = value(c['left']), value(c['right'])
            _require((a == 'bool') == (b == 'bool'), 'incompatible equality')
        elif op == 'bit_test':
            _fields(c, ('op', 'value', 'bit'))
            _require(value(c['value']) != 'bool' and type(c['bit']) is int and 0 <= c['bit'] < 64, 'invalid bit test')
        elif op == 'not':
            _fields(c, ('op', 'condition')); condition(c['condition'], depth+1)
        elif op == 'and':
            _fields(c, ('op', 'conditions'))
            _require(isinstance(c['conditions'], list) and bool(c['conditions']), 'invalid conjunction')
            for child in c['conditions']: condition(child, depth+1)
        else: raise ILInvalid('unknown condition')
    def blocks(body, depth):
        _require(depth <= 32, 'depth budget exceeded')
        _require(isinstance(body, list), 'body must be a list')
        for block in body:
            count[0] += 1
            _require(count[0] <= 1024, 'node budget exceeded')
            _require(isinstance(block, dict), 'invalid block')
            op = block.get('op')
            fields = {'set': ('var','value'), 'add': ('var','value'), 'subtract': ('var','value'), 'lookup': ('var','table','index'), 'if': ('condition','then','else'), 'require': ('condition',), 'text': ('resource',), 'load_graphic': ('resource','x','y'), 'play_sound': ('resource',), 'click': ('target',)}
            _require(op in fields, 'unknown block')
            _fields(block, ('id','op',*fields[op]), ('evidence',))
            ident = block['id']
            _require(isinstance(ident, str) and bool(ident) and ident not in ids, 'invalid or duplicate block id')
            ids.add(ident)
            refs = block.get('evidence', [])
            _require(isinstance(refs, list) and all(isinstance(x, str) and x in evidence for x in refs), 'invalid evidence reference')
            if op in ('set','add','subtract'):
                var = block['var']; _require(var in variables, 'unknown variable')
                typ = variables[var]['type']; vtyp = value(block['value'])
                _require((typ == 'bool') == (vtyp == 'bool') and (op == 'set' or typ != 'bool'), 'incompatible assignment')
                if not isinstance(block['value'], dict): _require(_typed(block['value'], typ), 'literal out of range')
            elif op == 'lookup':
                _require(isinstance(block['var'], str) and block['var'] in variables
                         and isinstance(block['table'], str) and block['table'] in tables,
                         'unknown lookup binding')
                _require(variables[block['var']]['type'] == tables[block['table']]['type'],
                         'lookup result type mismatch')
                _require(value(block['index']) in ('integer', 'u8', 'u16'), 'invalid lookup index type')
                if not isinstance(block['index'], dict):
                    _require(0 <= block['index'] < len(tables[block['table']]['values']), 'lookup index out of range')
            elif op == 'if':
                condition(block['condition'], depth+1); blocks(block['then'], depth+1); blocks(block['else'], depth+1)
            elif op == 'require':
                condition(block['condition'], depth+1)
            elif op in ('text','load_graphic','play_sound'):
                ref = block['resource']; expected = {'text':'text','load_graphic':'graphic','play_sound':'sound'}[op]
                _require(isinstance(ref, str) and ref in resources and resources[ref]['kind'] == expected, 'invalid resource reference')
                if op == 'load_graphic':
                    _require(value(block['x']) != 'bool' and value(block['y']) != 'bool', 'invalid coordinates')
            else:
                _require(isinstance(block['target'], str) and bool(block['target']), 'invalid click target')
    blocks(document['body'], 1)
    return True

def change_role(document, role):
    validate_il(document)
    _require(role in ('udl', 'uil'), 'invalid role')
    result = deepcopy(document); result['role'] = role
    return result

def execute_il(document, state=None, capabilities=(), max_steps=1024):
    """Evaluate atomically. Pending host events are plans, not executed effects.

    Returns committed state, proposed_state, events and visited block IDs. On a
    budget or validation failure there are no events and no state changes.
    """
    original = deepcopy(state)
    try:
        validate_il(document)
        _require(type(max_steps) is int and max_steps >= 0, 'invalid step budget')
        _require(isinstance(capabilities, (list, tuple, set, frozenset)) and all(isinstance(x, str) for x in capabilities), 'invalid capabilities')
        _require(set(capabilities) <= set(_CAP.values()), 'unknown capability')
        declarations = document['variables']
        initial = {k: v['initial'] for k,v in declarations.items()}
        if state is None: state = initial
        _require(isinstance(state, dict) and state.keys() == declarations.keys(), 'invalid state keys')
        _require(all(_typed(state[k], v['type']) for k,v in declarations.items()), 'invalid state value')
        original = deepcopy(state)
        def preflight(body):
            for b in body:
                if b['op'] in _CAP: _require(_CAP[b['op']] in capabilities, 'missing capability: ' + _CAP[b['op']])
                if b['op'] == 'if': preflight(b['then']); preflight(b['else'])
        preflight(document['body'])
        work, events, visited = deepcopy(state), [], []
        def val(v): return work[v['var']] if isinstance(v, dict) else v
        def cond(c):
            op = c['op']
            if op == 'eq': return val(c['left']) == val(c['right'])
            if op == 'bit_test': return bool(val(c['value']) & (1 << c['bit']))
            if op == 'not': return not cond(c['condition'])
            return all(cond(x) for x in c['conditions'])
        def run(body):
            for b in body:
                _require(len(visited) < max_steps, 'step budget exceeded')
                visited.append(b['id']); op = b['op']
                if op in ('set','add','subtract'):
                    name, v = b['var'], val(b['value']); typ = declarations[name]['type']
                    if op == 'set':
                        _require(_typed(v, typ), 'assignment out of range'); work[name] = v
                    else:
                        bits = int(typ[1:]); n = (work[name] + (v if op == 'add' else -v)) % (1 << bits)
                        work[name] = n - (1 << bits) if typ[0] == 'i' and n >= (1 << (bits-1)) else n
                elif op == 'lookup':
                    values = document['tables'][b['table']]['values']
                    index = val(b['index'])
                    _require(0 <= index < len(values), 'lookup index out of range')
                    work[b['var']] = values[index]
                elif op == 'if': run(b['then'] if cond(b['condition']) else b['else'])
                elif op == 'require': _require(cond(b['condition']), 'qualification condition not met')
                else:
                    event = {'op': op, 'block_id': b['id'], 'evidence': deepcopy(b.get('evidence', []))}
                    if 'resource' in b:
                        event['resource'] = b['resource']; event['resource_data'] = deepcopy(document['resources'][b['resource']])
                    if op == 'load_graphic': event.update(x=val(b['x']), y=val(b['y']))
                    if op == 'click': event['target'] = b['target']
                    events.append(event)
        run(document['body'])
        pending = any(e['op'] in _CAP for e in events)
        return {'complete': not pending, 'status': 'pending_host' if pending else 'complete', 'state': original if pending else work, 'proposed_state': work, 'events': events, 'visited': visited, 'evidence': deepcopy(document.get('evidence', {}))}
    except (ILInvalid, TypeError, KeyError, RecursionError) as exc:
        return {'complete': False, 'status': 'refused', 'error': str(exc), 'state': original, 'events': [], 'visited': []}
