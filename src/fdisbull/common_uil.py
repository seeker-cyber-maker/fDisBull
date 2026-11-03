"""Versioned indexed UIL contracts, independent of source language and layout.

This is an additive bounded profile. Legacy IL documents keep their semantics.
Values and native/resource bindings belong to presentation; UIL references only
typed slots. Catalog declarations do not establish source correspondence.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

FORMAT = 'fdisbull-common-uil-1'
PRESENTATION = 'fdisbull-uil-presentation-1'
ORCHESTRATION = 'fdisbull-uil-orchestration-1'
CAPABILITIES = frozenset(('core.scalar@1', 'core.array@1', 'core.calls@1', 'host.effects@1'))
SERVICES = {
    'text.show': ('resource',), 'image.show': ('resource',),
    'sound.play': ('resource',), 'music.start': ('resource', 'bool'),
    'music.stop': ('resource',),
}
RESOURCE_KINDS = {'text.show': 'text', 'image.show': 'graphic',
                  'sound.play': 'sound', 'music.start': 'music', 'music.stop': 'music'}
_NUMERIC = {f'{s}{n}' for s in 'ui' for n in (8, 16, 32, 64)}
_SCALARS = _NUMERIC | {'bool', 'resource', 'text'}
_ARRAYS = {'u8-array', 'u16-array', 'u32-array'}
_SEMANTIC = re.compile(r'semantic:[0-9a-f]{64}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')


def canonical_bytes(document):
    """Canonical finite JSON; semantic integer values use decimal strings."""
    stack = [(document, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > 1000000 or depth > 80:
            raise ValueError('common UIL document node/depth budget exceeded')
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise ValueError('JSON object keys must be strings')
            stack.extend((v, depth + 1) for v in value.values())
        elif type(value) is list:
            stack.extend((v, depth + 1) for v in value)
        elif value is not None and type(value) not in (str, bool, int):
            raise ValueError('common UIL requires integer/string finite JSON')
        elif type(value) is int and abs(value) > (1 << 64):
            raise ValueError('JSON integer exceeds common UIL bounds')
    try:
        raw = json.dumps(document, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError('invalid common UIL JSON') from exc
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('common UIL document exceeds 4 MiB')
    return raw


def digest(document):
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def load_json(path):
    """Reject duplicate keys rather than silently changing a program."""
    from pathlib import Path
    raw = Path(path).read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('common UIL input exceeds 4 MiB')
    def pairs(items):
        result = {}
        for k, value in items:
            if k in result:
                raise ValueError('duplicate JSON key')
            result[k] = value
        return result
    result = json.loads(raw, object_pairs_hook=pairs)
    canonical_bytes(result)
    return result


def _fields(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= obj.keys() or set(obj) - set(required) - set(optional):
        raise ValueError('invalid common UIL fields')


def _index(value, sequence, label='slot'):
    if type(value) is not int or not 0 <= value < len(sequence):
        raise ValueError(f'invalid zero-based {label} index')
    return sequence[value]


def validate_type(descriptor, *, scalar=False):
    if type(descriptor) is not dict or type(descriptor.get('type')) is not str or descriptor['type'] not in _SCALARS | _ARRAYS:
        raise ValueError('invalid common UIL type')
    typ = descriptor['type']
    if typ in _ARRAYS:
        _fields(descriptor, ('type', 'length'))
        if scalar or type(descriptor['length']) is not int or not 1 <= descriptor['length'] <= 131072:
            raise ValueError('invalid array type/length')
    else:
        _fields(descriptor, ('type',))
    return descriptor


def typed(value, descriptor):
    validate_type(descriptor)
    typ = descriptor['type']
    if typ in _ARRAYS:
        element = {'type': typ.split('-')[0]}
        return (type(value) is list and len(value) == descriptor['length']
                and all(typed(v, element) for v in value))
    if typ == 'bool':
        return type(value) is bool
    if typ == 'text':
        return type(value) is str and len(value.encode('utf-8')) <= 1048576
    if typ == 'resource':
        return type(value) is int and 0 <= value < (1 << 31)
    bits = int(typ[1:])
    lo, hi = (0, (1 << bits)-1) if typ[0] == 'u' else (-(1 << (bits-1)), (1 << (bits-1))-1)
    return type(value) is int and lo <= value <= hi


def default_value(descriptor):
    validate_type(descriptor)
    typ = descriptor['type']
    if typ in _ARRAYS:
        return [0] * descriptor['length']
    return False if typ == 'bool' else ('' if typ == 'text' else 0)


def wrap(value, typ):
    if typ not in _NUMERIC:
        raise ValueError('wrapping requires an integer type')
    bits = int(typ[1:]); value = int(value) & ((1 << bits)-1)
    return value - (1 << bits) if typ[0] == 'i' and value >= (1 << (bits-1)) else value


def presentation_value(value, descriptor):
    """Decode canonical presentation values; live runtime inputs stay typed."""
    validate_type(descriptor)
    typ = descriptor['type']
    if typ in _NUMERIC:
        if type(value) is not str or not re.fullmatch(r'0|-?[1-9][0-9]*', value):
            raise ValueError('integer presentation values require canonical decimal strings')
        value = int(value)
    if not typed(value, descriptor):
        raise ValueError('presentation value/type mismatch')
    return deepcopy(value)


def expression_type(expr, function, _depth=0):
    if _depth > 40 or type(expr) is not dict:
        raise ValueError('invalid common UIL expression/depth')
    if set(expr) == {'var'}:
        return _index(expr['var'], function['variables'], 'variable')
    if set(expr) == {'const'}:
        return _index(expr['const'], function['constants'], 'constant')
    if expr.get('op') == 'load':
        _fields(expr, ('op', 'array', 'index'))
        array = _index(expr['array'], function['variables'], 'array')
        index = expression_type(expr['index'], function, _depth + 1)['type']
        if array['type'] not in _ARRAYS or index not in {'u8','u16','u32','u64'}:
            raise ValueError('load requires an array and unsigned index')
        return {'type': array['type'].split('-')[0]}
    _fields(expr, ('op', 'type', 'args'))
    op, typ, args = expr['op'], expr['type'], expr['args']
    if type(op) is not str or type(typ) is not str or typ not in _SCALARS or type(args) is not list or not 1 <= len(args) <= 3:
        raise ValueError('invalid expression result type/arguments')
    types = [expression_type(v, function, _depth + 1)['type'] for v in args]
    numeric_binary = {'add','sub','mul','div','mod','and','or','xor','shl','shr'}
    if op in numeric_binary:
        if len(types) != 2 or typ not in _NUMERIC or types != [typ, typ]:
            raise ValueError('numeric operands require identical explicit types')
    elif op in {'eq','ne','lt','le','gt','ge'}:
        if (len(types) != 2 or typ != 'bool' or types[0] != types[1]
                or types[0] not in _SCALARS
                or op not in {'eq','ne'} and types[0] not in _NUMERIC):
            raise ValueError('invalid typed comparison')
    elif op == 'not':
        if types != ['bool'] or typ != 'bool':
            raise ValueError('not requires bool')
    elif op == 'cast':
        if len(types) != 1 or typ not in _NUMERIC | {'bool'} or types[0] not in _NUMERIC | {'bool'}:
            raise ValueError('invalid explicit numeric cast')
    elif op == 'select':
        if len(types) != 3 or types != ['bool', typ, typ]:
            raise ValueError('invalid select types')
    elif op == 'parity_even':
        if len(types) != 1 or types[0] not in _NUMERIC or typ != 'bool':
            raise ValueError('invalid parity input')
    else:
        raise ValueError('unsupported common UIL expression')
    return {'type': typ}


def _walk(body):
    for node in body:
        yield node
        if node['op'] in ('group', 'while'):
            yield from _walk(node['body'])
        elif node['op'] == 'if':
            yield from _walk(node['then']); yield from _walk(node['else'])


def validate_function(function):
    canonical_bytes(function)
    _fields(function, ('variables','constants','inputs','outputs','max_steps','body'))
    if (type(function['variables']) is not list or not 0 <= len(function['variables']) <= 1024
            or type(function['constants']) is not list or len(function['constants']) > 8192):
        raise ValueError('invalid function slot tables')
    for d in function['variables']: validate_type(d)
    for d in function['constants']: validate_type(d, scalar=True)
    if sum(d.get('length',0) for d in function['variables']) > 262144:
        raise ValueError('function array storage exceeds 262144 cells')
    for side in ('inputs','outputs'):
        ports = function[side]
        if type(ports) is not list or len(ports) > 256:
            raise ValueError('invalid indexed function interface')
        for p in ports: _index(p, function['variables'], side)
        if len(set(ports)) != len(ports):
            raise ValueError('duplicate function port slot')
    if type(function['max_steps']) is not int or not 1 <= function['max_steps'] <= 4000000:
        raise ValueError('invalid function execution budget')
    count = [0]
    def boolean(expr):
        if expression_type(expr, function) != {'type':'bool'}:
            raise ValueError('condition requires bool')
    def visit(body, depth=0):
        if type(body) is not list or depth > 40:
            raise ValueError('invalid body/depth')
        for node in body:
            count[0] += 1
            if count[0] > 100000 or type(node) is not dict:
                raise ValueError('statement budget/type exceeded')
            op = node.get('op')
            if op == 'set':
                _fields(node, ('op','dst','value'))
                if _index(node['dst'], function['variables']) != expression_type(node['value'], function):
                    raise ValueError('assignment type differs')
            elif op == 'store':
                _fields(node, ('op','array','index','value'))
                array = _index(node['array'], function['variables'])
                if array['type'] not in _ARRAYS:
                    raise ValueError('store requires array')
                if expression_type(node['index'], function)['type'] not in {'u8','u16','u32','u64'}:
                    raise ValueError('store index must be unsigned')
                if expression_type(node['value'], function) != {'type':array['type'].split('-')[0]}:
                    raise ValueError('store value type differs')
            elif op == 'if':
                _fields(node, ('op','condition','then','else')); boolean(node['condition'])
                visit(node['then'], depth+1); visit(node['else'], depth+1)
            elif op == 'while':
                _fields(node, ('op','condition','limit','body')); boolean(node['condition'])
                if type(node['limit']) is not int or not 1 <= node['limit'] <= 4000000:
                    raise ValueError('invalid loop bound')
                visit(node['body'], depth+1)
            elif op in ('call','invoke'):
                _fields(node, ('op', 'function' if op=='call' else 'block','inputs','outputs'))
                target = node['function' if op=='call' else 'block']
                if type(target) is not int or target < 0 or type(node['inputs']) is not list or type(node['outputs']) is not list:
                    raise ValueError('invalid function/import call')
                for expr in node['inputs']: expression_type(expr, function)
                for slot in node['outputs']: _index(slot, function['variables'])
                if len(set(node['outputs'])) != len(node['outputs']):
                    raise ValueError('call outputs require distinct slots')
            elif op == 'require':
                _fields(node, ('op','condition')); boolean(node['condition'])
            elif op == 'effect':
                _fields(node, ('op','service','inputs'))
                signature = SERVICES.get(node['service']) if type(node['service']) is str else None
                if signature is None or type(node['inputs']) is not list or [expression_type(x,function)['type'] for x in node['inputs']] != list(signature):
                    raise ValueError('invalid typed host service')
            elif op == 'group':
                _fields(node, ('op','semantic_id','body'))
                if type(node['semantic_id']) is not str or not _SEMANTIC.fullmatch(node['semantic_id']):
                    raise ValueError('invalid group semantic identity')
                visit(node['body'], depth+1)
            elif op == 'return':
                _fields(node, ('op',))
            else:
                raise ValueError('unsupported common UIL statement')
    visit(function['body'])
    return True


def required_capabilities(program):
    caps = {'core.scalar@1'}
    if program.get('imports'): caps.add('core.calls@1')
    if any(d['type'] in _ARRAYS for spec in program.get('imports', [])
           for d in spec['inputs'] + spec['outputs']):
        caps.add('core.array@1')
    for function in program.get('functions', []):
        if any(d['type'] in _ARRAYS for d in function['variables']): caps.add('core.array@1')
        for node in _walk(function['body']):
            if node['op'] in ('call','invoke'): caps.add('core.calls@1')
            if node['op'] == 'effect': caps.add('host.effects@1')
    if any(x.get('effects') for x in program.get('imports', [])): caps.add('host.effects@1')
    return caps


def validate_program(program):
    canonical_bytes(program)
    _fields(program, ('format','capabilities','imports','functions','entry'))
    if program['format'] != FORMAT:
        raise ValueError('unsupported common UIL format')
    if (type(program['capabilities']) is not list or any(type(c) is not str for c in program['capabilities'])
            or len(set(program['capabilities'])) != len(program['capabilities'])
            or set(program['capabilities']) - CAPABILITIES):
        raise ValueError('unsupported/duplicate required capability')
    if type(program['functions']) is not list or not 1 <= len(program['functions']) <= 256:
        raise ValueError('invalid function table')
    for function in program['functions']: validate_function(function)
    _index(program['entry'], program['functions'], 'entry function')
    if type(program['imports']) is not list or len(program['imports']) > 256:
        raise ValueError('invalid import table')
    for item in program['imports']:
        _fields(item, ('semantic_id','inputs','outputs','effects'))
        if type(item['semantic_id']) is not str or not _SEMANTIC.fullmatch(item['semantic_id']):
            raise ValueError('invalid imported semantic identity')
        for side in ('inputs','outputs'):
            if type(item[side]) is not list or len(item[side]) > 256:
                raise ValueError('invalid imported ports')
            for d in item[side]: validate_type(d)
        if type(item['effects']) is not list or any(type(x) is not str or x not in SERVICES for x in item['effects']) or len(set(item['effects']))!=len(item['effects']):
            raise ValueError('invalid imported effects')
    graph = {i:set() for i in range(len(program['functions']))}
    for i, function in enumerate(program['functions']):
        for node in _walk(function['body']):
            if node['op'] not in ('call','invoke'): continue
            if node['op'] == 'call':
                target = _index(node['function'], program['functions'], 'callee'); graph[i].add(node['function'])
                inputs = [target['variables'][s] for s in target['inputs']]
                outputs = [target['variables'][s] for s in target['outputs']]
            else:
                target = _index(node['block'], program['imports'], 'import')
                inputs, outputs = target['inputs'], target['outputs']
            if ([expression_type(x,function) for x in node['inputs']] != inputs
                    or [function['variables'][x] for x in node['outputs']] != outputs):
                raise ValueError('call/import signature mismatch')
    visiting = set(); heights = {}
    def depth(index):
        if index in visiting:
            raise ValueError('recursive call graph is unsupported')
        if index in heights: return heights[index]
        visiting.add(index)
        height = 1 + max((depth(child) for child in graph[index]), default=0)
        visiting.remove(index); heights[index] = height
        if height > 32: raise ValueError('deep call graph is unsupported')
        return height
    for i in graph: depth(i)
    if required_capabilities(program) - set(program['capabilities']):
        raise ValueError('missing required capability declaration')
    return True


def validate_presentation(program, presentation):
    validate_program(program); canonical_bytes(presentation)
    _fields(presentation, ('format','program_sha256','functions','resources'), ('names','layout'))
    if presentation['format'] != PRESENTATION or presentation['program_sha256'] != digest(program):
        raise ValueError('stale/invalid presentation program binding')
    if type(presentation['functions']) is not list or len(presentation['functions']) != len(program['functions']):
        raise ValueError('presentation function bindings incomplete')
    resources = presentation['resources']
    if type(resources) is not list or len(resources) > 8192:
        raise ValueError('invalid resource table')
    for resource in resources:
        if type(resource) is not dict: raise ValueError('invalid resource')
        if resource.get('kind') == 'text':
            _fields(resource, ('kind','text'))
            if not typed(resource['text'], {'type':'text'}): raise ValueError('invalid text resource')
        elif resource.get('kind') in ('graphic','sound','music'):
            _fields(resource, ('kind','uri'))
            if type(resource['uri']) is not str or not resource['uri'] or len(resource['uri']) > 4096:
                raise ValueError('invalid resource locator')
        else: raise ValueError('unsupported resource kind')
    for fn, binding in zip(program['functions'], presentation['functions']):
        _fields(binding, ('constants','initial'))
        for key, declarations in (('constants',fn['constants']), ('initial',fn['variables'])):
            values = binding[key]
            if type(values) is not list or len(values) != len(declarations):
                raise ValueError('presentation slot bindings incomplete')
            for value, descriptor in zip(values, declarations):
                decoded = presentation_value(value, descriptor)
                if descriptor['type'] == 'resource': _index(decoded, resources, 'resource')
    if 'names' in presentation and type(presentation['names']) is not dict:
        raise ValueError('debug names must be presentation metadata')
    if 'layout' in presentation:
        _fields(presentation['layout'], ('profile',), ('description',))
        if presentation['layout']['profile'] != 'indexed-owned-frames-1':
            raise ValueError('unsupported presentation memory layout')
        if 'description' in presentation['layout'] and type(presentation['layout']['description']) is not str:
            raise ValueError('invalid layout description')
    return True


def validate_orchestration(program, catalog, plan):
    validate_program(program)
    from .uil_catalog import validate_catalog
    validate_catalog(catalog); canonical_bytes(plan)
    _fields(plan, ('format','program_sha256','bindings','ownership','max_call_depth'), ('context',))
    if plan['format'] != ORCHESTRATION or plan['program_sha256'] != digest(program):
        raise ValueError('stale/invalid orchestration program binding')
    if plan['ownership'] != 'copy-in-copy-out' or type(plan['max_call_depth']) is not int or not 1 <= plan['max_call_depth'] <= 32:
        raise ValueError('unsupported ownership/call-depth policy')
    if 'context' in plan:
        _fields(plan['context'], ('session','generation','revision','selection_epoch','provider_epoch'))
        if any(type(v) is not int or not 0 <= v < (1 << 53) for v in plan['context'].values()):
            raise ValueError('invalid orchestration context epochs')
    if type(plan['bindings']) is not list or len(plan['bindings']) != len(program['imports']):
        raise ValueError('every import needs one exact selected implementation')
    implementations = {impl['id']:(group,impl) for group in catalog['groups'] for impl in group['implementations']}
    resolved = {}; shims = []
    for binding in plan['bindings']:
        _fields(binding, ('import','implementation'))
        expected = _index(binding['import'], program['imports'], 'import')
        if binding['import'] in resolved or type(binding['implementation']) is not str or binding['implementation'] not in implementations:
            raise ValueError('duplicate/missing implementation binding')
        group, impl = implementations[binding['implementation']]
        function = impl['function']
        inputs = [function['variables'][s] for s in function['inputs']]
        outputs = [function['variables'][s] for s in function['outputs']]
        effects = group['effects']
        if group['semantic_id'] != expected['semantic_id'] or inputs != expected['inputs'] or outputs != expected['outputs'] or effects != expected['effects']:
            raise ValueError('selected implementation has a different semantic contract')
        if required_capabilities({'functions':[function],'imports':[]}) - set(program['capabilities']):
            raise ValueError('selected implementation requires an undeclared capability')
        resolved[binding['import']] = deepcopy(impl)
        shim = {'import':binding['import'],'implementation':impl['id']}
        for side in ('inputs','outputs'):
            shim[side] = [{'port':i,'variable':slot,'type':deepcopy(function['variables'][slot]),'ownership':'copy'} for i,slot in enumerate(function[side])]
        shims.append(shim)
    return {'resolved':resolved,'shims':shims,'sha256':digest(plan)}


def validate_realization(program, presentation, catalog, plan):
    """Preflight the complete closure, including selected resource constants."""
    validate_presentation(program,presentation)
    result = validate_orchestration(program,catalog,plan)
    resources = presentation['resources']
    functions = [(fn,binding['constants']) for fn,binding in zip(program['functions'],presentation['functions'])]
    functions += [(impl['function'],impl['constants']) for impl in result['resolved'].values()]
    for fn, values in functions:
        for d,v in zip(fn['constants'],values):
            decoded = presentation_value(v,d)
            if d['type'] == 'resource': _index(decoded,resources,'selected resource')
        for node in _walk(fn['body']):
            if node['op'] == 'effect' and set(node['inputs'][0]) == {'const'}:
                index = values[node['inputs'][0]['const']]
                resource = _index(index,resources,'effect resource')
                if resource['kind'] != RESOURCE_KINDS[node['service']]:
                    raise ValueError('statically bound effect resource kind differs')
    return result


def fold_function(program, function_index, semantic_id):
    """Retain an exact lower-level child graph in a transparent named fold."""
    validate_program(program)
    function = _index(function_index, program['functions'], 'function')
    if type(semantic_id) is not str or not _SEMANTIC.fullmatch(semantic_id):
        raise ValueError('invalid folded semantic identity')
    folded = deepcopy(program)
    folded['functions'][function_index]['body'] = [{'op':'group','semantic_id':semantic_id,'body':deepcopy(function['body'])}]
    validate_program(folded)
    recovery = {'format':'fdisbull-uil-recovery-1','before_sha256':digest(program),
                'after_sha256':digest(folded),'function':function_index,'original':deepcopy(function)}
    return {'program':folded,'recovery':recovery}


def expand_fold(program, recovery):
    validate_program(program); canonical_bytes(recovery)
    _fields(recovery, ('format','before_sha256','after_sha256','function','original'))
    if recovery['format'] != 'fdisbull-uil-recovery-1' or digest(program) != recovery['after_sha256']:
        raise ValueError('stale fold recovery binding')
    _index(recovery['function'], program['functions'], 'recovery function')
    restored = deepcopy(program); restored['functions'][recovery['function']] = deepcopy(recovery['original'])
    validate_program(restored)
    if digest(restored) != recovery['before_sha256']:
        raise ValueError('corrupt fold recovery graph')
    # Check that the current node really encloses the retained graph. The
    # label is a declaration; it cannot erase or replace its child behavior.
    body = program['functions'][recovery['function']]['body']
    if len(body) != 1 or body[0].get('op') != 'group' or body[0]['body'] != recovery['original']['body']:
        raise ValueError('fold children differ from recovery graph')
    return restored
