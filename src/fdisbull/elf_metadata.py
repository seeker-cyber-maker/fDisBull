"""Bounded ELF linkage metadata from LIEF and native, slot-proven PLT bytes.

Addresses are preferred static virtual addresses, without a runtime load bias.
DT_NEEDED is never used as proof that an unversioned symbol belongs to a library.
No loader, resolver, IFUNC, imported function or generated code is executed.
"""
from __future__ import annotations

from collections import defaultdict

import capstone
import iced_x86 as ix
import lief


_UNDEF, _ABS, _COMMON = 0, 0xfff1, 0xfff2
_PLT_SECTIONS = {'.plt', '.plt.sec', '.plt.got', '.iplt'}
_GLOBAL = {'GLOBAL', 'WEAK', 'GNU_UNIQUE'}


def _enum(value):
    return str(value).rsplit('.', 1)[-1]


def _bounded(values, limit, warnings, label):
    for index, value in enumerate(values):
        if index >= limit:
            warnings.append(f'{label} capped at {limit} entries')
            return
        yield value


def _symbol_fields(symbol, requirements, definitions):
    index, hidden, version, required = None, False, None, None
    if symbol.has_version:
        native = symbol.symbol_version
        raw = int(native.value)
        index, hidden = raw & 0x7fff, bool(raw & 0x8000)
        if index > 1:
            if native.has_auxiliary_version:
                version = native.symbol_version_auxiliary.name or None
            required_entries = requirements.get(index, set())
            matching = {(module, name) for module, name in required_entries if version is None or version == name}
            if len(required_entries) == 1 and len(matching) == 1:
                required, proven_version = next(iter(matching))
                version = version or proven_version
            elif int(symbol.shndx) != _UNDEF and not version:
                version = definitions.get(index)
    type_, binding = _enum(symbol.type), _enum(symbol.binding)
    return dict(name=symbol.name or None, symbol_type=type_, binding=binding,
                visibility=_enum(symbol.visibility), weak=binding == 'WEAK',
                symbol_defined=int(symbol.shndx) != _UNDEF, section_index=int(symbol.shndx),
                size=int(symbol.size), value=int(symbol.value), version=version,
                version_index=index, version_hidden=hidden, required_module=required,
                version_source='requirement' if required else 'definition' if index in definitions else None)


def _x86_stubs(content, start, bits, slots, budget, warnings):
    """Walk actual instruction boundaries; do not assume a PLT entry stride."""
    result, offset, previous = [], 0, None
    while offset < len(content) and budget[0] > 0:
        instruction = ix.Decoder(bits, content[offset:offset + 15], ip=start + offset).decode()
        if instruction.is_invalid:
            warnings.append(f'PLT native decoding stopped at invalid/truncated x86 bytes at 0x{start + offset:x}')
            break
        budget[0] -= 1
        slot = None
        if instruction.mnemonic == ix.Mnemonic.JMP and instruction.op_count == 1 and instruction.op0_kind == ix.OpKind.MEMORY and instruction.memory_segment not in (ix.Register.FS, ix.Register.GS):
            if instruction.is_ip_rel_memory_operand:
                slot = instruction.ip_rel_memory_address
            elif instruction.memory_base == ix.Register.NONE and instruction.memory_index == ix.Register.NONE and instruction.memory_segment not in (ix.Register.FS, ix.Register.GS):
                slot = instruction.memory_displacement
        if slot in slots and ix.MemorySizeExt.size(instruction.memory_size) == bits // 8:
            entry = instruction.ip
            if previous is not None and previous.next_ip == instruction.ip and previous.mnemonic in (ix.Mnemonic.ENDBR32, ix.Mnemonic.ENDBR64):
                entry = previous.ip
            end = instruction.next_ip
            result.append(dict(address=entry, slot=slot, arch='x86', bits=bits,
                               bytes=content[entry - start:end - start].hex(),
                               evidence=['native decoded indirect JMP memory operand equals a relocation-backed GOT slot',
                                         'entry is the JMP or its immediately preceding ENDBR instruction; no fixed PLT stride']))
        previous, offset = instruction, offset + instruction.len
    return result


def _arm64_stubs(content, start, slots, budget, warnings):
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    rows = []
    for offset in range(0, len(content), 4):
        if budget[0] <= 0:
            break
        instruction = next(decoder.disasm(content[offset:offset + 4], start + offset, count=1), None)
        if instruction is None:
            warnings.append(f'PLT native decoding stopped at invalid/truncated ARM64 bytes at 0x{start + offset:x}')
            break
        rows.append(instruction)
        budget[0] -= 1
    result = []
    reg, imm, mem = capstone.arm64.ARM64_OP_REG, capstone.arm64.ARM64_OP_IMM, capstone.arm64.ARM64_OP_MEM
    def general(instruction, operand):
        name = instruction.reg_name(operand.reg)
        return name.startswith('x') and name[1:].isdigit() and 0 <= int(name[1:]) <= 30
    for index, first in enumerate(rows):
        operands = first.operands
        if first.mnemonic != 'adrp' or len(operands) != 2 or operands[0].type != reg or operands[1].type != imm or not general(first, operands[0]):
            continue
        constants, loads = {operands[0].reg: operands[1].imm}, {}
        for following in rows[index + 1:index + 5]:
            ops = following.operands
            if following.mnemonic == 'ldr' and len(ops) == 2 and ops[0].type == reg and ops[1].type == mem and not following.writeback:
                address = ops[1].mem
                if address.base not in constants or address.index or not general(following, ops[0]):
                    break
                loads[ops[0].reg] = constants[address.base] + address.disp
                constants.pop(ops[0].reg, None)
            elif following.mnemonic == 'add' and len(ops) == 3 and ops[0].type == ops[1].type == reg and ops[2].type == imm and ops[1].reg in constants:
                shift = ops[2].shift.value
                if shift not in (0, 12) or not general(following, ops[0]):
                    break
                constants[ops[0].reg] = constants[ops[1].reg] + (ops[2].imm << shift)
                loads.pop(ops[0].reg, None)
            elif following.mnemonic == 'br' and len(ops) == 1 and ops[0].type == reg:
                slot = loads.get(ops[0].reg)
                if slot in slots:
                    entry = first.address
                    if index and rows[index - 1].mnemonic == 'bti':
                        entry = rows[index - 1].address
                    end = following.address + following.size
                    result.append(dict(address=entry, slot=slot, arch='arm64', bits=64,
                                       bytes=content[entry - start:end - start].hex(),
                                       evidence=['native ADRP and LDR compute a relocation-backed GOT slot; BR uses that loaded register',
                                                 'optional ADD and preceding BTI are decoded; no fixed PLT stride']))
                break
            else:
                break
    return result


def inspect_elf(binary, data, max_items=10000):
    """Return JSON-compatible imports, exports, relocations and loader linkage.

    ``binary`` must be the LIEF ELF object parsed from ``data``. GOT imports are
    backed by JUMP_SLOT/GLOB_DAT relocation addresses in mapped PT_LOAD storage.
    Undefined symbols without such a slot retain address=None. Dynamic symbols
    are classified by shndx/binding/type, including cases LIEF's imported and
    exported convenience flags omit (NOTYPE, weak, TLS and ABS).
    """
    if not isinstance(binary, lief.ELF.Binary) or not isinstance(data, bytes) or not data or len(data) > 64 * 1024 * 1024:
        raise ValueError('expected a parsed ELF Binary and its nonempty bytes, at most 64 MiB')
    if type(max_items) is not int or not 1 <= max_items <= 100000:
        raise ValueError('max_items must be an integer in 1..100000')
    warnings, requirements, definitions = [], defaultdict(set), {}
    machine = _enum(binary.header.machine_type)
    bits = 64 if _enum(binary.header.identity_class) == 'ELF64' else 32
    little = _enum(binary.header.identity_data) == 'LSB'
    segments = list(_bounded(binary.segments, max_items, warnings, 'ELF segments'))

    def mapped(address, size=1, executable=False):
        return any(segment.type == lief.ELF.Segment.TYPE.LOAD and
                   int(segment.virtual_address) <= address and address + size <= int(segment.virtual_address) + int(segment.virtual_size) and
                   (not executable or segment.has(lief.ELF.Segment.FLAGS.X)) for segment in segments)

    def read(address, size):
        matches = []
        for segment in segments:
            base, count = int(segment.virtual_address), int(segment.physical_size)
            if segment.type == lief.ELF.Segment.TYPE.LOAD and base <= address and address + size <= base + count:
                offset = int(segment.file_offset) + address - base
                if 0 <= offset <= offset + size <= len(data):
                    matches.append(data[offset:offset + size])
        return matches[0] if matches and all(value == matches[0] for value in matches) else None

    needed, rpath, runpath, soname = [], [], [], None
    for entry in _bounded(binary.dynamic_entries, max_items, warnings, 'ELF dynamic entries'):
        tag = _enum(entry.tag)
        if tag == 'NEEDED' and entry.name not in needed:
            needed.append(entry.name)
        elif tag == 'RPATH':
            rpath.extend(_bounded(entry.paths, max_items - len(rpath), warnings, 'ELF RPATH components'))
        elif tag == 'RUNPATH':
            runpath.extend(_bounded(entry.paths, max_items - len(runpath), warnings, 'ELF RUNPATH components'))
        elif tag == 'SONAME':
            soname = entry.name
    auxiliary_count = 0
    for requirement in _bounded(binary.symbols_version_requirement, max_items, warnings, 'ELF version requirements'):
        for auxiliary in _bounded(requirement.get_auxiliary_symbols(), max_items - auxiliary_count, warnings, 'ELF auxiliary version requirements'):
            requirements[int(auxiliary.other) & 0x7fff].add((requirement.name, auxiliary.name))
            auxiliary_count += 1
        if auxiliary_count >= max_items:
            warnings.append('ELF auxiliary version requirement budget reached; additional bindings may be unresolved')
            break
    for definition in _bounded(binary.symbols_version_definition, max_items, warnings, 'ELF version definitions'):
        names = iter(definition.auxiliary_symbols)
        first = next(names, None)
        if first is not None:
            definitions[int(definition.ndx) & 0x7fff] = first.name
    if any(len(values) > 1 for values in requirements.values()):
        warnings.append('Conflicting version requirement indices are retained; ambiguous symbol modules remain unresolved')

    candidate_libraries = needed[:64]
    if len(candidate_libraries) < len(needed):
        warnings.append('Per-symbol module candidates capped at 64; complete retained DT_NEEDED list is in linkage')
    imports, exports, relocations = [], [], []
    slots, symbols_with_slots = defaultdict(list), set()
    copy_symbols = set()
    for relocation in _bounded(binary.relocations, max_items, warnings, 'ELF relocations'):
        address, type_ = int(relocation.address), _enum(relocation.type)
        symbol = relocation.symbol if relocation.has_symbol and relocation.symbol.name else None
        fields = _symbol_fields(symbol, requirements, definitions) if symbol is not None else {}
        is_got = type_.endswith(('_JUMP_SLOT', '_JMP_SLOT', '_GLOB_DAT')) and symbol is not None
        is_copy = type_.endswith('_COPY') and symbol is not None
        slot = address if is_got and mapped(address, bits // 8) else None
        copy_storage = address if is_copy and mapped(address, fields['size'] or 1) else None
        row = dict(address=address, type=type_, addend=int(relocation.addend) if relocation.is_rela else None,
                   lief_addend_raw=int(relocation.addend),
                   has_addend=bool(relocation.is_rela), addend_source='explicit_RELA' if relocation.is_rela else 'implicit_REL_storage_not_decoded',
                   size_bits=int(relocation.size),
                   symbol=fields.get('name'), symbol_type=fields.get('symbol_type'),
                   version=fields.get('version'), version_index=fields.get('version_index'),
                   required_module=fields.get('required_module'), slot=slot, copy_storage=copy_storage,
                   purpose=_enum(relocation.purpose), encoding=_enum(relocation.encoding),
                   symbol_index=int(relocation.info))
        relocations.append(row)
        if is_got or is_copy:
            if is_got and slot is None:
                warnings.append(f'GOT relocation at 0x{address:x} is outside retained PT_LOAD storage; slot address is unresolved')
            if len(imports) >= max_items:
                continue
            module = fields['required_module']
            item = dict(fields, module=module, module_source='ELF version requirement' if module else None,
                        runtime_provider_observed=False,
                        module_candidates=[] if module else list(candidate_libraries),
                        ordinal=None, address=None if is_copy else slot, storage_address=copy_storage if is_copy else None,
                        kind='copy_storage' if is_copy else 'got' if slot is not None else 'dynamic_symbol',
                        address_kind='copy_storage' if is_copy else 'loader_pointer_slot' if slot is not None else None,
                        callable=False if is_copy or fields['symbol_type'] in ('OBJECT', 'TLS') else
                        True if fields['symbol_type'] in ('FUNC', 'GNU_IFUNC') else None,
                        relocation_address=address, relocation_type=type_, stub_addresses=[],
                        binding_scope='imported_copy_storage' if is_copy else 'preemptible_definition' if fields['symbol_defined'] else 'undefined_symbol',
                        evidence=[f'ELF {type_} relocation references this dynamic symbol',
                                  'required module proven by symbol-version requirement index' if module else 'symbol-to-module binding unresolved'])
            imports.append(item)
            if is_got and slot is not None:
                item.update(runtime_unresolved=True, binding_state='runtime_unresolved', pointer_width=bits // 8)
            symbols_with_slots.add((fields['name'], fields['version_index']))
            if is_copy:
                copy_symbols.add((fields['name'], fields['version_index']))
            if slot is not None:
                slots[slot].append(item)

    for symbol in _bounded(binary.dynamic_symbols, max_items, warnings, 'ELF dynamic symbols'):
        if not symbol.name:
            continue
        fields = _symbol_fields(symbol, requirements, definitions)
        if fields['binding'] not in _GLOBAL:
            continue
        if not fields['symbol_defined']:
            if (fields['name'], fields['version_index']) not in symbols_with_slots and len(imports) < max_items:
                module = fields['required_module']
                imports.append(dict(fields, module=module, module_source='ELF version requirement' if module else None,
                                    runtime_provider_observed=False,
                                    module_candidates=[] if module else list(candidate_libraries),
                                    ordinal=None, address=None, kind='dynamic_symbol', stub_addresses=[],
                                    callable=False if fields['symbol_type'] in ('OBJECT', 'TLS') else
                                    True if fields['symbol_type'] in ('FUNC', 'GNU_IFUNC') else None,
                                    binding_scope='undefined_symbol', evidence=['undefined externally bound ELF dynamic symbol; no retained GOT slot']))
            continue
        if fields['visibility'] not in ('DEFAULT', 'PROTECTED') or len(exports) >= max_items:
            continue
        type_, section, value = fields['symbol_type'], fields['section_index'], fields['value']
        tls, absolute, common = type_ == 'TLS', section == _ABS, section == _COMMON
        ifunc, function = type_ == 'GNU_IFUNC', type_ == 'FUNC'
        address = None if tls or absolute or common else value
        kind = 'tls_offset' if tls else 'absolute' if absolute else 'common_alignment' if common else 'ifunc_resolver' if ifunc else 'virtual_address'
        row = dict(fields, address=address, ordinal=None, forwarder=None, address_kind=kind,
                   is_function=function, is_ifunc=ifunc, is_tls=tls, absolute=absolute,
                   imported_copy=(fields['name'], fields['version_index']) in copy_symbols,
                   code_seed_eligible=bool(function and not (tls or absolute or common) and
                                           (fields['name'], fields['version_index']) not in copy_symbols and mapped(value, executable=True)))
        if ifunc:
            row['resolver_address'] = value
        if tls:
            row['tls_offset'] = value
        if absolute:
            row['absolute_value'] = value
        exports.append(row)

    stubs, instructions_budget, bytes_budget = [], [min(max_items * 16, 1000000)], min(max_items * 64, 1024 * 1024)
    supported = little and machine in ('X86_64', 'I386', 'AARCH64')
    if slots and supported:
        for section in _bounded(binary.sections, max_items, warnings, 'ELF PLT section search'):
            if section.name not in _PLT_SECTIONS or not int(section.flags) & 4:
                continue
            size, address = int(section.size), int(section.virtual_address)
            if size <= 0 or not mapped(address, size, executable=True):
                continue
            count = min(size, bytes_budget)
            content = read(address, count)
            if content is None:
                warnings.append(f'PLT section {section.name} is not entirely backed by retained file bytes')
                continue
            if machine == 'AARCH64':
                found = _arm64_stubs(content, address, slots, instructions_budget, warnings) if address % 4 == 0 else []
            else:
                found = _x86_stubs(content, address, bits, slots, instructions_budget, warnings)
            for stub in found:
                for item in slots[stub['slot']]:
                    if item['callable'] is False:
                        continue
                    item['callable'] = True
                    if stub['address'] not in item['stub_addresses'] and len(item['stub_addresses']) < max_items:
                        item['stub_addresses'].append(stub['address'])
                    if len(stubs) < max_items:
                        stubs.append(dict(stub, name=item['name'], version=item['version'], module=item['module'], section=section.name))
            bytes_budget -= count
            if count < size or bytes_budget <= 0 or instructions_budget[0] <= 0:
                warnings.append('ELF PLT native-validation budget exhausted; additional stubs remain unresolved')
                break
    elif slots:
        warnings.append('Native PLT validation is implemented only for little-endian x86 and ARM64; other stubs remain unresolved')
    if len(imports) >= max_items:
        warnings.append(f'ELF import list reached its {max_items}-entry cap; additional entries may be omitted')
    if len(exports) >= max_items:
        warnings.append(f'ELF export list reached its {max_items}-entry cap; additional entries may be omitted')
    if any(item['module'] is None for item in imports):
        warnings.append('Unversioned or ambiguously versioned symbols have no proven library binding; DT_NEEDED names are candidates only')
    if slots:
        warnings.append('PLT recognition uses named executable sections and decoded slot-proven patterns; absent stub addresses are unresolved, not a fixed-stride guess')
    interpreter = binary.interpreter if binary.has_interpreter else None
    linkage = dict(needed=needed, interpreter=interpreter, rpath=rpath, runpath=runpath, soname=soname,
                   stubs=stubs, address_model='preferred static ELF virtual addresses; runtime load bias and interposition are not applied',
                   native_stubs_executed=False)
    return dict(imports=imports, exports=exports,
                libraries=[dict(name=name, kind='needed', source='DT_NEEDED') for name in needed],
                relocations=relocations, linkage=linkage,
                header=dict(is_pie=bool(binary.is_pie), interpreter=interpreter, needed=needed,
                            rpath=rpath, runpath=runpath, soname=soname),
                warnings=list(dict.fromkeys(warnings)))
