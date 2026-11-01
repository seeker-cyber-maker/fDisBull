"""Exact semantic catalog and deliberately bounded source-to-common-UIL adapters.

An identity covers a normalized *model*, not proof of its source correspondence.
Native instructions are decoded by Capstone, never inferred from source labels.
Unsupported source is refused, including unsupported unreachable source branches.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import re

FORMAT = 'fdisbull-uil-catalog-1'
_ID = re.compile(r'semantic:[0-9a-f]{64}\Z')
_IMPL = re.compile(r'implementation:[0-9a-f]{64}\Z')
_INTEGER = re.compile(r'(?:0|-?[1-9][0-9]*)\Z')
_REGS = ('ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di')
_SERVICES = {'text.show', 'image.show', 'sound.play', 'music.start', 'music.stop'}


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('expected finite JSON') from exc


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('invalid catalog/adapter fields')


def _constant(value, descriptor):
    typ = descriptor['type']
    if typ == 'bool':
        if type(value) is not bool:
            raise ValueError('boolean constant required')
        return value
    if typ in ('resource', 'text'):
        if typ == 'resource' and (type(value) is not int or not 0 <= value < (1 << 31)):
            raise ValueError('invalid resource constant')
        if typ == 'text' and (not isinstance(value, str) or len(value.encode('utf-8')) > 1048576):
            raise ValueError('invalid text constant')
        return value
    if re.fullmatch(r'[ui](8|16|32|64)', typ):
        if isinstance(value, str):
            if not _INTEGER.fullmatch(value):
                raise ValueError('integer constant must use canonical decimal')
            integer = int(value)
        elif type(value) is int:
            integer = value
        else:
            raise ValueError('invalid integer constant')
        bits = int(typ[1:])
        low, high = (0, (1 << bits) - 1) if typ[0] == 'u' else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)
        if not low <= integer <= high:
            raise ValueError('constant outside declared type')
        return str(integer)
    raise ValueError('only scalar constants are supported')


def _closed(function):
    from .common_uil import validate_function
    validate_function(function)
    def visit(nodes):
        for node in nodes:
            if node['op'] in ('call', 'invoke'):
                raise ValueError('catalog functions must be closed: call/invoke belongs to orchestration')
            if node['op'] == 'group':
                visit(node['body'])
            elif node['op'] == 'if':
                visit(node['then']); visit(node['else'])
            elif node['op'] == 'while':
                visit(node['body'])
    visit(function['body'])


def _effects(function):
    found = set()
    def visit(nodes):
        for node in nodes:
            if node['op'] == 'effect': found.add(node['service'])
            elif node['op'] == 'if': visit(node['then']); visit(node['else'])
            elif node['op'] in ('group', 'while'): visit(node['body'])
    visit(function['body'])
    return sorted(found)


def canonical_function(function, constants):
    """Return port-first alpha-normal form plus its typed constant pool.

    This removes transparent groups and unused declarations, and renumbers
    referenced constants by first use. It does not reorder arithmetic, inline
    temporaries, discard charged statements, or guess algebraic equivalence.
    Execution budgets remain part of the definition.
    """
    _closed(function)
    if type(constants) is not list or len(constants) != len(function['constants']):
        raise ValueError('constant table does not match function')
    values = [_constant(v, t) for v, t in zip(constants, function['constants'])]
    variables, consts, normalized_values = [], [], []
    vmap, cmap = {}, {}
    def variable(index):
        if index not in vmap:
            vmap[index] = len(variables)
            variables.append(deepcopy(function['variables'][index]))
        return vmap[index]
    inputs = [variable(i) for i in function['inputs']]
    outputs = [variable(i) for i in function['outputs']]
    def constant(index):
        key = _json([function['constants'][index], values[index]])
        if key not in cmap:
            cmap[key] = len(consts)
            consts.append(deepcopy(function['constants'][index]))
            normalized_values.append(deepcopy(values[index]))
        return cmap[key]
    def expression(expr):
        if set(expr) == {'var'}: return {'var': variable(expr['var'])}
        if set(expr) == {'const'}: return {'const': constant(expr['const'])}
        if expr['op'] == 'load':
            return {'op': 'load', 'array': variable(expr['array']), 'index': expression(expr['index'])}
        return {'op': expr['op'], 'type': expr['type'], 'args': [expression(x) for x in expr['args']]}
    def body(nodes):
        result = []
        for node in nodes:
            op = node['op']
            if op == 'group':
                result.extend(body(node['body'])); continue
            item = {'op': op}
            if op == 'set': item.update(dst=variable(node['dst']), value=expression(node['value']))
            elif op == 'store': item.update(array=variable(node['array']), index=expression(node['index']), value=expression(node['value']))
            elif op == 'if': item.update(condition=expression(node['condition']), then=body(node['then']), **{'else': body(node['else'])})
            elif op == 'while': item.update(condition=expression(node['condition']), limit=node['limit'], body=body(node['body']))
            elif op == 'require': item['condition'] = expression(node['condition'])
            elif op == 'effect': item.update(service=node['service'], inputs=[expression(x) for x in node['inputs']])
            elif op != 'return': raise ValueError('unsupported catalog statement')
            result.append(item)
        return result
    normalized_body = body(function['body'])
    return {'format': 'fdisbull-common-function-semantics-1', 'function': {
        'variables': variables, 'constants': consts, 'inputs': inputs, 'outputs': outputs,
        'max_steps': function['max_steps'], 'body': normalized_body},
        'constants': normalized_values}


def function_semantic_id(function, constants):
    return 'semantic:' + _digest(canonical_function(function, constants))


def _metadata(source):
    if source is None: return {}
    if type(source) is not dict or len(_json(source)) > 65536:
        raise ValueError('source must be bounded metadata only')
    forbidden = {'code', 'code_hex', 'source_text', 'payload', 'data', 'raw', 'bytes_hex', 'initial_memory', 'program', 'body'}
    def visit(item, depth=0):
        if depth > 24: raise ValueError('source metadata depth exceeded')
        if isinstance(item, dict):
            if any(not isinstance(k, str) or k in forbidden for k in item):
                raise ValueError('raw source is not permitted in source metadata')
            for value in item.values(): visit(value, depth + 1)
        elif isinstance(item, list):
            for value in item: visit(value, depth + 1)
        elif item is not None and type(item) not in (str, int, bool):
            raise ValueError('source metadata requires finite integer/string JSON')
    visit(source)
    return json.loads(_json(source))


def _with_source(imported, source, raw=None):
    metadata = _metadata(source)
    if raw is not None:
        sha = hashlib.sha256(raw).hexdigest()
        if 'sha256' in metadata and metadata['sha256'] != sha:
            raise ValueError('supplied source digest mismatch')
        metadata['sha256'] = sha
        metadata['size'] = len(raw)
    # Decoder/adapter facts cannot be replaced with caller claims.
    overlap = metadata.keys() & imported['source'].keys()
    if any(metadata[k] != imported['source'][k] for k in overlap):
        raise ValueError('source metadata disagrees with admitted source facts')
    imported['source'] = {**metadata, **imported['source']}
    return imported


def _result(function, constants, language, source=None, assurance=None):
    _closed(function)
    if type(constants) is not list or len(constants) != len(function['constants']):
        raise ValueError('constant table mismatch')
    constants = [_constant(v, t) for v, t in zip(constants, function['constants'])]
    return {'function': function, 'constants': constants, 'language': language,
            'source': _metadata(source), 'assurance': assurance or 'source correspondence declaration; bounded model only; not original-code or native-execution proof'}


class _Builder:
    def __init__(self, variables, inputs, outputs, max_steps=1024):
        self.function = {'variables': deepcopy(variables), 'constants': [], 'inputs': inputs,
                         'outputs': outputs, 'max_steps': max_steps, 'body': []}
        self.constants = []
        self._constant_indices = {}
    def constant(self, value, typ):
        descriptor = {'type': typ}; value = _constant(value, descriptor)
        key = (typ, _json(value))
        if key in self._constant_indices:
            return {'const': self._constant_indices[key]}
        self._constant_indices[key] = len(self.constants)
        self.function['constants'].append(descriptor); self.constants.append(value)
        return {'const': len(self.constants) - 1}
    def variable(self, typ):
        self.function['variables'].append({'type': typ})
        return len(self.function['variables']) - 1


def _op(op, typ, *args):
    return {'op': op, 'type': typ, 'args': list(args)}


def _cast(value, typ):
    return _op('cast', typ, value)


def from_scalar_il(program, inputs, outputs):
    """Import pure legacy scalar IL; preserve checked set versus wrapping math."""
    from .interaction_il import validate_il
    validate_il(program)
    names = sorted(program['variables'])
    if not isinstance(inputs, list) or not isinstance(outputs, list) or len(set(inputs)) != len(inputs) or len(set(outputs)) != len(outputs) or not set(inputs + outputs) <= set(names):
        raise ValueError('invalid scalar adapter ports')
    indices = {name: i for i, name in enumerate(names)}
    types = {name: program['variables'][name]['type'] for name in names}
    b = _Builder([{'type': types[n]} for n in names], [indices[n] for n in inputs], [indices[n] for n in outputs])
    def value(v, typ=None):
        if isinstance(v, dict):
            expr = {'var': indices[v['var']]}; own = types[v['var']]
            return _cast(expr, typ) if typ is not None and typ != own else expr
        return b.constant(v, typ or ('bool' if type(v) is bool else 'u64'))
    false = lambda: b.constant(False, 'bool')
    true = lambda: b.constant(True, 'bool')
    def conjunction(conditions):
        result = true()
        for condition in reversed(conditions): result = _op('select', 'bool', condition, result, false())
        return result
    def condition(c):
        op = c['op']
        if op == 'not': return _op('not', 'bool', condition(c['condition']))
        if op == 'and': return conjunction([condition(x) for x in c['conditions']])
        if op == 'bit_test':
            v = c['value']
            expr = value(v, 'u64') if isinstance(v, dict) else b.constant(v % (1 << 64), 'u64')
            return _op('ne', 'bool', _op('and', 'u64', expr, b.constant(1 << c['bit'], 'u64')), b.constant(0, 'u64'))
        left, right = c['left'], c['right']
        if not isinstance(left, dict) and not isinstance(right, dict): return b.constant(left == right, 'bool')
        if isinstance(left, dict) and isinstance(right, dict):
            lt, rt = types[left['var']], types[right['var']]
            if lt == rt: return _op('eq', 'bool', value(left), value(right))
            guards = []
            for item, typ in ((left, lt), (right, rt)):
                if typ.startswith('i'): guards.append(_op('ge', 'bool', value(item), b.constant(0, typ)))
            equal = _op('eq', 'bool', value(left, 'u64'), value(right, 'u64'))
            # Both signed values must retain negative equality as well.
            if lt.startswith('i') and rt.startswith('i'):
                return _op('eq', 'bool', value(left, 'i64'), value(right, 'i64'))
            return conjunction(guards + [equal])
        var, literal = (left, right) if isinstance(left, dict) else (right, left)
        typ = types[var['var']]
        try: constant = b.constant(literal, typ)
        except ValueError: return false()
        return _op('eq', 'bool', value(var), constant)
    def assignment_guard(v, typ):
        if not isinstance(v, dict) or types[v['var']] == typ: return []
        source_type = types[v['var']]
        if typ == 'bool' or source_type == 'bool': raise ValueError('incompatible scalar assignment')
        width, swidth = int(typ[1:]), int(source_type[1:])
        lo, hi = (0, (1 << width) - 1) if typ[0] == 'u' else (-(1 << (width - 1)), (1 << (width - 1)) - 1)
        slo, shi = (0, (1 << swidth) - 1) if source_type[0] == 'u' else (-(1 << (swidth - 1)), (1 << (swidth - 1)) - 1)
        guards = []
        if slo < lo: guards.append(_op('ge', 'bool', value(v), b.constant(lo, source_type)))
        if shi > hi: guards.append(_op('le', 'bool', value(v), b.constant(hi, source_type)))
        return [{'op': 'require', 'condition': guard} for guard in guards]
    def body(nodes):
        result = []
        for node in nodes:
            op = node['op']
            if op in ('set', 'add', 'subtract'):
                name = node['var']; typ = types[name]
                if op == 'set': result.extend(assignment_guard(node['value'], typ))
                expr = value(node['value'], typ)
                if op != 'set': expr = _op('add' if op == 'add' else 'sub', typ, {'var': indices[name]}, expr)
                result.append({'op': 'set', 'dst': indices[name], 'value': expr})
            elif op == 'if': result.append({'op': 'if', 'condition': condition(node['condition']), 'then': body(node['then']), 'else': body(node['else'])})
            elif op == 'require': result.append({'op': 'require', 'condition': condition(node['condition'])})
            else: raise ValueError('legacy scalar host effects require an explicit resource/host adapter')
        return result
    prefix = [{'op': 'set', 'dst': indices[n], 'value': b.constant(program['variables'][n]['initial'], types[n])}
              for n in names if n not in inputs and program['variables'][n]['initial'] not in (0, False)]
    b.function['body'] = prefix + body(program['body'])
    def count(nodes):
        return sum(1 + (count(n['then']) + count(n['else']) if n['op'] == 'if' else 0) for n in nodes)
    # Prefix initialization and checked narrowing add statements. The base
    # budget stays identical for the ordinary one-statement source adapters.
    b.function['max_steps'] += max(0, count(b.function['body']) - count(program['body']))
    return _result(b.function, b.constants, 'scalar-il', {
        'sha256': _digest(program), 'format': program['format'],
        'inputs': list(inputs), 'outputs': list(outputs),
        'evidence': _metadata(program.get('evidence', {})),
        'budget_scope': 'common statement/guard budget; not identical legacy refusal timing'})


def _memory_validate(program):
    """Admit the frozen legacy grammar without importing an unmerged branch."""
    if len(_json(program)) > 4194304: raise ValueError('legacy memory document budget exceeded')
    _fields(program, ('format', 'role', 'memory', 'variables', 'functions'), ('evidence',))
    if program['format'] != 'fdisbull-memory-uil-1' or program['role'] not in ('udl', 'uil'): raise ValueError('invalid legacy memory format')
    _fields(program['memory'], ('words',))
    integer = lambda x, lo, hi: type(x) is int and lo <= x <= hi
    if not integer(program['memory']['words'], 1, 131072): raise ValueError('invalid legacy arena length')
    variables, functions = program['variables'], program['functions']
    if type(variables) is not dict or len(variables) > 256 or type(functions) is not dict or not 1 <= len(functions) <= 32: raise ValueError('invalid legacy memory declarations')
    name = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
    for key, decl in variables.items():
        if not isinstance(key, str) or not key.startswith('$') or not name.fullmatch(key[1:]): raise ValueError('invalid legacy local')
        _fields(decl, ('type', 'initial'))
        if decl['type'] != 'u32' or not integer(decl['initial'], 0, 0xffffffff): raise ValueError('invalid legacy local type/default')
    evidence = program.get('evidence', {})
    if type(evidence) is not dict or any(not isinstance(k, str) or not k or type(v) is not dict for k, v in evidence.items()): raise ValueError('invalid legacy evidence')
    count = [0]
    def charge(depth, limit):
        count[0] += 1
        if count[0] > 65536 or depth > limit: raise ValueError('legacy memory node/depth budget exceeded')
    def expr(v, depth=0):
        charge(depth, 48)
        if integer(v, 0, 0xffffffff): return
        if type(v) is not dict: raise ValueError('invalid legacy memory expression')
        if set(v) == {'var'}:
            if not isinstance(v['var'], str) or v['var'] not in variables: raise ValueError('unknown legacy local')
        elif set(v) == {'load'}: expr(v['load'], depth + 1)
        elif set(v) == {'op', 'left', 'right'} and v['op'] in ('add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'shr', 'div', 'mod', 'eq', 'ne', 'lt', 'le', 'gt', 'ge'):
            expr(v['left'], depth + 1); expr(v['right'], depth + 1)
        else: raise ValueError('unsupported legacy memory expression')
    for key, function in functions.items():
        if not isinstance(key, str) or not name.fullmatch(key): raise ValueError('invalid legacy function name')
        _fields(function, ('body', 'max_steps'))
        if not integer(function['max_steps'], 1, 4000000): raise ValueError('invalid legacy execution budget')
        ids = set()
        def body(nodes, depth=0):
            if type(nodes) is not list or depth > 32: raise ValueError('invalid legacy statement list/depth')
            for node in nodes:
                charge(depth, 32)
                if type(node) is not dict: raise ValueError('invalid legacy statement')
                op = node.get('op')
                fields = {'set': ('var', 'value'), 'store': ('index', 'value'), 'if': ('condition', 'then', 'else'), 'while': ('condition', 'limit', 'body'), 'return': ()}
                if not isinstance(op, str) or op not in fields: raise ValueError('unsupported legacy memory operation')
                _fields(node, ('op', *fields[op]), ('id', 'evidence'))
                if 'id' in node:
                    if not isinstance(node['id'], str) or not node['id'] or node['id'] in ids: raise ValueError('invalid legacy statement id')
                    ids.add(node['id'])
                if type(node.get('evidence', [])) is not list or any(not isinstance(k, str) or k not in evidence for k in node.get('evidence', [])): raise ValueError('unknown legacy evidence')
                if op == 'set':
                    if node['var'] not in variables: raise ValueError('unknown legacy set local')
                    expr(node['value'])
                elif op == 'store': expr(node['index']); expr(node['value'])
                elif op in ('if', 'while'):
                    expr(node['condition'])
                    if op == 'if': body(node['then'], depth + 1); body(node['else'], depth + 1)
                    else:
                        if not integer(node['limit'], 1, 1000000): raise ValueError('invalid legacy loop bound')
                        body(node['body'], depth + 1)
        body(function['body'])


def from_memory_uil(program, function_name):
    """Import one legacy arena function; arena slot0 is copied input/output."""
    _memory_validate(program)
    if not isinstance(function_name, str) or function_name not in program['functions']: raise ValueError('unknown legacy memory function')
    names = sorted(program['variables']); indices = {name: i + 1 for i, name in enumerate(names)}
    selected = program['functions'][function_name]
    b = _Builder([{'type': 'u32-array', 'length': program['memory']['words']}] + [{'type': 'u32'} for _ in names], [0], [0], selected['max_steps'])
    comparisons = {'eq', 'ne', 'lt', 'le', 'gt', 'ge'}
    def expr(v):
        if type(v) is int: return b.constant(v, 'u32')
        if 'var' in v: return {'var': indices[v['var']]}
        if 'load' in v: return {'op': 'load', 'array': 0, 'index': expr(v['load'])}
        op = v['op']; left, right = expr(v['left']), expr(v['right'])
        if op in ('shl', 'shr'): right = _op('and', 'u32', right, b.constant(31, 'u32'))
        result = _op(op, 'bool' if op in comparisons else 'u32', left, right)
        return _cast(result, 'u32') if op in comparisons else result
    def condition(v): return _op('ne', 'bool', expr(v), b.constant(0, 'u32'))
    def body(nodes):
        result = []
        for n in nodes:
            op = n['op']
            if op == 'set': item = {'op': op, 'dst': indices[n['var']], 'value': expr(n['value'])}
            elif op == 'store': item = {'op': op, 'array': 0, 'index': expr(n['index']), 'value': expr(n['value'])}
            elif op == 'if': item = {'op': op, 'condition': condition(n['condition']), 'then': body(n['then']), 'else': body(n['else'])}
            elif op == 'while': item = {'op': op, 'condition': condition(n['condition']), 'limit': n['limit'], 'body': body(n['body'])}
            else: item = {'op': 'return'}
            result.append(item)
        return result
    prefix = [{'op': 'set', 'dst': indices[n], 'value': b.constant(program['variables'][n]['initial'], 'u32')}
              for n in names if program['variables'][n]['initial']]
    if selected['max_steps'] + len(prefix) > 4000000:
        raise ValueError('legacy initialization requires a common execution budget beyond the profile cap')
    b.function['max_steps'] += len(prefix)
    b.function['body'] = prefix + body(selected['body'])
    return _result(b.function, b.constants, 'memory-uil', {
        'sha256': _digest(program), 'format': program['format'], 'function_name': function_name,
        'locals': names, 'arena_slot': 0,
        'evidence': _metadata(program.get('evidence', {})),
        'budget_scope': 'legacy statement/loop budget plus exactly the initialization prefix'})


def from_asm_instruction(code, *, bits=16, flags='explicit', registers=None, source=None):
    """Lift exactly one register INC/ADD/ADC using actual native operand facts.

    Explicit output order is destination, CF, PF, AF, ZF, SF, OF. INC preserves
    incoming CF. ADC always consumes incoming CF, including projected mode.
    The contract is isolated register views, not alias/memory/ABI/CPU parity.
    """
    import capstone
    from capstone import x86_const
    if type(code) is not bytes or not 1 <= len(code) <= 15 or type(bits) is not int or bits not in (16, 32, 64) or flags not in ('explicit', 'unobserved'):
        raise ValueError('expected one bounded x86 instruction and explicit flag policy')
    decoder = capstone.Cs(capstone.CS_ARCH_X86, {16: capstone.CS_MODE_16, 32: capstone.CS_MODE_32, 64: capstone.CS_MODE_64}[bits])
    decoder.detail = True
    decoded = list(decoder.disasm(code, 0))
    if len(decoded) != 1 or decoded[0].size != len(code): raise ValueError('native decoder must cover exactly one instruction')
    ins = decoded[0]; operands = ins.operands
    if ins.mnemonic not in ('inc', 'add', 'adc') or any(p and p != 0x66 for p in ins.prefix): raise ValueError('unsupported native instruction/prefix')
    if len(operands) != (1 if ins.mnemonic == 'inc' else 2) or operands[0].type != x86_const.X86_OP_REG or operands[0].size not in (1, 2, 4, 8): raise ValueError('register destination required')
    width = operands[0].size * 8; typ = f'u{width}'
    dest = ins.reg_name(operands[0].reg)
    if not re.fullmatch(r'(?:[abcd][lh]|[abcd]x|[sd]i|[sb]p|e(?:[abcd]x|[sd]i|[sb]p)|r(?:[abcd]x|[sd]i|[sb]p|[89]|1[0-5])(?:[bwd])?|[sb]pl|[sd]il|r(?:[89]|1[0-5])[bwd])', dest): raise ValueError('unsupported register view')
    names = [dest]
    source_operand = None
    if len(operands) == 2:
        operand = operands[1]
        if operand.type == x86_const.X86_OP_REG and operand.size == operands[0].size:
            source_operand = ins.reg_name(operand.reg)
            if source_operand not in names: names.append(source_operand)
        elif operand.type != x86_const.X86_OP_IMM: raise ValueError('register/immediate source required; memory is unsupported')
    if registers is not None and registers != names: raise ValueError('declared register ports disagree with native decode')
    need_carry = ins.mnemonic == 'adc' or (ins.mnemonic == 'inc' and flags == 'explicit')
    variables = [{'type': typ} for _ in names]
    carry_slot = len(variables) if need_carry else None
    if need_carry: variables.append({'type': 'bool'})
    b = _Builder(variables, list(range(len(variables))), [0])
    a = {'var': 0}
    if ins.mnemonic == 'inc': operand_expr = b.constant(1, typ)
    elif source_operand is not None: operand_expr = {'var': names.index(source_operand)}
    else: operand_expr = b.constant(operands[1].imm % (1 << width), typ)
    result = _op('add', typ, a, operand_expr)
    if flags == 'unobserved':
        if need_carry: result = _op('add', typ, result, _cast({'var': carry_slot}, typ))
        b.function['body'] = [{'op': 'set', 'dst': 0, 'value': result}]
    else:
        flag_slots = [b.variable('bool') for _ in range(6)]
        b.function['outputs'] += flag_slots
        sum_slot = b.variable(typ)
        body = [{'op': 'set', 'dst': sum_slot, 'value': result}]
        first = {'var': sum_slot}
        if ins.mnemonic == 'adc':
            result_slot = b.variable(typ)
            body.append({'op': 'set', 'dst': result_slot, 'value': _op('add', typ, first, _cast({'var': carry_slot}, typ))})
            r = {'var': result_slot}
        else: r = first
        zero = b.constant(0, typ)
        def nonzero(v): return _op('ne', 'bool', v, zero)
        def mask(v, n): return _op('and', typ, v, b.constant(n, typ))
        def both(x, y): return _op('select', 'bool', x, y, b.constant(False, 'bool'))
        if ins.mnemonic == 'inc': cf = {'var': carry_slot}
        else:
            cf = _op('lt', 'bool', first, a)
            if ins.mnemonic == 'adc': cf = _op('select', 'bool', cf, b.constant(True, 'bool'), _op('lt', 'bool', r, first))
        sign_a, sign_b, sign_r = [nonzero(mask(v, 1 << (width - 1))) for v in (a, operand_expr, r)]
        of = both(_op('eq', 'bool', sign_a, sign_b), _op('ne', 'bool', sign_a, sign_r))
        expressions = [cf, _op('parity_even', 'bool', _cast(r, 'u8')),
                       nonzero(mask(_op('xor', typ, _op('xor', typ, a, operand_expr), r), 16)),
                       _op('eq', 'bool', r, zero), sign_r, of]
        body += [{'op': 'set', 'dst': slot, 'value': expr} for slot, expr in zip(flag_slots, expressions)]
        body.append({'op': 'set', 'dst': 0, 'value': r})
        b.function['body'] = body
    metadata = {'decoder': 'capstone', 'bits': bits, 'mnemonic': ins.mnemonic,
                'inputs': names + (['cf'] if need_carry else []),
                'outputs': [dest] + (['cf', 'pf', 'af', 'zf', 'sf', 'of'] if flags == 'explicit' else []),
                'flags': flags,
                'scope': 'isolated register views and declared arithmetic flags; other aliases, flags, memory, traps, ABI and timing excluded'}
    return _with_source(_result(b.function, b.constants, f'x86-{bits}', metadata,
                               'native-decoder-backed bounded model; source correspondence declaration, native execution unverified'), source, code)


def _source_ports(spec):
    inputs, outputs = spec.get('inputs'), spec.get('outputs')
    if not isinstance(inputs, list) or not isinstance(outputs, list) or any(not isinstance(n, str) for n in inputs + outputs): raise ValueError('explicit string source ports required')
    names = set(inputs + outputs)
    bindings = spec.get('bindings', {name: '$' + name for name in sorted(names)})
    return bindings, inputs, outputs


def _python_lift(text, bindings, inputs, outputs):
    from .udl_blocks import lift_c_block
    if not isinstance(text, str) or not 1 <= len(text.encode('utf-8')) <= 1024: raise ValueError('invalid bounded Python source')
    try: tree = ast.parse(text, mode='exec')
    except (SyntaxError, ValueError) as exc: raise ValueError('invalid Python source') from exc
    statements = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name): raise ValueError('Python subset requires explicit masked assignment')
        name, value = node.targets[0].id, node.value
        if isinstance(value, ast.Constant) and type(value.value) is int and 0 <= value.value <= 65535:
            statements.append(f'{name} = {value.value};'); continue
        if not (isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitAnd) and isinstance(value.right, ast.Constant) and type(value.right.value) is int and value.right.value == 65535): raise ValueError('Python arithmetic requires an explicit uint16 mask')
        expr = value.left
        if not (isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Add, ast.Sub)) and isinstance(expr.left, ast.Name) and expr.left.id == name and isinstance(expr.right, ast.Constant) and type(expr.right.value) is int and 0 <= expr.right.value <= 65535): raise ValueError('unsupported masked Python arithmetic')
        statements.append(f'{name} {"+=" if isinstance(expr.op, ast.Add) else "-="} {expr.right.value};')
    # Existing restricted C reader independently checks bindings/initialization.
    return lift_c_block(' '.join(statements), bindings, inputs=inputs, outputs=outputs)


def import_udl(spec):
    """Read one declared bounded source; unsupported source raises ValueError."""
    if type(spec) is not dict or not isinstance(spec.get('language'), str): raise ValueError('source language required')
    language = spec['language']
    if language == 'common':
        _fields(spec, ('language', 'function', 'constants'), ('source', 'origin_language'))
        label = spec.get('origin_language', 'common')
        if not isinstance(label, str) or not 1 <= len(label) <= 128: raise ValueError('invalid source language label')
        return _result(deepcopy(spec['function']), deepcopy(spec['constants']), label, spec.get('source'))
    if language == 'scalar-il':
        _fields(spec, ('language', 'program', 'inputs', 'outputs'), ('source',))
        return _with_source(from_scalar_il(spec['program'], spec['inputs'], spec['outputs']), spec.get('source'))
    if language == 'memory-uil':
        _fields(spec, ('language', 'program', 'function_name'), ('source',))
        return _with_source(from_memory_uil(spec['program'], spec['function_name']), spec.get('source'))
    if language == 'x86-16':
        _fields(spec, ('language', 'code'), ('flags', 'bits', 'source', 'inputs', 'outputs', 'bindings'))
        code = spec['code']
        if isinstance(code, str):
            if len(code) > 128: raise ValueError('single-instruction hex source exceeds budget')
            try: code = bytes.fromhex(code)
            except ValueError as exc: raise ValueError('invalid source hex') from exc
        result = from_asm_instruction(code, bits=spec.get('bits', 16), flags=spec.get('flags', 'explicit'), source=spec.get('source'))
        for key in ('inputs', 'outputs'):
            if key in spec and spec[key] != result['source'][key]: raise ValueError('source port declaration disagrees with native decode')
        if 'bindings' in spec:
            bindings = spec['bindings']
            if not isinstance(bindings, dict) or set(bindings) != set(result['source']['inputs'] + result['source']['outputs']) or any(not isinstance(v, str) or not re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*', v) for v in bindings.values()) or len(set(bindings.values())) != len(bindings): raise ValueError('invalid native binding metadata')
            result['source']['bindings'] = dict(bindings)
        return result
    if language in ('c-u16', 'python-u16'):
        _fields(spec, ('language', 'source_text', 'inputs', 'outputs'), ('bindings', 'source'))
        from .udl_blocks import lift_c_block
        bindings, inputs, outputs = _source_ports(spec)
        text = spec['source_text']
        lifted = lift_c_block(text, bindings, inputs=inputs, outputs=outputs) if language == 'c-u16' else _python_lift(text, bindings, inputs, outputs)
        imported = from_scalar_il(lifted['uil'], [bindings[x] for x in inputs], [bindings[x] for x in outputs])
        imported['language'] = language
        imported['source'] = {'bindings': dict(bindings), 'inputs': list(inputs), 'outputs': list(outputs),
                              'assumptions': lifted['assumptions'] if language == 'c-u16' else ['ordinary Python integer assignment with explicit &65535 width masks; ports are uint16 values'],
                              'flags': 'unobserved'}
        return _with_source(imported, spec.get('source'), text.encode('utf-8'))
    raise ValueError('unsupported source language; no implicit execution or fallback')


def implementation_id(document):
    payload = {k: v for k, v in document.items() if k != 'id'}
    _fields(payload, ('language', 'function', 'constants', 'source', 'assurance'))
    return 'implementation:' + _digest(payload)


def build_catalog(specs):
    if type(specs) is not list or len(specs) > 4096: raise ValueError('bounded source list required')
    groups, rejected = {}, []
    for index, spec in enumerate(specs):
        try:
            imported = import_udl(spec)
            normalized = canonical_function(imported['function'], imported['constants'])
            ident = function_semantic_id(imported['function'], imported['constants'])
            implementation = {'id': implementation_id(imported), **deepcopy(imported)}
            group = groups.setdefault(ident, {'semantic_id': ident, **deepcopy(normalized),
                                            'effects': _effects(imported['function']), 'implementations': []})
            group.pop('format', None)
            if not any(item['id'] == implementation['id'] for item in group['implementations']): group['implementations'].append(implementation)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            # Never retain rejected raw source or parser snippets in diagnostics.
            label = spec.get('language') if isinstance(spec, dict) else None
            rejection = {'index': index, 'language': label if isinstance(label, str) and len(label) <= 128 else 'unknown', 'reason': str(exc)[:240]}
            if isinstance(spec, dict):
                try: metadata = _metadata(spec.get('source'))
                except ValueError: metadata = {}
                raw = spec.get('source_text', spec.get('code'))
                if isinstance(raw, str) and len(raw) <= 4194304: raw = raw.encode('utf-8')
                if isinstance(raw, bytes) and len(raw) <= 4194304:
                    metadata['input_sha256'] = hashlib.sha256(raw).hexdigest()
                    metadata['input_size'] = len(raw)
                if metadata: rejection['source'] = metadata
            rejected.append(rejection)
    result = {'format': FORMAT, 'groups': [groups[key] for key in sorted(groups)], 'rejected': rejected}
    for group in result['groups']: group['implementations'].sort(key=lambda x: x['id'])
    validate_catalog(result)
    return result


def validate_catalog(catalog):
    _fields(catalog, ('format', 'groups', 'rejected'))
    if catalog['format'] != FORMAT or type(catalog['groups']) is not list or len(catalog['groups']) > 4096 or type(catalog['rejected']) is not list or len(catalog['rejected']) > 4096 or len(_json(catalog)) > 16777216: raise ValueError('invalid catalog format/budget')
    ids, implementations = set(), set()
    for group in catalog['groups']:
        _fields(group, ('semantic_id', 'function', 'constants', 'effects', 'implementations'))
        ident = group['semantic_id']
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in ids: raise ValueError('duplicate/invalid semantic id')
        ids.add(ident)
        normalized = canonical_function(group['function'], group['constants'])
        if group['function'] != normalized['function'] or group['constants'] != normalized['constants'] or function_semantic_id(group['function'], group['constants']) != ident: raise ValueError('group semantic identity mismatch')
        if group['effects'] != _effects(group['function']) or any(x not in _SERVICES for x in group['effects']): raise ValueError('effect declaration mismatch')
        if type(group['implementations']) is not list or not group['implementations']: raise ValueError('group implementations required')
        for impl in group['implementations']:
            _fields(impl, ('id', 'language', 'function', 'constants', 'source', 'assurance'))
            if not isinstance(impl['id'], str) or not _IMPL.fullmatch(impl['id']) or impl['id'] in implementations or implementation_id(impl) != impl['id']: raise ValueError('implementation identity mismatch')
            implementations.add(impl['id'])
            if not isinstance(impl['language'], str) or not 1 <= len(impl['language']) <= 128 or not isinstance(impl['assurance'], str) or not 1 <= len(impl['assurance']) <= 2048: raise ValueError('invalid implementation metadata')
            if type(impl['source']) is not dict: raise ValueError('implementation source must be a metadata object')
            _metadata(impl['source'])
            if function_semantic_id(impl['function'], impl['constants']) != ident or _effects(impl['function']) != group['effects']: raise ValueError('implementation does not match semantic group')
            if impl['constants'] != [_constant(v, t) for v, t in zip(impl['constants'], impl['function']['constants'])]: raise ValueError('noncanonical implementation constants')
    for rejection in catalog['rejected']:
        _fields(rejection, ('index', 'language', 'reason'), ('source',))
        if type(rejection['index']) is not int or rejection['index'] < 0 or not isinstance(rejection['language'], str) or len(rejection['language']) > 128 or not isinstance(rejection['reason'], str) or len(rejection['reason']) > 240: raise ValueError('invalid rejected-source diagnostic')
        if 'source' in rejection and type(rejection['source']) is not dict: raise ValueError('rejected source must be a metadata object')
        _metadata(rejection.get('source'))
    return True
