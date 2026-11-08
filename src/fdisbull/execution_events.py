"""Pure, bounded searches over qualified before-instruction observations.

No target is run or modified here. The storage adapter owns trace provenance.
Searches compare observed feature sets, never event ordinals, function identity,
causation, or whole-program absence. State retains hashes and witness references,
not instruction bytes. Its seal detects corruption; it is not authentication.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from iced_x86 import Decoder, Mnemonic

from .execution_clock import validate_clock, validate_clock_predicate, validate_trace_clocks


MAX_EVENTS = 10_000
MAX_SAMPLES = 10_000
MAX_CANDIDATES = 32_768
MAX_HISTORY = 128
MAX_RESULT_ROWS = 4096
MAX_REGIONS = 64
MAX_PREDICATE_NODES = 64
MAX_PREDICATE_DEPTH = 8
MAX_ROW_SAMPLES = 8
_ADDRESS_MAX = (1 << 64) - 1
_DOS = {'dosbox', 'dosbox-qemu', 'qemu-dos'}
_PE = {'wine-qemu', 'ida-wine-qemu'}
_COMPARISONS = {'equals', 'not_equals', 'lt', 'le', 'gt', 'ge'}
_MNEMONICS = {value: name.lower() for name, value in vars(Mnemonic).items()
              if name.isupper() and type(value) is int}
_REGISTERS = {}
for _family, _names in (
    ('a', ('rax', 'eax', 'ax', 'al', 'ah')),
    ('b', ('rbx', 'ebx', 'bx', 'bl', 'bh')),
    ('c', ('rcx', 'ecx', 'cx', 'cl', 'ch')),
    ('d', ('rdx', 'edx', 'dx', 'dl', 'dh')),
    ('si', ('rsi', 'esi', 'si', 'sil')),
    ('di', ('rdi', 'edi', 'di', 'dil')),
    ('bp', ('rbp', 'ebp', 'bp', 'bpl')),
    ('sp', ('rsp', 'esp', 'sp', 'spl')),
    ('ip', ('rip', 'eip', 'ip')),
    ('flags', ('rflags', 'eflags', 'flags')),
):
    for _name, _width, _shift in zip(_names, (64, 32, 16, 8, 8), (0, 0, 0, 0, 8)):
        _REGISTERS[_name] = (_family, _width, _shift)
for _number in range(8, 16):
    for _suffix, _width in (('', 64), ('d', 32), ('w', 16), ('b', 8)):
        _REGISTERS[f'r{_number}{_suffix}'] = (f'r{_number}', _width, 0)
for _name in ('cs', 'ds', 'es', 'fs', 'gs', 'ss'):
    _REGISTERS[_name] = (_name, 16, 0)
for _name in ('cr0', 'cr2', 'cr3', 'cr4'):
    _REGISTERS[_name] = (_name, 64, 0)


def _number(value, name, maximum=_ADDRESS_MAX):
    if type(value) is str and re.fullmatch(r'0[xX][0-9a-fA-F]{1,17}', value):
        value = int(value, 16)
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be an unsigned integer or hexadecimal string <= {maximum}')
    return value


def _text(value, name, maximum=256):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name} must be a nonempty string of at most {maximum} characters')
    return value


def _digest(value, name):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError(f'{name} must be a lowercase SHA-256 digest')
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _register(value):
    name = _text(value, 'register', 16).lower()
    if name not in _REGISTERS:
        raise ValueError('Unsupported integer register: ' + name)
    return name


def _registers(values):
    if type(values) is not list or not 1 <= len(values) <= 32:
        raise ValueError('registers requires 1..32 explicit names')
    result = [_register(v) for v in values]
    if len(set(result)) != len(result):
        raise ValueError('Duplicate register names')
    return result


def validate_regions(regions):
    """Normalize half-open regions. Labels never establish region identity."""
    if regions is None:
        return []
    if type(regions) is not list or len(regions) > MAX_REGIONS:
        raise ValueError('regions must contain at most 64 regions')
    result, ids = [], set()
    for item in regions:
        if (type(item) is not dict or not {'id', 'space', 'start', 'end'} <= item.keys()
                or set(item) - {'id', 'name', 'space', 'start', 'end'}):
            raise ValueError('Region requires id, space, start, end and optional name')
        identifier = _text(item['id'], 'region id', 128)
        if identifier in ids:
            raise ValueError('Duplicate region id')
        ids.add(identifier)
        if item['space'] not in ('project', 'linear'):
            raise ValueError('Region space must be project or linear')
        start = _number(item['start'], 'region start')
        end = _number(item['end'], 'region end', _ADDRESS_MAX + 1)
        if start >= end:
            raise ValueError('Region bounds must be nonempty and half-open')
        region = dict(id=identifier, space=item['space'], start=start, end=end)
        if 'name' in item:
            region['name'] = _text(item['name'], 'region name')
        result.append(region)
    result.sort(key=lambda r: (r['space'], r['start'], r['id']))
    for before, after in zip(result, result[1:]):
        if before['space'] == after['space'] and before['end'] > after['start']:
            raise ValueError('Regions overlap in the same address space')
    return result


def validate_predicate(predicate):
    """Validate a finite, typed, unsigned before-state predicate. No eval."""
    nodes = 0

    def visit(value, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_PREDICATE_NODES or depth > MAX_PREDICATE_DEPTH:
            raise ValueError('Predicate exceeds its node or depth budget')
        if type(value) is not dict:
            raise ValueError('Predicate must be an object')
        for operator in ('all', 'any'):
            if operator in value:
                children = value[operator]
                if set(value) != {operator} or type(children) is not list or not 1 <= len(children) <= MAX_PREDICATE_NODES:
                    raise ValueError('Boolean predicate requires a nonempty bounded list')
                return {operator: [visit(c, depth + 1) for c in children]}
        kind = value.get('kind')
        if kind == 'virtual-time-range':
            return validate_clock_predicate(value)
        if kind in ('register', 'any-register'):
            field = 'register' if kind == 'register' else 'registers'
            names = [_register(value.get(field))] if kind == 'register' else _registers(value.get(field))
            operators = set(value) & _COMPARISONS
            if len(operators) != 1 or set(value) - {'kind', field, 'mask'} - operators:
                raise ValueError('Register predicate requires exactly one comparison')
            operator = next(iter(operators))
            if kind == 'any-register' and operator != 'equals':
                raise ValueError('any-register supports equals only')
            width = min(_REGISTERS[name][1] for name in names)
            maximum = (1 << width) - 1
            result = {'kind': kind, field: names[0] if kind == 'register' else names,
                      operator: _number(value[operator], 'comparison value', maximum)}
            if 'mask' in value:
                result['mask'] = _number(value['mask'], 'register mask', maximum)
            return result
        if kind == 'pc-range':
            space = value.get('space')
            keys = {'kind', 'space', 'start', 'end'} | ({'segment'} if space == 'segmented' else set())
            if space not in ('project', 'linear', 'segmented') or set(value) != keys:
                raise ValueError('PC range requires a valid space and exact bounds/segment fields')
            start = _number(value['start'], 'PC start')
            end = _number(value['end'], 'PC end', _ADDRESS_MAX + 1)
            if start >= end:
                raise ValueError('PC interval must be nonempty and half-open')
            result = dict(kind=kind, space=space, start=start, end=end)
            if space == 'segmented':
                result['segment'] = _number(value['segment'], 'PC segment', 0xffff)
            return result
        if kind == 'mnemonic' and set(value) == {'kind', 'equals'}:
            name = _text(value['equals'], 'mnemonic', 32).lower()
            if name not in _MNEMONICS.values() or name == 'invalid':
                raise ValueError('Use one canonical decoded mnemonic without prefixes or operands')
            return {'kind': kind, 'equals': name}
        if kind in ('region-change', 'nonsequential') and set(value) == {'kind'}:
            return {'kind': kind}
        raise ValueError('Unknown or malformed execution predicate')

    return visit(predicate, 1)


def _register_value(values, name):
    family, width, shift = _REGISTERS[name]
    for observed, value in values.items():
        if observed not in _REGISTERS:
            continue
        parent, bits, offset = _REGISTERS[observed]
        if parent == family and offset <= shift and offset + bits >= shift + width:
            return (value >> (shift - offset)) & ((1 << width) - 1)
    return None


def _region_key(region):
    return None if region is None else {k: region[k] for k in ('id', 'space', 'start', 'end')}


def _adjacent(previous, event):
    return (previous is not None and event.get('sequence') == previous.get('sequence', -2) + 1
            and event.get('index') == previous.get('index', -2) + 1)


def _evaluate(predicate, event, initial, previous):
    def answer(value, reason=None):
        return {'matched': value, 'unknown': [] if reason is None else [reason]}

    if event.get('observation', {}).get('registers_stage') != 'before-instruction':
        return answer(None, 'Event lacks a before-instruction observation')
    for operator in ('all', 'any'):
        if operator in predicate:
            results = [_evaluate(p, event, initial, previous) for p in predicate[operator]]
            values = [r['matched'] for r in results]
            matched = (False if False in values else None if None in values else True) if operator == 'all' else (True if True in values else None if None in values else False)
            return {'matched': matched, 'unknown': sorted({s for r in results for s in r['unknown']})}
    kind = predicate['kind']
    if kind == 'virtual-time-range':
        if 'clock' not in event:
            return answer(None, 'Qualified virtual clock unavailable')
        clock = validate_clock(event['clock'])
        if any(clock[field] != predicate[field] for field in ('run', 'epoch', 'native_epoch')):
            return answer(None, 'Virtual clock identity differs from predicate')
        return answer(predicate['start_ns'] <= clock['virtual_ns'] < predicate['end_ns'])
    if kind in ('register', 'any-register'):
        names = [predicate['register']] if kind == 'register' else predicate['registers']
        operator = next(k for k in _COMPARISONS if k in predicate)
        expected = predicate[operator]
        values, unknown = [], []
        for name in names:
            value = _register_value(event.get('registers', {}), name)
            if value is None:
                values.append(None); unknown.append('Register unavailable: ' + name)
                continue
            if 'mask' in predicate:
                value &= predicate['mask']
            values.append({'equals': value == expected, 'not_equals': value != expected,
                           'lt': value < expected, 'le': value <= expected,
                           'gt': value > expected, 'ge': value >= expected}[operator])
        return {'matched': True if True in values else None if None in values else False, 'unknown': unknown}
    if kind == 'pc-range':
        pc = event['pc']
        if predicate['space'] == 'segmented':
            if pc.get('segment') is None:
                return answer(None, 'Segmented PC unavailable')
            return answer(pc['segment'] == predicate['segment'] and predicate['start'] <= pc['offset'] < predicate['end'])
        value = pc.get(predicate['space'])
        return answer(None, 'PC address space unavailable') if value is None else answer(predicate['start'] <= value < predicate['end'])
    if kind == 'mnemonic':
        value = event.get('mnemonic')
        return answer(None, 'Instruction decode unavailable') if value is None else answer(value == predicate['equals'])
    if kind == 'region-change':
        if initial is None or initial.get('region') is None or event.get('region') is None:
            return answer(None, 'Initial or current region unavailable')
        return answer(_region_key(initial['region']) != _region_key(event['region']))
    if not _adjacent(previous, event):
        return answer(None, 'No contiguous previous event')
    if (previous.get('observation', {}).get('registers_stage') != 'before-instruction'
            or previous.get('execution_context') != event.get('execution_context')):
        return answer(None, 'Execution context changed or is unavailable')
    bits, size = previous.get('code_bits'), previous.get('size')
    if bits not in (16, 32, 64) or not size:
        return answer(None, 'Previous instruction width or length unavailable')
    before, after = previous['pc'], event['pc']
    if (before['segment'] is None) != (after['segment'] is None):
        return answer(None, 'PC domain changed')
    if before['segment'] != after['segment']:
        return answer(True)
    return answer(after['offset'] != (before['offset'] + size) % (1 << bits))


def evaluate_predicate(predicate, event, initial=None, previous=None):
    """Return matched true/false/unknown without changing the supplied events."""
    return _evaluate(validate_predicate(predicate), event, initial, previous)


def _identity(value):
    if type(value) is not dict or set(value) != {'source_sha256', 'version_sha256', 'version', 'backend'}:
        raise ValueError('Execution identity requires source/version hashes, version and backend')
    version = value['version']
    if type(version) is not int or version < 1:
        raise ValueError('version must be a positive integer')
    return {'source_sha256': _digest(value['source_sha256'], 'source_sha256'),
            'version_sha256': _digest(value['version_sha256'], 'version_sha256'),
            'version': version, 'backend': _text(value['backend'], 'backend', 64)}


def _updates(value, bits):
    if type(value) is not dict or len(value) > 128:
        raise ValueError('Register snapshot/delta must be a bounded object')
    result = {}
    fields = [(k, v) for k, v in value.items() if k not in ('general', 'segments', 'address_context')]
    for group in ('general', 'segments', 'address_context'):
        nested = value.get(group, {})
        if type(nested) is not dict or len(nested) > 128:
            raise ValueError('Register group must be a bounded object')
        fields.extend(nested.items())
    for key, value in fields:
        name = key.lower() if type(key) is str else ''
        if name == 'instruction_pointer':
            name = 'rip' if bits == 64 else 'eip'
        elif name == 'flags':
            name = 'eflags'  # Native DOS flags contains the complete 32-bit flags value.
        if name in _REGISTERS:
            number = _number(value, 'register ' + name, (1 << _REGISTERS[name][1]) - 1)
            if name in result and result[name] != number:
                raise ValueError('Contradictory duplicate register observation')
            result[name] = number
    # Duplicate aliases are accepted only when their observed bits agree.
    for name, value in result.items():
        rest = {key: number for key, number in result.items() if key != name}
        alias = _register_value(rest, name)
        if alias is not None and alias != value:
            raise ValueError('Contradictory register aliases')
    return result


def _merge_registers(previous, updates):
    # A partial delta does not prove upper bits. Invalidate other aliases in that
    # family rather than guessing architectural write/zero-extension semantics.
    changed = {_REGISTERS[name][0] for name in updates}
    return {**{k: v for k, v in previous.items() if _REGISTERS[k][0] not in changed}, **updates}


def _address_context(raw, full, updates, carried, mode, bits):
    """Preserve observed mapping facts separately from the instruction address.

    A changed page table or hidden descriptor can leave CS:EIP numerically
    sequential. That is not evidence of sequential flow in one address space.
    Control-register deltas can be carried only through the same qualified
    register stream; explicit address-context snapshots are never invented.
    """
    nodes = 0

    def canonical(value, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 256 or depth > 4:
            raise ValueError('Address context exceeds its metadata budget')
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            return _number(value, 'address context integer')
        if type(value) is str:
            _text(value, 'address context value', 128)
            return _number(value, 'address context value') if re.fullmatch(r'0[xX][0-9a-fA-F]{1,16}', value) else value
        if type(value) is dict and len(value) <= 64:
            return {_text(key, 'address context key', 64): canonical(child, depth + 1)
                    for key, child in value.items()}
        if type(value) is list and len(value) <= 32:
            return [canonical(child, depth + 1) for child in value]
        raise ValueError('Address context must contain bounded JSON values')

    observed = {}
    for source in (raw.get('address_context'), (full or {}).get('address_context')):
        if source is None:
            continue
        if type(source) is not dict:
            raise ValueError('Observed address context must be an object')
        for name, value in canonical(source).items():
            if name in observed and observed[name] != value:
                raise ValueError('Contradictory observed address contexts')
            observed[name] = value
    if observed.get('cpu_mode') is not None and mode is not None and observed['cpu_mode'] != mode:
        raise ValueError('Address context CPU mode differs from event mode')
    if observed.get('code_bits') is not None and bits is not None and observed['code_bits'] != bits:
        raise ValueError('Address context code width differs from event width')
    for name in ('cr0', 'cr3', 'cr4'):
        if name in observed:
            observed[name] = _number(observed[name], 'address context ' + name)
            if name in updates and updates[name] != observed[name]:
                raise ValueError('Control register differs from observed address context')
        elif name in carried:
            observed[name] = carried[name]
    return observed or None


def _pc(raw, backend, mode):
    address = raw.get('address')
    pc = {'project': None, 'linear': None, 'segment': None, 'offset': 0}
    if type(address) is dict:
        space = address.get('space')
        if space == 'segmented':
            pc['segment'] = _number(address.get('segment'), 'PC segment', 0xffff)
            pc['offset'] = _number(address.get('offset'), 'PC offset')
            if mode == 'real':
                pc['linear'] = pc['segment'] * 16 + pc['offset']
        elif space == 'linear':
            pc['linear'] = pc['offset'] = _number(address.get('offset', address.get('address')), 'linear PC')
        else:
            raise ValueError('Unsupported trace PC address space')
    else:
        pc['linear'] = pc['offset'] = _number(address, 'PC')
    if backend == 'qemu-dos':
        segmented = raw.get('segmented_address')
        if segmented is not None:
            if type(segmented) is not dict or segmented.get('space') != 'segmented':
                raise ValueError('Native DOS trace requires an explicit segmented PC')
            segment = _number(segmented.get('segment'), 'PC segment', 0xffff)
            offset = _number(segmented.get('offset'), 'PC offset', 0xffffffff)
            if pc['segment'] is not None and (pc['segment'], pc['offset']) != (segment, offset):
                raise ValueError('Native DOS trace has contradictory segmented PCs')
            pc['segment'], pc['offset'] = segment, offset
        if pc['segment'] is None:
            raise ValueError('Native DOS trace lacks its observed CS:IP')
        cache = (raw.get('address_context') or {}).get('cs')
        if cache is not None:
            if type(cache) is not dict:
                raise ValueError('Native DOS observed CS cache must be an object')
            if _number(cache.get('selector'), 'CS cache selector', 0xffff) != pc['segment']:
                raise ValueError('Native DOS CS cache differs from the observed segment')
            base = _number(cache.get('base'), 'CS cache base')
            expected = base + pc['offset']
            if mode == 'real' and base != pc['segment'] * 16:
                raise ValueError('Native DOS source trace has a changed real-mode CS base')
        elif mode == 'real':
            expected = pc['segment'] * 16 + pc['offset']
        else:
            expected = None
        if expected is not None:
            if pc['linear'] is not None and pc['linear'] != expected:
                raise ValueError('Native DOS linear PC differs from its observed CS:IP')
            pc['linear'] = expected
    project = raw.get('project_address')
    if project is not None and (backend in _PE or backend in _DOS and mode == 'real' and pc['segment'] is not None):
        pc['project'] = _number(project, 'project PC')
    return pc


def normalize_trace(document, *, regions=None):
    """Compile an owned trace without retaining instruction payload bytes."""
    if type(document) is not dict or type(document.get('mapping')) is not dict:
        raise ValueError('Trace requires document and mapping identity')
    mapping = document['mapping']; contract = document.get('observation_contract', {})
    if type(contract) is not dict:
        raise ValueError('Trace observation contract must be an object')
    identity = _identity({'source_sha256': mapping.get('source_sha256'), 'version_sha256': mapping.get('version_sha256'),
                          'version': document.get('version'), 'backend': contract.get('backend')})
    backend = identity['backend']
    if backend == 'qemu-dos':
        from .qemu_trace_identity import CAPTURE_FORMAT, SOURCE_SCOPE
        capture = document.get('native_process_capture')
        if (type(capture) is not dict or capture.get('format') != CAPTURE_FORMAT
                or capture.get('source_scope') != SOURCE_SCOPE):
            raise ValueError('Native DOS events require a source-bound process capture')
        epoch = _text(document.get('capture_epoch'), 'native capture epoch', 128)
        if capture.get('capture_epoch', epoch) != epoch:
            raise ValueError('Native DOS capture epoch fields disagree')
    run = document.get('run'); run = run.get('run') if type(run) is dict else run
    run = _text(run, 'trace run', 128)
    raw_events = document.get('events')
    if type(raw_events) is not list or len(raw_events) > MAX_EVENTS:
        raise ValueError('Trace event budget exceeded or events are missing')
    clocks, endpoint_clock = validate_trace_clocks(document, run=run, backend=backend, mapping=mapping)
    regions = validate_regions(regions)
    events, registers, last_sequence, last_context, gaps = [], {}, None, None, 0
    explicit_sequence = None
    for index, raw in enumerate(raw_events):
        if type(raw) is not dict:
            raise ValueError('Trace event must be an object')
        has_sequence = 'sequence' in raw
        sequence = _number(raw.get('sequence', index + 1), 'event sequence')
        if index and has_sequence and explicit_sequence and sequence <= last_sequence:
            raise ValueError('Trace event sequence must increase')
        contiguous = bool(index and has_sequence == explicit_sequence and sequence == last_sequence + 1)
        if index and not contiguous:
            gaps += 1
        full = raw.get('registers')
        if full is not None and type(full) is not dict:
            raise ValueError('Full register observation must be an object')
        mode = raw.get('cpu_mode', 'flat' if backend in _PE else None)
        if backend in _PE and mode is None:
            mode = 'flat'
        if mode is not None and mode not in ('real', 'protected', 'v86', 'flat'):
            raise ValueError('Invalid observed CPU mode')
        bits = raw.get('code_bits', raw.get('instruction_bits', (full or {}).get('bits')))
        if mode == 'real':
            bits = 16
        elif backend in _PE and bits is None and 'rip' in (full or {}):
            bits = 64  # The explicit RIP register establishes the PE64 register schema.
        if bits is not None and (type(bits) is not int or bits not in (16, 32, 64)):
            raise ValueError('Invalid observed code width')
        if backend in _DOS and mode not in ('real', 'protected', 'v86'):
            bits = None
        observation = raw.get('observation', {})
        if type(observation) is not dict:
            raise ValueError('Event observation must be an object')
        context = {'cpu_mode': mode, 'code_bits': bits,
                   'thread': raw.get('thread', (full or {}).get('thread')),
                   'task_id': raw.get('task_id'), 'mapping_id': raw.get('mapping_id'),
                   'registers_stage': observation.get('registers_stage')}
        for field in ('thread', 'task_id', 'mapping_id'):
            value = context[field]
            if value is not None and (type(value) not in (int, str) or type(value) is str and len(value) > 128):
                raise ValueError('Invalid execution context identity')
        previous_base = {k: v for k, v in last_context.items() if k != 'address_context'} if last_context else None
        if not contiguous or context != previous_base or full is not None:
            registers = {}
        if full is not None and 'register_changes' in raw:
            raise ValueError('Trace event cannot mix a full register snapshot with sparse deltas')
        updates = _updates(full if full is not None else raw.get('register_changes', {}), bits)
        if backend in _DOS and observation.get('flags_materialized') is not True:
            # Native DOS fetch traces can retain lazy arithmetic FLAGS and omit
            # their deltas. Only an explicitly materialized stopped observation
            # qualifies them; neither a seed nor a prior qualified value does.
            updates = {name: value for name, value in updates.items() if _REGISTERS[name][0] != 'flags'}
            registers = {name: value for name, value in registers.items() if _REGISTERS[name][0] != 'flags'}
        registers = _merge_registers(registers, updates)
        context['address_context'] = _address_context(raw, full, updates, registers, mode, bits)
        if last_context is not None and context != last_context:
            registers = dict(updates)
        if context['address_context'] is not None:
            controls = {name: context['address_context'][name] for name in ('cr0', 'cr3', 'cr4')
                        if name in context['address_context']}
            registers = _merge_registers(registers, controls)
        pc = _pc(raw, backend, mode)
        if observation.get('registers_stage') == 'before-instruction':
            pointer = 'rip' if bits == 64 else 'eip'
            width = _REGISTERS[pointer][1]
            if pc['offset'] <= (1 << width) - 1:
                for name in updates:
                    family, register_width, shift = _REGISTERS[name]
                    if family == 'ip' and updates[name] != (pc['offset'] >> shift) & ((1 << register_width) - 1):
                        raise ValueError('Observed instruction pointer differs from event PC')
                registers = _merge_registers(registers, {pointer: pc['offset']})
                if pc['segment'] is not None:
                    if 'cs' in updates and updates['cs'] != pc['segment']:
                        raise ValueError('Observed CS differs from event PC')
                    registers = _merge_registers(registers, {'cs': pc['segment']})
        source_identity = raw.get('identity', {})
        if type(source_identity) is not dict:
            raise ValueError('Event identity must be an object')
        if source_identity.get('source_version', identity['version']) != identity['version']:
            raise ValueError('Event source version identity mismatch')
        if source_identity.get('project_address') is not None and pc['project'] is not None:
            if _number(source_identity['project_address'], 'identity project PC') != pc['project']:
                raise ValueError('Event project address identity mismatch')
        if backend == 'qemu-dos' and ((source_identity.get('project_address') is None)
                                    != (pc['project'] is None)):
            raise ValueError('Native DOS source PC claims must agree')
        if source_identity.get('runtime_address') is not None:
            claimed = {'address': source_identity['runtime_address']}
            if backend == 'qemu-dos':
                claimed = dict(address=raw['address'], segmented_address=source_identity['runtime_address'],
                               address_context=raw.get('address_context'))
            claimed_pc = _pc(claimed, backend, mode)
            if any(claimed_pc[name] != pc[name] for name in ('linear', 'segment', 'offset')):
                raise ValueError('Event runtime address identity mismatch')
        source_context = None
        if backend in _DOS and pc['project'] is not None:
            projected_cs, remainder = divmod(pc['project'] - pc['offset'], 16)
            if remainder == 0 and 0 <= projected_cs <= 0xffff:
                source_context = f'real:{projected_cs:04x}'
            if source_context is None or source_identity.get('context', source_context) != source_context:
                raise ValueError('Inconsistent real-mode source address context')
            if 'runtime_load_segment' in mapping and 'static_load_segment' in mapping:
                delta = (_number(mapping['runtime_load_segment'], 'runtime load segment', 0xffff)
                         - _number(mapping['static_load_segment'], 'static load segment', 0xffff)) * 16
                if pc['linear'] - delta != pc['project']:
                    raise ValueError('Trace project mapping identity mismatch')
            if backend == 'qemu-dos':
                native_mapping = mapping.get('process', {}).get('source_mapping', {})
                static = _number(native_mapping.get('static_base'), 'native static image base')
                runtime = _number(native_mapping.get('runtime_base'), 'native runtime image base')
                if pc['project'] != pc['linear'] - runtime + static:
                    raise ValueError('Native DOS project mapping identity mismatch')
        elif backend in _PE and pc['project'] is not None:
            source_context = 'flat'
            if source_identity.get('context', 'flat') != 'flat':
                raise ValueError('Inconsistent flat source context')
            if 'runtime_image_base' in mapping and 'static_image_base' in mapping:
                delta = _number(mapping['runtime_image_base'], 'runtime image base') - _number(mapping['static_image_base'], 'static image base')
                if pc['linear'] - delta != pc['project']:
                    raise ValueError('Trace project mapping identity mismatch')
        mnemonic, size, digest = None, None, None
        code = raw.get('execution_bytes', raw.get('bytes'))
        if code is not None:
            if type(code) is not str or len(code) > 30 or len(code) % 2 or not re.fullmatch('[0-9a-fA-F]*', code):
                raise ValueError('Instruction lookahead must contain at most 15 hexadecimal bytes')
            if bits is not None and code:
                instruction = Decoder(bits, bytes.fromhex(code), ip=pc['offset']).decode()
                if not instruction.is_invalid:
                    size = instruction.len
                    mnemonic = _MNEMONICS.get(instruction.mnemonic)
                    digest = hashlib.sha256(bytes.fromhex(code)[:size]).hexdigest()
        site = None
        site_digest = digest
        if backend == 'qemu-dos':
            # The owned storage adapter independently reconstructs this claim
            # from original bytes, ordered fixups and the initial entry receipt.
            # Keep the observed runtime digest on the event for inspection.
            site_digest = source_identity.get('source_instruction_sha256')
            if site_digest is not None:
                _digest(site_digest, 'native source instruction sha256')
                if source_context is None or not digest or bits != 16:
                    raise ValueError('Native DOS source instruction has no qualified source PC')
        if (source_context is not None and site_digest and observation.get('registers_stage') == 'before-instruction'
                and (backend not in _PE or bits in (32, 64))):
            site = {'space': 'project', 'address': pc['project'], 'context': source_context,
                    'cpu_mode': mode, 'code_bits': bits, 'instruction_sha256': site_digest}
        matching_regions = [r for r in regions if pc[r['space']] is not None and r['start'] <= pc[r['space']] < r['end']]
        # Project regions take precedence over linear labels when both were supplied.
        region = next((r for r in matching_regions if r['space'] == 'project'), next(iter(matching_regions), None))
        events.append({'index': index, 'sequence': sequence, 'site': site, 'pc': pc,
                       'registers': dict(registers), 'mnemonic': mnemonic, 'size': size,
                       'instruction_sha256': digest, 'region': deepcopy(region),
                       'observation': deepcopy(observation), 'cpu_mode': mode, 'code_bits': bits,
                       'execution_context': context, 'contiguous': contiguous})
        if clocks[index] is not None:
            events[-1]['clock'] = clocks[index]
        last_sequence, last_context, explicit_sequence = sequence, context, has_sequence
    explicit = document.get('window')
    requested = document.get('requested_count')
    if requested is not None:
        requested = _number(requested, 'requested count', MAX_EVENTS)
    if explicit is not None:
        if type(explicit) is not dict or type(explicit.get('closed')) is not bool:
            raise ValueError('Explicit trace window requires boolean closed')
        closed = explicit['closed']; reason = _text(explicit.get('reason', 'explicit bounded window'), 'window reason')
    else:
        if type(document.get('complete', False)) is not bool:
            raise ValueError('Trace complete must be boolean')
        closed = document.get('complete', False) and requested is not None and requested == len(events)
        reason = 'requested event window captured' if closed else 'incomplete trace window'
    if gaps:
        closed, reason = False, 'sequence gaps in captured window'
    compiled = {'format': 'fdisbull-execution-events-1', 'identity': identity, 'run': run,
                'regions': regions, 'events': events,
                'window': {'closed': bool(closed), 'reason': reason, 'requested_count': requested,
                           'event_count': len(events), 'sequence_gaps': gaps},
                'unqualified_events': sum(e['site'] is None for e in events)}
    if endpoint_clock is not None:
        compiled['collector'] = {'current_stop': {'clock': endpoint_clock}}
    return compiled


def _artifact(compiled):
    value = compiled.get('artifact')
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'id', 'sha256'}:
        raise ValueError('Trace artifact requires id and sha256')
    return {'id': _text(value['id'], 'artifact id', 128), 'sha256': _digest(value['sha256'], 'artifact sha256')}


def _check_compiled(compiled):
    if type(compiled) is not dict or compiled.get('format') != 'fdisbull-execution-events-1':
        raise ValueError('Expected normalized execution events')
    _identity(compiled.get('identity'))
    _text(compiled.get('run'), 'run', 128)
    _artifact(compiled)
    if type(compiled.get('events')) is not list or len(compiled['events']) > MAX_EVENTS:
        raise ValueError('Compiled event budget exceeded')
    validate_trace_clocks(compiled, run=compiled['run'], backend=compiled['identity']['backend'])
    if type(compiled.get('window')) is not dict or compiled['window'].get('closed') is not True:
        raise ValueError('Narrowing requires a closed bounded trace window')
    validate_regions(compiled.get('regions'))


def _features(compiled, feature, registers, predicate):
    rows, unknown = {}, 0
    events = compiled['events']; initial = events[0] if events else None
    for index, event in enumerate(events):
        if predicate is not None:
            evaluated = _evaluate(predicate, event, initial, events[index - 1] if index else None)
            unknown += evaluated['matched'] is None
            if evaluated['matched'] is not True:
                continue
        if event['site'] is None:
            continue
        features = [{'feature': 'site', 'site': event['site']}] if feature == 'site' else []
        if feature == 'register-value':
            for name in registers:
                value = _register_value(event['registers'], name)
                if value is None:
                    unknown += 1
                else:
                    features.append({'feature': feature, 'site': event['site'], 'register': name, 'value': value})
        for item in features:
            key = _hash(item)
            if key not in rows:
                if len(rows) >= MAX_CANDIDATES:
                    raise ValueError('Execution candidate budget exceeded')
                rows[key] = {**deepcopy(item), 'key': key, 'hit_count': 0, 'indices': []}
            rows[key]['hit_count'] += 1
            if len(rows[key]['indices']) < MAX_ROW_SAMPLES:
                rows[key]['indices'].append(event['index'])
    return rows, unknown


def _seal(state):
    state['count'] = state['candidate_count'] = len(state['candidates'])
    state['state_sha256'] = _hash(state)
    return state


def _add_trial(state, compiled, observed, unknown, mode, label, predicate):
    if len(state['history']) >= MAX_HISTORY:
        raise ValueError('Execution search history budget exceeded')
    artifact = _artifact(compiled)
    sample_lookup = {_hash(sample): index for index, sample in enumerate(state['samples'])}
    for row in state['candidates']:
        match = observed.get(row['key'])
        if match is None:
            continue
        row['support_trials'] += 1
        row['hit_count'] += match['hit_count']
        for index in match['indices']:
            if len(row['samples']) >= MAX_ROW_SAMPLES:
                break
            event = compiled['events'][index]
            sample = {'artifact': artifact, 'run': compiled['run'], 'index': index, 'sequence': event['sequence']}
            if 'clock' in event:
                sample['clock'] = validate_clock(event['clock'], run=compiled['run'])
            digest = _hash(sample)
            if digest not in sample_lookup:
                if len(state['samples']) >= MAX_SAMPLES:
                    raise ValueError('Execution witness sample budget exceeded')
                sample_lookup[digest] = len(state['samples']); state['samples'].append(sample)
            number = sample_lookup[digest]
            if number not in row['samples']:
                row['samples'].append(number)
    state['history'].append({'mode': mode, 'label': _text(label, 'trial label', 128),
                             'predicate': deepcopy(predicate), 'artifact': artifact, 'run': compiled['run'],
                             'window': deepcopy(compiled['window']), 'event_count': len(compiled['events']),
                             'unqualified_events': compiled['unqualified_events'], 'unknown_observations': unknown,
                             'observed_count': len(observed), 'candidate_count': len(state['candidates'])})


def start_search(compiled, *, feature='site', registers=None, predicate=None, label='trial'):
    """Seed candidates from one complete bounded window of observed features."""
    _check_compiled(compiled)
    if feature not in ('site', 'register-value'):
        raise ValueError('Execution feature must be site or register-value')
    if feature == 'register-value':
        registers = _registers(registers)
    elif registers is not None:
        raise ValueError('registers applies only to register-value searches')
    predicate = validate_predicate(predicate) if predicate is not None else None
    observed, unknown = _features(compiled, feature, registers, predicate)
    rows = [{**{k: v for k, v in row.items() if k not in ('indices', 'hit_count')},
             'hit_count': 0, 'support_trials': 0, 'samples': []} for _, row in sorted(observed.items())]
    state = {'format': 'fdisbull-execution-search-1', 'identity': deepcopy(compiled['identity']),
             'feature': feature, 'registers': deepcopy(registers), 'regions': deepcopy(compiled['regions']),
             'candidates': rows, 'samples': [], 'history': [], 'complete': True, 'parent_sha256': None}
    _add_trial(state, compiled, observed, unknown, 'start', label, predicate)
    return _seal(state)


def validate_search(state):
    """Validate bounded retained state; callers still authenticate its artifacts."""
    keys = {'format', 'identity', 'feature', 'registers', 'regions', 'candidates', 'samples', 'history',
            'complete', 'parent_sha256', 'count', 'candidate_count', 'state_sha256'}
    if type(state) is not dict or set(state) != keys or state.get('format') != 'fdisbull-execution-search-1':
        raise ValueError('Expected an execution search state')
    for name, maximum in (('candidates', MAX_CANDIDATES), ('samples', MAX_SAMPLES), ('history', MAX_HISTORY)):
        if type(state[name]) is not list or len(state[name]) > maximum:
            raise ValueError('Execution state ' + name + ' budget exceeded')
    _identity(state['identity']); validate_regions(state['regions'])
    if state['feature'] == 'register-value':
        _registers(state['registers'])
    elif state['feature'] != 'site' or state['registers'] is not None:
        raise ValueError('Invalid execution search feature')
    if state['complete'] is not True or not state['history']:
        raise ValueError('Execution search requires complete retained history')
    count = len(state['candidates'])
    if type(state['count']) is not int or type(state['candidate_count']) is not int or state['count'] != count or state['candidate_count'] != count:
        raise ValueError('Execution candidate count mismatch')
    if state['parent_sha256'] is not None:
        _digest(state['parent_sha256'], 'parent state sha256')
    digest = _digest(state['state_sha256'], 'state sha256')
    payload = {k: v for k, v in state.items() if k != 'state_sha256'}
    try:
        encoded = _encoded(payload)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError('Execution state must contain finite JSON data') from error
    if len(encoded) > 32 * 1024 * 1024 or hashlib.sha256(encoded).hexdigest() != digest:
        raise ValueError('Execution state seal mismatch or size budget exceeded')
    seen = set()
    for row in state['candidates']:
        fields = {'key', 'feature', 'site', 'hit_count', 'support_trials', 'samples'} | ({'register', 'value'} if state['feature'] == 'register-value' else set())
        if type(row) is not dict or set(row) != fields or row['feature'] != state['feature']:
            raise ValueError('Invalid candidate row')
        key = _digest(row['key'], 'candidate key')
        site = row['site']
        if (type(site) is not dict or set(site) != {'space', 'address', 'context', 'cpu_mode', 'code_bits', 'instruction_sha256'}
                or site['space'] != 'project' or type(site['code_bits']) is not int or site['code_bits'] not in (16, 32, 64)
                or site['cpu_mode'] not in ('real', 'protected', 'v86', 'flat')):
            raise ValueError('Invalid qualified candidate site')
        _number(site['address'], 'site address'); _text(site['context'], 'site context', 128)
        _digest(site['instruction_sha256'], 'site instruction sha256')
        feature = {k: row[k] for k in ('feature', 'site')}
        if state['feature'] == 'register-value':
            name = _register(row['register'])
            if name not in state['registers']:
                raise ValueError('Candidate register differs from search specification')
            feature.update(register=name, value=_number(row['value'], 'candidate value', (1 << _REGISTERS[name][1]) - 1))
        if key in seen or _hash(feature) != key:
            raise ValueError('Duplicate or inconsistent candidate identity')
        seen.add(key)
        _number(row['hit_count'], 'hit count', MAX_EVENTS * MAX_HISTORY)
        _number(row['support_trials'], 'support trials', MAX_HISTORY)
        if type(row['samples']) is not list or not 1 <= len(row['samples']) <= MAX_ROW_SAMPLES:
            raise ValueError('Candidate requires bounded witness samples')
        for sample in row['samples']:
            _number(sample, 'sample index', len(state['samples']) - 1)
    for sample in state['samples']:
        fields = {'artifact', 'run', 'index', 'sequence'}
        if type(sample) is dict and 'clock' in sample:
            fields.add('clock')
        if type(sample) is not dict or set(sample) != fields:
            raise ValueError('Invalid witness sample')
        _artifact({'artifact': sample['artifact']}); _text(sample['run'], 'sample run', 128)
        _number(sample['index'], 'sample event index', MAX_EVENTS - 1)
        _number(sample['sequence'], 'sample event sequence')
        if 'clock' in sample:
            if state['identity']['backend'] != 'qemu-dos':
                raise ValueError('Source clock witness requires the native DOS backend')
            validate_clock(sample['clock'], run=sample['run'])
    for index, trial in enumerate(state['history']):
        fields = {'mode', 'label', 'predicate', 'artifact', 'run', 'window', 'event_count',
                  'unqualified_events', 'unknown_observations', 'observed_count', 'candidate_count'}
        if type(trial) is not dict or set(trial) != fields or trial['mode'] not in (('start',) if index == 0 else ('retain', 'exclude')):
            raise ValueError('Invalid trial history')
        _text(trial['label'], 'trial label', 128); _text(trial['run'], 'trial run', 128)
        _artifact({'artifact': trial['artifact']})
        if trial['predicate'] is not None and validate_predicate(trial['predicate']) != trial['predicate']:
            raise ValueError('Trial predicate is not normalized')
        if type(trial['window']) is not dict or trial['window'].get('closed') is not True:
            raise ValueError('Trial history requires closed windows')
        for name in ('event_count', 'unqualified_events'):
            _number(trial[name], 'trial ' + name, MAX_EVENTS)
        _number(trial['unknown_observations'], 'trial unknown observations', MAX_EVENTS * 32)
        for name in ('observed_count', 'candidate_count'):
            _number(trial[name], 'trial ' + name, MAX_CANDIDATES)
        if index and trial['candidate_count'] > state['history'][index - 1]['candidate_count']:
            raise ValueError('Trial history widens candidates')
    if state['history'][-1]['candidate_count'] != count:
        raise ValueError('Trial history candidate count mismatch')
    return deepcopy(state)


def refine_search(state, compiled, *, mode='retain', predicate=None, label='trial'):
    """Intersect/subtract observed features without reintroducing candidates."""
    parent = validate_search(state)
    _check_compiled(compiled)
    if mode not in ('retain', 'exclude'):
        raise ValueError('Refinement mode must be retain or exclude')
    if parent['identity'] != compiled['identity']:
        raise ValueError('Execution comparison identity mismatch')
    if [_region_key(r) for r in parent['regions']] != [_region_key(r) for r in compiled['regions']]:
        raise ValueError('Execution comparison region identity mismatch')
    predicate = validate_predicate(predicate) if predicate is not None else None
    observed, unknown = _features(compiled, parent['feature'], parent['registers'], predicate)
    parent['parent_sha256'] = parent.pop('state_sha256')
    parent['candidates'] = [row for row in parent['candidates'] if (row['key'] in observed) == (mode == 'retain')]
    used = sorted({number for row in parent['candidates'] for number in row['samples']})
    remap = {number: index for index, number in enumerate(used)}
    parent['samples'] = [parent['samples'][number] for number in used]
    for row in parent['candidates']:
        row['samples'] = [remap[number] for number in row['samples']]
    _add_trial(parent, compiled, observed, unknown, mode, label, predicate)
    return _seal(parent)


def search_results(state, *, offset=0, limit=64):
    state = validate_search(state)
    offset = _number(offset, 'result offset', MAX_CANDIDATES)
    if type(limit) is not int or not 1 <= limit <= MAX_RESULT_ROWS:
        raise ValueError('Result limit must be 1..4096')
    rows = state['candidates'][offset:offset + limit]
    used = sorted({number for row in rows for number in row['samples']})
    samples = [dict(state['samples'][number], sample_index=number) for number in used]
    return {'rows': rows, 'count': state['candidate_count'], 'total': state['candidate_count'],
            'candidate_count': state['candidate_count'], 'returned_count': len(rows),
            'offset': offset, 'limit': limit, 'next_offset': offset + len(rows) if offset + len(rows) < state['candidate_count'] else None,
            'history': state['history'], 'samples': samples, 'identity': state['identity'],
            'feature': state['feature'], 'state_sha256': state['state_sha256'],
            'scope': 'Observed qualified features in declared bounded windows; no function, cause, or whole-program absence claim.'}
