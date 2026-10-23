"""Read-only byte ownership and native function-boundary evidence.

An instruction span is a stored fact. A prologue, return or tail-jump pattern
is evidence for a candidate boundary, never proof of a whole function.
"""
from __future__ import annotations

import bisect
import re

_SCAN_BYTES = 4 * 1024 * 1024
_SCAN_CANDIDATES = 4096


def _key(address):
    return f'{address:016x}'


def _hx(address):
    return f'0x{address:x}'


def _position(offset, size):
    if size == 1:
        return 'single'
    return 'begin' if offset == 0 else 'end' if offset == size - 1 else 'part'


def _selector(context):
    return int(context.rsplit('=', 1)[1], 16) if ':cs=' in context else None


def _normalized(instruction):
    return instruction['mnemonic'].lower(), re.sub(r'\s+', '', instruction['operands'].lower())


def _could_start(row):
    """Cheap candidate selection; native decoding still verifies every match."""
    if row['flow'] in ('return', 'jump', 'indirect_jump'):
        return True
    mnemonic, operands = _normalized(row)
    if mnemonic in ('enter', 'endbr32', 'endbr64', 'leave'):
        return True
    if mnemonic in ('push', 'pop'):
        return operands in ('bp', 'ebp', 'rbp')
    if mnemonic == 'mov':
        return operands in ('sp,bp', 'esp,ebp', 'rsp,rbp')
    if mnemonic == 'add':
        return operands.startswith(('sp,', 'esp,', 'rsp,'))
    if mnemonic == 'sub':
        return operands.startswith('sp,sp,')
    return mnemonic in ('stp', 'ldp') and operands.startswith('x29,x30,[sp')


def _pattern_matches(chain, arch):
    """Yield (kind, pattern, instruction count, qualification)."""
    if not chain:
        return
    first = chain[0]
    mnemonic, operands = _normalized(first)
    normalized = [_normalized(item) for item in chain]
    if arch == 'x86':
        frame = [('bp', 'sp'), ('ebp', 'esp'), ('rbp', 'rsp')]
        shift = 1 if mnemonic in ('endbr32', 'endbr64') else 0
        if len(chain) >= shift + 2:
            push, move = normalized[shift:shift + 2]
            if any(push == ('push', bp) and move == ('mov', bp + ',' + sp) for bp, sp in frame):
                yield 'prologue', 'x86_endbr_frame_setup' if shift else 'x86_frame_setup', shift + 2, 'frame setup; may also occur inside a function'
        if mnemonic == 'enter':
            yield 'prologue', 'x86_enter_frame', 1, 'native ENTER frame setup; not a proven function entry'
        if len(chain) >= 2 and chain[1]['flow'] == 'return':
            if mnemonic == 'leave':
                yield 'epilogue', 'x86_leave_return', 2, 'frame teardown followed by a native return'
            elif mnemonic == 'pop' and operands in ('bp', 'ebp', 'rbp'):
                yield 'epilogue', 'x86_pop_frame_return', 2, 'frame-register restoration followed by a native return'
            elif mnemonic == 'add' and operands.startswith(('sp,', 'esp,', 'rsp,')) and first.get('immediates'):
                yield 'epilogue', 'x86_adjust_stack_return', 2, 'constant stack adjustment followed by a native return'
        if len(chain) >= 3 and chain[2]['flow'] == 'return':
            for bp, sp in frame:
                if normalized[0] == ('mov', sp + ',' + bp) and normalized[1] == ('pop', bp):
                    yield 'epilogue', 'x86_restore_frame_return', 3, 'stack/frame restoration followed by a native return'
                elif mnemonic == 'add' and operands.startswith(sp + ',') and normalized[1] == ('pop', bp):
                    yield 'epilogue', 'x86_release_frame_return', 3, 'stack release and frame restoration followed by a native return'
    elif arch == 'arm64':
        def saved_pair(item):
            return item[0] == 'stp' and item[1].startswith('x29,x30,[sp')
        def frame_pointer(item):
            return item == ('mov', 'x29,sp') or (item[0] == 'add' and item[1].startswith('x29,sp,'))
        if len(chain) >= 2 and saved_pair(normalized[0]) and frame_pointer(normalized[1]):
            yield 'prologue', 'arm64_frame_setup', 2, 'frame/link register save and frame-pointer setup'
        if len(chain) >= 3 and mnemonic == 'sub' and operands.startswith('sp,sp,') and saved_pair(normalized[1]) and frame_pointer(normalized[2]):
            yield 'prologue', 'arm64_allocate_frame_setup', 3, 'stack allocation followed by frame/link register setup'
        if mnemonic == 'ldp' and operands.startswith('x29,x30,[sp'):
            if len(chain) >= 2 and chain[1]['flow'] == 'return':
                yield 'epilogue', 'arm64_restore_frame_return', 2, 'frame/link register restoration followed by a native return'
            elif len(chain) >= 3 and normalized[1][0] in ('autiasp', 'autibsp') and chain[2]['flow'] == 'return':
                yield 'epilogue', 'arm64_authenticated_frame_return', 3, 'frame restoration and return authentication'
            elif len(chain) >= 3 and normalized[1][0] == 'add' and normalized[1][1].startswith('sp,sp,') and chain[2]['flow'] == 'return':
                yield 'epilogue', 'arm64_restore_release_return', 3, 'frame restoration and stack adjustment followed by a native return'
    if first['flow'] == 'return':
        yield 'return', 'native_return', 1, 'return instruction; a shared or interior exit is possible'
    if first['flow'] in ('jump', 'indirect_jump'):
        yield 'tail_jump', 'unconditional_jump', 1, 'possible tail exit; may instead be an intra-function branch or dispatch'


class BoundaryMixin:
    def _boundary_address(self, address, cs):
        from .project import number
        if self.meta['format'] == 'MZ':
            return self._dos_parse_address(address, cs)
        if cs is not None:
            raise ValueError('CS selection applies only to DOS MZ projects')
        return number(address), None

    def _boundary_presentation(self, version, address, context=None):
        if self.meta['format'] == 'MZ':
            return self._dos_presentation(version, address, context)
        return self._presentation(version, address)

    def locate(self, address, version=None, cs=None):
        """Describe the queried byte itself, including every stored overlapping span."""
        a, selector = self._boundary_address(address, cs)
        with self.transaction():
            v = self.version(version)['id']
            region = next((r for r in self.regions(v) if r.start <= a < r.start + len(r.data)), None)
            selected = f'x86:16:little:cs={selector:04x}' if selector is not None else None
            params = [v, _key(max(0, a - 14)), _key(a)]
            query = 'SELECT * FROM instructions WHERE version=? AND address>=? AND address<=?'
            if selected is not None:
                query += ' AND context=?'
                params.append(selected)
            spans = []
            for row in self.db.execute(query + ' ORDER BY address,context', params):
                start, size = int(row['address'], 16), row['size']
                if not start <= a < start + size:
                    continue
                context = row['context']
                item = dict(address=_hx(start), end=_hx(start + size - 1), end_exclusive=_hx(start + size),
                            size=size, byte_offset=a - start, position=_position(a - start, size),
                            context=context, bytes=row['bytes'], mnemonic=row['mnemonic'], operands=row['operands'],
                            presentation=self._boundary_presentation(v, start, context))
                code_selector = _selector(context)
                if code_selector is not None:
                    item.update(cs=code_selector, ip=start - code_selector * 16,
                                segmented_address=f'{code_selector:04x}:{start - code_selector * 16:04x}')
                spans.append(item)
            definitions, data = [], []
            for table in ('definitions', 'data_items'):
                for row in self.db.execute(f'SELECT * FROM {table} WHERE version=? AND address<=? ORDER BY address,context', (v, _key(a))):
                    start, size = int(row['address'], 16), row['size']
                    if not start <= a < start + size:
                        continue
                    item = dict(address=_hx(start), end=_hx(start + size - 1), end_exclusive=_hx(start + size),
                                size=size, byte_offset=a - start, position=_position(a - start, size),
                                representation=row['representation'], context=row['context'],
                                presentation=self._boundary_presentation(v, start),
                                source='explicit definition' if table == 'definitions' else row['source'])
                    if table == 'definitions':
                        definitions.append(item)
                    elif not any(d['address'] == item['address'] for d in definitions):
                        data.append(item)
            explicit_data = [item for item in definitions if item['representation'] not in ('code', 'unexplored')]
            data = explicit_data + data
            held = any(item['representation'] == 'unexplored' for item in definitions)
            code = bool(spans) or any(item['representation'] == 'code' for item in definitions)
            classification = 'outside' if region is None else 'unexplored' if held else 'code' if code else 'data' if data else 'unexplored'
            owner = (definitions or data or spans)
            presentation = owner[0]['presentation'] if owner else self._boundary_presentation(v, a, selected)
            return dict(version=v, address=_hx(a), requested_context=selected, mapped=region is not None,
                        classification=classification, held=held, decoded=bool(spans),
                        overlap=len(spans) > 1 or len(data) > 1 or bool(spans and data), presentation=presentation,
                        byte=f'{region.data[a - region.start]:02x}' if region else None,
                        region=dict(name=region.name, address=_hx(region.start), end_exclusive=_hx(region.start + len(region.data))) if region else None,
                        instructions=spans, definitions=definitions, data=data,
                        note='End is the final included byte; end_exclusive is the following address. No bytes were decoded by locate.')

    def function_patterns(self, version=None, limit=200, offset=0, scan_unexplored=False):
        """Return native pattern evidence without changing analysis or scheduling work."""
        from .project import integer
        from .decoder import decode
        from .dos_decoder import decode_dos
        limit = integer(limit, 'limit', 1, 10000)
        offset = integer(offset, 'offset', 0, (1 << 63) - 1)
        if not isinstance(scan_unexplored, bool):
            raise ValueError('scan_unexplored must be a boolean')
        with self.transaction():
            v = self.version(version)['id']
            regions = self.regions(v)
            rows = self.db.execute('SELECT * FROM instructions WHERE version=? ORDER BY address,context', (v,)).fetchall()
            stored = {(row['context'], int(row['address'], 16)): row for row in rows}
            function_entries = {(row['context'], int(row['address'], 16)) for row in self.db.execute('SELECT context,address FROM functions WHERE version=?', (v,))}
            cache, evidence, seen = {}, [], set()
            warnings = []
            dos = self.meta['format'] == 'MZ'

            def current_bytes(a, size=15):
                region = next((r for r in regions if r.start <= a < r.start + len(r.data)), None)
                return region.data[a - region.start:a - region.start + size] if region else b''

            def native(context, a, raw=False):
                identity = (context, a, raw)
                if identity in cache:
                    return cache[identity]
                row = stored.get((context, a))
                if not raw and row is None:
                    return None
                source = current_bytes(a)
                if not raw and source[:row['size']].hex() != row['bytes']:
                    cache[identity] = None
                    return None
                if dos:
                    selector = _selector(context)
                    ins = decode_dos(source, a, selector) if selector is not None and 0 <= a - selector * 16 <= 0xFFFF else None
                else:
                    ins = decode(source, a, self.arch, self.bits)
                if ins is not None and not raw and ins['size'] != row['size']:
                    ins = None
                cache[identity] = ins
                return ins

            def chain(context, a, raw=False):
                result = []
                for _ in range(4):
                    item = native(context, a, raw)
                    if item is None:
                        break
                    result.append(item)
                    following = item.get('next_address', a + item['size'])
                    if following < a or item['flow'] in ('return', 'jump', 'indirect_jump', 'stop'):
                        break
                    a = following
                return result

            def emit(context, a, instructions, raw=False, allowed=None):
                for kind, pattern, length, qualification in _pattern_matches(instructions, self.arch):
                    if raw and kind not in ('prologue', 'epilogue'):
                        continue
                    identity = (context, a, kind, pattern)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    items = instructions[:length]
                    if allowed is not None and not all(allowed(pos) for ins in items
                                                       for pos in range(ins['address'], ins['address'] + ins['size'])):
                        continue
                    end = items[-1]['address'] + items[-1]['size']
                    item = dict(kind=kind, pattern=pattern, status='candidate', qualification=qualification,
                                address=_hx(a), end_exclusive=_hx(end), context=context,
                                source='unexplored_bytes' if raw else 'stored_instructions',
                                function_entry_known=(context, a) in function_entries,
                                presentation=self._boundary_presentation(v, a, context),
                                instructions=[dict(address=_hx(ins['address']), bytes=ins['bytes'],
                                                   mnemonic=ins['mnemonic'], operands=ins['operands'], size=ins['size']) for ins in items])
                    if dos:
                        selector = _selector(context)
                        item.update(cs=selector, segmented_address=f'{selector:04x}:{a - selector * 16:04x}',
                                    context_status='candidate' if raw else 'stored')
                    evidence.append(item)

            for row in rows:
                if not _could_start(row):
                    continue
                a = int(row['address'], 16)
                emit(row['context'], a, chain(row['context'], a))

            scan = dict(requested=scan_unexplored, scanned_bytes=0, candidate_checks=0,
                        byte_limit=_SCAN_BYTES, candidate_limit=_SCAN_CANDIDATES, partial=False)
            if scan_unexplored:
                intervals = [(int(row['address'], 16), int(row['address'], 16) + row['size']) for row in rows]
                intervals += [(int(row['address'], 16), int(row['address'], 16) + row['size'])
                              for row in self.db.execute('SELECT address,size FROM definitions WHERE version=?', (v,))]
                intervals += [(int(row['address'], 16), int(row['address'], 16) + row['size'])
                              for row in self.db.execute('SELECT address,size FROM data_items WHERE version=?', (v,))]
                merged = []
                for low, high in sorted(intervals):
                    if merged and low <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
                    else:
                        merged.append((low, high))
                lows = [item[0] for item in merged]

                def unexplored(a):
                    index = bisect.bisect_right(lows, a) - 1
                    return index < 0 or not merged[index][0] <= a < merged[index][1]

                contexts = [row[0] for row in self.db.execute('SELECT selector FROM dos_segments WHERE version=? ORDER BY selector', (v,))] if dos else []
                prefix = re.compile(rb'\x55(?:\x48(?:\x89\xe5|\x8b\xec)|\x89\xe5|\x8b\xec)|\xc8...|\xc9[\xc3\xcb]|\x5d[\xc3\xcb]', re.DOTALL)
                stopped = False
                for region in regions:
                    if not region.executable:
                        continue
                    available = _SCAN_BYTES - scan['scanned_bytes']
                    if available <= 0:
                        scan['partial'] = True
                        break
                    data = region.data[:available]
                    scan['scanned_bytes'] += len(data)
                    if len(data) < len(region.data):
                        scan['partial'] = True
                    if self.arch == 'x86':
                        candidates = (match.start() for match in prefix.finditer(data))
                    else:
                        aligned = (-region.start) % 4
                        candidates = (i for i in range(aligned, len(data) - 3, 4)
                                      if int.from_bytes(data[i:i + 4], 'little') & 0x7FFF == 0x7BFD)
                    for index in candidates:
                        a = region.start + index
                        if not unexplored(a):
                            continue
                        choices = [f'x86:16:little:cs={selector:04x}' for selector in contexts
                                   if 0 <= a - selector * 16 <= 0xFFFF] if dos else [self.context]
                        for context in choices:
                            if scan['candidate_checks'] >= _SCAN_CANDIDATES:
                                scan['partial'], stopped = True, True
                                break
                            scan['candidate_checks'] += 1
                            instructions = chain(context, a, raw=True)
                            # Only the matched sequence, rather than speculative
                            # lookahead, must lie wholly in unexplored bytes.
                            emit(context, a, instructions, raw=True, allowed=unexplored)
                        if stopped:
                            break
                    if stopped:
                        break
                if dos:
                    warnings.append('Raw DOS patterns use candidate CS windows; candidate context and bytes do not establish executable code.')
                if scan['partial']:
                    warnings.append('Optional unexplored-byte scan reached its bounded scope; candidate coverage is partial.')
            evidence.sort(key=lambda item: (int(item['address'], 16), item['context'], item['kind'], item['pattern']))
            return dict(version=v, items=evidence[offset:offset + limit], total=len(evidence), offset=offset,
                        has_more=offset + limit < len(evidence), scan=scan, warnings=warnings,
                        note='Pattern matches are candidate evidence. Returns and jumps do not prove function ends; no facts or queues were changed.')
