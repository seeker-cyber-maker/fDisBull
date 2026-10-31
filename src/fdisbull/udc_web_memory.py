"""Strict bounded-memory UIL, reference execution and two portable realizations.

This is a separate profile from scalar UIL. It supplies unsigned word memory,
local arithmetic and bounded structured control flow, with no game operations
or implicit host effects. Admission/compilation is not original-code recovery.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

FORMAT = 'fdisbull-memory-uil-1'
BUILD = 'fdisbull-web-memory-block-1'
TARGETS = ('wasm32-memory-1', 'webgpu-wgsl-memory-1')
MAX_WORDS = 131072
MAX_STEPS = 4000000
MASK = 0xffffffff
OPS = {'add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'shr', 'div', 'mod',
       'eq', 'ne', 'lt', 'le', 'gt', 'ge'}
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise ValueError('invalid bounded-memory fields')


def validate_memory_uil(program):
    """Validate the entire finite profile, including unexecuted branches."""
    try:
        raw = _json(program)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('bounded-memory UIL requires finite JSON') from exc
    if len(raw) > 4194304:
        raise ValueError('bounded-memory document budget exceeded')
    _fields(program, ('format', 'role', 'memory', 'variables', 'functions'), ('evidence',))
    if program['format'] != FORMAT or program['role'] not in ('udl', 'uil'):
        raise ValueError('invalid bounded-memory format/role')
    _fields(program['memory'], ('words',))
    if not _integer(program['memory']['words'], 1, MAX_WORDS):
        raise ValueError('bounded-memory word count outside profile')
    variables = program['variables']
    if type(variables) is not dict or len(variables) > 256:
        raise ValueError('invalid bounded-memory variables')
    for name, decl in variables.items():
        if not isinstance(name, str) or not name.startswith('$') or not NAME.fullmatch(name[1:]):
            raise ValueError('invalid local name')
        _fields(decl, ('type', 'initial'))
        if decl['type'] != 'u32' or not _integer(decl['initial'], 0, MASK):
            raise ValueError('bounded-memory locals require unsigned words')
    evidence = program.get('evidence', {})
    if type(evidence) is not dict or any(not isinstance(k, str) or not k or type(v) is not dict for k, v in evidence.items()):
        raise ValueError('invalid bounded-memory evidence')
    functions = program['functions']
    if type(functions) is not dict or not 1 <= len(functions) <= 32:
        raise ValueError('invalid bounded-memory functions')
    count = 0
    def expr(value, depth=0):
        nonlocal count
        count += 1
        if count > 65536 or depth > 48:
            raise ValueError('bounded-memory expression budget exceeded')
        if _integer(value, 0, MASK):
            return
        if type(value) is not dict:
            raise ValueError('invalid unsigned expression')
        if set(value) == {'var'}:
            if not isinstance(value['var'], str) or value['var'] not in variables:
                raise ValueError('unknown bounded-memory local')
        elif set(value) == {'load'}:
            expr(value['load'], depth + 1)
        elif set(value) == {'op', 'left', 'right'} and isinstance(value['op'], str) and value['op'] in OPS:
            expr(value['left'], depth + 1); expr(value['right'], depth + 1)
        else:
            raise ValueError('unsupported bounded-memory expression')
    for name, function in functions.items():
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError('invalid bounded-memory function name')
        _fields(function, ('body', 'max_steps'))
        if not _integer(function['max_steps'], 1, MAX_STEPS):
            raise ValueError('invalid bounded-memory execution budget')
        ids = set()
        def body(nodes, depth=0):
            nonlocal count
            if type(nodes) is not list or depth > 32:
                raise ValueError('bounded-memory statement depth exceeded')
            for n in nodes:
                count += 1
                if count > 65536 or type(n) is not dict:
                    raise ValueError('bounded-memory node budget exceeded')
                fields = {'set': ('var', 'value'), 'store': ('index', 'value'),
                          'if': ('condition', 'then', 'else'),
                          'while': ('condition', 'limit', 'body'), 'return': ()}
                if not isinstance(n.get('op'), str) or n['op'] not in fields:
                    raise ValueError('unsupported bounded-memory operation')
                _fields(n, ('op', *fields[n['op']]), ('id', 'evidence'))
                if 'id' in n:
                    if not isinstance(n['id'], str) or not n['id'] or n['id'] in ids:
                        raise ValueError('duplicate or invalid bounded-memory node id')
                    ids.add(n['id'])
                if type(n.get('evidence', [])) is not list or any(not isinstance(k, str) or k not in evidence for k in n.get('evidence', [])):
                    raise ValueError('unknown bounded-memory evidence reference')
                op = n['op']
                if op == 'set':
                    if not isinstance(n['var'], str) or n['var'] not in variables:
                        raise ValueError('unknown bounded-memory local')
                    expr(n['value'])
                elif op == 'store':
                    expr(n['index']); expr(n['value'])
                elif op == 'if':
                    expr(n['condition']); body(n['then'], depth + 1); body(n['else'], depth + 1)
                elif op == 'while':
                    if not _integer(n['limit'], 1, 1000000):
                        raise ValueError('invalid bounded loop limit')
                    expr(n['condition']); body(n['body'], depth + 1)
        body(function['body'])
    # Normalize the JSON tree, including callers that reused Python node objects.
    # Object aliasing is not an extra semantic feature or a compiler local key.
    return json.loads(raw)


def _words(program, words):
    if not isinstance(words, (list, tuple)) or len(words) != program['memory']['words'] or any(not _integer(v, 0, MASK) for v in words):
        raise ValueError('expected exact unsigned word arena')
    return list(words)


class _Refuse(Exception):
    pass


class _Return(Exception):
    pass


def execute_memory_uil(program, function, words):
    """Execute atomically at the public arena boundary; return owned words."""
    validate_memory_uil(program)
    if not isinstance(function, str) or function not in program['functions']:
        raise ValueError('unknown bounded-memory function')
    original = _words(program, words)
    work = original.copy()
    local = {k: v['initial'] for k, v in program['variables'].items()}
    remaining = program['functions'][function]['max_steps']
    used = 0
    def charge():
        nonlocal remaining, used
        if remaining == 0:
            raise _Refuse('execution budget exhausted')
        remaining -= 1; used += 1
    def expr(v):
        if type(v) is int:
            return v
        if 'var' in v:
            return local[v['var']]
        if 'load' in v:
            i = expr(v['load'])
            if i >= len(work):
                raise _Refuse('load outside arena')
            return work[i]
        a, b, op = expr(v['left']), expr(v['right']), v['op']
        if op in ('div', 'mod') and b == 0:
            raise _Refuse('zero divisor')
        if op == 'add': return (a + b) & MASK
        if op == 'sub': return (a - b) & MASK
        if op == 'mul': return (a * b) & MASK
        if op == 'and': return a & b
        if op == 'or': return a | b
        if op == 'xor': return a ^ b
        if op == 'shl': return (a << (b & 31)) & MASK
        if op == 'shr': return a >> (b & 31)
        if op == 'div': return a // b
        if op == 'mod': return a % b
        return int({'eq': a == b, 'ne': a != b, 'lt': a < b, 'le': a <= b, 'gt': a > b, 'ge': a >= b}[op])
    def run(nodes):
        for n in nodes:
            charge()
            op = n['op']
            if op == 'set': local[n['var']] = expr(n['value'])
            elif op == 'store':
                i, value = expr(n['index']), expr(n['value'])
                if i >= len(work): raise _Refuse('store outside arena')
                work[i] = value
            elif op == 'if': run(n['then'] if expr(n['condition']) else n['else'])
            elif op == 'return': raise _Return()
            else:
                iterations = 0
                while True:
                    charge()
                    if not expr(n['condition']): break
                    if iterations == n['limit']: raise _Refuse('loop limit exhausted')
                    iterations += 1
                    run(n['body'])
    try:
        run(program['functions'][function]['body'])
    except _Return:
        pass
    except _Refuse as exc:
        return {'status': 'refused', 'words': original, 'steps': used, 'error': str(exc)}
    return {'status': 'complete', 'words': work, 'steps': used}


def _leb(value, signed=False):
    out = bytearray()
    while True:
        b = value & 127; value >>= 7
        done = (value == 0 and not b & 64) or (value == -1 and bool(b & 64)) if signed else value == 0
        out.append(b if done else b | 128)
        if done: return bytes(out)


def _vec(values):
    return _leb(len(values)) + b''.join(values)


def _section(number, data):
    return bytes([number]) + _leb(len(data)) + data


def _wasm(program, function, report_steps=False, capture_locals=()):
    """Direct Wasm encoding; no external compiler or target-specific formula."""
    variables = sorted(program['variables'])
    indices = {name: n for n, name in enumerate(variables)}
    loops = {}
    def discover(nodes):
        for n in nodes:
            if n['op'] == 'while':
                loops[id(n)] = len(variables) + 1 + len(loops)
                discover(n['body'])
            elif n['op'] == 'if': discover(n['then']); discover(n['else'])
    spec = program['functions'][function]
    discover(spec['body'])
    steps = len(variables)
    def const(v): return b'\x41' + _leb(v if v < 0x80000000 else v - 0x100000000, True)
    def get(i): return b'\x20' + _leb(i)
    def put(i): return b'\x21' + _leb(i)
    # The opt-in global survives a trap so the owner can charge refused work.
    # The ordinary profile keeps its original local and byte encoding.
    def get_steps(): return b'\x23\x00' if report_steps else get(steps)
    def put_steps(): return b'\x24\x00' if report_steps else put(steps)
    def capture():
        return b''.join(get(indices[name]) + b'\x24' + _leb(i + int(report_steps))
                        for i, name in enumerate(capture_locals))
    def when(condition, yes, no=None):
        return condition + b'\x04\x40' + yes + (b'\x05' + no if no is not None else b'') + b'\x0b'
    refuse = const(1) + b'\x0f'
    def charge():
        return when(get_steps() + b'\x45', refuse) + get_steps() + const(1) + b'\x6b' + put_steps()
    opcode = {'add': 0x6a, 'sub': 0x6b, 'mul': 0x6c, 'and': 0x71, 'or': 0x72,
              'xor': 0x73, 'shl': 0x74, 'shr': 0x76, 'div': 0x6e, 'mod': 0x70,
              'eq': 0x46, 'ne': 0x47, 'lt': 0x49, 'le': 0x4d, 'gt': 0x4b, 'ge': 0x4f}
    def expr(v):
        if type(v) is int: return const(v)
        if 'var' in v: return get(indices[v['var']])
        if 'load' in v: return expr(v['load']) + b'\x10\x01'
        return expr(v['left']) + expr(v['right']) + bytes([opcode[v['op']]])
    def body(nodes):
        out = b''
        for n in nodes:
            out += charge()
            op = n['op']
            if op == 'set': out += expr(n['value']) + put(indices[n['var']])
            elif op == 'store': out += expr(n['index']) + expr(n['value']) + b'\x10\x02'
            elif op == 'return': out += capture() + const(0) + b'\x0f'
            elif op == 'if': out += when(expr(n['condition']), body(n['then']), body(n['else']))
            else:
                counter = loops[id(n)]
                out += const(0) + put(counter) + b'\x02\x40\x03\x40'
                out += charge() + expr(n['condition']) + b'\x45\x0d\x01'
                out += when(get(counter) + const(n['limit']) + b'\x4f', refuse)
                out += get(counter) + const(1) + b'\x6a' + put(counter)
                out += body(n['body']) + b'\x0c\x00\x0b\x0b'
        return out
    local_count = len(variables) + 1 + len(loops)
    code = _leb(1) + _leb(local_count) + b'\x7f'
    for name in variables: code += const(program['variables'][name]['initial']) + put(indices[name])
    code += const(spec['max_steps']) + put_steps() + body(spec['body']) + capture() + const(0) + b'\x0b'
    words = program['memory']['words']
    load = b'\x00' + when(get(0) + const(words) + b'\x4f', b'\x00') + get(0) + const(2) + b'\x74\x28\x02\x00\x0b'
    store = b'\x00' + when(get(0) + const(words) + b'\x4f', b'\x00') + get(0) + const(2) + b'\x74' + get(1) + b'\x36\x02\x00\x0b'
    signatures = [b'\x60' + _vec([]) + _vec([b'\x7f']),
                  b'\x60' + _vec([b'\x7f']) + _vec([b'\x7f']),
                  b'\x60' + _vec([b'\x7f', b'\x7f']) + _vec([])]
    pages = (words * 4 + 65535) // 65536
    exports = [_leb(5) + b'block\x00\x00', _leb(6) + b'memory\x02\x00']
    if report_steps:
        exports.append(_leb(9) + b'remaining\x03\x00')
    for i, name in enumerate(capture_locals):
        exported = ('capture_' + str(i)).encode()
        exports.append(_leb(len(exported)) + exported + b'\x03' + _leb(i + int(report_steps)))
    globals_ = [b'\x7f\x01\x41\x00\x0b'] * (int(report_steps) + len(capture_locals))
    return (b'\0asm\x01\0\0\0' + _section(1, _vec(signatures))
            + _section(3, _vec([b'\x00', b'\x01', b'\x02']))
            + _section(5, _vec([b'\x01' + _leb(pages) + _leb(pages)]))
            + (_section(6, _vec(globals_)) if globals_ else b'')
            + _section(7, _vec(exports))
            + _section(10, _vec([_leb(len(c)) + c for c in (code, load, store)])))


def _wgsl(program, function, report_steps=False, capture_locals=()):
    words = program['memory']['words']
    names = {n: 'v' + str(i) for i, n in enumerate(sorted(program['variables']))}
    spec = program['functions'][function]
    operators = {'add': '+', 'sub': '-', 'mul': '*', 'and': '&', 'or': '|', 'xor': '^',
                 'eq': '==', 'ne': '!=', 'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>='}
    def expr(v):
        if type(v) is int: return str(v) + 'u'
        if 'var' in v: return names[v['var']]
        if 'load' in v: return 'get_word(' + expr(v['load']) + ')'
        a, b, op = expr(v['left']), expr(v['right']), v['op']
        if op in ('div', 'mod'): return ('divide' if op == 'div' else 'remainder') + '(' + a + ',' + b + ')'
        # WGSL constant expressions reject overflow instead of wrapping. Calls
        # make literal-only UIL arithmetic runtime u32 arithmetic as required.
        if op in ('add', 'sub', 'mul', 'shl', 'shr'):
            return 'word_' + op + '(' + a + ',' + b + ')'
        value = '(' + a + ' ' + operators[op] + ' ' + b + ')'
        return 'select(0u,1u,' + value + ')' if op in ('eq', 'ne', 'lt', 'le', 'gt', 'ge') else value
    counters = [0]
    def capture(indent='  '):
        return [indent + 'captured_' + str(i) + ' = ' + names[name] + ';'
                for i, name in enumerate(capture_locals)]
    def body(nodes, indent='  '):
        lines = []
        for n in nodes:
            lines.append(indent + 'if (!charge()) { return; }')
            op = n['op']
            if op == 'set': lines.append(indent + names[n['var']] + ' = ' + expr(n['value']) + ';')
            elif op == 'store': lines.append(indent + 'put_word(' + expr(n['index']) + ',' + expr(n['value']) + ');')
            elif op == 'return':
                lines += capture(indent) + [indent + 'return;']
                continue
            elif op == 'if':
                # Evaluate once, then reject expression faults before taking a branch.
                ident = 'c' + str(counters[0]); counters[0] += 1
                lines += [indent + 'let ' + ident + ' = ' + expr(n['condition']) + ';',
                          indent + 'if (failed) { return; }', indent + 'if (' + ident + ' != 0u) {',
                          *body(n['then'], indent + '  '), indent + '} else {',
                          *body(n['else'], indent + '  '), indent + '}']
            else:
                ident = 'loop' + str(counters[0]); counters[0] += 1
                lines += [indent + '{', indent + '  var ' + ident + ':u32 = 0u;', indent + '  loop {',
                          indent + '    if (!charge()) { return; }',
                          indent + '    let test = ' + expr(n['condition']) + ';',
                          indent + '    if (failed) { return; }', indent + '    if (test == 0u) { break; }',
                          indent + '    if (' + ident + ' >= ' + str(n['limit']) + 'u) { failed=true; return; }',
                          indent + '    ' + ident + ' += 1u;', *body(n['body'], indent + '    '),
                          indent + '  }', indent + '}']
            lines.append(indent + 'if (failed) { return; }')
        return lines
    lines = ['@group(0) @binding(0) var<storage,read> in_words:array<u32>;',
             '@group(0) @binding(1) var<storage,read_write> out_words:array<u32>;',
             'var<private> failed:bool = false;',
             'var<private> remaining:u32 = ' + str(spec['max_steps']) + 'u;',
             'fn charge()->bool { if (remaining==0u) { failed=true; return false; } remaining-=1u; return true; }',
             'fn get_word(i:u32)->u32 { if (i>=' + str(words) + 'u) { failed=true; return 0u; } return out_words[i+1u]; }',
             'fn put_word(i:u32,v:u32) { if (i>=' + str(words) + 'u) { failed=true; return; } out_words[i+1u]=v; }',
             'fn divide(a:u32,b:u32)->u32 { if (b==0u) { failed=true; return 0u; } return a/b; }',
             'fn remainder(a:u32,b:u32)->u32 { if (b==0u) { failed=true; return 0u; } return a%b; }',
             'fn word_add(a:u32,b:u32)->u32 { return a+b; }',
             'fn word_sub(a:u32,b:u32)->u32 { return a-b; }',
             'fn word_mul(a:u32,b:u32)->u32 { return a*b; }',
             'fn word_shl(a:u32,b:u32)->u32 { return a << (b & 31u); }',
             'fn word_shr(a:u32,b:u32)->u32 { return a >> (b & 31u); }',
             *['var<private> captured_' + str(i) + ':u32 = 0u;' for i in range(len(capture_locals))],
             'fn run() {']
    lines += ['  var ' + names[n] + ':u32 = ' + str(d['initial']) + 'u;' for n, d in sorted(program['variables'].items())]
    fallthrough_capture = capture() if not spec['body'] or spec['body'][-1]['op'] != 'return' else []
    lines += body(spec['body']) + fallthrough_capture + ['}', '@compute @workgroup_size(1) fn main() {',
              '  for (var i=0u;i<' + str(words) + 'u;i+=1u) { out_words[i+1u]=in_words[i]; }',
              '  run();', '  if (failed) {',
              '    for (var i=0u;i<' + str(words) + 'u;i+=1u) { out_words[i+1u]=in_words[i]; }',
              '    out_words[0]=1u;', '  } else { out_words[0]=0u; }']
    if report_steps:
        lines.append('  out_words[' + str(words + 1) + 'u]=' + str(spec['max_steps']) + 'u-remaining;')
    for i, name in enumerate(capture_locals):
        lines.append('  out_words[' + str(words + 1 + int(report_steps) + i) + 'u]=captured_' + str(i) + ';')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def build_memory_block(program, function, target, destination, *, report_steps=False, capture_locals=()):
    """Build one named function; generated artifacts must remain outside Git."""
    program = validate_memory_uil(program)
    if type(report_steps) is not bool:
        raise ValueError('execution-step reporting requires a boolean')
    if type(capture_locals) not in (list, tuple) or any(type(name) is not str or name not in program['variables'] for name in capture_locals) or len(set(capture_locals)) != len(capture_locals):
        raise ValueError('local capture requires distinct declared local names')
    capture_locals = sorted(capture_locals)
    if not isinstance(function, str) or function not in program['functions'] or target not in TARGETS:
        raise ValueError('unsupported bounded-memory function/target')
    destination = Path(destination).expanduser().absolute()
    if os.path.lexists(destination):
        raise ValueError('bounded-memory output must be new and outside Git')
    destination = destination.resolve()
    if any((p / '.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('bounded-memory output must be new and outside Git')
    artifact = 'block.wasm' if target == TARGETS[0] else 'block.wgsl'
    data = _wasm(program, function, report_steps, capture_locals) if target == TARGETS[0] else _wgsl(program, function, report_steps, capture_locals).encode()
    receipt = {'format': BUILD, 'target': target, 'function': function,
               'module_uil_sha256': digest(program), 'execution': False, 'source_to_uil': False,
               'abi': {'format': 'fdisbull-web-memory-abi-1', 'memory_words': program['memory']['words'],
                       'word': 'u32-le', 'max_steps': program['functions'][function]['max_steps'],
                       'status': {'complete': 0, 'refused': 1}},
               'artifacts': {artifact: hashlib.sha256(data).hexdigest()},
               'scope': 'one bounded-memory function; no services; atomic public arena result; original fidelity checked separately'}
    if report_steps:
        receipt['abi']['report_steps'] = True
    if capture_locals:
        receipt['abi']['capture_locals'] = capture_locals
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    (destination / artifact).write_bytes(data)
    (destination / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
