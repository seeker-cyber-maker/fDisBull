"""Pure, evidence-qualified library identities and caller memory effects.

This module neither executes helpers nor assigns meaning from an arbitrary
label. Metadata identities remain conditional contracts. Byte signatures match
the complete supplied contiguous function body, never a prologue or substring.
The bundled byte loops are small, authored fixtures, not signatures for every
implementation of a C library function. Normalized expressions use ``op`` and
``args`` as in the flow-data API; unknown values remain visible.
"""
from __future__ import annotations

from copy import deepcopy
import re


_IDENTITIES = {'import', 'export', 'exact_signature', 'user_confirmed'}
_MAX = (1 << 64) - 1


def _arg(name, type_, role):
    return dict(name=name, type=type_, role=role)


def _effect(access, pointer, *length, **extra):
    size = {'op': 'arg', 'name': length[0]}
    if len(length) == 2:
        size = {'op': 'mul', 'args': [size, {'op': 'arg', 'name': length[1]}]}
    return dict(access=access, pointer={'op': 'arg', 'name': pointer}, size=size, **extra)


_CONTRACTS = {
    'memset': dict(arguments=[_arg('dest', 'pointer', 'output'), _arg('value', 'int', 'fill_byte'), _arg('n', 'size_t', 'byte_count')],
                   effects=[_effect('write', 'dest', 'n', fill={'op': 'and', 'args': [{'op': 'arg', 'name': 'value'}, {'op': 'const', 'value': 255}]})],
                   returns={'op': 'arg', 'name': 'dest'}, overlap='not_applicable'),
    'memcpy': dict(arguments=[_arg('dest', 'pointer', 'output'), _arg('src', 'pointer', 'input'), _arg('n', 'size_t', 'byte_count')],
                   effects=[_effect('read', 'src', 'n'), _effect('write', 'dest', 'n')],
                   returns={'op': 'arg', 'name': 'dest'}, overlap='forbidden'),
    'memmove': dict(arguments=[_arg('dest', 'pointer', 'output'), _arg('src', 'pointer', 'input'), _arg('n', 'size_t', 'byte_count')],
                    effects=[_effect('read', 'src', 'n'), _effect('write', 'dest', 'n')],
                    returns={'op': 'arg', 'name': 'dest'}, overlap='allowed_snapshot'),
    'read': dict(arguments=[_arg('fd', 'int', 'handle'), _arg('buf', 'pointer', 'output'), _arg('count', 'size_t', 'byte_count')],
                 effects=[_effect('write', 'buf', 'count', extent='upper_bound')], returns={'op': 'unknown', 'reason': 'actual byte count or error'}, overlap='not_applicable'),
    'write': dict(arguments=[_arg('fd', 'int', 'handle'), _arg('buf', 'pointer', 'input'), _arg('count', 'size_t', 'byte_count')],
                  effects=[_effect('read', 'buf', 'count', extent='upper_bound')], returns={'op': 'unknown', 'reason': 'actual byte count or error'}, overlap='not_applicable'),
    'fread': dict(arguments=[_arg('ptr', 'pointer', 'output'), _arg('size', 'size_t', 'element_size'), _arg('count', 'size_t', 'element_count'), _arg('stream', 'pointer', 'stream')],
                  effects=[_effect('write', 'ptr', 'size', 'count', extent='upper_bound')], returns={'op': 'unknown', 'reason': 'actual complete element count'}, overlap='not_applicable'),
    'fwrite': dict(arguments=[_arg('ptr', 'pointer', 'input'), _arg('size', 'size_t', 'element_size'), _arg('count', 'size_t', 'element_count'), _arg('stream', 'pointer', 'stream')],
                   effects=[_effect('read', 'ptr', 'size', 'count', extent='upper_bound')], returns={'op': 'unknown', 'reason': 'actual complete element count'}, overlap='not_applicable'),
}

# Independently decoded in tests. x86 loops use CLD and REP byte operations;
# ARM loops guard n==0, advance pointers, and decrement n once per byte.
_SIGNATURES = (
    dict(id='fixture.x86_64.sysv.memcpy.byte_loop', name='memcpy', arch='x86', bits=64,
         bytes='4889f84889d1fcf3a4c3', abi='sysv_x86_64'),
    dict(id='fixture.x86_64.sysv.memset.byte_loop', name='memset', arch='x86', bits=64,
         bytes='4989f84889d189f0fcf3aa4c89c0c3', abi='sysv_x86_64'),
    dict(id='fixture.arm64.aapcs64.memcpy.byte_loop', name='memcpy', arch='arm64', bits=64,
         bytes='e30300aaa20000b42414403864140038420400f1a1ffff54c0035fd6', abi='aapcs64'),
    dict(id='fixture.arm64.aapcs64.memset.byte_loop', name='memset', arch='arm64', bits=64,
         bytes='e30300aa820000b461140038420400f1c1ffff54c0035fd6', abi='aapcs64'),
)


def builtin_signatures():
    """Return an editable copy of the narrow, authored helper catalog."""
    return [dict(item, source='authored byte-loop fixture; not a vendor-library fingerprint',
                 confidence='exact_bytes', whole_function=True) for item in _SIGNATURES]


def _mode(arch, bits):
    if type(bits) is not int or (arch == 'x86' and bits not in (16, 32, 64)) or (arch == 'arm64' and bits != 64) or arch not in ('x86', 'arm64'):
        raise ValueError('explicit x86 16/32/64 or arm64 64 mode required')


def _hex(value, label):
    if not isinstance(value, str):
        raise ValueError(label + ' must be hexadecimal text')
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(label + ' must be hexadecimal text') from error


def validate_signature(signature):
    """Validate an explicitly supplied full-body signature and relocation mask.

    Every wildcard byte needs a declared relocation range. A mask is bytewise
    FF/00; wildcard opcode-bit heuristics are deliberately unsupported.
    """
    if not isinstance(signature, dict):
        raise ValueError('signature must be a mapping')
    item = deepcopy(signature)
    _mode(item.get('arch'), item.get('bits'))
    for key in ('id', 'name', 'source'):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError('signature requires ' + key)
    data = _hex(item.get('bytes'), 'signature bytes')
    if not data or len(data) > 65536:
        raise ValueError('signature length must be 1..65536 bytes')
    mask = _hex(item.get('mask', 'ff' * len(data)), 'signature mask')
    if len(mask) != len(data) or any(value not in (0, 255) for value in mask) or not any(mask):
        raise ValueError('mask must contain FF/00 bytes, match length, and constrain some bytes')
    declared = set()
    for relocation in item.get('relocations', []):
        if not isinstance(relocation, dict):
            raise ValueError('relocation must be a mapping')
        start, size = relocation.get('offset'), relocation.get('size')
        if type(start) is not int or type(size) is not int or size < 1 or start < 0 or start + size > len(data) or not relocation.get('kind'):
            raise ValueError('relocation requires bounded offset/size and kind')
        selected = set(range(start, start + size))
        if selected & declared:
            raise ValueError('relocation ranges must not overlap')
        declared.update(selected)
    if {i for i, value in enumerate(mask) if value == 0} != declared:
        raise ValueError('every masked byte must have exactly one declared relocation')
    item.update(bytes=data.hex(), mask=mask.hex(), whole_function=True)
    item.setdefault('confidence', 'registered_bytes')
    confidence=item['confidence']
    if not ((isinstance(confidence,str) and bool(confidence.strip())) or (type(confidence) in (int,float) and 0<=confidence<=1)):
        raise ValueError('signature confidence must be a qualification or a number in 0..1')
    return item


def match_signatures(instructions, signatures=None, arch='x86', bits=64):
    """Match only a complete, contiguous supplied function body, at offset zero.

    Instructions may be native/normalized dictionaries with address/size/bytes.
    The caller must supply the whole function; this module cannot prove its
    ownership. Overlapping or discontinuous instruction lists fail closed.
    """
    _mode(arch, bits)
    rows = list(instructions)
    catalog = [validate_signature(item) for item in (builtin_signatures() if signatures is None else signatures)]
    if not rows:
        return []
    chunks, expected, start = [], None, None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('instructions must be mappings')
        address, size = row.get('address'), row.get('size')
        if type(address) is not int or not 0 <= address <= _MAX or type(size) is not int or size < 1:
            raise ValueError('instruction address/size must be bounded integers')
        data = _hex(row.get('bytes'), 'instruction bytes')
        if len(data) != size or address + size > _MAX + 1:
            raise ValueError('instruction byte length/address range is inconsistent')
        if expected is not None and address != expected:
            return []
        if arch == 'arm64' and (address % 4 or size != 4):
            return []
        start = address if start is None else start
        chunks.append(data)
        expected = address + size
    data = b''.join(chunks)
    result = []
    for item in catalog:
        signature, mask = bytes.fromhex(item['bytes']), bytes.fromhex(item['mask'])
        if (item['arch'], item['bits']) != (arch, bits) or len(signature) != len(data):
            continue
        if all((left & bitmask) == (right & bitmask) for left, right, bitmask in zip(data, signature, mask)):
            result.append(dict(signature_id=item['id'], name=item['name'], address=start, size=len(data),
                               arch=arch, bits=bits, abi=item.get('abi'), source=item['source'],
                               confidence=item['confidence'], evidence_source='exact_signature',
                               match='masked_bytes' if 0 in mask else 'exact_bytes',
                               masked_offsets=[i for i, value in enumerate(mask) if not value],
                               input_hex=data.hex(), whole_supplied_body=True,
                               function_boundary_proven=False, runtime_observed=False))
    return result


def _validate_expr(expr, names, depth=0):
    if depth > 16 or not isinstance(expr, dict):
        raise ValueError('summary expressions must be bounded mappings')
    op = expr.get('op')
    if op == 'arg' and expr.get('name') in names:
        return
    if op == 'const' and type(expr.get('value')) is int:
        return
    if op in ('add', 'sub', 'mul', 'and', 'shl') and isinstance(expr.get('args'), list) and len(expr['args']) == 2:
        for child in expr['args']:
            _validate_expr(child, names, depth + 1)
        return
    if op == 'unknown' and isinstance(expr.get('reason'), str):
        return
    raise ValueError('unsupported expression or undeclared argument')


def validate_prototype(prototype):
    """Validate typed named arguments; a prototype alone supplies no effects."""
    if not isinstance(prototype, dict) or not isinstance(prototype.get('arguments'), list):
        raise ValueError('prototype requires an arguments list')
    item, seen = deepcopy(prototype), set()
    if len(item['arguments']) > 64:
        raise ValueError('prototype has too many arguments')
    for argument in item['arguments']:
        if not isinstance(argument, dict) or not isinstance(argument.get('name'), str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', argument['name']) or argument['name'] in seen:
            raise ValueError('argument names must be unique identifiers')
        if not isinstance(argument.get('type'), str) or not argument['type'].strip():
            raise ValueError('each argument requires an explicit type')
        if 'role' in argument and (not isinstance(argument['role'], str) or not argument['role'].strip()):
            raise ValueError('argument role must be text')
        seen.add(argument['name'])
    for index, argument in enumerate(item['arguments']):
        if 'index' in argument and (type(argument['index']) is not int or argument['index'] != index):
            raise ValueError('argument indices must match their declared order')
        argument['index'] = index
    return item


def validate_summary(summary):
    """Validate a serializable, explicitly registered memory contract."""
    if not isinstance(summary, dict):
        raise ValueError('summary must be a mapping')
    item = deepcopy(summary)
    item.update(validate_prototype(item))
    if not isinstance(item.get('name'), str) or not item['name'].strip():
        raise ValueError('summary requires a name')
    confidence = item.get('confidence')
    qualified_confidence = ((isinstance(confidence, str) and bool(confidence.strip())) or
                            (type(confidence) in (int, float) and 0 <= confidence <= 1))
    if item.get('evidence_source') not in _IDENTITIES or not item.get('source') or not qualified_confidence:
        raise ValueError('summary requires qualified evidence and confidence')
    effects = item.get('effects')
    if not isinstance(effects, list) or len(effects) > 32:
        raise ValueError('summary requires at most 32 effects')
    names = {argument['name'] for argument in item['arguments']}
    for effect in effects:
        if not isinstance(effect, dict) or effect.get('access') not in ('read', 'write') or effect.get('extent', 'exact') not in ('exact', 'upper_bound'):
            raise ValueError('effect requires read/write access and exact/upper_bound extent')
        for key in ('pointer', 'size'):
            _validate_expr(effect.get(key), names)
        if 'fill' in effect:
            _validate_expr(effect['fill'], names)
    if item.get('overlap', 'not_applicable') not in ('not_applicable', 'forbidden', 'allowed_snapshot'):
        raise ValueError('unsupported overlap contract')
    if 'returns' in item:
        _validate_expr(item['returns'], names)
    return item


def resolve_summary(name, *, source=None, prototype=None, summary=None, confidence=None):
    """Resolve known metadata/signature identities or a user-confirmed contract.

    ``source`` is a kind string or ``{kind, detail, ...}`` evidence dictionary.
    Arbitrary names, annotations and unsupported symbols return None. Custom
    prototypes/effects require user_confirmed evidence; changing a known
    prototype also requires explicit effects, preventing accidental ABI reuse.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError('summary name must be text')
    evidence = dict(source) if isinstance(source, dict) else {'kind': source}
    kind = evidence.get('kind')
    if kind not in _IDENTITIES:
        return None
    if summary is not None or prototype is not None:
        if kind != 'user_confirmed':
            raise ValueError('custom prototype/summary requires user_confirmed evidence')
        contract = deepcopy(summary or {})
        if prototype is not None:
            contract.update(validate_prototype(prototype))
        contract.setdefault('effects', [])
    else:
        contract = deepcopy(_CONTRACTS.get(name))
        if contract is None:
            return None
    contract.update(name=name, evidence_source=kind, source=evidence,
                    confidence=confidence if confidence is not None else
                    {'import': 'metadata_identity', 'export': 'metadata_identity',
                     'exact_signature': 'exact_bytes', 'user_confirmed': 'user_confirmed'}[kind])
    contract.setdefault('overlap', 'not_applicable')
    contract['runtime_observed'] = False
    return validate_summary(contract)


def _expression(value, depth=0):
    if depth > 16:
        raise ValueError('argument expression is too deep')
    if type(value) is int:
        return {'op': 'const', 'value': value}
    if value is None:
        return {'op': 'unknown', 'reason': 'argument not recovered'}
    if not isinstance(value, dict) or not isinstance(value.get('op'), str):
        raise ValueError('argument must be an integer or normalized expression')
    result = deepcopy(value)
    if result['op'] == 'const' and type(result.get('value')) is not int:
        raise ValueError('constant argument must be an integer')
    for child in result.get('args', []):
        _expression(child, depth + 1)
    return result


def _substitute(expr, arguments):
    if expr['op'] == 'arg':
        return deepcopy(arguments[expr['name']])
    item = deepcopy(expr)
    if 'args' in item:
        item['args'] = [_substitute(child, arguments) for child in item['args']]
    return item


def _value(expr, state, depth=0):
    if depth > 16:
        return None
    op = expr.get('op')
    if op == 'const':
        return expr.get('value') if type(expr.get('value')) is int else None
    if op == 'reg':
        # A flow expression with a symbol denotes a frozen earlier value,
        # not whatever happens to occupy that register in a later state.
        if expr.get('symbol') is not None:
            return None
        register = state.get('registers', {}).get(expr.get('name'))
        return _value(_expression(register), {}, depth + 1) if register is not None else None
    args = expr.get('args', [])
    if op not in ('add', 'sub', 'mul', 'and', 'shl') or len(args) != 2:
        return None
    left, right = (_value(child, state, depth + 1) for child in args)
    if op == 'mul' and (left == 0 or right == 0):
        return 0
    if left is None or right is None or abs(left) > _MAX or abs(right) > _MAX:
        return None
    if op == 'shl' and not 0 <= right <= 63:
        return None
    result = {'add': lambda: left + right, 'sub': lambda: left - right,
              'mul': lambda: left * right, 'and': lambda: left & right,
              'shl': lambda: left << right}[op]()
    return result


def _bounds(expr, state, depth=0):
    """Use only supplied, symbol-matched flow bounds; never infer a guard."""
    if depth > 16:
        return None
    value = _value(expr, state)
    if value is not None:
        return dict(min=value, max=value, evidence=[])
    if expr.get('op') == 'reg':
        name = expr.get('name')
        bound = state.get('bounds', {}).get(name)
        symbol = expr.get('symbol', state.get('symbols', {}).get(name))
        if not isinstance(bound, dict) or symbol is None or bound.get('symbol') != symbol:
            return None
        low, high = bound.get('min'), bound.get('max')
        if type(low) is int and type(high) is int and 0 <= low <= high <= _MAX and bound.get('evidence'):
            return dict(min=low, max=high, evidence=deepcopy(bound['evidence']))
        return None
    args = expr.get('args', [])
    if expr.get('op') not in ('add', 'sub', 'mul') or len(args) != 2:
        return None
    left, right = (_bounds(child, state, depth + 1) for child in args)
    if left is None or right is None:
        return None
    op = expr['op']
    values = [a + b if op == 'add' else a - b if op == 'sub' else a * b
              for a in (left['min'], left['max']) for b in (right['min'], right['max'])]
    if not 0 <= min(values) <= max(values) <= _MAX:
        return None
    return dict(min=min(values), max=max(values), evidence=left['evidence'] + right['evidence'])


def instantiate_effects(summary, arguments, state=None):
    """Bind a qualified contract to caller values without reading/executing code.

    Accept named values, positional expressions, frame ``argument_values`` or
    frame ``arguments`` records. Ranges are half-open. I/O ranges are potential
    upper bounds, never a claim that all requested bytes were transferred.
    Invalid lengths/overflow or known memcpy overlap emit diagnostics and no
    facts. memmove retains its snapshot-copy contract when ranges overlap.
    """
    contract = validate_summary(summary)
    state = state or {}
    if not isinstance(state, dict):
        raise ValueError('state must be a mapping')
    pointer_bits = state.get('pointer_bits', 64)
    if type(pointer_bits) is not int or pointer_bits not in (16, 32, 64):
        raise ValueError('pointer_bits must be 16, 32 or 64')
    if isinstance(arguments, dict) and 'argument_values' in arguments:
        arguments = arguments['argument_values']
    elif isinstance(arguments, dict) and isinstance(arguments.get('arguments'), list):
        arguments = arguments['arguments']
    if isinstance(arguments, (list, tuple)):
        if all(isinstance(value, dict) and 'index' in value and 'value' in value for value in arguments):
            indexed = {}
            for item in arguments:
                index = item['index']
                if type(index) is not int or index < 0 or index in indexed:
                    raise ValueError('frame argument indices must be unique nonnegative integers')
                indexed[index] = item['value']
            values = {item['name']: _expression(indexed.get(i)) for i, item in enumerate(contract['arguments'])}
        else:
            values = {item['name']: _expression(arguments[i] if i < len(arguments) else None) for i, item in enumerate(contract['arguments'])}
    elif isinstance(arguments, dict):
        values = {item['name']: _expression(arguments.get(item['name'])) for item in contract['arguments']}
    else:
        raise ValueError('arguments must be a mapping or sequence')
    effects, diagnostics = [], []
    limit = 1 << pointer_bits
    for effect in contract['effects']:
        pointer, size = (_substitute(effect[key], values) for key in ('pointer', 'size'))
        address, length = _value(pointer, state), _value(size, state)
        pointer_bounds, size_bounds = _bounds(pointer, state), _bounds(size, state)
        # Reject negative factors even if multiplying two negatives is positive.
        def invalid_count(expr):
            value = _value(expr, state)
            return (value is not None and not 0 <= value <= _MAX) or any(invalid_count(child) for child in expr.get('args', []))
        if invalid_count(size) or (length is not None and not 0 <= length <= _MAX):
            diagnostics.append('invalid byte count: negative or exceeds unsigned 64-bit range')
            continue
        if address is not None and (not 0 <= address < limit or (length is not None and address + length > limit)):
            diagnostics.append('pointer/range exceeds the supplied address width')
            continue
        extent = effect.get('extent', 'exact')
        row = dict(access=effect['access'], address=address, size=length, pointer_expression=pointer,
                   size_expression=size, extent=extent, minimum_size=0 if extent == 'upper_bound' else length,
                   end_exclusive=address + length if address is not None and length is not None else None,
                   empty=length == 0, resolved=address is not None and length is not None,
                   status='conditional_static_effect', evidence_source=contract['evidence_source'],
                   confidence=contract['confidence'], runtime_observed=False)
        row['address_range'] = pointer_bounds
        row['size_range'] = size_bounds
        row['maximum_size'] = size_bounds['max'] if size_bounds else None
        if extent == 'exact' and size_bounds:
            row['minimum_size'] = size_bounds['min']
        row['possible_range'] = None
        if pointer_bounds and size_bounds:
            end = pointer_bounds['max'] + size_bounds['max']
            if end > limit:
                diagnostics.append('bounded pointer/range may exceed the supplied address width')
                continue
            row['possible_range'] = dict(start=pointer_bounds['min'], end_exclusive=end,
                                         qualification='potential accessed bytes, conditional on the contract')
        if 'fill' in effect:
            row['fill_expression'] = _substitute(effect['fill'], values)
            row['fill_byte'] = _value(row['fill_expression'], state)
        effects.append(row)
    overlap = dict(contract=contract.get('overlap', 'not_applicable'), status='not_applicable')
    if overlap['contract'] in ('forbidden', 'allowed_snapshot'):
        reads = [item for item in effects if item['access'] == 'read']
        writes = [item for item in effects if item['access'] == 'write']
        overlap['status'] = 'unknown'
        if len(reads) == len(writes) == 1 and reads[0]['resolved'] and writes[0]['resolved']:
            read, write = reads[0], writes[0]
            aliases = bool(read['size'] and write['size'] and read['address'] < write['end_exclusive'] and write['address'] < read['end_exclusive'])
            overlap['status'] = 'overlap' if aliases else 'disjoint'
            if aliases and overlap['contract'] == 'forbidden':
                diagnostics.append('memcpy non-overlap precondition violated; no defined copy effects asserted')
    if diagnostics:
        effects = []
    conditions = ['callee identity, ABI and recovered arguments are correct', 'normal completion without memory faults']
    if overlap['contract'] == 'forbidden' and overlap['status'] == 'unknown':
        conditions.append('source and destination byte ranges do not overlap')
    return dict(name=contract['name'], valid=not diagnostics, effects=effects, arguments=values,
                diagnostics=diagnostics, overlap=overlap, conditions=conditions,
                source=deepcopy(contract['source']), confidence=contract['confidence'],
                returns=_substitute(contract.get('returns', {'op': 'unknown', 'reason': 'not specified'}), values),
                runtime_observed=False)
