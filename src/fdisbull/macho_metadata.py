"""Bounded Mach-O linkage metadata, without loading or executing the image.

LIEF supplies decoded dyld/chained bindings and rebases. Raw load commands,
indirect-symbol indices and export tries preserve identities that its abstract
symbol views omit. Layout references: Apple's mach-o/loader.h, nlist.h and
reloc.h in apple-oss-distributions/xnu; LIEF 1.0 Mach-O Python documentation.
Addresses are preferred static VAs; an import's external target stays unknown.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import islice
import struct

import lief


_MAX_INPUT = 64 * 1024 * 1024
_MAX_ITEMS = 10000
_DYLIBS = {0xC: 'load_dylib', 0x80000018: 'weak_dylib', 0x8000001F: 'reexport_dylib',
           0x20: 'lazy_load_dylib', 0x80000023: 'upward_dylib'}
_POINTER_SECTIONS = {6: 'non_lazy', 7: 'lazy', 0x10: 'lazy_dylib', 0x13: 'thread_local'}
_ZEROFILL = {1, 0xC, 0x12}


def _enum(value):
    return str(value).rsplit('.', 1)[-1].lower()


def _permissions(value):
    return ''.join(letter if value & bit else '-' for bit, letter in ((1, 'r'), (2, 'w'), (4, 'x')))


class _Raw:
    def __init__(self, data, maximum):
        magic = {b'\xce\xfa\xed\xfe': (32, '<'), b'\xcf\xfa\xed\xfe': (64, '<'),
                 b'\xfe\xed\xfa\xce': (32, '>'), b'\xfe\xed\xfa\xcf': (64, '>')}
        if data[:4] not in magic:
            raise ValueError('Mach-O metadata requires one thin Mach-O byte slice')
        self.data, self.maximum = data, maximum
        self.bits, self.endian = magic[data[:4]]
        header_size = 32 if self.bits == 64 else 28
        if len(data) < header_size:
            raise ValueError('truncated Mach-O header')
        _, self.cpu, _, self.file_type, count, size, self.flags = struct.unpack_from(self.endian + '7I', data)
        if count > 4096 or header_size + size > len(data):
            raise ValueError('Mach-O load commands are truncated or exceed limits')
        self.warnings, self.partial = [], set()
        self.sections, self.segments, self.libraries, self.commands = [], [], [], []
        self.identifier, self.symtab, self.dysymtab = None, None, None
        self.export_ranges, self.chained_range, self.binding_ranges = [], None, []
        self.symbol_cache = {}
        position, end = header_size, header_size + size
        for _ in range(count):
            if position + 8 > end:
                raise ValueError('truncated Mach-O load-command header')
            command, command_size = struct.unpack_from(self.endian + 'II', data, position)
            if command_size < 8 or position + command_size > end:
                raise ValueError('invalid Mach-O load-command extent')
            self.commands.append((command, position, command_size))
            if command in (1, 0x19):
                self._segment(command, position, command_size)
            elif command in _DYLIBS or command == 0xD:
                if command_size < 24:
                    self.warn('libraries', 'truncated dylib command')
                else:
                    name_offset, timestamp, current, compatibility = struct.unpack_from(self.endian + '4I', data, position + 8)
                    name = self.string(position + name_offset, position + command_size, 'dylib name') if 24 <= name_offset < command_size else None
                    if name is None:
                        self.warn('libraries', 'invalid dylib command name')
                    item = dict(name=name, command=_DYLIBS.get(command, 'id_dylib'), timestamp=timestamp,
                                current_version=current, compatibility_version=compatibility)
                    if command == 0xD:
                        self.identifier = item
                    else:
                        item['ordinal'] = len(self.libraries) + 1
                        self.libraries.append(item)
            elif command == 2:
                if command_size < 24:
                    self.warn('symbols', 'truncated LC_SYMTAB')
                else:
                    self.symtab = struct.unpack_from(self.endian + '4I', data, position + 8)
            elif command == 0xB:
                if command_size < 80:
                    self.warn('indirect_symbols', 'truncated LC_DYSYMTAB')
                else:
                    self.dysymtab = struct.unpack_from(self.endian + '18I', data, position + 8)
            elif command in (0x22, 0x80000022):
                if command_size < 48:
                    self.warn('dyld_bindings', 'truncated LC_DYLD_INFO')
                else:
                    values = struct.unpack_from(self.endian + '10I', data, position + 8)
                    self.binding_ranges.extend((values[index], values[index + 1]) for index in (2, 4, 6))
                    if values[9]:
                        self.export_ranges.append((values[8], values[9], 'LC_DYLD_INFO export trie'))
            elif command == 0x80000033:
                if command_size < 16:
                    self.warn('exports', 'truncated LC_DYLD_EXPORTS_TRIE')
                else:
                    offset, length = struct.unpack_from(self.endian + 'II', data, position + 8)
                    self.export_ranges.append((offset, length, 'LC_DYLD_EXPORTS_TRIE'))
            elif command == 0x80000034:
                if command_size < 16:
                    self.warn('chained_fixups', 'truncated LC_DYLD_CHAINED_FIXUPS')
                else:
                    self.chained_range = struct.unpack_from(self.endian + 'II', data, position + 8)
            position += command_size
        if position != end:
            self.warn('header', 'Mach-O command count does not cover its declared command bytes')
        if self.symtab:
            offset, count, strings, length = self.symtab
            if not self.range(offset, count * (16 if self.bits == 64 else 12), 'symbol table') or not self.range(strings, length, 'string table'):
                self.partial.add('symbols')
                self.symtab = None
        if self.dysymtab:
            offset, count = self.dysymtab[12:14]
            if not self.range(offset, count * 4, 'indirect-symbol table'):
                self.partial.add('indirect_symbols')
                self.dysymtab = None

    def warn(self, category, message):
        self.partial.add(category)
        if len(self.warnings) < 1024 and message not in self.warnings:
            self.warnings.append(message)

    def range(self, offset, size, description):
        valid = 0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset
        if not valid:
            self.warn(description, f'{description} exceeds file bounds')
        return valid

    def string(self, offset, end, description):
        if not 0 <= offset < end <= len(self.data):
            self.warn('strings', f'invalid {description} extent')
            return None
        stop = self.data.find(b'\0', offset, min(end, offset + 4097))
        if stop < 0:
            self.warn('strings', f'unterminated or oversized {description}')
            return None
        return self.data[offset:stop].decode('utf-8', 'backslashreplace')

    def _segment(self, command, position, size):
        wide = command == 0x19
        fixed, stride = (72, 80) if wide else (56, 68)
        if size < fixed:
            self.warn('sections', 'truncated segment command')
            return
        name = self.data[position + 8:position + 24].split(b'\0', 1)[0].decode('utf-8', 'backslashreplace')
        address, virtual_size, offset, file_size = struct.unpack_from(self.endian + ('4Q' if wide else '4I'), self.data, position + 24)
        protection_offset = position + (56 if wide else 40)
        maximum, initial, count, flags = struct.unpack_from(self.endian + '4I', self.data, protection_offset)
        if address + virtual_size > 1 << self.bits:
            self.warn('sections', 'segment virtual range exceeds address width')
            return
        segment = dict(name=name, virtual_address=address, virtual_size=virtual_size, file_offset=offset,
                       file_size=file_size, max_protection=maximum, init_protection=initial,
                       permissions=_permissions(initial), flags=flags)
        self.segments.append(segment)
        self.range(offset, file_size, 'segment file range')
        if count > 4096 or len(self.sections) + count > 4096 or fixed + count * stride > size:
            self.warn('sections', 'section count or section records exceed segment command limits')
            return
        for index in range(count):
            at = position + fixed + index * stride
            section_name = self.data[at:at + 16].split(b'\0', 1)[0].decode('utf-8', 'backslashreplace')
            declared_segment = self.data[at + 16:at + 32].split(b'\0', 1)[0].decode('utf-8', 'backslashreplace')
            va, length = struct.unpack_from(self.endian + ('QQ' if wide else 'II'), self.data, at + 32)
            fields = struct.unpack_from(self.endian + '7I', self.data, at + (48 if wide else 40))
            file_offset, alignment, relocation_offset, relocation_count, section_flags, reserved1, reserved2 = fields
            if va < address or va + length > address + virtual_size:
                self.warn('sections', f'section {section_name} exceeds its owning segment virtual range')
                continue
            if declared_segment != name:
                self.warn('sections', f'section {section_name} segment name disagrees with its owning command')
            zero = section_flags & 255 in _ZEROFILL
            backed = not zero and self.range(file_offset, length, 'section file range')
            self.sections.append(dict(index=len(self.sections) + 1, name=section_name, segment=name,
                full_name=f'{name}:{section_name}', virtual_address=va, virtual_size=length,
                file_offset=file_offset if not zero else None, file_size=length if backed else 0,
                permissions=segment['permissions'], init_protection=initial, max_protection=maximum,
                executable=bool(initial & 4), writable=bool(initial & 2), readable=bool(initial & 1),
                flags=section_flags, section_type=section_flags & 255,
                instruction_attributes=bool(section_flags & 0x80000400),
                is_code=bool(initial & 4 and (section_flags & 0x80000400 or section_flags & 255 == 8)),
                reserved1=reserved1, reserved2=reserved2, relocation_offset=relocation_offset,
                relocation_count=relocation_count, alignment=alignment, file_backed=backed))

    def symbol(self, index):
        if index in self.symbol_cache:
            return self.symbol_cache[index]
        if not self.symtab or not 0 <= index < self.symtab[1]:
            self.warn('symbols', 'indirect or relocation symbol index is outside LC_SYMTAB')
            return None
        offset, _, strings, string_size = self.symtab
        fields = struct.unpack_from(self.endian + ('IBBHQ' if self.bits == 64 else 'IBBHI'), self.data,
                                    offset + index * (16 if self.bits == 64 else 12))
        string_index, kind, section, description, value = fields
        name = self.string(strings + string_index, strings + string_size, 'symbol name') if string_index < string_size else None
        ordinal = description >> 8
        ordinal = -2 if ordinal == 0xFE else -1 if ordinal == 0xFF else ordinal
        record = dict(index=index, name=name, type=kind, section=section, description=description,
                      value=value, library_ordinal=ordinal, weak_import=bool(description & 0x40))
        self.symbol_cache[index] = record
        return record

    def library(self, ordinal):
        if 1 <= ordinal <= len(self.libraries):
            return self.libraries[ordinal - 1]['name'], 'library'
        if ordinal == 0:
            return (self.identifier or {}).get('name'), 'self'
        return None, {-1: 'main_executable', -2: 'flat_lookup', -3: 'weak_lookup'}.get(ordinal, 'unknown_ordinal')

    def mapped(self, address, width=1):
        return any(s['virtual_address'] <= address and address + width <= s['virtual_address'] + s['virtual_size'] for s in self.segments)

    def file_offset(self, address, width=1):
        for segment in self.segments:
            delta = address - segment['virtual_address']
            if 0 <= delta and delta + width <= segment['file_size']:
                result = segment['file_offset'] + delta
                if 0 <= result <= len(self.data) - width:
                    return result
        return None


def _uleb(data, position, end):
    value = 0
    for shift in range(0, 70, 7):
        if position >= end:
            raise ValueError('truncated export-trie ULEB128')
        byte = data[position]
        position += 1
        if shift == 63 and byte & 0xFE:
            raise ValueError('oversized export-trie ULEB128')
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, position
    raise ValueError('oversized export-trie ULEB128')


def _export_record(raw, imagebase, name, flags, value, source):
    kind = flags & 3
    if kind == 3:
        raise ValueError('unsupported export-trie symbol kind')
    address = value if kind == 2 else imagebase + value
    if not 0 <= address < 1 << raw.bits:
        raise ValueError('export address exceeds Mach-O address width')
    section = next((s for s in raw.sections if s['virtual_address'] <= address < s['virtual_address'] + s['virtual_size']), None)
    is_code = bool(kind == 0 and section and section['is_code'])
    return dict(name=name, address=address, ordinal=None, kind='absolute' if kind == 2 else 'thread_local' if kind == 1 else 'code' if is_code else 'data' if section else 'unknown',
                is_code=is_code, forwarder=None, reexport=None, flags=flags,
                weak_definition=bool(flags & 4), source=source,
                file_offset=raw.file_offset(address), section=section['full_name'] if section else None)


def _exports(raw, imagebase):
    result, seen, truncated = [], set(), False
    # The modern command takes precedence if both representations are present.
    ranges = [item for item in raw.export_ranges if item[2] == 'LC_DYLD_EXPORTS_TRIE'] or raw.export_ranges
    for offset, size, source in ranges[:1]:
        if not raw.range(offset, size, 'export trie') or not size:
            if size:
                raw.partial.add('exports')
            continue
        end, queue, visited, work = offset + size, [(offset, '', frozenset())], set(), 0
        while queue:
            at, prefix, ancestors = queue.pop()
            if at in ancestors:
                raw.warn('exports', 'cyclic export trie')
                continue
            if len(ancestors) > 256:
                raw.warn('exports', 'export-trie depth exceeds 256 nodes')
                continue
            if (at, prefix) in visited:
                continue
            visited.add((at, prefix));work += 1
            if work > raw.maximum * 16 + 4096:
                truncated = True
                break
            try:
                terminal_size, cursor = _uleb(raw.data, at, end)
                terminal_end = cursor + terminal_size
                if terminal_end >= end:
                    raise ValueError('export-trie terminal exceeds payload')
                if terminal_size:
                    if not prefix:
                        raise ValueError('export trie contains an empty symbol name')
                    flags, item_cursor = _uleb(raw.data, cursor, terminal_end)
                    if flags & 8:
                        ordinal, item_cursor = _uleb(raw.data, item_cursor, terminal_end)
                        imported = raw.string(item_cursor, terminal_end, 'reexport imported name')
                        if imported is None:
                            raise ValueError('invalid reexport imported name')
                        imported = imported or prefix
                        module, scope = raw.library(ordinal)
                        item = dict(name=prefix, address=None, ordinal=None, kind='reexport', is_code=False,
                                    forwarder=f'{module}!{imported}' if module else imported,
                                    reexport=dict(module=module, name=imported, library_ordinal=ordinal, library_scope=scope),
                                    flags=flags, weak_definition=bool(flags & 4), source=source, file_offset=None)
                    else:
                        value, item_cursor = _uleb(raw.data, item_cursor, terminal_end)
                        item = _export_record(raw, imagebase, prefix, flags, value, source)
                        if flags & 0x10:
                            resolver, item_cursor = _uleb(raw.data, item_cursor, terminal_end)
                            if not 0 <= imagebase + resolver < 1 << raw.bits:
                                raise ValueError('export resolver address exceeds Mach-O address width')
                            item['resolver_address'] = imagebase + resolver
                    if prefix not in seen:
                        if len(result) >= raw.maximum:
                            truncated = True
                            break
                        seen.add(prefix);result.append(item)
                child_count = raw.data[terminal_end]
                child_cursor = terminal_end + 1
                children = []
                for _ in range(child_count):
                    label = raw.string(child_cursor, end, 'export-trie edge')
                    if label is None:
                        raise ValueError('invalid export-trie edge')
                    stop = raw.data.find(b'\0', child_cursor, end)
                    child, child_cursor = _uleb(raw.data, stop + 1, end)
                    if child >= size or len(prefix) + len(label) > 4096:
                        raise ValueError('export-trie child or symbol name exceeds limits')
                    children.append((offset + child, prefix + label, ancestors | {at}))
                queue.extend(reversed(children))
            except (ValueError, IndexError) as error:
                raw.warn('exports', str(error))
    # Old images/object files may expose only external symbols. Keep their
    # weaker visibility evidence distinct from an authoritative export trie.
    if not ranges and raw.symtab:
        for index in range(min(raw.symtab[1], raw.maximum)):
            symbol = raw.symbol(index)
            if symbol and symbol['name'] and symbol['type'] & 1 and not symbol['type'] & 0xE0 and symbol['type'] & 0xE in (2, 0xE):
                item = _export_record(raw, imagebase, symbol['name'], 2 if symbol['type'] & 0xE == 2 else 0,
                                      symbol['value'] if symbol['type'] & 0xE == 2 else symbol['value'] - imagebase,
                                      'LC_SYMTAB external defined symbol')
                item['visibility'] = 'external_symbol_only'
                result.append(item)
        if raw.symtab[1] > raw.maximum:
            truncated = True
    return result, truncated


def inspect_macho(binary, data: bytes, max_items: int = 10000) -> dict:
    """Inspect a matching LIEF thin binary and its original file byte slice.

    ``max_items`` caps every output collection and each binding/indirect scan.
    No import address is a resolved external function target. Stub aliases
    require exact LC_DYSYMTAB symbol indices, not equal-looking names or code.
    """
    if not isinstance(data, bytes) or len(data) > _MAX_INPUT:
        raise ValueError('Mach-O metadata requires bytes of at most 64 MiB')
    if isinstance(max_items, bool) or not isinstance(max_items, int) or not 1 <= max_items <= _MAX_ITEMS:
        raise ValueError('max_items must be an integer in 1..10000')
    if not isinstance(binary, lief.MachO.Binary):
        raise ValueError('Mach-O metadata requires a LIEF MachO.Binary')
    raw = _Raw(data, max_items)
    imagebase = int(binary.imagebase)
    pointer_width = raw.bits // 8
    truncated = {key: False for key in ('imports', 'exports', 'libraries', 'relocations', 'linkage', 'sections')}
    imports, order, by_symbol, stubs = {}, [], defaultdict(list), []

    def add_import(name, ordinal, address, source, *, binding_class=None, weak=False, addend=0, kind='dyld_pointer', evidence=None):
        if not name:
            raw.warn('imports', 'binding or indirect symbol has no complete name')
            return None
        module, scope = raw.library(ordinal)
        if scope == 'unknown_ordinal':
            raw.warn('libraries', 'binding library ordinal is outside the load-dylib commands')
        if binding_class == 'weak':
            module, scope = None, 'weak_lookup'
        key = name, ordinal, address, kind
        detail = dict(source=source, **(evidence or {}))
        if key in imports:
            item = imports[key]
            if detail not in item['provenance']:
                item['provenance'].append(detail)
            if source not in item['sources']:
                item['sources'].append(source)
            item['weak_import'] |= weak
            return key
        if len(imports) >= max_items:
            truncated['imports'] = True
            return None
        imports[key] = dict(module=module, name=name, ordinal=None, library_ordinal=ordinal, library_scope=scope,
                            address=address, kind=kind, stub_addresses=[], target=None, addend=addend,
                            binding_state='runtime_unresolved', pointer_width=pointer_width,
                            weak_import=weak, binding_class=binding_class, source=source, sources=[source],
                            evidence='Static binding site or exact indirect-symbol identity; external target unresolved.',
                            provenance=[detail], file_offset=raw.file_offset(address, pointer_width) if address is not None else None)
        order.append(key)
        return key

    binding_count, chained_count = 0, 0
    streams = [('dyld_bind', binary.bindings)]
    if binary.has_dyld_chained_fixups:
        streams.append(('dyld_chained_fixups', binary.dyld_chained_fixups.bindings))
    seen_native = set()
    for source, stream in streams:
        for index, binding in enumerate(islice(stream, max_items + 1)):
            if index == max_items:
                truncated['imports'] = True
                raw.warn('dyld_bindings', f'{source} binding enumeration capped at {max_items}')
                break
            if isinstance(binding, lief.MachO.IndirectBindingInfo):
                continue  # Raw indices below distinguish pointers from stubs.
            binding_source = 'dyld_chained_fixups' if isinstance(binding, lief.MachO.ChainedBindingInfo) else source
            name = binding.symbol.name if binding.has_symbol else None
            ordinal, address = int(binding.library_ordinal), int(binding.address)
            identity = name, ordinal, address, type(binding).__name__
            if identity in seen_native:
                continue
            seen_native.add(identity)
            binding_count += 1
            chained_count += binding_source == 'dyld_chained_fixups'
            binding_class = _enum(binding.binding_class) if isinstance(binding, lief.MachO.DyldBindingInfo) else 'chained'
            pointer = not isinstance(binding, lief.MachO.DyldBindingInfo) or int(binding.binding_type) == 1
            width = pointer_width if pointer else 4
            if not raw.mapped(address, width):
                raw.warn('imports', 'native binding site is outside declared mapped segments')
                address = None
            evidence = dict(binding_class=binding_class, addend=int(binding.addend), weak_import=bool(binding.weak_import))
            if isinstance(binding, lief.MachO.ChainedBindingInfo):
                evidence.update(pointer_format=_enum(binding.ptr_format), imports_format=_enum(binding.format))
            add_import(name, ordinal, address, binding_source, binding_class=binding_class,
                       weak=bool(binding.weak_import), addend=int(binding.addend),
                       kind='dyld_pointer' if pointer else 'dyld_' + _enum(binding.binding_type), evidence=evidence)

    indirect_examined = 0
    for section in raw.sections:
        kind = section['section_type']
        if kind not in _POINTER_SECTIONS and kind != 8:
            continue
        stride = section['reserved2'] if kind == 8 else pointer_width
        if not stride or not section['file_backed'] or not raw.dysymtab:
            raw.warn('indirect_symbols', f'{section["full_name"]} lacks a valid stride, file bytes or indirect-symbol table')
            continue
        count, remainder = divmod(section['virtual_size'], stride)
        if remainder:
            raw.warn('indirect_symbols', f'{section["full_name"]} has a partial linkage entry')
        examined_here = min(count, max_items - indirect_examined)
        for index in range(examined_here):
            indirect_examined += 1
            table_index = section['reserved1'] + index
            table_offset, table_count = raw.dysymtab[12:14]
            if table_index >= table_count:
                raw.warn('indirect_symbols', 'section indirect-symbol range exceeds LC_DYSYMTAB')
                continue
            symbol_index = struct.unpack_from(raw.endian + 'I', data, table_offset + table_index * 4)[0]
            if symbol_index & 0xC0000000:
                continue  # LOCAL/ABS sentinels never identify an import.
            symbol = raw.symbol(symbol_index)
            if not symbol or not symbol['name'] or symbol['type'] & 0xE0 or not symbol['type'] & 1 or symbol['type'] & 0xE not in (0, 0xC):
                continue
            address = section['virtual_address'] + index * stride
            evidence = dict(symbol_index=symbol_index, indirect_index=table_index, section=section['full_name'])
            if kind == 8:
                if section['executable']:
                    stubs.append(dict(address=address, size=stride, symbol=symbol, evidence=evidence))
                else:
                    raw.warn('linkage', 'symbol stub is in a non-executable segment; no code alias emitted')
            else:
                key = add_import(symbol['name'], symbol['library_ordinal'], address, 'indirect_symbol_table',
                                 binding_class=_POINTER_SECTIONS[kind], weak=symbol['weak_import'], evidence=evidence)
                if key is not None and key not in by_symbol[symbol_index]:
                    by_symbol[symbol_index].append(key)
        if examined_here < count:
            # The scan is capped across all sections, not separately per table.
            truncated['linkage'] = True
            truncated['imports'] = True
    linkage = []
    for stub in stubs:
        symbol = stub['symbol'];keys = by_symbol[symbol['index']]
        if not keys:
            key = add_import(symbol['name'], symbol['library_ordinal'], None, 'indirect_symbol_table',
                             kind='unresolved_import', binding_class='stub_only', weak=symbol['weak_import'], evidence=stub['evidence'])
            keys = [key] if key is not None else []
        slots = []
        for key in keys:
            item = imports[key]
            if stub['address'] not in item['stub_addresses']:
                item['stub_addresses'].append(stub['address'])
            if item['address'] is not None:
                slots.append(item['address'])
        module, _ = raw.library(symbol['library_ordinal'])
        linkage.append(dict(kind='stub', address=stub['address'], size=stub['size'], name=symbol['name'],
                            module=module, library_ordinal=symbol['library_ordinal'], slot_addresses=sorted(set(slots)),
                            authoritative=True, source='indirect_symbol_table', **stub['evidence']))
    if raw.symtab:
        known_imports = {(key[0], key[1]) for key in imports}
        for index in range(min(raw.symtab[1], max_items)):
            symbol = raw.symbol(index)
            if not symbol or not symbol['name'] or symbol['type'] & 0xE0 or not symbol['type'] & 1 or symbol['type'] & 0xE not in (0, 0xC):
                continue
            identity = symbol['name'], symbol['library_ordinal']
            if identity not in known_imports and symbol['value'] == 0:
                add_import(symbol['name'], symbol['library_ordinal'], None, 'LC_SYMTAB undefined external',
                           kind='unresolved_import', weak=symbol['weak_import'], evidence=dict(symbol_index=index))
                known_imports.add(identity)
        if raw.symtab[1] > max_items:
            truncated['imports'] = True

    exports, truncated['exports'] = _exports(raw, imagebase)
    relocations = []
    for section in raw.sections:
        count, offset = section['relocation_count'], section['relocation_offset']
        if not count:
            continue
        if not raw.range(offset, count * 8, 'section relocation table'):
            raw.partial.add('relocations')
            continue
        processed = min(count, max_items - len(relocations))
        for index in range(processed):
            address_word, bits = struct.unpack_from(raw.endian + 'II', data, offset + index * 8)
            # Scattered records belong to 32-bit Mach-O. In a 64-bit record
            # this high bit is the sign of r_address, never a second layout.
            scattered = raw.bits == 32 and bool(address_word & 0x80000000)
            if scattered:
                relative, length, pc_relative, relocation_type = address_word & 0xFFFFFF, address_word >> 28 & 3, bool(address_word & 0x40000000), address_word >> 24 & 15
                external, symbol_index, target, symbol_name = False, None, bits, None
            else:
                relative = struct.unpack(raw.endian + 'i', struct.pack(raw.endian + 'I', address_word))[0]
                if raw.endian == '<':
                    symbol_index, pc_relative, length, external, relocation_type = bits & 0xFFFFFF, bool(bits >> 24 & 1), bits >> 25 & 3, bool(bits >> 27 & 1), bits >> 28
                else:
                    symbol_index, pc_relative, length, external, relocation_type = bits >> 8, bool(bits >> 7 & 1), bits >> 5 & 3, bool(bits >> 4 & 1), bits & 15
                symbol = raw.symbol(symbol_index) if external else None
                symbol_name = symbol['name'] if symbol else None
                target = symbol['value'] if symbol and symbol['type'] & 0xE in (2, 0xE) else None
            width = 1 << length
            if relative < 0 or relative + width > section['virtual_size']:
                raw.warn('relocations', 'section relocation offset exceeds its section')
                continue
            address = section['virtual_address'] + relative
            relocations.append(dict(address=address, file_offset=raw.file_offset(address, width), width=width,
                                    kind='section_relocation', type=relocation_type, pc_relative=pc_relative,
                                    external=external, scattered=scattered, symbol=symbol_name, symbol_index=symbol_index,
                                    target=target, section=section['full_name'], source='section relocation table',
                                    evidence=dict(record_file_offset=offset + index * 8, section_relative_offset=relative)))
        if count > processed:
            truncated['relocations'] = True
    for index, relocation in enumerate(islice(binary.relocations, max_items + 1)):
        if index == max_items:
            truncated['relocations'] = True
            break
        if isinstance(relocation, lief.MachO.RelocationObject):
            continue  # Raw records above retain exact VA and r_length width.
        if len(relocations) >= max_items:
            truncated['relocations'] = True
            break
        address = int(relocation.address)
        bit_width = int(relocation.size)
        width = bit_width // 8 if bit_width > 0 and bit_width % 8 == 0 else None
        target = int(relocation.target) if isinstance(relocation, lief.MachO.RelocationFixup) else None
        relocations.append(dict(address=address, file_offset=raw.file_offset(address, width or 1), width=width,
                                kind='chained_rebase' if isinstance(relocation, lief.MachO.RelocationFixup) else 'dyld_rebase',
                                type=_enum(relocation.type), pc_relative=bool(relocation.pc_relative), target=target,
                                symbol=relocation.symbol.name if relocation.has_symbol else None,
                                source='LIEF dyld relocation record'))
    for key, collection in (('libraries', raw.libraries), ('sections', raw.sections), ('linkage', linkage)):
        if len(collection) > max_items:
            truncated[key] = True
    for key, value in truncated.items():
        if value:
            raw.warn(key, f'Mach-O {key} capped at {max_items} entries or scan items')
    chained = dict(present=raw.chained_range is not None, binding_count=chained_count, status='absent')
    if raw.chained_range is not None:
        chained['status'] = 'parsed_by_lief' if binary.has_dyld_chained_fixups else 'unavailable'
        if binary.has_dyld_chained_fixups:
            fixups = binary.dyld_chained_fixups
            chained.update(imports_count=int(fixups.imports_count), imports_format=_enum(fixups.imports_format),
                           fixups_version=int(fixups.fixups_version), symbols_format=int(fixups.symbols_format))
            if fixups.imports_count and not chained_count:
                chained['status'] = 'no_bound_slots_returned'
                raw.warn('chained_fixups', 'Chained imports exist but LIEF returned no binding slots; unused imports or unsupported/truncated chains remain unresolved.')
        else:
            raw.warn('chained_fixups', 'LC_DYLD_CHAINED_FIXUPS is unavailable through the supplied LIEF binary; no binding slots invented.')
        if not raw.range(*raw.chained_range, 'chained-fixups payload'):
            raw.partial.add('chained_fixups')
            chained['status'] = 'partial'
    classic_present = any(size for _, size in raw.binding_ranges)
    for offset, size in raw.binding_ranges:
        if size and not raw.range(offset, size, 'dyld binding bytecode'):
            raw.partial.add('dyld_bindings')
    if classic_present and binding_count == chained_count:
        raw.warn('dyld_bindings', 'Dyld binding bytecode is present but LIEF returned no binding records; empty, unsupported or parser-disabled bindings remain unproven.')
    sections = raw.sections[:max_items]
    return dict(header=dict(imagebase=imagebase, bits=raw.bits, endian='little' if raw.endian == '<' else 'big',
                            file_type=_enum(binary.header.file_type), flags=raw.flags, dylib_id=raw.identifier),
                imports=[imports[key] for key in order], exports=exports, libraries=raw.libraries[:max_items],
                relocations=relocations, linkage=linkage[:max_items], sections=sections,
                section_permissions={section['full_name']: section['permissions'] for section in sections},
                warnings=raw.warnings, truncated=truncated,
                availability=dict(dyld_bindings=dict(record_count=binding_count - chained_count, present=classic_present, status='partial' if 'dyld_bindings' in raw.partial else 'parsed_by_lief' if classic_present else 'absent'),
                                  chained_fixups=chained, indirect_symbols=dict(present=raw.dysymtab is not None, entries_examined=indirect_examined),
                                  export_trie=dict(present=bool(raw.export_ranges), status='partial' if 'exports' in raw.partial else 'parsed' if raw.export_ranges else 'absent'),
                                  partial_categories=sorted(raw.partial)),
                assumptions=['Addresses are preferred static VAs; slides and runtime dyld resolution were not observed.',
                             'External import targets remain unknown. Stubs are joined only through exact indirect-symbol indices.',
                             'Segment init_protection supplies section permissions; instruction attributes are separate facts.'])
