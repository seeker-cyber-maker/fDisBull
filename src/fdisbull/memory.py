"""Static memory-access facts and read-only queries over decoded instructions.

The CPU libraries describe accesses; constant register state only resolves their
addresses. Unknown state is never replaced by zero. These facts describe possible
instruction effects, not execution or a proof that all runtime writers are known.
"""
from __future__ import annotations

from functools import lru_cache
import itertools
import json
import math
import re
from types import SimpleNamespace

import capstone as csapi
import iced_x86 as ix

MEMORY_FACTS_REVISION = 1
_MAX_ADDRESS = (1 << 64) - 1
_REG = {value: name.lower() for name, value in vars(ix.Register).items()
        if name.isupper() and isinstance(value, int)}
_PARENT16 = {ix.RegisterExt.full_register(value): name for value, name in _REG.items()
             if ix.RegisterExt.is_gpr16(value)}
_ACCESS = {
    ix.OpAccess.READ: ('read', True, False, False, False),
    ix.OpAccess.COND_READ: ('read', True, False, True, False),
    ix.OpAccess.WRITE: ('write', False, True, False, False),
    ix.OpAccess.COND_WRITE: ('conditional_write', False, True, False, True),
    ix.OpAccess.READ_WRITE: ('read_write', True, True, False, False),
    ix.OpAccess.READ_COND_WRITE: ('conditional_write', True, True, False, True),
    ix.OpAccess.NO_MEM_ACCESS: ('address_only', False, False, False, False),
}


def _integer(value, name, low=0, high=_MAX_ADDRESS):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _states(registers):
    if registers is None:
        return [{}]
    if not isinstance(registers, dict):
        raise ValueError('registers must contain known register constants')
    state, varying = {}, []
    for name, value in registers.items():
        if not isinstance(name, str) or name.startswith('_'):
            continue
        name = name.lower()
        if isinstance(value, list) and name in ('ds', 'es', 'ss', 'fs', 'gs'):
            values = sorted({_integer(v, name, high=0xffff) for v in value})
            if not 1 <= len(values) <= 4:
                raise ValueError('segment variants require one to four known selectors')
            varying.append((name, values))
        else:
            state[name] = _integer(value, name)
    if not varying:
        return [state]
    if math.prod(len(values) for _, values in varying) > 64:
        raise ValueError('register state exceeds 64 segment combinations')
    return [dict(state, **dict(zip((name for name, _ in varying), values)))
            for values in itertools.product(*(values for _, values in varying))]


def _known_x86(name, state, assumptions):
    value = state.get(name)
    if value is None:
        register = getattr(ix.Register, name.upper(), ix.Register.NONE)
        if register != ix.Register.NONE and ix.RegisterExt.is_gpr(register):
            full = _REG.get(ix.RegisterExt.full_register(register))
            full32 = _REG.get(ix.RegisterExt.full_register32(register))
            full16 = _PARENT16.get(ix.RegisterExt.full_register(register))
            parent = next((n for n in (full, full32, full16) if n in state and
                           ix.RegisterExt.size(getattr(ix.Register, n.upper())) >= ix.RegisterExt.size(register)), None)
            if parent:
                shift = 8 if name in ('ah', 'bh', 'ch', 'dh') else 0
                value = (state[parent] >> shift) & ((1 << (ix.RegisterExt.size(register) * 8)) - 1)
                assumptions.append(dict(kind='register_constant', register=parent, value=state[parent]))
    elif value is not None:
        assumptions.append(dict(kind='register_constant', register=name, value=value))
    return value


def _address_bits(raw, bits):
    override = False
    for byte in raw:
        if byte == 0x67:
            override = True
        elif byte not in (0x66, 0xf0, 0xf2, 0xf3, 0x26, 0x2e, 0x36, 0x3e, 0x64, 0x65) and not (bits == 64 and 0x40 <= byte <= 0x4f):
            break
    return ({16: 32, 32: 16, 64: 32}[bits] if override else bits)


def _base_fact(access, width, address_bits):
    category, read, write, cond_read, cond_write = _ACCESS.get(access, ('unknown', None, None, False, False))
    return dict(access=category, may_read=read, may_write=write,
                conditional_read=cond_read, conditional_write=cond_write,
                width=width or None, address_bits=address_bits,
                segment_register=None, segment_selector=None, base_register=None,
                index_register=None, scale=1, displacement=0, effective_offset=None,
                concrete_target=None, interval_start=None, interval_end=None,
                interval_exact=False, possible_start=None, possible_end=None,
                repeat=None, unresolved_reasons=[], assumptions=[])


def _interval(fact, target, width, *, address_only=False):
    fact['concrete_target'] = target
    if target is not None and (width or address_only):
        end = target + (width or 1)
        if end <= _MAX_ADDRESS + 1:
            fact.update(interval_start=target, interval_end=end, interval_exact=True,
                        possible_start=target, possible_end=end)
        else:
            fact['unresolved_reasons'].append('memory interval exceeds the 64-bit address range')


def _x86(raw, address, bits, selector, state):
    ip = address - selector * 16 if selector is not None else address
    ins = ix.Decoder(bits, raw[:15], ip=ip).decode()
    if ins.is_invalid or (selector is not None and ip + ins.len > 0x10000):
        return []
    info = ix.InstructionInfoFactory().info(ins)
    memory = list(info.used_memory())
    indices = [i for i in range(ins.op_count) if ins.op_kind(i) == ix.OpKind.MEMORY]
    if ins.mnemonic == ix.Mnemonic.LEA:
        memory = [SimpleNamespace(access=ix.OpAccess.NO_MEM_ACCESS, memory_size=ins.memory_size,
                  address_size={16: 1, 32: 2, 64: 3}[_address_bits(raw, bits)],
                  segment=ix.Register.NONE, base=ins.memory_base, index=ins.memory_index,
                  scale=ins.memory_index_scale, displacement=ins.memory_displacement,
                  displacement_i64=ins.memory_displacement, vsib_size=0)]
    result = []
    repeated = ins.is_string_instruction and (ins.has_rep_prefix or ins.has_repne_prefix)
    for ordinal, mem in enumerate(memory):
        address_bits = {1: 16, 2: 32, 3: 64}.get(mem.address_size, bits)
        width = ix.MemorySizeExt.size(mem.memory_size) or (ix.MemorySizeExt.size(ins.memory_size) if repeated else 0)
        fact = _base_fact(mem.access, width, address_bits)
        # A memory CALL/PUSH/POP has both an explicit memory operand and
        # an implicit stack access. Decorate only the explicit operand.
        stack_access = (ins.is_stack_instruction and mem.base in (ix.Register.SP, ix.Register.ESP, ix.Register.RSP)
                        and ((ins.stack_pointer_increment < 0 and mem.access == ix.OpAccess.WRITE)
                             or (ins.stack_pointer_increment > 0 and mem.access == ix.OpAccess.READ)))
        explicit = bool(indices) and not stack_access
        fact.update(operand_index=indices[0] if len(indices) == 1 and explicit else None,
                    implicit=not explicit, decoder='iced-x86 InstructionInfo',
                    segment_register=_REG.get(mem.segment) if mem.segment != ix.Register.NONE else None,
                    base_register=_REG.get(mem.base) if mem.base != ix.Register.NONE else None,
                    index_register=_REG.get(mem.index) if mem.index != ix.Register.NONE else None,
                    scale=mem.scale, displacement=mem.displacement_i64)
        assumptions, unresolved = fact['assumptions'], fact['unresolved_reasons']
        offset, known = mem.displacement, not bool(mem.vsib_size)
        if mem.vsib_size:
            unresolved.append('vector-indexed memory has per-lane addresses, not a known scalar index')
        for register, scale in ((mem.base, 1), (mem.index, mem.scale)):
            if register == ix.Register.NONE:
                continue
            if ins.is_ip_rel_memory_operand and register in (ix.Register.RIP, ix.Register.EIP):
                offset = ins.ip_rel_memory_address
                continue
            value = _known_x86(_REG.get(register, str(register)), state, assumptions)
            if value is None:
                known = False
                unresolved.append(f'unknown address register {_REG.get(register, register)}')
            else:
                offset += value * scale
        if ins.is_ip_rel_memory_operand and explicit:
            # InstructionInfo normalizes RIP/EIP-relative operands to an absolute
            # displacement. Preserve the encoded expression as well as its VA.
            fact.update(base_register=_REG[ins.memory_base], ip_relative=True,
                        displacement=((ins.ip_rel_memory_address - ins.next_ip + (1 << 31)) % (1 << 32)) - (1 << 31))
        offset = offset & ((1 << address_bits) - 1) if known else None
        fact['effective_offset'] = offset
        segment = fact['segment_register']
        base = None
        if fact['access'] == 'address_only':
            # LEA ignores segment overrides and only computes an effective offset.
            base = None if bits == 16 else 0
            fact['segment_register'] = None
            if bits == 16:
                unresolved.append('LEA computes an offset, not a real-mode physical address')
        elif bits == 16:
            selected = selector if segment == 'cs' else state.get(segment)
            if isinstance(selected, int) and 0 <= selected <= 0xffff:
                fact['segment_selector'], base = selected, selected * 16
                assumptions.append(dict(kind='real_mode_segment', register=segment, value=selected))
            else:
                unresolved.append(f'unknown real-mode segment {segment}')
        elif segment in ('fs', 'gs'):
            base = state.get(segment + '_base')
            if base is None:
                unresolved.append(f'unknown {segment.upper()} base; its selector is not a linear base')
            else:
                assumptions.append(dict(kind='segment_base_constant', register=segment + '_base', value=base))
        else:
            base = 0
            assumptions.append(dict(kind='native_flat_segment', register=segment, base=0,
                                    reason='static native image address model'))
        if base is not None:
            fact.update(possible_start=base, possible_end=min(base + (1 << address_bits), _MAX_ADDRESS + 1))
        if offset is not None and base is not None:
            target = base + offset
            if bits == 16 and (target >= 0x100000 or (width and offset + width > (1 << address_bits))):
                unresolved.append('real-mode address crosses the supported offset/A20 boundary')
            elif target <= _MAX_ADDRESS:
                _interval(fact, target, width, address_only=fact['access'] == 'address_only')
        if repeated:
            count_register = {16: 'cx', 32: 'ecx', 64: 'rcx'}[address_bits]
            count = _known_x86(count_register, state, assumptions)
            if count is not None:
                count &= (1 << address_bits) - 1
            if count == 0:
                continue
            direction = state.get('df')
            if direction is None:
                flags = next((state[n] for n in ('rflags', 'eflags', 'flags') if n in state), None)
                direction = (flags >> 10) & 1 if flags is not None else None
            if direction not in (None, 0, 1):
                raise ValueError('df must be zero or one')
            if direction is not None:
                assumptions.append(dict(kind='direction_flag', value=direction))
            early_stop = ins.mnemonic in (ix.Mnemonic.CMPSB, ix.Mnemonic.CMPSW, ix.Mnemonic.CMPSD, ix.Mnemonic.CMPSQ,
                                          ix.Mnemonic.SCASB, ix.Mnemonic.SCASW, ix.Mnemonic.SCASD, ix.Mnemonic.SCASQ)
            fact['repeat'] = dict(prefix='repne' if ins.has_repne_prefix else 'rep', count_register=count_register,
                                  count=count, direction=direction, early_stop=early_stop)
            fact.update(interval_start=None, interval_end=None, interval_exact=False)
            # First-element addresses do not imply that every repeated address is
            # known. Count/direction are required; wraparound is left unresolved.
            if count is not None and direction is not None and offset is not None and width and base is not None:
                first = offset - (count - 1) * width if direction else offset
                end = offset + width if direction else offset + count * width
                if 0 <= first <= end <= (1 << address_bits) and base + end <= (0x100000 if bits == 16 else _MAX_ADDRESS + 1):
                    fact.update(interval_start=base + first, interval_end=base + end,
                                interval_exact=not early_stop, possible_start=base + first, possible_end=base + end)
                else:
                    unresolved.append('repeated access can wrap its offset/address range')
            else:
                unresolved.append('repeated interval requires known count, direction, start, and element width')
            if fact['interval_start'] is None:
                fact.update(possible_start=base, possible_end=min(base + (1 << address_bits), _MAX_ADDRESS + 1) if base is not None else None)
        result.append(fact)
    return result


@lru_cache(maxsize=1)
def _arm_decoder():
    decoder = csapi.Cs(csapi.CS_ARCH_ARM64, csapi.CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    return decoder


def _arm_known(name, state, assumptions):
    if name in ('xzr', 'wzr'):
        return 0  # Architectural zero register, not an assumed register value.
    value = state.get(name)
    if value is None and name and name.startswith('w') and 'x' + name[1:] in state:
        value = state['x' + name[1:]] & 0xffffffff
    if value is not None:
        assumptions.append(dict(kind='register_constant', register=name, value=value))
    return value


def _arm(raw, address, state):
    if len(raw) < 4 or address % 4:
        return []
    ins = next(_arm_decoder().disasm(raw[:4], address, count=1), None)
    if ins is None:
        return []
    result = []
    mnemonic = ins.mnemonic
    for index, operand in enumerate(ins.operands):
        literal = operand.type == csapi.arm64.ARM64_OP_IMM and mnemonic in ('ldr', 'ldrsw', 'prfm')
        if operand.type != csapi.arm64.ARM64_OP_MEM and not literal:
            continue
        # Capstone 5 reports ordinary STR/STP memory as READ|WRITE. Correct
        # these known opcode families; retain its access bits for other forms.
        if mnemonic.startswith(('prfm', 'prfum')):
            access = ix.OpAccess.NO_MEM_ACCESS
        elif mnemonic.startswith(('stxr', 'stlxr', 'stxp', 'stlxp')):
            access = ix.OpAccess.COND_WRITE
        elif mnemonic.startswith(('cas', 'casp')):
            access = ix.OpAccess.READ_COND_WRITE
        elif mnemonic.startswith(('swp', 'ldadd', 'ldclr', 'ldeor', 'ldset', 'ldsmax', 'ldsmin', 'ldumax', 'ldumin',
                                  'stadd', 'stclr', 'steor', 'stset', 'stsmax', 'stsmin', 'stumax', 'stumin')):
            access = ix.OpAccess.READ_WRITE
        elif mnemonic.startswith(('st',)):
            access = ix.OpAccess.WRITE
        elif mnemonic.startswith(('ld',)) or literal:
            access = ix.OpAccess.READ
        else:
            access = {1: ix.OpAccess.READ, 2: ix.OpAccess.WRITE, 3: ix.OpAccess.READ_WRITE}.get(operand.access, ix.OpAccess.NONE)
        preceding = [o for o in ins.operands[:index] if o.type == csapi.arm64.ARM64_OP_REG]
        names = [ins.reg_name(o.reg) for o in preceding]
        width = None
        if re.fullmatch(r'(?:ld|st)[1-4]r?', mnemonic):
            arrangements = {'16B': (16, 1), '8B': (8, 1), '4B': (4, 1), '1B': (1, 1),
                            '8H': (16, 2), '4H': (8, 2), '2H': (4, 2), '1H': (2, 2),
                            '4S': (16, 4), '2S': (8, 4), '1S': (4, 4),
                            '2D': (16, 8), '1D': (8, 8), '1Q': (16, 16)}
            widths = {getattr(csapi.arm64, 'ARM64_VAS_' + n): pair for n, pair in arrangements.items()
                      if hasattr(csapi.arm64, 'ARM64_VAS_' + n)}
            values = [widths.get(o.vas) for o in preceding]
            if values and all(values):
                width = sum(pair[1] if o.vector_index >= 0 or mnemonic.endswith('r') else pair[0]
                            for o, pair in zip(preceding, values))
        elif mnemonic not in ('prfm', 'prfum') and not mnemonic.startswith(('stg', 'stzg', 'st2g', 'stz2g', 'ldg')):
            if mnemonic.endswith('b') or mnemonic.startswith(('ldrsb', 'ldursb', 'ldtrsb')):
                width = 1
            elif mnemonic.endswith('h') or mnemonic.startswith(('ldrsh', 'ldursh', 'ldtrsh')):
                width = 2
            elif mnemonic in ('ldrsw', 'ldursw', 'ldtrsw', 'ldpsw'):
                width = 4
            elif names:
                # Exclusive stores begin with a status register, then data.
                data_name = names[1] if mnemonic.startswith(('stxr', 'stlxr', 'stxp', 'stlxp')) and len(names) > 1 else names[0]
                width = 8 if data_name in ('fp', 'lr') else {'b': 1, 'h': 2, 's': 4, 'w': 4, 'd': 8, 'x': 8, 'q': 16}.get(data_name[:1])
            if mnemonic.startswith(('ldp', 'stp', 'ldnp', 'stnp', 'ldxp', 'ldaxp', 'stxp', 'stlxp', 'casp')) and width:
                width *= 2
        fact = _base_fact(access, width, 64)
        fact.update(operand_index=index, implicit=False, decoder='Capstone ARM64 with opcode access corrections')
        assumptions, unresolved = fact['assumptions'], fact['unresolved_reasons']
        if literal:
            target = operand.imm & _MAX_ADDRESS
            fact.update(effective_offset=target, base_register='pc', displacement=target-address, ip_relative=True)
        else:
            base_name, index_name = ins.reg_name(operand.mem.base), ins.reg_name(operand.mem.index)
            fact.update(base_register=base_name, index_register=index_name, displacement=operand.mem.disp,
                        scale=1 << operand.shift.value if operand.shift.type == csapi.arm64.ARM64_SFT_LSL else 1,
                        writeback=bool(ins.writeback))
            base = _arm_known(base_name, state, assumptions)
            value = _arm_known(index_name, state, assumptions) if index_name else 0
            if base is None:
                unresolved.append(f'unknown address register {base_name}')
            if value is None:
                unresolved.append(f'unknown address register {index_name}')
            if operand.ext not in (0, csapi.arm64.ARM64_EXT_UXTW, csapi.arm64.ARM64_EXT_SXTW, csapi.arm64.ARM64_EXT_UXTX, csapi.arm64.ARM64_EXT_SXTX):
                unresolved.append('unsupported ARM64 index extension')
                value = None
            if value is not None and operand.ext in (csapi.arm64.ARM64_EXT_UXTW, csapi.arm64.ARM64_EXT_SXTW):
                value &= 0xffffffff
                if operand.ext == csapi.arm64.ARM64_EXT_SXTW and value & 0x80000000:
                    value -= 1 << 32
            if operand.shift.type not in (0, csapi.arm64.ARM64_SFT_LSL):
                unresolved.append('unsupported ARM64 memory index shift')
                value = None
            target = (base + value * fact['scale'] + operand.mem.disp) & _MAX_ADDRESS if base is not None and value is not None else None
            fact['effective_offset'] = target
        _interval(fact, target, width, address_only=fact['access'] == 'address_only')
        if width is None and fact['access'] != 'address_only':
            unresolved.append('memory transfer width is not established for this ARM64 form')
        result.append(fact)
    return result


def instruction_memory_accesses(raw, address, arch, bits, cs=None, registers=None):
    """Return JSON-compatible static accesses for exactly one real instruction.

    ``registers`` contains only established unsigned constants; DOS selectors may
    contain up to four observed alternatives. A concrete DOS address requires its
    actual selector. Native FS/GS require a *_base constant, never a selector.
    Intervals have exclusive ends; a non-exact interval is a possible bound only.
    """
    if not isinstance(raw, bytes):
        raise ValueError('instruction bytes must be bytes')
    _integer(address, 'instruction address')
    if arch not in ('x86', 'arm64') or bits not in ((16, 32, 64) if arch == 'x86' else (64,)):
        raise ValueError('memory decoding supports x86 16/32/64 and ARM64')
    if cs is not None:
        _integer(cs, 'CS', high=0xffff)
        if arch != 'x86' or bits != 16 or not 0 <= address - cs * 16 <= 0xffff:
            raise ValueError('CS requires a 16-bit instruction inside its segment window')
    if not raw:
        return []
    result, seen = [], set()
    for state in _states(registers):
        facts = _x86(raw, address, bits, cs, state) if arch == 'x86' else _arm(raw, address, state)
        for fact in facts:
            identity = json.dumps(fact, sort_keys=True, separators=(',', ':'))
            if identity not in seen:
                seen.add(identity)
                result.append(fact)
    return result


class MemoryMixin:
    def memory_accesses(self, address, size=1, version=None, access='all', limit=200,
                        offset=0, include_unresolved=True):
        """Find overlapping accesses, with unknown candidates explicitly separate.

        Segmented query selectors identify the data interval, not an instruction
        CS filter. Every stored source context is considered. No database writes
        or runtime execution are performed; older fact revisions are re-decoded.
        """
        _integer(size, 'size', 1, 1 << 20)
        _integer(limit, 'limit', 1, 10000)
        _integer(offset, 'offset', 0, 1000000)
        if access not in ('all', 'read', 'write', 'read_write', 'conditional_write', 'address_only'):
            raise ValueError('access must be all, read, write, read_write, conditional_write, or address_only')
        if not isinstance(include_unresolved, bool):
            raise ValueError('include_unresolved must be a boolean')
        if self.meta.get('format') == 'MZ':
            queried, selector = self._dos_parse_address(address)
        else:
            try:
                queried = int(address, 0) if isinstance(address, str) else address
            except ValueError as error:
                raise ValueError('address must be an integer or integer string') from error
            _integer(queried, 'address')
            selector = None
        end = queried + size
        if end > _MAX_ADDRESS + 1:
            raise ValueError('queried interval exceeds the 64-bit address range')
        with self.transaction():
            version_id = self.version(version)['id']
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            revision = self.db.execute('SELECT revision FROM analysis_facts_revision WHERE version=?', (version_id,)).fetchone() if 'analysis_facts_revision' in tables else None
            persisted = 'memory_refs' in tables and revision and revision[0] == MEMORY_FACTS_REVISION
            state_join = 'LEFT JOIN dos_states s ON s.version=i.version AND s.context=i.context AND s.address=i.address' if 'dos_states' in tables else ''
            state_fields = ',s.registers AS state_registers,s.state AS state_status,s.reason AS state_reason' if state_join else ',NULL AS state_registers,NULL AS state_status,NULL AS state_reason'
            fields = 'i.context,i.address,i.bytes,i.mnemonic,i.operands' + state_fields
            if persisted:
                query = f'SELECT {fields},m.detail FROM memory_refs m JOIN instructions i ON i.version=m.version AND i.context=m.context AND i.address=m.source {state_join} WHERE i.version=? ORDER BY i.address,i.context,m.fact_key'
            else:
                query = f'SELECT {fields} FROM instructions i {state_join} WHERE i.version=? ORDER BY i.address,i.context'
            exact, uncertain, exact_count, uncertain_count, scanned = [], [], 0, 0, 0
            warnings = ['Static stored-instruction scope: unknown control flow, register state, and runtime-generated code prevent a proof of all runtime writers.']
            truncated = False
            for row in self.db.execute(query, (version_id,)):
                scanned += 1
                if scanned > (1000000 if persisted else 250000):
                    truncated = True
                    break
                source = int(row['address'], 16)
                match = re.fullmatch(r'x86:16:little:cs=([0-9a-fA-F]{4})', row['context'])
                source_cs = int(match[1], 16) if match else None
                state = json.loads(row['state_registers']) if row['state_registers'] else {}
                facts = [json.loads(row['detail'])] if persisted else instruction_memory_accesses(bytes.fromhex(row['bytes']), source, self.arch, self.bits, cs=source_cs, registers=state)
                for fact in facts:
                    if access == 'read' and fact.get('may_read') is False or access == 'write' and fact.get('may_write') is False:
                        continue
                    if access not in ('all', 'read', 'write') and fact.get('access') != access:
                        continue
                    start, stop = fact.get('interval_start'), fact.get('interval_end')
                    known = bool(fact.get('interval_exact') and start is not None and stop is not None
                                 and fact.get('access') != 'unknown')
                    if known:
                        if not start < end or not stop > queried:
                            continue
                        kind = 'overlap'
                    else:
                        if not include_unresolved:
                            continue
                        low, high = fact.get('possible_start'), fact.get('possible_end')
                        if low is not None and high is not None and not (low < end and high > queried):
                            continue
                        kind = 'unresolved_candidate'
                    item = dict(fact, source=f'0x{source:x}', context=row['context'], bytes=row['bytes'],
                                mnemonic=row['mnemonic'], operands=row['operands'], match=kind,
                                source_cs=source_cs, source_ip=source-source_cs*16 if source_cs is not None else None,
                                state_assumptions=dict(registers=state, state=row['state_status'], reason=row['state_reason']))
                    if known:
                        exact_count += 1
                        if len(exact) < offset + limit:
                            exact.append(item)
                    else:
                        uncertain_count += 1
                        if len(uncertain) < offset + limit:
                            uncertain.append(item)
            if truncated:
                warnings.append('Memory query scan budget exhausted; counts cover only the scanned prefix.')
            total = exact_count + uncertain_count
            # Confirmed address overlaps precede unresolved candidates; both keep
            # their actual read/write/conditional classifications.
            if offset < exact_count:
                items = exact[offset:offset+limit]
                if len(items) < limit:
                    items += uncertain[:limit-len(items)]
            else:
                items = uncertain[offset-exact_count:offset-exact_count+limit]
            for item in items:
                source=int(item['source'],16)
                item['source_name']=self._dos_label(version_id,source,item['context']) if self.meta['format']=='MZ' else self._label(version_id,source)
                target=item.get('concrete_target')
                item['target_name']=self._label(version_id,target) if target is not None else None
            return dict(version=version_id, address=f'0x{queried:x}', name=self._label(version_id,queried), size=size, selector=selector,
                        access=access, items=items, total=total, address_matches=exact_count,
                        unresolved_candidates=uncertain_count, offset=offset, has_more=offset+len(items)<total,
                        facts_source='persisted' if persisted else 'decoded_stored_instructions',
                        facts_revision=MEMORY_FACTS_REVISION, candidates_examined=scanned,
                        budget_exhausted=truncated, scope='stored instructions and established static register state',
                        analysis=self.analysis_status(version_id), warnings=warnings)
