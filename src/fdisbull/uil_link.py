"""Deterministic, data-only native module contracts and resolution locks.

Generic provider declarations never authorize code execution or emission.
Native builders admit only the locally reconstructed builtin provider IDs.
Intrinsic meaning depends on version/types/ABI/ownership/profile, not language.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .common_uil import (FORMAT as PROFILE, SERVICES, canonical_bytes, digest,
                        expression_type, validate_realization, validate_type)
from .uil_catalog import function_semantic_id

TARGETS = ('macos-arm64', 'linux-x64', 'windows-x64')
ABI = 'uil-native-intrinsics-1'
OWNERSHIP = 'copy-in-copy-out'
ALU = ('add', 'sub', 'mul', 'and', 'or', 'xor')
_NUMERIC = tuple(f'{s}{n}' for s in 'ui' for n in (8, 16, 32, 64))
_BINARY = ALU + ('div', 'mod', 'shl', 'shr')
_COMPARE = ('eq', 'ne', 'lt', 'le', 'gt', 'ge')
_LABEL = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z')
_ID = re.compile(r'(?:requirement|module|provider):[0-9a-f]{64}\Z')
_MAX_NODES = 1024


def _fields(doc, required, optional=()):
    if type(doc) is not dict or not set(required) <= doc.keys() or doc.keys() - set(required) - set(optional):
        raise ValueError('invalid link fields')


def _label(value):
    if type(value) is not str or not _LABEL.fullmatch(value):
        raise ValueError('invalid link identifier label')


def _target(target):
    if type(target) is not str or target not in TARGETS:
        raise ValueError('unsupported native target')


def _metadata(value):
    if value is None: return {}
    if type(value) is not dict or len(canonical_bytes(value)) > 65536:
        raise ValueError('bounded module metadata object required')
    forbidden = {'code', 'code_hex', 'bytes_hex', 'payload', 'raw', 'source_text', 'program', 'body'}
    def visit(node):
        if type(node) is dict:
            if forbidden & node.keys(): raise ValueError('module metadata cannot retain raw source/payloads')
            for item in node.values(): visit(item)
        elif type(node) is list:
            for item in node: visit(item)
    visit(value)
    return deepcopy(value)


def _stamp(prefix, payload):
    result = deepcopy(payload)
    result['id'] = prefix + ':' + digest(payload)
    return result


def _identity(doc, prefix):
    if type(doc) is not dict or type(doc.get('id')) is not str or not doc['id'].startswith(prefix + ':') or not _ID.fullmatch(doc['id']):
        raise ValueError('invalid module/provider/requirement identity')
    if doc['id'] != prefix + ':' + digest({k: v for k, v in doc.items() if k != 'id'}):
        raise ValueError('stale module/provider/requirement identity')


def make_requirement(intrinsic, version=1, *, inputs=None, outputs=None,
                     abi=ABI, ownership=OWNERSHIP, profile=PROFILE, effects=None):
    payload = {'format': 'fdisbull-udc-intrinsic-requirement-1',
               'intrinsic': intrinsic, 'version': version,
               'inputs': deepcopy(inputs if inputs is not None else []),
               'outputs': deepcopy(outputs if outputs is not None else []),
               'abi': abi, 'ownership': ownership, 'profile': profile,
               'effects': sorted(effects if effects is not None else [])}
    result = _stamp('requirement', payload)
    _requirement(result)
    return result


def _requirement(req):
    _fields(req, ('format', 'id', 'intrinsic', 'version', 'inputs', 'outputs', 'abi', 'ownership', 'profile', 'effects'))
    _identity(req, 'requirement')
    if req['format'] != 'fdisbull-udc-intrinsic-requirement-1' or type(req['version']) is not int or not 1 <= req['version'] <= 2147483647:
        raise ValueError('unsupported intrinsic contract/version')
    for key in ('intrinsic', 'abi', 'ownership', 'profile'): _label(req[key])
    for side in ('inputs', 'outputs'):
        if type(req[side]) is not list or len(req[side]) > 256: raise ValueError('invalid typed intrinsic ports')
        for descriptor in req[side]: validate_type(descriptor)
    if type(req['effects']) is not list or len(req['effects']) > 32 or any(type(v) is not str or not _LABEL.fullmatch(v) for v in req['effects']) or req['effects'] != sorted(set(req['effects'])):
        raise ValueError('intrinsic effects must be an exact canonical list')


def _requirements(values):
    if type(values) is not list or len(values) > 2048: raise ValueError('bounded intrinsic requirements required')
    seen = set()
    for req in values:
        _requirement(req)
        if req['id'] in seen: raise ValueError('duplicate intrinsic requirement')
        seen.add(req['id'])
    return sorted(deepcopy(values), key=lambda r: r['id'])


def make_module(name, requires, *, metadata=None):
    _label(name)
    return _stamp('module', {'format': 'fdisbull-udc-link-module-1', 'name': name,
                             'requires': _requirements(requires), 'metadata': _metadata(metadata)})


def make_provider(name, provides, *, target, requires=None, metadata=None):
    _label(name); _target(target)
    offered = _requirements(provides)
    if not offered: raise ValueError('provider must offer at least one exact contract')
    return _stamp('provider', {'format': 'fdisbull-udc-link-provider-1', 'name': name,
                               'target': target, 'provides': offered,
                               'requires': _requirements(requires if requires is not None else []),
                               'metadata': _metadata(metadata)})


def _admit(modules, providers, target, pins):
    _target(target)
    if type(modules) is not list or type(providers) is not list or len(modules) + len(providers) > _MAX_NODES:
        raise ValueError('module/provider graph budget exceeded')
    nodes = {}; total = 0
    for prefix, documents in (('module', modules), ('provider', providers)):
        for doc in documents:
            required = ('format', 'id', 'name', 'requires', 'metadata') + (('target', 'provides') if prefix == 'provider' else ())
            _fields(doc, required); _identity(doc, prefix); _label(doc['name']); _metadata(doc['metadata'])
            if doc['format'] != f'fdisbull-udc-link-{prefix}-1': raise ValueError('unsupported link module/provider format')
            if doc['requires'] != _requirements(doc['requires']): raise ValueError('noncanonical intrinsic requirement order')
            total += len(doc['requires'])
            if prefix == 'provider':
                _target(doc['target'])
                if not doc['provides'] or doc['provides'] != _requirements(doc['provides']): raise ValueError('invalid provider contracts')
                total += len(doc['provides'])
            if doc['id'] in nodes: raise ValueError('duplicate module/provider identity')
            nodes[doc['id']] = doc
    if total > 16384: raise ValueError('intrinsic graph requirement budget exceeded')
    canonical_bytes({'modules': modules, 'providers': providers})
    pins = {} if pins is None else pins
    if type(pins) is not dict or len(pins) > _MAX_NODES: raise ValueError('invalid provider pins')
    by_provider = {p['id']: p for p in providers}
    for node, choices in pins.items():
        if node not in nodes or type(choices) is not dict or not choices: raise ValueError('unknown/empty provider pin node')
        required = {r['id'] for r in nodes[node]['requires']}
        for req, provider in choices.items():
            if req not in required or type(provider) is not str or provider not in by_provider: raise ValueError('unknown/unused requirement or provider pin')
    return nodes, by_provider, deepcopy(pins)


def _eligible(req, providers, target):
    return sorted(p['id'] for p in providers.values()
                  if p['target'] == target and any(r['id'] == req['id'] for r in p['provides']))


def _seal(payload):
    result = deepcopy(payload); result['sha256'] = digest(payload)
    return result


def resolve_modules(modules, providers, *, target, pins=None):
    """Resolve exact dependencies, rejecting rather than ranking ambiguity."""
    nodes, candidates, pins = _admit(modules, providers, target, pins)
    visiting = set(); visited = set(); selected = []; bindings = []; used = set(); versions = {}
    def visit(node_id):
        if node_id in visiting: raise ValueError('provider dependency cycle')
        if node_id in visited: return
        if len(visiting) >= 64: raise ValueError('provider dependency depth exceeds 64')
        visiting.add(node_id)
        for req in nodes[node_id]['requires']:
            prior = versions.setdefault(req['intrinsic'], req['version'])
            if prior != req['version']: raise ValueError('conflicting required intrinsic versions: ' + req['intrinsic'])
            eligible = _eligible(req, candidates, target)
            pin = pins.get(node_id, {}).get(req['id'])
            if pin is not None:
                if pin not in eligible: raise ValueError('pinned provider has incompatible target/ABI/ownership/profile/contract')
                chosen = pin; used.add((node_id, req['id']))
            elif not eligible:
                raise ValueError(f'missing compatible intrinsic {req["intrinsic"]}@{req["version"]}')
            elif len(eligible) != 1:
                raise ValueError(f'ambiguous intrinsic {req["intrinsic"]}@{req["version"]}; exact provider pin required')
            else: chosen = eligible[0]
            bindings.append({'node': node_id, 'requirement': req['id'], 'provider': chosen})
            visit(chosen)
        visiting.remove(node_id); visited.add(node_id)
        if node_id in candidates: selected.append(node_id)
    for module in sorted(modules, key=lambda m: m['id']): visit(module['id'])
    declared = {(node, req) for node, choices in pins.items() for req in choices}
    if used != declared: raise ValueError('unused provider pins outside the resolved closure')
    return _seal({'format': 'fdisbull-udc-link-lock-1', 'target': target,
                  'modules': sorted(deepcopy(modules), key=lambda m: m['id']),
                  'providers': [deepcopy(candidates[p]) for p in selected],
                  'bindings': sorted(bindings, key=lambda b: (b['node'], b['requirement']))})


def describe_components(modules, providers, *, target, pins=None):
    """Finite cascading choice graph; a declaration does not execute providers."""
    nodes, candidates, pins = _admit(modules, providers, target, pins)
    todo = sorted(m['id'] for m in modules); described = {}; edges = {}; choice_count = 0
    while todo:
        node_id = todo.pop(0)
        if node_id in described: continue
        choices = []; edges[node_id] = set()
        for req in nodes[node_id]['requires']:
            eligible = _eligible(req, candidates, target)
            pin = pins.get(node_id, {}).get(req['id'])
            if pin is not None and pin not in eligible: raise ValueError('incompatible component pin')
            selected = pin if pin is not None else (eligible[0] if len(eligible) == 1 else None)
            choice_count += len(eligible)
            if choice_count > 16384: raise ValueError('component choice graph budget exceeded')
            # Child contracts are present exactly once in the corresponding
            # provider node. Options reference them instead of expanding a
            # possibly shared/cyclic dependency tree exponentially.
            options = [{'provider': p, 'requires': [r['id'] for r in candidates[p]['requires']]} for p in eligible]
            choices.append({'requirement': deepcopy(req), 'eligible': options, 'selected': selected})
            children = [selected] if selected is not None else eligible
            edges[node_id].update(children); todo.extend(children)
        described[node_id] = {'id': node_id, 'name': nodes[node_id]['name'], 'requirements': choices}
    cycles = []; active = []; done = set(); truncated = set()
    def visit(node_id):
        if node_id in active:
            cycle = active[active.index(node_id):] + [node_id]
            if cycle not in cycles: cycles.append(cycle)
            return
        if node_id in done: return
        if len(active) >= 64:
            truncated.add(node_id); return
        active.append(node_id)
        for child in sorted(edges.get(node_id, ())): visit(child)
        active.pop(); done.add(node_id)
    for node in sorted(described): visit(node)
    try:
        lock = resolve_modules(modules, providers, target=target, pins=pins)
        resolution = {'status': 'resolved', 'lock_sha256': lock['sha256']}
    except ValueError as exc:
        resolution = {'status': 'unresolved', 'reason': str(exc)}
    return _seal({'format': 'fdisbull-udc-component-choices-1', 'target': target,
                  'roots': sorted(m['id'] for m in modules),
                  'nodes': [described[n] for n in sorted(described)], 'cycles': cycles,
                  'depth_limited_nodes': sorted(truncated),
                  'resolution': resolution, 'execution_authorized': False})


def _runtime_requirements():
    result = [make_requirement('frame.copy', inputs=[{'type': 'u32'}] * 2),
              make_requirement('budget.consume', inputs=[{'type': 'u32'}])]
    result += [make_requirement(name, inputs=[{'type': typ} for typ in signature],
                                effects=[name]) for name, signature in SERVICES.items()]
    return result


def _standard(req):
    """Return the supported v1 typed contract, independent of requested version."""
    name = req['intrinsic']; ins = req['inputs']; outs = req['outputs']
    if name in ('frame.copy', 'budget.consume') or name in SERVICES:
        return next(r for r in _runtime_requirements() if r['intrinsic'] == name)
    if not name.startswith('core.'): return None
    op = name[5:]; ts = [d['type'] for d in ins]
    valid = False
    if op in _BINARY: valid = len(ins) == 2 and ts[0] in _NUMERIC and ins[0] == ins[1] and outs == [ins[0]]
    elif op in _COMPARE: valid = len(ins) == 2 and ins[0] == ins[1] and ts[0] in _NUMERIC + ('bool', 'resource', 'text') and (op in ('eq', 'ne') or ts[0] in _NUMERIC) and outs == [{'type': 'bool'}]
    elif op == 'cast': valid = len(ins) == len(outs) == 1 and ts[0] in _NUMERIC + ('bool',) and outs[0]['type'] in _NUMERIC + ('bool',)
    elif op == 'not': valid = ins == outs == [{'type': 'bool'}]
    elif op == 'parity_even': valid = len(ins) == 1 and ts[0] in _NUMERIC and outs == [{'type': 'bool'}]
    elif op == 'select': valid = len(ins) == 3 and ins[0] == {'type': 'bool'} and ins[1] == ins[2] and outs == [ins[1]]
    elif op in ('load', 'store'):
        valid = len(ins) == (2 if op == 'load' else 3) and ts[0] in ('u8-array', 'u16-array', 'u32-array') and ts[1] in ('u8', 'u16', 'u32', 'u64')
        element = {'type': ts[0].split('-')[0]} if valid else None
        valid = valid and (outs == [element] if op == 'load' else ins[2] == element and outs == [ins[0]])
    return make_requirement(name, inputs=ins, outputs=outs) if valid else None


def _builtins(target, requirements):
    _target(target)
    # Baseline ALU signatures also give an empty/nonnumeric function a concrete
    # declared arithmetic-provider policy. They do not invent an executed op.
    scalar = {r['id']: r for r in [make_requirement('core.' + op, inputs=[{'type': 'u64'}] * 2, outputs=[{'type': 'u64'}]) for op in ALU]}
    runtime = {r['id']: r for r in _runtime_requirements()}
    for req in requirements:
        standard = _standard(req)
        if standard is not None:
            (scalar if standard['intrinsic'].startswith('core.') else runtime)[standard['id']] = standard
    carrier = {'profile': PROFILE, 'abi': ABI, 'ownership': OWNERSHIP,
               'calling_convention': {'macos-arm64': 'apple-aapcs64', 'linux-x64': 'sysv-amd64', 'windows-x64': 'win64'}[target],
               'code_authority': 'builtin-emitter-only; metadata is not executable authority'}
    c = make_provider('portable-c', list(scalar.values()), target=target,
                      metadata={**carrier, 'arithmetic': 'portable-c', 'realization': 'generator-owned-typed-c-1'})
    asm = make_provider('native-asm', [r for r in scalar.values() if r['intrinsic'][5:] in ALU], target=target,
                        metadata={**carrier, 'arithmetic': 'native-asm', 'realization': 'u64-alu-typed-wrap-1'})
    host = make_provider('common-runtime', list(runtime.values()), target=target,
                         metadata={**carrier, 'realization': 'owned-frames-budget-and-pending-plans-1', 'physical_effects': False})
    return {'portable-c': c, 'native-asm': asm, 'runtime': host}


def _function_requirements(function):
    required = {r['id']: r for r in _runtime_requirements()[:2]}
    def add(name, ins, outs, effects=None):
        req = make_requirement(name, inputs=ins, outputs=outs, effects=effects)
        required[req['id']] = req
    def expr(value):
        if 'op' not in value: return
        op = value['op']
        if op == 'load':
            expr(value['index'])
            add('core.load', [function['variables'][value['array']], expression_type(value['index'], function)], [expression_type(value, function)])
        else:
            for child in value['args']: expr(child)
            add('core.' + op, [expression_type(x, function) for x in value['args']], [expression_type(value, function)])
    def body(nodes):
        for node in nodes:
            op = node['op']
            if op == 'set': expr(node['value'])
            elif op == 'store':
                expr(node['index']); expr(node['value'])
                array = function['variables'][node['array']]
                add('core.store', [array, expression_type(node['index'], function), expression_type(node['value'], function)], [array])
            elif op in ('if', 'while', 'require'):
                expr(node['condition'])
                if op == 'if': body(node['then']); body(node['else'])
                elif op == 'while': body(node['body'])
            elif op in ('call', 'invoke'):
                for value in node['inputs']: expr(value)
            elif op == 'effect':
                for value in node['inputs']: expr(value)
                add(node['service'], [expression_type(x, function) for x in node['inputs']], [], [node['service']])
            elif op == 'group': body(node['body'])
    body(function['body'])
    return list(required.values())


def _config(value):
    if type(value) is not dict or value.keys() - {'arithmetic', 'requires', 'components', 'pins'}: raise ValueError('invalid native module requirements')
    style = value.get('arithmetic')
    if style is not None and style not in ('portable-c', 'native-asm'): raise ValueError('unsupported arithmetic provider')
    components = value.get('components', {})
    if type(components) is not dict or components.keys() - set(ALU) or any(v not in ('portable-c', 'native-asm') for v in components.values()): raise ValueError('unsupported arithmetic component choice')
    if type(value.get('requires', [])) is not list or len(value.get('requires', [])) > 256: raise ValueError('invalid hard module requirements')
    if type(value.get('pins', {})) is not dict: raise ValueError('invalid exact module pins')
    return deepcopy(value)


def _extra_requirements(base, extras):
    result = {r['id']: r for r in base}
    for extra in extras:
        if type(extra) is dict and set(extra) == {'intrinsic', 'version'}:
            name, version = extra['intrinsic'], extra['version']
            matches = [r for r in result.values() if r['intrinsic'] == name]
            if not matches:
                matches = [r for r in _runtime_requirements() if r['intrinsic'] == name]
            if not matches: raise ValueError('unknown shorthand intrinsic needs a full typed requirement')
            for old in matches:
                new = make_requirement(name, version, inputs=old['inputs'], outputs=old['outputs'],
                                       abi=old['abi'], ownership=old['ownership'], profile=old['profile'], effects=old['effects'])
                result.pop(old['id'], None); result[new['id']] = new
        else:
            _requirement(extra); result[extra['id']] = deepcopy(extra)
    return list(result.values())


def resolve_native_link(program, presentation, catalog, orchestration, target, *,
                        arithmetic='portable-c', module_requirements=None):
    """Pin native lowering requirements around unchanged common documents."""
    _target(target)
    if arithmetic not in ('portable-c', 'native-asm'): raise ValueError('unsupported arithmetic provider')
    docs = deepcopy((program, presentation, catalog, orchestration))
    program, presentation, catalog, orchestration = docs
    resolved = validate_realization(program, presentation, catalog, orchestration)['resolved']
    options = {} if module_requirements is None else deepcopy(module_requirements)
    if type(options) is not dict or options.keys() - {'functions', 'implementations'}: raise ValueError('invalid native requirement selectors')
    for side in options:
        if type(options[side]) is not dict: raise ValueError('native requirement selector map required')
    local_options = options.get('functions', {}); import_options = options.get('implementations', {})
    if set(local_options) - {str(i) for i in range(len(program['functions']))} or set(import_options) - {i['id'] for i in resolved.values()}:
        raise ValueError('unused/unknown native requirement selector')
    modules = []; mapping = {'functions': {}, 'imports': {}}; configs = {}; all_reqs = []
    for kind, objects in (('functions', enumerate(program['functions'])), ('imports', sorted(resolved.items()))):
        for index, obj in objects:
            fn = obj if kind == 'functions' else obj['function']
            constants = presentation['functions'][index]['constants'] if kind == 'functions' else obj['constants']
            key = str(index) if kind == 'functions' else obj['id']
            config = _config((local_options if kind == 'functions' else import_options).get(key, {}))
            style = config.get('arithmetic', arithmetic)
            components = {op: config.get('components', {}).get(op, style) for op in ALU}
            requirements = _extra_requirements(_function_requirements(fn), config.get('requires', []))
            metadata = {'kind': kind, 'index': index,
                        'semantic_id': function_semantic_id(fn, constants) if kind == 'imports' else digest({'function': fn, 'constants': constants})}
            if kind == 'imports': metadata['implementation'] = obj['id']
            module = make_module(kind + '.' + str(index), requirements, metadata=metadata)
            modules.append(module); all_reqs.extend(module['requires']); configs[module['id']] = config
            mapping[kind][str(index)] = {'module': module['id'], 'arithmetic': style,
                                        'components': components, 'semantic_id': metadata['semantic_id']}
            if kind == 'imports': mapping[kind][str(index)]['implementation'] = obj['id']
    builtins = _builtins(target, all_reqs); pins = {}
    for kind in mapping:
        for item in mapping[kind].values():
            item['arithmetic_provider'] = builtins[item['arithmetic']]['id']
            item['component_providers'] = {op: builtins[style]['id'] for op, style in item['components'].items()}
            module = next(m for m in modules if m['id'] == item['module'])
            chosen = {}
            for req in module['requires']:
                op = req['intrinsic'][5:] if req['intrinsic'].startswith('core.') else None
                style = item['components'][op] if op in ALU else ('portable-c' if op else 'runtime')
                if builtins[style]['id'] not in _eligible(req, {p['id']: p for p in builtins.values()}, target):
                    raise ValueError(f'missing compatible intrinsic {req["intrinsic"]}@{req["version"]}')
                chosen[req['id']] = builtins[style]['id']
            explicit = configs[module['id']].get('pins', {})
            for req, provider in explicit.items():
                if req not in chosen or provider != chosen[req]: raise ValueError('unknown/conflicting builtin provider pin')
            pins[module['id']] = chosen
    resolution = resolve_modules(modules, list(builtins.values()), target=target, pins=pins)
    return _seal({'format': 'fdisbull-uil-native-link-1', 'target': target,
                  'closure': {name + '_sha256': digest(doc) for name, doc in zip(('program', 'presentation', 'catalog', 'orchestration'), docs)},
                  'modules': mapping, 'resolution': resolution,
                  'builtin_provider_ids': sorted(p['id'] for p in builtins.values()),
                  'physical_effects': False})


def _check_seal(lock, fields, format_name):
    _fields(lock, (*fields, 'sha256'))
    if lock['format'] != format_name or lock['sha256'] != digest({k: v for k, v in lock.items() if k != 'sha256'}): raise ValueError('stale native link lock identity')


def validate_native_link(lock):
    _check_seal(lock, ('format', 'target', 'closure', 'modules', 'resolution', 'builtin_provider_ids', 'physical_effects'), 'fdisbull-uil-native-link-1')
    _target(lock['target'])
    _fields(lock['closure'], tuple(name + '_sha256' for name in ('program', 'presentation', 'catalog', 'orchestration')))
    if any(type(v) is not str or not re.fullmatch('[0-9a-f]{64}', v) for v in lock['closure'].values()) or lock['physical_effects'] is not False: raise ValueError('invalid native closure/physical effect authority')
    resolution = lock['resolution']
    _check_seal(resolution, ('format', 'target', 'modules', 'providers', 'bindings'), 'fdisbull-udc-link-lock-1')
    if resolution['target'] != lock['target']: raise ValueError('native resolution target mismatch')
    requirements = [r for m in resolution['modules'] for r in m['requires']]
    builtin = _builtins(lock['target'], requirements)
    if lock['builtin_provider_ids'] != sorted(p['id'] for p in builtin.values()): raise ValueError('unknown native builtin provider identity')
    for provider in resolution['providers']:
        if provider not in builtin.values(): raise ValueError('native metadata cannot authorize arbitrary providers')
    pins = {}
    for binding in resolution['bindings']:
        _fields(binding, ('node', 'requirement', 'provider'))
        if binding['requirement'] in pins.setdefault(binding['node'], {}): raise ValueError('duplicate native link edge')
        pins[binding['node']][binding['requirement']] = binding['provider']
    if resolve_modules(resolution['modules'], list(builtin.values()), target=lock['target'], pins=pins) != resolution: raise ValueError('native resolution closure differs')
    _fields(lock['modules'], ('functions', 'imports'))
    modules = {m['id']: m for m in resolution['modules']}; seen = set()
    for kind in ('functions', 'imports'):
        entries = lock['modules'][kind]
        if type(entries) is not dict or len(entries) > 256: raise ValueError('invalid native module map')
        for index, item in entries.items():
            if type(index) is not str or not re.fullmatch('0|[1-9][0-9]*', index): raise ValueError('invalid native module index')
            fields = ('module', 'arithmetic', 'components', 'semantic_id', 'arithmetic_provider', 'component_providers') + (('implementation',) if kind == 'imports' else ())
            _fields(item, fields)
            if item['module'] not in modules or item['module'] in seen: raise ValueError('missing/duplicate native module')
            seen.add(item['module']); module = modules[item['module']]
            if module['metadata'].get('kind') != kind or module['metadata'].get('index') != int(index) or module['metadata'].get('semantic_id') != item['semantic_id']: raise ValueError('native module source identity differs')
            if kind == 'imports' and module['metadata'].get('implementation') != item['implementation']: raise ValueError('selected implementation identity differs')
            if item['arithmetic'] not in ('portable-c', 'native-asm') or item['arithmetic_provider'] != builtin[item['arithmetic']]['id']: raise ValueError('native arithmetic provider differs')
            if type(item['components']) is not dict or set(item['components']) != set(ALU) or type(item['component_providers']) is not dict or set(item['component_providers']) != set(ALU): raise ValueError('incomplete native ALU component map')
            for op, style in item['components'].items():
                if style not in ('portable-c', 'native-asm') or item['component_providers'][op] != builtin[style]['id']: raise ValueError('native ALU child provider differs')
            for req in module['requires']:
                op = req['intrinsic'][5:] if req['intrinsic'].startswith('core.') else None
                style = item['components'][op] if op in ALU else ('portable-c' if op else 'runtime')
                if pins[module['id']][req['id']] != builtin[style]['id']: raise ValueError('native per-operation resolution differs')
    if seen != set(modules): raise ValueError('unmapped native modules')
    return True


def native_arithmetic(lock, kind, index):
    validate_native_link(lock)
    if kind not in ('functions', 'imports') or type(index) is not int or index < 0 or str(index) not in lock['modules'][kind]: raise ValueError('unknown native function/import selector')
    return lock['modules'][kind][str(index)]['arithmetic']


def native_operation_arithmetic(lock, kind, index, op):
    native_arithmetic(lock, kind, index)
    if op not in ALU: raise ValueError('unsupported native ALU child')
    return lock['modules'][kind][str(index)]['components'][op]
