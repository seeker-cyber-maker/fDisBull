"""Bounded captured-region equivalence and reversible evidence contraction.

Proofs concern a caller-declared live-state/private-RAM contract and the two
captured paths. They do not establish whole-function or external equivalence.
"""
from copy import deepcopy
import hashlib
import json
import time

import capstone
from capstone import x86_const as X
from iced_x86 import Decoder

from .behavior_diff import _correspondences, _site
from .pe_guard_analysis import _receipt
from .pe_guard_model import ARITHMETIC_MASK, FLAG_BITS, condition_name
from .pe_path_transfer import _qualified_trace, _state
from .wine_arch import register_names


_GPR32_TO_64 = dict(zip(
    ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'),
    ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'))) | {
        f'r{index}d': f'r{index}' for index in range(8, 16)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _contract(value, bits):
    if not isinstance(value, dict) or set(value) - {
            'live_registers', 'live_flags', 'entry_registers', 'entry_register_ranges', 'entry_memory', 'memory_ranges',
            'memory_model', 'memory_observation'}:
        raise ValueError('Unknown regional contract field')
    names = register_names(bits) - ({'rip', 'rflags'} if bits == 64 else {'eip', 'eflags'})
    live = value.get('live_registers', sorted(names))
    flags = value.get('live_flags', 0xffffffff)
    entry = value.get('entry_registers', {})
    register_ranges = value.get('entry_register_ranges', {})
    if (not isinstance(live, list) or any(not isinstance(n, str) or n not in names for n in live)
            or len(live) != len(set(live)) or type(flags) is not int or not 0 <= flags <= 0xffffffff
            or not isinstance(entry, dict) or any(n not in names or not isinstance(v, str)
            or not v.startswith('0x') or not 0 <= int(v, 16) < 1 << bits for n, v in entry.items())):
        raise ValueError('Invalid live state or entry-register assumptions')
    if not isinstance(register_ranges, dict):
        raise ValueError('Entry-register ranges must be a mapping')
    for name, bounds in register_ranges.items():
        if (name not in names or not isinstance(bounds, dict) or set(bounds) != {'min', 'max'}
                or any(not isinstance(v, str) or not v.startswith('0x') for v in bounds.values())
                or not 0 <= int(bounds['min'], 16) <= int(bounds['max'], 16) < 1 << bits):
            raise ValueError('Entry-register ranges require inclusive unsigned min/max bounds')
    ranges = value.get('memory_ranges', [])
    mode = value.get('memory_observation', 'ordered')
    if not isinstance(ranges, list) or len(ranges) > 32 or mode not in ('ordered', 'final'):
        raise ValueError('Invalid memory observation contract')
    addresses = set()
    normalized = []
    for item in ranges:
        if (not isinstance(item, dict) or set(item) != {'address', 'length'}
                or not isinstance(item['address'], str) or not item['address'].startswith('0x')
                or type(item['length']) is not int or not 1 <= item['length'] <= 256):
            raise ValueError('Memory ranges require an address and 1..256 bytes')
        address, length = int(item['address'], 16), item['length']
        cells = set(range(address, address + length))
        if address < 0 or address + length > 1 << bits or addresses & cells:
            raise ValueError('Memory ranges overlap or exceed process width')
        addresses |= cells
        normalized.append({'address': hex(address), 'length': length})
    if len(addresses) > 256 or (addresses and value.get('memory_model') != 'private_ordinary_ram'):
        raise ValueError('At most 256 bytes of explicitly private ordinary RAM are supported')
    entry_memory = value.get('entry_memory', [])
    if not isinstance(entry_memory, list) or len(entry_memory) > 256:
        raise ValueError('Entry-memory assumptions require at most 256 bounded rows')
    entry_cells, fixed_memory = set(), []
    for item in entry_memory:
        if (not isinstance(item, dict) or set(item) != {'address', 'hex'}
                or not isinstance(item['address'], str) or not item['address'].startswith('0x')
                or not isinstance(item['hex'], str) or not 2 <= len(item['hex']) <= 512
                or len(item['hex']) % 2):
            raise ValueError('Entry-memory assumptions require an address and 1..256 exact bytes')
        address, raw = int(item['address'], 16), bytes.fromhex(item['hex'])
        cells = set(range(address, address + len(raw)))
        if len(raw) * 2 != len(item['hex']) or not cells <= addresses or cells & entry_cells:
            raise ValueError('Entry-memory assumptions must be nonoverlapping subsets of declared RAM')
        entry_cells |= cells
        fixed_memory.append({'address': hex(address), 'hex': raw.hex()})
    return {'live_registers': sorted(live), 'live_flags': flags,
            'entry_registers': {n: hex(int(v, 16)) for n, v in sorted(entry.items())},
            'entry_register_ranges': {n: {key: hex(int(v, 16)) for key, v in sorted(bounds.items())}
                                      for n, bounds in sorted(register_ranges.items())},
            'entry_memory': sorted(fixed_memory, key=lambda row: int(row['address'], 16)),
            'memory_ranges': sorted(normalized, key=lambda r: int(r['address'], 16)),
            'memory_model': 'private_ordinary_ram' if addresses else 'no_memory_access',
            'memory_observation': mode}, sorted(addresses), sorted(names)


def _snapshots(document, addresses):
    if not addresses:
        if document not in (None, {'entry': [], 'exit': []}):
            raise ValueError('Memory evidence supplied without a memory contract')
        return {}, {}
    if not isinstance(document, dict) or set(document) != {'entry', 'exit'}:
        raise ValueError('Entry and exit RAM evidence is required')
    result = []
    for label in ('entry', 'exit'):
        cells = {}
        if not isinstance(document[label], list) or len(document[label]) > 256:
            raise ValueError('Malformed memory evidence')
        for row in document[label]:
            if (not isinstance(row, dict) or set(row) != {'address', 'hex'}
                    or not isinstance(row['address'], str) or not isinstance(row['hex'], str)
                    or not 2 <= len(row['hex']) <= 512 or len(row['hex']) % 2):
                raise ValueError('Malformed memory snapshot')
            raw = bytes.fromhex(row['hex'])
            address = int(row['address'], 16)
            for offset, byte in enumerate(raw):
                if address + offset in cells:
                    raise ValueError('Overlapping memory snapshots')
                cells[address + offset] = byte
        if set(cells) != set(addresses):
            raise ValueError('Snapshots must cover exactly the declared RAM')
        result.append(cells)
    return tuple(result)


def _condition(z, name, flags):
    f = {n: z.Extract(bit, bit, flags) == 1 for n, bit in FLAG_BITS.items()}
    return {'always': z.BoolVal(True), 'o': f['of'], 'no': z.Not(f['of']),
            'b': f['cf'], 'ae': z.Not(f['cf']), 'e': f['zf'], 'ne': z.Not(f['zf']),
            'be': z.Or(f['cf'], f['zf']), 'a': z.Not(z.Or(f['cf'], f['zf'])),
            's': f['sf'], 'ns': z.Not(f['sf']), 'p': f['pf'], 'np': z.Not(f['pf']),
            'l': f['sf'] != f['of'], 'ge': f['sf'] == f['of'],
            'le': z.Or(f['zf'], f['sf'] != f['of']),
            'g': z.And(z.Not(f['zf']), f['sf'] == f['of'])}[name]


def _arithmetic_flags(z, op, a, b, result, flags, fresh):
    bits = a.size()
    sign = lambda v: z.Extract(bits - 1, bits - 1, v) == 1
    logical = op in ('xor', 'and', 'or')
    carry = z.BoolVal(False) if logical else z.ULT(a, b) if op in ('sub', 'cmp') else z.ULT(result, a)
    overflow = (z.BoolVal(False) if logical else
                z.And(sign(a) != sign(b), sign(result) != sign(a)) if op in ('sub', 'cmp') else
                z.And(sign(a) == sign(b), sign(result) != sign(a)))
    parity = z.Extract(0, 0, result)
    for bit in range(1, 8):
        parity = parity ^ z.Extract(bit, bit, result)
    values = {'cf': carry, 'of': overflow, 'sf': sign(result), 'zf': result == 0,
              'pf': parity == 0, 'af': fresh if logical else z.Extract(4, 4, a ^ b ^ result) == 1}
    out = flags & z.BitVecVal((~ARITHMETIC_MASK) & 0xffffffff, 32)
    for name, bit in FLAG_BITS.items():
        out = out | z.If(values[name], z.BitVecVal(1 << bit, 32), z.BitVecVal(0, 32))
    return out


def _execute(z, trace, bits, initial, initial_flags, initial_memory, contract, snapshots, side, deadline):
    regs, flags, memory = dict(initial), initial_flags, dict(initial_memory)
    domains, accesses, returns = [], [], []
    safety, alias_work = [], 0
    runs = []
    for address in sorted(memory):
        if runs and runs[-1][1] == address:
            runs[-1][1] += 1
        else:
            runs.append([address, address + 1])
    undefined = 0
    events = trace['events']
    concrete, concrete_flags, _ = _state(events[0], bits)
    if concrete_flags & 2 != 2:
        raise ValueError('Captured FLAGS contradict fixed architectural bit 1')
    if any(concrete[n] != int(v, 16) for n, v in contract['entry_registers'].items()):
        raise ValueError('Captured entry contradicts fixed-register assumptions')
    if any(not int(bounds['min'], 16) <= concrete[n] <= int(bounds['max'], 16)
           for n, bounds in contract['entry_register_ranges'].items()):
        raise ValueError('Captured entry contradicts register-range assumptions')
    for row in contract['entry_memory']:
        address = int(row['address'], 16)
        if any(snapshots[0][address + offset] != byte
               for offset, byte in enumerate(bytes.fromhex(row['hex']))):
            raise ValueError('Captured entry contradicts fixed-memory assumptions')
    substitutions = [(initial[n], z.BitVecVal(v, bits)) for n, v in concrete.items()]
    substitutions += [(initial_flags, z.BitVecVal(concrete_flags, 32))]
    substitutions += [(initial_memory[a], z.BitVecVal(v, 8)) for a, v in snapshots[0].items()]
    def observed(expression):
        result = z.simplify(z.substitute(expression, *substitutions))
        if not z.is_bv_value(result):
            raise ValueError('Sampled expression is not concrete')
        return result.as_long()
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64 if bits == 64 else capstone.CS_MODE_32)
    decoder.detail = True
    for index, event in enumerate(events[:-1]):
        if time.monotonic() >= deadline:
            raise ValueError('Total regional proof deadline exhausted during model construction')
        following = events[index + 1]
        if event['observation'].get('instruction_completed') is not True:
            raise ValueError(f'Event {index}: incomplete instruction')
        _, _, thread = _state(event, bits)
        next_regs, next_flags, next_thread = _state(following, bits)
        if thread is None or thread != next_thread:
            raise ValueError(f'Event {index}: selected thread changes')
        code = event.get('execution_bytes', event.get('bytes'))
        if not isinstance(code, str) or not 2 <= len(code) <= 30 or len(code) % 2:
            raise ValueError(f'Event {index}: missing exact instruction')
        raw = bytes.fromhex(code)
        address = int(event['address'], 16)
        native = list(decoder.disasm(raw, address))
        if len(native) != 1 or native[0].size != len(raw) or any(native[0].prefix):
            raise ValueError(f'Event {index}: unsupported decode or legacy prefix')
        ins = native[0]
        iced = Decoder(bits, raw, ip=address).decode()
        sequential = (address + len(raw)) % (1 << bits)
        next_address = int(following['address'], 16)
        def reg_name(operand):
            name = ins.reg_name(operand.reg)
            if name not in regs or operand.size * 8 != bits:
                raise ValueError(f'Event {index}: partial register operand')
            return name
        def memory_location(value, width):
            nonlocal alias_work
            fixed = [(initial[n], z.BitVecVal(int(v, 16), bits))
                     for n, v in contract['entry_registers'].items()]
            value = z.simplify(z.substitute(value, *fixed))
            if width not in (1, 2, 4, 8):
                raise ValueError(f'Event {index}: unsupported memory width')
            concrete_address = observed(value)
            if concrete_address + width > 1 << bits or any(
                    concrete_address + k not in memory for k in range(width)):
                raise ValueError(f'Event {index}: memory access outside declared RAM')
            valid = z.Or(*[z.And(z.UGE(value, start), z.ULE(value, end - width))
                           for start, end in runs if end - start >= width])
            # Check under guards preceding the access, never guards encountered later.
            safety.append({'event_index': index, 'address': value, 'width': width,
                           'prefix': z.And(*domains), 'valid': valid})
            if not z.is_bv_value(value):
                alias_work += width * len(memory)
                if alias_work > 32768:
                    raise ValueError('Symbolic alias-expression budget exceeds 32768 byte-cell operations')
            return value, width
        def location(operand):
            value = z.BitVecVal(operand.mem.disp % (1 << bits), bits)
            for register, scale in ((operand.mem.base, 1), (operand.mem.index, operand.mem.scale)):
                if not register:
                    continue
                name = ins.reg_name(register)
                term = z.BitVecVal(sequential, bits) if name in ('rip', 'eip') else regs.get(name)
                if term is None:
                    raise ValueError(f'Event {index}: unknown address register')
                value = value + term * scale
            return memory_location(value, operand.size)
        def byte_at(address):
            address = z.simplify(address)
            if z.is_bv_value(address):
                return memory.get(address.as_long(), z.BitVecVal(0, 8))
            value = z.BitVecVal(0, 8)
            for cell, byte in memory.items():
                value = z.If(address == cell, byte, value)
            return value
        def read_memory(address, width):
            value = byte_at(address) if width == 1 else z.Concat(*[
                byte_at(address + k) for k in reversed(range(width))])
            accesses.append(('read', address, width, value))
            return value
        def read(operand):
            if operand.type == X.X86_OP_REG:
                return regs[reg_name(operand)]
            if operand.type == X.X86_OP_IMM:
                return z.BitVecVal(operand.imm % (1 << (operand.size * 8)), operand.size * 8)
            if operand.type == X.X86_OP_MEM:
                a, width = location(operand)
                return read_memory(a, width)
            raise ValueError(f'Event {index}: unknown operand')
        if raw == b'\xc3':
            stack = 'rsp' if bits == 64 else 'esp'
            stack_address, width = memory_location(regs[stack], bits // 8)
            target = read_memory(stack_address, width)
            if observed(target) != next_address:
                raise ValueError(f'Event {index}: return target contradicts captured successor')
            # The observed caller is a path condition, not an inferred constant
            # value for arbitrary stack data. Bounds use only preceding guards.
            domains.append(target == z.BitVecVal(next_address, bits))
            returns.append({'event_index': index, 'target': target,
                            'stack_address': stack_address, 'width': width})
            regs[stack] = regs[stack] + width
        elif iced.is_jcc_short_or_near or iced.is_jmp_short_or_near:
            predicate = _condition(z, condition_name(iced), flags)
            # Guard feasibility is checked against captured FLAGS, including equal target/fallthrough.
            from .pe_guard_model import decision
            actual_flags = int(event['registers']['rflags' if bits == 64 else 'eflags'], 16)
            taken = decision(condition_name(iced), actual_flags)
            if next_address != (iced.near_branch_target if taken else sequential):
                raise ValueError(f'Event {index}: impossible branch successor')
            domains.append(predicate if taken else z.Not(predicate))
        else:
            if next_address != sequential:
                raise ValueError(f'Event {index}: unexpected control transfer')
            operands = ins.operands
            if raw == b'\x90':
                pass
            elif ins.mnemonic in ('mov', 'movabs') and len(operands) == 2:
                dest, src = operands
                if bits == 64 and dest.type == X.X86_OP_REG and dest.size == 4:
                    # A PE64 dword GPR write replaces the complete 64-bit value:
                    # read only the source's low half, then clear the high half.
                    name = _GPR32_TO_64.get(ins.reg_name(dest.reg))
                    source = _GPR32_TO_64.get(ins.reg_name(src.reg)) if src.type == X.X86_OP_REG else None
                    if name is None or src.size != 4:
                        raise ValueError(f'Event {index}: unsupported dword MOV operands')
                    if src.type == X.X86_OP_IMM:
                        value = z.BitVecVal(src.imm % (1 << 32), 32)
                    elif source is not None:
                        value = z.Extract(31, 0, regs[source])
                    else:
                        raise ValueError(f'Event {index}: dword MOV requires an immediate or GPR source')
                    regs[name] = z.ZeroExt(32, value)
                elif dest.type == X.X86_OP_REG:
                    value = read(src)
                    name = reg_name(dest)
                    if value.size() != bits:
                        raise ValueError(f'Event {index}: aliased load width')
                    regs[name] = value
                elif dest.type == X.X86_OP_MEM and src.type != X.X86_OP_MEM:
                    value = read(src)
                    a, width = location(dest)
                    value = (z.SignExt(width * 8 - value.size(), value) if value.size() < width * 8
                             else z.Extract(width * 8 - 1, 0, value))
                    accesses.append(('write', a, width, value))
                    for k in range(width):
                        pointer = z.simplify(a + k)
                        byte = z.Extract(k * 8 + 7, k * 8, value)
                        if z.is_bv_value(pointer):
                            if pointer.as_long() in memory:
                                memory[pointer.as_long()] = byte
                        else:
                            memory = {cell: z.If(pointer == cell, byte, old) for cell, old in memory.items()}
                else:
                    raise ValueError(f'Event {index}: unsupported MOV destination')
            elif ins.mnemonic in ('add', 'sub', 'xor', 'and', 'or', 'cmp') and len(operands) == 2:
                if operands[0].type != X.X86_OP_REG or operands[1].type not in (X.X86_OP_REG, X.X86_OP_IMM):
                    raise ValueError(f'Event {index}: arithmetic memory effect unsupported')
                name = reg_name(operands[0])
                a, b = regs[name], read(operands[1])
                if b.size() != bits:
                    b = z.SignExt(bits - b.size(), b)
                op = ins.mnemonic
                result = {'add': lambda: a + b, 'sub': lambda: a - b, 'cmp': lambda: a - b,
                          'xor': lambda: a ^ b, 'and': lambda: a & b, 'or': lambda: a | b}[op]()
                fresh = z.Bool(f'{side}_undefined_af_{index}')
                flags = _arithmetic_flags(z, op, a, b, result, flags, fresh)
                undefined = (1 << FLAG_BITS['af']) if op in ('xor', 'and', 'or') else 0
                if op != 'cmp':
                    regs[name] = result
            else:
                raise ValueError(f'Event {index}: instruction outside regional model')
        for name, expected in next_regs.items():
            if observed(regs[name]) != expected:
                raise ValueError(f'Event {index}: register {name} contradicts regional model')
        mask = 0xffffffff ^ undefined
        if observed(flags & z.BitVecVal(mask, 32)) != next_flags & mask:
            raise ValueError(f'Event {index}: FLAGS contradict regional model')
    if contract['live_flags'] & undefined:
        raise ValueError('Live FLAGS include undefined AF from a logical operation')
    if any(observed(memory[a]) != v for a, v in snapshots[1].items()):
        raise ValueError('Exit RAM snapshot contradicts modeled stores')
    return {'registers': regs, 'flags': flags, 'memory': memory,
            'domain': z.And(*domains), 'accesses': accesses, 'safety': safety,
            'alias_byte_cell_operations': alias_work, 'returns': returns}


def compare_pe_regions(baseline, layer, *, contract, same_source=False, correspondence=None,
                       baseline_memory=None, layer_memory=None, timeout_ms=1000):
    """Prove captured-path regional equivalence under an explicit live-state contract.

    Internal sites may be n:m; entry and exit correspondence must be established.
    Solver absence, unsupported behavior, vacuity and timeout never contract.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    if type(same_source) is not bool:
        raise ValueError('same_source must be boolean')
    bits, other_bits = _qualified_trace(baseline), _qualified_trace(layer)
    if bits != other_bits:
        raise ValueError('Regional comparison requires matching PE widths')
    normalized, addresses, names = _contract(contract, bits)
    base = {'format': 'fdisbull-pe-region-equivalence-1', 'status': 'unknown', 'contract': normalized,
            'contraction': None, 'counterexample': None, 'semantic_equivalence': None,
            'scope': 'Captured paths and declared live state/private RAM; other paths, timing and external effects unknown'}
    try:
        snapshots = [_snapshots(doc, addresses) for doc in (baseline_memory, layer_memory)]
    except (TypeError, ValueError) as error:
        return base | {'reason': str(error)}
    base['sampled_entry_state_equal'] = (_state(baseline['events'][0], bits)[:2]
        == _state(layer['events'][0], bits)[:2] and snapshots[0][0] == snapshots[1][0])
    base['sampled_exit_state_equal'] = (_state(baseline['events'][-1], bits)[:2]
        == _state(layer['events'][-1], bits)[:2] and snapshots[0][1] == snapshots[1][1])
    if same_source and correspondence is not None:
        raise ValueError('Choose same_source or explicit boundary correspondence')
    if same_source:
        if any(baseline['mapping'][k] != layer['mapping'][k] for k in ('source_sha256', 'version_sha256')):
            raise ValueError('Same-source regions require matching byte identities')
        boundaries = all(_site(baseline['events'][i]) == _site(layer['events'][i]) for i in (0, -1))
    else:
        left_map, right_map = _correspondences(correspondence or [])
        boundaries = all(left_map.get(_site(baseline['events'][i])) is not None
                         and left_map.get(_site(baseline['events'][i])) == right_map.get(_site(layer['events'][i]))
                         for i in (0, -1))
    if not boundaries:
        return base | {'reason': 'Common entry and exit correspondence is required'}
    if any(len(t['events']) > 257 for t in (baseline, layer)):
        return base | {'reason': 'Regional instruction budget exceeds 256 steps'}
    # Declared ordinary RAM cannot also be an instruction source, including the exit site.
    for trace in (baseline, layer):
        for event in trace['events']:
            code = event.get('execution_bytes', event.get('bytes'))
            if not isinstance(code, str) or len(code) > 30 or len(code) % 2:
                return base | {'reason': 'Invalid bounded code evidence'}
            try:
                start = int(event['address'], 16)
                length = len(bytes.fromhex(code))
            except ValueError:
                return base | {'reason': 'Malformed instruction-byte evidence'}
            if any(a in addresses for a in range(start, start + length)):
                return base | {'reason': 'Declared memory overlaps captured code'}
    try:
        import z3 as z
    except ImportError:
        return base | {'reason': 'Optional z3 proof dependency is unavailable'}
    deadline = time.monotonic() + timeout_ms / 1000
    base['solver'] = {'name': 'z3', 'version': z.get_version_string(), 'timeout_ms_total': timeout_ms}
    base['sources'] = {'baseline': _receipt(baseline) | {'memory_sha256': _digest(baseline_memory)},
                       'layer': _receipt(layer) | {'memory_sha256': _digest(layer_memory)}}
    initial = {n: z.BitVec('entry_' + n, bits) for n in names}
    flags = z.BitVec('entry_flags', 32)
    memory = {a: z.BitVec(f'entry_ram_{a:x}', 8) for a in addresses}
    assumptions = [initial[n] == int(v, 16) for n, v in normalized['entry_registers'].items()]
    for n, bounds in normalized['entry_register_ranges'].items():
        assumptions += [z.UGE(initial[n], int(bounds['min'], 16)), z.ULE(initial[n], int(bounds['max'], 16))]
    for row in normalized['entry_memory']:
        address = int(row['address'], 16)
        assumptions += [memory[address + offset] == byte
                        for offset, byte in enumerate(bytes.fromhex(row['hex']))]
    assumptions.append((flags & 2) == 2)  # Fixed architectural FLAGS bit.
    try:
        a = _execute(z, baseline, bits, initial, flags, memory, normalized, snapshots[0], 'baseline', deadline)
        b = _execute(z, layer, bits, initial, flags, memory, normalized, snapshots[1], 'layer', deadline)
    except ValueError as error:
        return base | {'reason': str(error)}
    solver = z.Solver()
    def query(claim):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            return z.unknown, None, 'Total regional proof deadline exhausted'
        solver.set(timeout=remaining)
        solver.push()
        solver.add(*assumptions, claim)
        result = solver.check()
        model = solver.model() if result == z.sat else None
        reason = solver.reason_unknown() if result == z.unknown else None
        solver.pop()
        return result, model, reason
    for side, modeled in (('baseline', a), ('layer', b)):
        for access in modeled['safety']:
            outcome, model, reason = query(z.And(access['prefix'], z.Not(access['valid'])))
            if outcome == z.sat:
                val = lambda expr: hex(model.eval(expr, model_completion=True).as_long())
                return base | {'reason': 'Memory access may escape declared RAM under its prior guards',
                    'safety_counterexample': {'side': side, 'event_index': access['event_index'],
                        'address': val(access['address']), 'width': access['width'],
                        'entry_general': {n: val(v) for n, v in initial.items()},
                        'entry_flags': val(flags), 'entry_memory': {hex(p): val(v) for p, v in memory.items()}}}
            if outcome == z.unknown:
                return base | {'reason': 'Memory bounds solver unknown: ' + str(reason)}
    base['memory_safety'] = {'status': 'proved_under_entry_assumptions_and_prior_guards',
                            'accesses_checked': len(a['safety']) + len(b['safety']),
                            'alias_byte_cell_operations': {'baseline': a['alias_byte_cell_operations'],
                                                           'layer': b['alias_byte_cell_operations']}}
    def failure(kind, model):
        value = lambda expr: hex(model.eval(expr, model_completion=True).as_long())
        return base | {'status': 'different', 'difference': kind, 'counterexample': {
            'entry_general': {n: value(v) for n, v in initial.items()}, 'entry_flags': value(flags),
            'entry_memory': {hex(p): value(v) for p, v in memory.items()},
            'baseline_path_admitted': z.is_true(model.eval(a['domain'], model_completion=True)),
            'layer_path_admitted': z.is_true(model.eval(b['domain'], model_completion=True)),
            'differing_live_registers': {n: {'baseline': value(a['registers'][n]), 'layer': value(b['registers'][n])}
                                         for n in normalized['live_registers']
                                         if value(a['registers'][n]) != value(b['registers'][n])},
            'masked_flags': {'baseline': value(a['flags'] & normalized['live_flags']),
                             'layer': value(b['flags'] & normalized['live_flags'])},
            'differing_memory_bytes': {hex(p): {'baseline': value(a['memory'][p]), 'layer': value(b['memory'][p])}
                                       for p in addresses if value(a['memory'][p]) != value(b['memory'][p])},
            'memory_access_counts': {'baseline': len(a['accesses']), 'layer': len(b['accesses'])},
            'validation': 'Symbolic model counterexample; native replay required'}}
    for domain in (a['domain'], b['domain']):
        outcome, _, reason = query(domain)
        if outcome != z.sat:
            return base | {'reason': 'Infeasible path domain' if outcome == z.unsat else 'Solver unknown: ' + str(reason)}
    outcome, model, reason = query(z.Xor(a['domain'], b['domain']))
    if outcome == z.sat:
        return failure('path_domain', model)
    if outcome == z.unknown:
        return base | {'reason': 'Solver unknown: ' + str(reason)}
    differences = [a['registers'][n] != b['registers'][n] for n in normalized['live_registers']]
    differences += [(a['flags'] & normalized['live_flags']) != (b['flags'] & normalized['live_flags'])]
    differences += [a['memory'][p] != b['memory'][p] for p in addresses]
    if normalized['memory_observation'] == 'ordered':
        if len(a['accesses']) != len(b['accesses']):
            differences.append(z.BoolVal(True))
        for x, y in zip(a['accesses'], b['accesses']):
            differences.append(z.BoolVal(True) if x[0] != y[0] or x[2] != y[2]
                               else z.Or(x[1] != y[1], x[3] != y[3]))
    outcome, model, reason = query(z.And(a['domain'], b['domain'], z.Or(*differences)))
    if outcome == z.sat:
        return failure('live_state_or_memory_effects', model)
    if outcome == z.unknown:
        return base | {'reason': 'Solver unknown: ' + str(reason)}
    # The operation node explains the reduced behavior as well as retaining proof receipts.
    # This bounded presentation is not a serialized solver certificate or executable UIL.
    presentation = {'remaining': 32768, 'truncated': False}
    def expression(value):
        text = z.simplify(value).sexpr()
        limit = min(2048, presentation['remaining'])
        presentation['remaining'] -= min(len(text), limit)
        if len(text) > limit:
            presentation['truncated'] = True
            return text[:limit] + ' [presentation truncated; expand original region]'
        return text
    effects = {'registers': {n: {'type': f'u{bits}', 'expression': expression(a['registers'][n])}
                              for n in normalized['live_registers']},
               'flags': {'type': 'u32', 'live_mask': normalized['live_flags'],
                         'expression': expression(a['flags'] & normalized['live_flags'])},
               'path_domain': expression(a['domain']),
               'memory_bytes': {hex(p): {'type': 'u8', 'expression': expression(a['memory'][p])}
                                for p in addresses},
               'memory_observation': normalized['memory_observation'],
               'ordered_accesses': [{'kind': kind, 'address': expression(address), 'width': width,
                                     'value': expression(value)} for kind, address, width, value in a['accesses']]
                                   if normalized['memory_observation'] == 'ordered' else [],
               'expression_language': 'Z3 SMT-LIB presentation over shared entry symbols',
               'other_memory': 'Unchanged by admitted instructions'}
    effects['presentation_truncated'] = presentation['truncated']
    contraction = {'format': 'fdisbull-pe-region-contraction-1', 'contract': normalized,
                   'reduced_effects': effects,
                   'memory_safety': base['memory_safety'],
                   'sources': base['sources'], 'solver': {'name': 'z3', 'version': z.get_version_string(),
                   'timeout_ms_total': timeout_ms, 'baseline_domain': 'sat', 'layer_domain': 'sat',
                   'domain_difference': 'unsat', 'effect_difference': 'unsat'},
                   'regions': {label: {'event_indices': list(range(len(trace['events']) - 1)),
                                      'entry': deepcopy(trace['events'][0]['identity']),
                                      'exit': deepcopy(trace['events'][-1]['identity'])}
                               for label, trace in (('baseline', baseline), ('layer', layer))},
                   'expansion_required': 'Original trace documents and memory evidence matching these digests',
                   'claim': base['scope']}
    contraction['sha256'] = _digest(contraction)
    return base | {'status': 'equivalent_under_contract', 'contraction': contraction,
                   'proof': contraction['solver']}


def expand_pe_contraction(contraction, baseline, layer, *, baseline_memory=None, layer_memory=None):
    """Recover exact supplied region evidence after digest checks; hashes are not proof signatures."""
    if (not isinstance(contraction, dict) or contraction.get('format') != 'fdisbull-pe-region-contraction-1'
            or contraction.get('sha256') != _digest({k: v for k, v in contraction.items() if k != 'sha256'})):
        raise ValueError('Contraction integrity check failed')
    for label, trace, evidence in (('baseline', baseline, baseline_memory), ('layer', layer, layer_memory)):
        receipt = _receipt(trace) | {'memory_sha256': _digest(evidence)}
        if receipt != contraction['sources'][label]:
            raise ValueError('Expansion evidence differs from contracted region')
    result = {'baseline': deepcopy(baseline), 'layer': deepcopy(layer)}
    if baseline_memory is not None or layer_memory is not None:
        result.update(baseline_memory=deepcopy(baseline_memory), layer_memory=deepcopy(layer_memory))
    return result
