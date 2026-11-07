"""Bounded x86-32 caller facts for explicitly identified serializer routines.

``read_bytes(address, size)`` reads the caller's declared address space; this
module neither guesses a loader mapping nor dereferences pointer globals. Pass
half-open instruction ranges and known register ABIs, for example
``{'entry': 0x5000, 'operation': 'write', 'filename': 'eax',
   'buffer': 'edx', 'length': 'ebx'}``. Registers listed in optional ``preserves``
are trusted ABI facts. Unspecified call effects kill register/stack knowledge.

Constant propagation follows bounded direct control flow and joins conflicting
definitions to unknown. Nearby filename literals used while constructing a
dynamic path are *candidates*, not a proved string-copy model. Results identify
follow-up work; they do not establish file formats, runtime reachability or
exhaustive state coverage. Inputs must be qualified native instruction bytes.
"""

from collections import deque
from dataclasses import dataclass
import re

import capstone as cs
from capstone import x86_const as x86


REGISTERS = frozenset(('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'))
_ALIASES = {part: whole for whole, parts in {
    'eax': ('eax', 'ax', 'al', 'ah'), 'ebx': ('ebx', 'bx', 'bl', 'bh'),
    'ecx': ('ecx', 'cx', 'cl', 'ch'), 'edx': ('edx', 'dx', 'dl', 'dh'),
    'esi': ('esi', 'si'), 'edi': ('edi', 'di'), 'ebp': ('ebp', 'bp'),
    'esp': ('esp', 'sp'),
}.items() for part in parts}


@dataclass(frozen=True)
class _Value:
    kind: str
    number: int


def _integer(value, name, low=0, high=0xffffffff):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _public(value):
    if value is None:
        return {'kind': 'unresolved'}
    return {'kind': value.kind, 'value': value.number}


def _join(old, new):
    if old is None:
        return new
    regs = {k: v for k, v in old[0].items() if new[0].get(k) == v}
    stack = {k: v for k, v in old[1].items() if new[1].get(k) == v}
    return regs, stack, old[2] | new[2]


def extract_serializer_candidates(read_bytes, *, ranges, serializers, code_base=0,
                                 address_space='linear32', max_instructions=20000,
                                 max_string_bytes=256, max_string_reads=512):
    """Return JSON-ready call candidates, paired filename families and limits.

    ``ranges`` are absolute [start, end) pairs in ``address_space``; ``code_base``
    records their binding and supplies callsite offsets, without rebasing bytes.
    Each range starts with unknown registers and a symbolic entry stack pointer.
    A reader must return bytes (short/unmapped reads stay unresolved). Code reads
    are at most 64 KiB; literal reads are cached and bounded. No state is written.
    """
    _integer(code_base, 'code_base')
    _integer(max_instructions, 'max_instructions', 1, 100000)
    _integer(max_string_bytes, 'max_string_bytes', 2, 4096)
    _integer(max_string_reads, 'max_string_reads', 1, 4096)
    if not callable(read_bytes) or not isinstance(address_space, str) or not address_space:
        raise ValueError('read_bytes and an explicit address-space name are required')
    if not isinstance(ranges, (list, tuple)) or not 1 <= len(ranges) <= 64:
        raise ValueError('ranges must contain 1..64 half-open instruction ranges')
    selected = []
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('each range must be [start, end)')
        start, end = pair
        _integer(start, 'range start'); _integer(end, 'range end', 1, 0x100000000)
        if not 0 < end - start <= 65536:
            raise ValueError('each code range must contain 1..65536 bytes')
        selected.append((start, end))
    selected.sort()
    if any(a[1] > b[0] for a, b in zip(selected, selected[1:])):
        raise ValueError('code ranges must not overlap')
    if sum(end-start for start, end in selected) > 1048576:
        raise ValueError('code ranges exceed 1 MiB')
    if not isinstance(serializers, (list, tuple)) or not 1 <= len(serializers) <= 128:
        raise ValueError('serializers must contain 1..128 known ABIs')
    abis = {}
    for original in serializers:
        if not isinstance(original, dict):
            raise ValueError('serializer ABI must be an object')
        spec = dict(original)
        required = {'entry', 'operation', 'filename', 'buffer'}
        if not required <= spec.keys() or spec.keys() - required - {'length', 'preserves'}:
            raise ValueError('serializer ABI needs entry, operation, filename and buffer')
        _integer(spec['entry'], 'serializer entry')
        if spec['entry'] in abis or spec['operation'] not in ('read', 'write'):
            raise ValueError('serializer entries must be unique and operations read/write')
        for field in ('filename', 'buffer', 'length'):
            if field in spec and spec[field] not in REGISTERS:
                raise ValueError(f'{field} ABI must name a 32-bit register')
        preserves = spec.get('preserves', ())
        if not isinstance(preserves, (list, tuple)) or any(r not in REGISTERS for r in preserves):
            raise ValueError('preserves must list 32-bit registers')
        abis[spec['entry']] = spec

    decoder = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_32)
    decoder.detail = True
    instructions, starts, issues = {}, [], set()
    limit_hit = False
    for start, end in selected:
        try:
            raw = read_bytes(start, end-start)
        except Exception as error:
            issues.add((start, 'code read failed: ' + type(error).__name__))
            continue
        if not isinstance(raw, bytes) or len(raw) != end-start:
            issues.add((start, 'code read did not return the requested bytes'))
            continue
        cursor = start
        for ins in decoder.disasm(raw, start):
            if len(instructions) >= max_instructions:
                limit_hit = True
                break
            instructions[ins.address] = ins
            cursor = ins.address + ins.size
        if start in instructions:
            starts.append(start)
        if cursor != end:
            issues.add((cursor, 'instruction budget stopped' if limit_hit else 'undecodable or truncated instruction'))
        if limit_hit:
            break

    strings = {}
    string_limit = False

    def literal(address):
        nonlocal string_limit
        if address in strings:
            return strings[address]
        if len(strings) >= max_string_reads:
            string_limit = True
            return None
        text = None
        try:
            raw = read_bytes(address, min(max_string_bytes, 0x100000000-address))
            if isinstance(raw, bytes) and b'\0' in raw:
                prefix = raw.split(b'\0', 1)[0]
                if prefix and all(32 <= byte < 127 for byte in prefix):
                    text = prefix.decode('ascii')
        except Exception:
            pass
        strings[address] = text
        return text

    def reg(ins, operand):
        return ins.reg_name(operand.reg)

    def effective(ins, operand, regs):
        m = operand.mem
        if m.segment and ins.reg_name(m.segment) not in ('ds', 'ss', 'es'):
            return None
        if m.index:
            return None
        if not m.base:
            return _Value('constant', m.disp & 0xffffffff)
        base = regs.get(ins.reg_name(m.base))
        if base and base.kind in ('constant', 'stack'):
            number = base.number + m.disp
            return _Value(base.kind, number & 0xffffffff if base.kind == 'constant' else number)
        return None

    def operand_value(ins, operand, regs, stack):
        if operand.type == x86.X86_OP_IMM:
            return _Value('constant', operand.imm & 0xffffffff)
        if operand.type == x86.X86_OP_REG:
            return regs.get(reg(ins, operand)) if operand.size == 4 else None
        if operand.type == x86.X86_OP_MEM and operand.size == 4:
            address = effective(ins, operand, regs)
            if address and address.kind == 'constant':
                return _Value('pointer_global', address.number)
            if address and address.kind == 'stack':
                return stack.get(address.number)
        return None

    def target(ins):
        return ins.operands[0].imm & 0xffffffff if len(ins.operands) == 1 and ins.operands[0].type == x86.X86_OP_IMM else None

    def transfer(ins, state):
        before, stack_before, refs = state
        regs, stack = dict(before), dict(stack_before)
        operands = ins.operands
        mnemonic = ins.mnemonic
        if ins.group(cs.CS_GRP_CALL):
            spec = abis.get(target(ins), {})
            keep = set(spec.get('preserves', ())) | {'esp'}
            return {r: v for r, v in regs.items() if r in keep}, {}, frozenset()
        # A length immediate can coincidentally point into a string. For dynamic
        # filenames, retain literals only when code actually reads their bytes.
        for operand in operands:
            if operand.type == x86.X86_OP_MEM and operand.size == 1 and operand.access & cs.CS_AC_READ:
                address = effective(ins, operand, before)
                if address and address.kind == 'constant':
                    refs = refs | {(ref, loc, text, ins.address) for ref, loc, text, _ in refs
                                   if loc <= address.number < loc+len(text)+1}
            if operand.type == x86.X86_OP_MEM and operand.access & cs.CS_AC_WRITE:
                address = effective(ins, operand, before)
                if address and address.kind == 'stack':
                    for slot in list(stack):
                        if slot < address.number+operand.size and address.number < slot+4:
                            stack.pop(slot)
                elif address is None:
                    stack.clear()
        # Kill every native-reported destination, including partial register writes.
        for written in ins.regs_access()[1]:
            regs.pop(_ALIASES.get(ins.reg_name(written), ''), None)
        if mnemonic == 'push' and len(operands) == 1:
            sp = before.get('esp')
            if sp and sp.kind == 'stack' and operands[0].size == 4:
                sp = _Value('stack', sp.number-4); regs['esp'] = sp
                value = operand_value(ins, operands[0], before, stack_before)
                if value is not None:
                    stack[sp.number] = value
                else:
                    stack.pop(sp.number, None)
        elif mnemonic == 'pop' and len(operands) == 1:
            sp = before.get('esp')
            if sp and sp.kind == 'stack' and operands[0].size == 4:
                regs['esp'] = _Value('stack', sp.number+4)
                value = stack.pop(sp.number, None)
                if value is not None and operands[0].type == x86.X86_OP_REG:
                    regs[reg(ins, operands[0])] = value
                elif operands[0].type == x86.X86_OP_MEM:
                    # POP addresses an ESP-based destination after advancing ESP.
                    # Do not reuse the pre-instruction address for a stale spill.
                    stack.clear()
        elif len(operands) == 2:
            dest, source = operands
            value = None
            if mnemonic == 'mov':
                value = operand_value(ins, source, before, stack_before)
            elif mnemonic == 'lea' and source.type == x86.X86_OP_MEM:
                value = effective(ins, source, before)
            elif mnemonic in ('xor', 'sub') and dest.type == source.type == x86.X86_OP_REG and dest.reg == source.reg:
                value = _Value('constant', 0)
            elif mnemonic in ('add', 'sub') and dest.type == x86.X86_OP_REG and source.type == x86.X86_OP_IMM:
                old = before.get(reg(ins, dest))
                if old and old.kind in ('constant', 'stack'):
                    number = old.number + source.imm * (1 if mnemonic == 'add' else -1)
                    value = _Value(old.kind, number & 0xffffffff if old.kind == 'constant' else number)
            if dest.type == x86.X86_OP_REG and dest.size == 4 and value is not None:
                regs[reg(ins, dest)] = value
                if mnemonic in ('mov', 'lea') and value.kind == 'constant':
                    text = literal(value.number)
                    if text and ('/' in text or '\\' in text or re.search(r'\.[A-Za-z0-9]{1,8}$', text)):
                        refs = refs | {(ins.address, value.number, text, 0)}
            if dest.type == x86.X86_OP_MEM and dest.access & cs.CS_AC_WRITE:
                address = effective(ins, dest, before)
                if address and address.kind == 'stack':
                    if dest.size == 4 and value is not None:
                        stack[address.number] = value
        return regs, stack, refs

    successors = {}
    for address, ins in instructions.items():
        fallthrough = address + ins.size
        nexts = []
        if ins.group(cs.CS_GRP_JUMP) or ins.mnemonic in ('loop', 'loope', 'loopne'):
            dest = target(ins)
            if dest in instructions:
                nexts.append(dest)
            else:
                issues.add((address, 'jump target is indirect or outside decoded ranges'))
            if ins.mnemonic not in ('jmp', 'ljmp'):
                nexts.append(fallthrough)
        elif not any(ins.group(g) for g in (cs.CS_GRP_RET, cs.CS_GRP_IRET, cs.CS_GRP_INT)):
            nexts.append(fallthrough)
        successors[address] = [n for n in nexts if n in instructions]

    states, queue = {}, deque()
    for start in starts:
        states[start] = _join(states.get(start), ({'esp': _Value('stack', 0)}, {}, frozenset()))
        queue.append(start)
    steps = 0
    while queue and steps < max_instructions*16:
        address = queue.popleft(); steps += 1
        output = transfer(instructions[address], states[address])
        for following in successors[address]:
            joined = _join(states.get(following), output)
            if states.get(following) != joined:
                states[following] = joined
                queue.append(following)
    if queue:
        limit_hit = True
        issues.add((queue[0], 'dataflow budget stopped; argument facts withheld'))

    candidates = []
    for address, ins in sorted(instructions.items()):
        spec = abis.get(target(ins)) if ins.group(cs.CS_GRP_CALL) else None
        if not spec or address not in states:
            continue
        regs, _, refs = states[address] if not limit_hit else ({}, {}, frozenset())
        filename_value = regs.get(spec['filename'])
        direct = literal(filename_value.number) if filename_value and filename_value.kind == 'constant' else None
        literals = [{'reference': ref, 'address': loc, 'text': text,
                     'byte_read_sites': sorted({read for r, a, t, read in refs
                                                if (r, a, t) == (ref, loc, text) and read})}
                    for ref, loc, text in sorted({(r, a, t) for r, a, t, read in refs if read})]
        filename = {'kind': 'direct' if direct else 'literal_candidate' if literals else 'unresolved',
                    'value': _public(filename_value), 'full_path_known': bool(direct), 'literals': literals}
        if direct:
            filename['text'] = direct
        elif len({item['text'] for item in literals}) == 1:
            filename['text'] = literals[0]['text']
        buffer_value = regs.get(spec['buffer'])
        buffer = ({'kind': 'direct', 'address': buffer_value.number} if buffer_value and buffer_value.kind == 'constant'
                  else {'kind': 'pointer_global', 'address': buffer_value.number, 'pointer_width': 4}
                  if buffer_value and buffer_value.kind == 'pointer_global' else _public(buffer_value))
        length_value = regs.get(spec.get('length'))
        length = length_value.number if length_value and length_value.kind == 'constant' else None
        unresolved = []
        if limit_hit:
            unresolved.append('analysis budget stopped; argument facts withheld')
        elif issues:
            unresolved.append('argument facts cover decoded paths only; unresolved flow may add definitions')
        if not direct:
            unresolved.append('full path unresolved; nearby literal references are candidates, not proved path construction')
        if buffer['kind'] not in ('direct', 'pointer_global'):
            unresolved.append('buffer address unresolved')
        elif buffer['kind'] == 'pointer_global':
            unresolved.append('buffer pointee not read; address identifies the pointer global')
        if length is None:
            unresolved.append('length not present in configured ABI' if 'length' not in spec else 'length argument unresolved')
        candidates.append({'id': f'{spec["operation"]}:{address:08x}', 'callsite': address,
                           'callsite_offset': address-code_base, 'serializer_entry': spec['entry'],
                           'operation': spec['operation'], 'filename': filename, 'buffer': buffer,
                           'length': length, 'unresolved': unresolved})
    groups = {}
    for candidate in candidates:
        text = candidate['filename'].get('text')
        if text:
            key = text.replace('\\', '/').rsplit('/', 1)[-1].casefold()
            if key:
                groups.setdefault(key, []).append(candidate)
    families = [{'filename': name, 'candidate_ids': [c['id'] for c in group],
                 'operations': sorted({c['operation'] for c in group}),
                 'basis': 'matching filename literal; directories and format equivalence are unproved'}
                for name, group in sorted(groups.items())]
    return {'format': 'fdisbull-serializer-candidates-1', 'address_space': address_space,
            'code_base': code_base, 'ranges': [list(pair) for pair in selected],
            'status': 'budget_stop' if limit_hit or string_limit else 'partial' if issues else 'bounded_complete',
            'decoded_instructions': len(instructions), 'dataflow_steps': steps,
            'string_reads': len(strings), 'string_budget_exhausted': string_limit,
            'candidates': candidates, 'families': families,
            'issues': [{'address': address, 'reason': reason} for address, reason in sorted(issues)],
            'scope': 'configured x86-32 callers and ABIs only; no whole-format or runtime-state claim'}


def summarize_serializer_candidates(result):
    """Present an existing extraction as compact paired rows; perform no reads.

    This is a lossy presentation view, not additional analysis. Candidate IDs
    refer back to the unchanged raw result. Repeated writes and unresolved facts
    remain separate; filename grouping does not imply equal buffers or formats.
    Pointer-global slot addresses never stand in for unobserved pointee values.
    """
    if not isinstance(result, dict) or result.get('format') != 'fdisbull-serializer-candidates-1':
        raise ValueError('expected a fdisbull-serializer-candidates-1 result')
    candidates = {candidate['id']: candidate for candidate in result['candidates']}
    if len(candidates) != len(result['candidates']):
        raise ValueError('candidate IDs must be unique')
    families = list(result['families'])
    grouped = {identifier for family in families for identifier in family['candidate_ids']}
    if grouped - candidates.keys():
        raise ValueError('family references an unknown candidate ID')
    families += [{'filename': None, 'candidate_ids': [identifier],
                  'basis': 'no unique filename; candidate remains unpaired'}
                 for identifier in candidates if identifier not in grouped]

    def buffer_view(buffer):
        if buffer['kind'] == 'pointer_global':
            return {'kind': 'pointer_global', 'slot_address': hex(buffer['address']),
                    'pointer_width': buffer['pointer_width'], 'pointee_address': None}
        if buffer['kind'] == 'direct':
            return {'kind': 'direct', 'address': hex(buffer['address'])}
        if buffer['kind'] == 'stack':
            return {'kind': 'stack', 'entry_sp_offset': hex(buffer['value'])}
        return dict(buffer)

    rows = []
    for family in families:
        members = [candidates[identifier] for identifier in family['candidate_ids']]
        reads, writes, messages = [], [], {}
        for candidate in members:
            if candidate['operation'] not in ('read', 'write'):
                raise ValueError('candidate operation must be read or write')
            entry = {'candidate_id': candidate['id'], 'callsite': hex(candidate['callsite']),
                     'serializer_entry': hex(candidate['serializer_entry']),
                     'filename': {key: candidate['filename'][key]
                                  for key in ('kind', 'text', 'full_path_known')
                                  if key in candidate['filename']},
                     'buffer': buffer_view(candidate['buffer']), 'length': candidate['length']}
            (reads if candidate['operation'] == 'read' else writes).append(entry)
            for message in candidate['unresolved']:
                messages.setdefault(message, []).append(candidate['id'])
        rows.append({'filename': family['filename'], 'basis': family['basis'],
                     'candidate_ids': list(family['candidate_ids']), 'reads': reads, 'writes': writes,
                     'observed_write_lengths': sorted({w['length'] for w in writes if w['length'] is not None}),
                     'unknown_write_length_count': sum(w['length'] is None for w in writes),
                     'unresolved_candidate_count': sum(bool(c['unresolved']) for c in members),
                     'unresolved_fact_count': sum(len(c['unresolved']) for c in members),
                     'unresolved': [{'message': message, 'candidate_ids': identifiers}
                                    for message, identifiers in messages.items()]})
    return {'format': 'fdisbull-serializer-candidate-summary-1',
            'source_format': result['format'], 'address_space': result['address_space'],
            'code_base': hex(result['code_base']), 'status': result['status'],
            'candidate_count': len(candidates), 'families': rows,
            'unresolved_candidate_count': sum(bool(c['unresolved']) for c in candidates.values()),
            'unresolved_fact_count': sum(len(c['unresolved']) for c in candidates.values()),
            'issues': [{**issue, 'address': hex(issue['address'])} for issue in result['issues']],
            'scope': result['scope']}
