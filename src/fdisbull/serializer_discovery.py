"""Read-only discovery of x86-32 serializers from loaded filename anchors.

This stage needs memory ranges, not a project-to-runtime module mapping or a
known serializer ABI. It scans the *loaded* bytes, so a COM launcher project can
investigate its DOS extender's executable without pretending the launcher owns
that code. Results are candidates for one breakpoint / changed-file experiment,
not permission to call arbitrary code. No target names or addresses are built in.
"""
from collections import defaultdict
import re
import struct

import capstone as cs
from capstone import x86_const as x86

from .serializer_candidates import REGISTERS, _ALIASES


_FILENAME = re.compile(rb'[A-Za-z0-9_./\\:-]{1,120}\.[A-Za-z0-9]{1,8}\x00')
_PROLOGUE = re.compile(rb'(?:\x55\x89\xe5|\x55\x8b\xec|[\x50-\x57]{3,8}(?:\x83\xec.|\x81\xec....))', re.DOTALL)
_ARGUMENT_REGS = ('eax', 'edx', 'ebx', 'ecx')


def _number(value, name, low=0, high=0xffffffff):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _ranges(ranges, max_bytes):
    if not isinstance(ranges, (list, tuple)) or not 1 <= len(ranges) <= 128:
        raise ValueError('ranges must contain 1..128 half-open ranges')
    result = []
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('each range must be [start,end)')
        start, end = pair
        _number(start, 'range start'); _number(end, 'range end', 1, 0x100000000)
        if start >= end:
            raise ValueError('range must be nonempty')
        result.append((start, end))
    result.sort()
    if any(a[1] > b[0] for a, b in zip(result, result[1:])):
        raise ValueError('ranges must not overlap')
    if sum(b-a for a, b in result) > max_bytes:
        raise ValueError('ranges exceed max_bytes')
    return result


def _snapshot(read_bytes, ranges):
    chunks, issues = [], []
    for start, end in ranges:
        parts, part_start = [], start
        for address in range(start, end, 65536):
            size = min(end-address, 65536)
            try:
                raw = read_bytes(address, size)
                if not isinstance(raw, bytes) or len(raw) != size:
                    raise ValueError('short or non-byte read')
            except Exception as error:
                if parts:
                    chunks.append((part_start, b''.join(parts))); parts = []
                issues.append({'address': address, 'length': size,
                               'reason': 'memory read failed: '+type(error).__name__})
                part_start = address+size
                continue
            parts.append(raw)
        if parts:
            chunks.append((part_start, b''.join(parts)))
    return chunks, issues


def _reader(chunks):
    def read(address, size):
        for start, raw in chunks:
            if start <= address and address+size <= start+len(raw):
                return raw[address-start:address-start+size]
        raise ValueError('outside acquired snapshot')
    return read


def _decoder():
    decoder = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_32)
    decoder.detail = True
    return decoder


def _filename_suffixes(text, wanted):
    """Keep plausible C-string starts inside one printable filename run.

    The regex cannot distinguish a path from preceding printable data. Code may
    point at a slash, component, or pooled suffix rather than the regex's first
    byte. Prefer those starts, then retain remaining valid path-prefix suffixes;
    an exact requested basename also works when garbage is attached directly.
    These are pointer-search candidates, not newly asserted filesystem names.
    """
    separators = [i for i, char in enumerate(text) if char in '/\\']
    starts = [0]
    for index in separators:
        starts.extend((index, index+1))
    if wanted is not None:
        lower = text.casefold()
        starts.extend(len(text)-len(name) for name in sorted(wanted)
                      if lower.endswith(name))
    if separators:
        starts.extend(range(1, separators[-1]+1))
    seen = set()
    for start in starts:
        if start in seen or start >= len(text):
            continue
        seen.add(start)
        suffix = text[start:]
        if _FILENAME.fullmatch(suffix.encode('ascii')+b'\0') is None:
            continue
        yield start, suffix


def _instruction(ins):
    return {'address': ins.address, 'size': ins.size, 'bytes': bytes(ins.bytes).hex(),
            'mnemonic': ins.mnemonic, 'operands': ins.op_str}


def _target(ins):
    return (ins.operands[0].imm & 0xffffffff
            if ins.group(cs.CS_GRP_CALL) and len(ins.operands) == 1
            and ins.operands[0].type == x86.X86_OP_IMM else None)


def _register_facts(instructions, anchor_addresses):
    """Deliberately local hypotheses; flow-qualified facts use the extractor."""
    regs = {'esp': {'kind': 'stack', 'offset': 0}}
    calls, definitions = [], {}

    def value(ins, operand):
        if operand.type == x86.X86_OP_IMM:
            address = operand.imm & 0xffffffff
            return {'kind': 'constant', 'value': address}
        if operand.type == x86.X86_OP_REG and operand.size == 4:
            return regs.get(ins.reg_name(operand.reg))
        if operand.type == x86.X86_OP_MEM and operand.size == 4:
            m = operand.mem
            if not m.base and not m.index:
                return {'kind': 'pointer_global', 'address': m.disp & 0xffffffff}
        return None

    for ins in instructions:
        operands = ins.operands
        if ins.group(cs.CS_GRP_CALL):
            target = _target(ins)
            if target is not None:
                calls.append({'callsite': ins.address, 'target': target,
                              'registers': {r: dict(v) for r, v in regs.items()},
                              'definitions': dict(definitions)})
            regs = {'esp': regs['esp']} if 'esp' in regs else {}
            definitions = {}
            continue
        before = dict(regs)
        src = value(ins, operands[1]) if len(operands) == 2 else None
        for written in ins.regs_access()[1]:
            reg = _ALIASES.get(ins.reg_name(written))
            regs.pop(reg, None); definitions.pop(reg, None)
        if ins.mnemonic == 'push':
            if before.get('esp', {}).get('kind') == 'stack':
                regs['esp'] = {'kind': 'stack', 'offset': before['esp']['offset']-4}
        elif ins.mnemonic == 'pop':
            if before.get('esp', {}).get('kind') == 'stack':
                regs['esp'] = {'kind': 'stack', 'offset': before['esp']['offset']+4}
        if len(operands) != 2 or operands[0].type != x86.X86_OP_REG or operands[0].size != 4:
            continue
        dest = ins.reg_name(operands[0].reg)
        if ins.mnemonic == 'lea' and operands[1].type == x86.X86_OP_MEM:
            m = operands[1].mem
            base = before.get(ins.reg_name(m.base)) if m.base else None
            if not m.base and not m.index:
                src = {'kind': 'constant', 'value': m.disp & 0xffffffff}
            elif not m.index and base and base['kind'] in ('stack', 'constant'):
                key = 'offset' if base['kind'] == 'stack' else 'value'
                src = {'kind': base['kind'], key: base[key]+m.disp}
        elif ins.mnemonic in ('add', 'sub') and operands[1].type == x86.X86_OP_IMM:
            old = before.get(dest)
            if old and old['kind'] in ('stack', 'constant'):
                key = 'offset' if old['kind'] == 'stack' else 'value'
                src = {'kind': old['kind'], key: old[key]+operands[1].imm*(1 if ins.mnemonic == 'add' else -1)}
        elif ins.mnemonic not in ('mov', 'lea'):
            src = None
        if src is not None:
            regs[dest] = dict(src); definitions[dest] = ins.address
    return calls


def _filename_reference_sites(instructions, chunks):
    """Find path-literal boundaries even for filenames outside the user filter.

    This reads only the existing snapshot. A later filename used to construct a
    path breaks a proximity-based association with the preceding filename.
    These linear sites are still candidates, not control-flow or string-copy
    proofs; exact argument-pointer hypotheses are handled separately.
    """
    sites = []
    for ins in instructions:
        if ins.mnemonic not in ('mov', 'lea', 'push'):
            continue
        addresses = set()
        for operand in ins.operands:
            if operand.type == x86.X86_OP_IMM:
                addresses.add(operand.imm & 0xffffffff)
            elif operand.type == x86.X86_OP_MEM and not operand.mem.base and not operand.mem.index:
                addresses.add(operand.mem.disp & 0xffffffff)
        for address in sorted(addresses):
            for base, raw in chunks:
                if base <= address < base+len(raw):
                    offset = address-base
                    match = _FILENAME.match(raw, offset, min(offset+130, len(raw)))
                    if match:
                        text = match.group()[:-1].decode('ascii')
                        sites.append({'address': ins.address, 'pointer': address, 'text': text,
                                      'basename': text.replace('\\', '/').rsplit('/', 1)[-1].casefold()})
                    break
    return sites


def _abi_hypotheses(call, filename, expected_size, ranges):
    regs, definitions = call['registers'], call['definitions']
    def mapped(number):
        return any(start <= number < end for start, end in ranges)
    filenames, buffers, lengths = [], [], []
    for reg in _ARGUMENT_REGS:
        fact = regs.get(reg, {})
        if fact.get('kind') == 'stack' or fact.get('kind') == 'constant' and fact.get('value') == filename['address']:
            filenames.append(reg)
        if fact.get('kind') == 'pointer_global' or fact.get('kind') == 'constant' and mapped(fact.get('value', -1)) and fact.get('value') != filename['address']:
            buffers.append(reg)
        if expected_size is not None and fact.get('kind') == 'constant' and fact.get('value') == expected_size:
            lengths.append(reg)
    result = []
    for name_reg in sorted(filenames, key=lambda r: definitions.get(r, 0), reverse=True):
        for buffer_reg in buffers:
            if name_reg == buffer_reg:
                continue
            for length_reg in lengths or [None]:
                if length_reg in (name_reg, buffer_reg):
                    continue
                spec = {'entry': call['target'], 'filename': name_reg, 'buffer': buffer_reg}
                if length_reg:
                    spec['length'] = length_reg
                result.append({'registers': spec,
                               'operation_candidate': 'write' if length_reg else 'read',
                               'basis': ('length register matches selected file size; direction still requires callee or event evidence'
                                         if length_reg else 'filename/buffer register pair without recovered byte count; direction unresolved'),
                               'qualified': False})
    return result


def discover_serializer_calls(read_bytes, *, ranges, filenames=None, file_sizes=None,
                              code_ranges=None, max_bytes=16*1024*1024,
                              max_anchors=256, max_xrefs=2048,
                              call_window=512, function_lookback=8192):
    """Find filename users, caller candidates and register ABI hypotheses.

    ``ranges`` identify acquired linear32 RAM. Optional ``code_ranges`` restrict
    code searching without requiring a file mapping. ``filenames`` are basename
    filters; ``file_sizes`` maps those names to observed disk sizes. Pass the
    names/sizes of a *single identified save or handoff inventory*, not a merged
    list from different runs. Reads are chunked to at most 64 KiB and retained for
    this call; output contains compact evidence, never a duplicate RAM image.

    The recognized entry patterns and linear local register summaries are
    hypotheses. The existing serializer extractor performs subsequent bounded
    control-flow analysis after the caller and ABI have been selected.
    """
    if not callable(read_bytes):
        raise ValueError('read_bytes must be callable')
    _number(max_bytes, 'max_bytes', 1, 64*1024*1024)
    _number(max_anchors, 'max_anchors', 1, 4096)
    _number(max_xrefs, 'max_xrefs', 1, 16384)
    _number(call_window, 'call_window', 32, 4096)
    _number(function_lookback, 'function_lookback', 32, 65536)
    ranges = _ranges(ranges, max_bytes)
    code_ranges = _ranges(code_ranges or ranges, max_bytes)
    if any(not any(a <= start and end <= b for a, b in ranges) for start, end in code_ranges):
        raise ValueError('code_ranges must be contained in acquired ranges')
    if filenames is not None and (not isinstance(filenames, (list, tuple)) or not all(isinstance(s, str) and s for s in filenames)):
        raise ValueError('filenames must be a list of nonempty names')
    def basename(name):
        return name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
    wanted = {basename(s) for s in filenames} if filenames is not None else None
    if file_sizes is not None and not isinstance(file_sizes, dict):
        raise ValueError('file_sizes must map filenames to observed sizes')
    sizes = {}
    for name, size in (file_sizes or {}).items():
        if not isinstance(name, str) or not name:
            raise ValueError('file size keys must be names')
        sizes[basename(name)] = _number(size, 'file size', 0, 0xffffffff)
    chunks, issues = _snapshot(read_bytes, ranges)
    snapshot_read = _reader(chunks)
    decoder = _decoder()
    anchors, anchor_addresses, limited = [], set(), False
    for start, raw in chunks:
        for match in _FILENAME.finditer(raw):
            text = match.group()[:-1].decode('ascii')
            match_address = start+match.start()
            for offset, suffix in _filename_suffixes(text, wanted):
                name = basename(suffix)
                if wanted is not None and name not in wanted:
                    continue
                address = match_address+offset
                if address in anchor_addresses:
                    continue
                if len(anchors) >= max_anchors:
                    limited = True; break
                anchor_addresses.add(address)
                anchors.append({'address': address, 'text': suffix,
                                'basename': name, 'expected_size': sizes.get(name),
                                'anchor_basis': 'full printable match' if offset == 0 else 'candidate string suffix',
                                'source_match': {'address': match_address, 'text': text}})
            if limited:
                break
    code_chunks = []
    for lo, hi in code_ranges:
        for base, raw in chunks:
            start, end = max(lo, base), min(hi, base+len(raw))
            if start < end:
                code_chunks.append((start, raw[start-base:end-base]))
    xrefs = []
    for anchor in anchors:
        needle = struct.pack('<I', anchor['address'])
        for base, raw in code_chunks:
            pos = raw.find(needle)
            while pos >= 0:
                for candidate in range(max(0, pos-10), pos):
                    ins = next(decoder.disasm(raw[candidate:pos+19], base+candidate, count=1), None)
                    if ins is None or not (ins.address <= base+pos and ins.address+ins.size >= base+pos+4):
                        continue
                    if ins.mnemonic not in ('mov', 'lea', 'push'):
                        continue
                    matches = [op for op in ins.operands if op.type == x86.X86_OP_IMM and op.imm & 0xffffffff == anchor['address']
                               or op.type == x86.X86_OP_MEM and not op.mem.base and not op.mem.index and op.mem.disp & 0xffffffff == anchor['address']]
                    if not matches:
                        continue
                    if len(xrefs) >= max_xrefs:
                        limited = True; break
                    xrefs.append({'filename': anchor, 'instruction': _instruction(ins),
                                  'alignment': 'candidate instruction containing exact relocated pointer'})
                if len(xrefs) >= max_xrefs:
                    break
                pos = raw.find(needle, pos+1)
    # Prefix candidates sometimes decode the same final operand in two ways.
    unique = {}
    for ref in xrefs:
        key = (ref['instruction']['address'], ref['filename']['address'])
        unique[key] = ref
    xrefs = sorted(unique.values(), key=lambda r: r['instruction']['address'])
    calls = {}
    functions = {}
    for ref in xrefs:
        address = ref['instruction']['address']
        for base, raw in code_chunks:
            if base <= address < base+len(raw):
                break
        offset = address-base
        prologues = list(_PROLOGUE.finditer(raw, max(0, offset-function_lookback), offset+1))
        entry = base+prologues[-1].start() if prologues else address
        if entry not in functions or address >= functions[entry]['end']:
            # One branch can return before a later filename-using branch of the
            # same function. Grow the cached span to cover each new anchor;
            # otherwise that anchor is attributed to a range excluding itself
            # and its serializer call never reaches the flow-aware extractor.
            filenames_seen = functions.get(entry, {}).get('filenames', set())
            stop = min(len(raw), entry-base+65536)
            instructions = []
            for ins in decoder.disasm(raw[entry-base:stop], entry):
                instructions.append(ins)
                if ins.address >= address and ins.group(cs.CS_GRP_RET):
                    break
                # Another common prologue after the anchor likely starts a new function.
                if ins.address > address and _PROLOGUE.match(raw, ins.address-base):
                    instructions.pop(); break
            end = instructions[-1].address+instructions[-1].size if instructions else entry
            if end <= entry:
                continue
            functions[entry] = {'entry': entry, 'end': end, 'entry_basis': 'recognized prologue candidate' if prologues else 'filename reference; enclosing entry unresolved',
                                'signature_hex': raw[entry-base:min(entry-base+24, len(raw))].hex(),
                                'filenames': filenames_seen, 'instructions': instructions,
                                'filename_sites': _filename_reference_sites(instructions, chunks),
                                'calls': _register_facts(instructions, {a['address'] for a in anchors})}
        function = functions[entry]
        function['filenames'].add(ref['filename']['basename'])
        for call in function['calls']:
            if not address <= call['callsite'] <= address+call_window:
                continue
            direct = any(fact.get('kind') == 'constant' and fact.get('value') == ref['filename']['address']
                         for reg, fact in call['registers'].items() if reg in _ARGUMENT_REGS)
            preceding = [site for site in function['filename_sites']
                         if address < site['address'] <= call['callsite']]
            if preceding and preceding[-1]['basename'] != ref['filename']['basename'] and not direct:
                # A selected file's literal is not evidence for a later file's
                # buffer merely because both calls fit the distance window.
                continue
            key = (call['callsite'], ref['filename']['basename'])
            if key in calls and calls[key]['filename_reference'] > address:
                continue
            hyp = _abi_hypotheses(call, ref['filename'], ref['filename']['expected_size'], ranges)
            excerpt = [i for i in function['instructions'] if call['callsite']-48 <= i.address <= call['callsite']]
            calls[key] = {**call, 'filename': ref['filename']['basename'],
                          'filename_reference': address, 'caller_entry_candidate': entry,
                          'caller_range': [entry, function['end']], 'abi_hypotheses': hyp,
                          'filename_relation': ('argument-pointer candidate' if direct else
                                                'nearest preceding filename-reference candidate; path construction unproved'),
                          'argument_evidence': [_instruction(i) for i in excerpt],
                          'facts_kind': 'linear local hypotheses; joins and reachability not qualified'}
    grouped = defaultdict(list)
    for call in calls.values():
        # Earlier calls may have been recorded before a later branch extended
        # this function. Keep all public descriptions of its span consistent.
        function = functions[call['caller_entry_candidate']]
        call['caller_range'] = [function['entry'], function['end']]
        grouped[call['target']].append(call)
    targets = []
    for entry, members in grouped.items():
        by_abi = defaultdict(list)
        for member in members:
            for hypothesis in member['abi_hypotheses']:
                key = tuple(sorted(hypothesis['registers'].items()))
                by_abi[key].append(member)
        guesses = []
        for key, support in sorted(by_abi.items(), key=lambda item: -len({m['filename'] for m in item[1]})):
            spec = dict(key)
            guesses.append({'registers': spec, 'filename_support': sorted({m['filename'] for m in support}),
                            'operation_candidate': 'write' if 'length' in spec else 'read',
                            'qualified': False})
        try:
            entry_excerpt = [_instruction(i) for i in decoder.disasm(snapshot_read(entry, 128), entry, count=24)]
        except ValueError:
            entry_excerpt = []
        targets.append({'entry': entry, 'entry_excerpt': entry_excerpt, 'filename_count': len({m['filename'] for m in members}),
                        'filenames': sorted({m['filename'] for m in members}),
                        'callsite_count': len({m['callsite'] for m in members}),
                        'abi_hypotheses': guesses,
                        'next_probe': {'address': entry, 'purpose': 'break at one original file event and inspect filename/buffer arguments; select operation from observed read/write or callee semantics',
                                       'requires': ['actual protected code selector', 'original UI event or qualified caller', 'matching argument and return context']}})
    targets.sort(key=lambda t: (-t['filename_count'], -t['callsite_count'], t['entry']))
    users = _caller_users(code_chunks, set(functions), decoder)
    published_functions = []
    for function in sorted(functions.values(), key=lambda f: f['entry']):
        published_functions.append({key: value for key, value in function.items() if key not in ('instructions', 'calls', 'filenames', 'filename_sites')}
                                   | {'filenames': sorted(function['filenames']),
                                      'entry_input_register_candidates': _entry_inputs(function['instructions']),
                                      'caller_users': users.get(function['entry'], [])})
    return {'format': 'fdisbull-serializer-discovery-1', 'address_space': 'live linear32',
            'status': 'budget_stop' if limited else 'partial' if issues else 'candidates_ready',
            'ranges': [list(p) for p in ranges], 'code_ranges': [list(p) for p in code_ranges],
            'anchors': anchors, 'references': xrefs, 'callers': published_functions,
            'serializer_targets': targets, 'calls': sorted(calls.values(), key=lambda c: (c['callsite'], c['filename'])),
            'issues': issues,
            'next_step': 'Inspect highest filename-count target and one original event; pass selected caller ranges and accepted ABI to serializer-candidates. Each enclosing caller lists direct caller_users and return addresses: inspect one to recover the directory argument and parent continuation. Qualify native entry/boundary/continuation separately.',
            'scope': 'loaded-byte candidates independent of launcher mapping; no automatic safe native call or source-file identity claim'}



def _entry_inputs(instructions):
    defined, inputs = set(), set()
    for ins in instructions:
        if ins.group(cs.CS_GRP_CALL) or ins.group(cs.CS_GRP_RET):
            break
        reads, writes = ins.regs_access()
        # PUSH saves do not imply arguments; their values are restored on return.
        if ins.mnemonic not in ('push', 'pop'):
            for reg_id in reads:
                reg = _ALIASES.get(ins.reg_name(reg_id))
                if reg in REGISTERS-{'esp', 'ebp'} and reg not in defined:
                    inputs.add(reg)
        defined |= {_ALIASES.get(ins.reg_name(r)) for r in writes}
    return sorted(inputs)


def _caller_users(code_chunks, entries, decoder, max_users=256):
    """Direct-call anchors are cheap even without a whole-module traversal."""
    users = defaultdict(list)
    count = 0
    for base, raw in code_chunks:
        offset = raw.find(b'\xe8')
        while offset >= 0:
            if offset+5 > len(raw):
                break
            target = (base+offset+5+struct.unpack_from('<i', raw, offset+1)[0]) & 0xffffffff
            if target in entries:
                prologues = list(_PROLOGUE.finditer(raw, max(0, offset-8192), offset+1))
                start = prologues[-1].start() if prologues else offset
                decoded = list(decoder.disasm(raw[start:min(offset+160, len(raw))], base+start))
                call = next((i for i in decoded if i.address == base+offset and _target(i) == target), None)
                # A relative-call bit pattern inside a different decoded instruction
                # remains a search lead, never a qualified original call boundary.
                aligned = call is not None
                if aligned:
                    facts = next((c for c in _register_facts(decoded, set()) if c['callsite'] == base+offset), {})
                    prior = [i for i in decoded if i.address < base+offset][-12:]
                    after = [i for i in decoded if i.address >= base+offset][:13]
                    edges = [{'address': i.address, 'target': i.operands[0].imm & 0xffffffff}
                             for i in decoded if i.group(cs.CS_GRP_JUMP) and len(i.operands) == 1
                             and i.operands[0].type == x86.X86_OP_IMM
                             and (i.operands[0].imm & 0xffffffff) < i.address]
                else:
                    facts, prior, after, edges = {}, [], [], []
                users[target].append({'callsite': base+offset, 'return_address': base+offset+5,
                                      'parent_entry_candidate': base+start if prologues else None,
                                      'alignment': 'decoded from parent prologue candidate' if aligned and prologues else 'direct-call byte candidate',
                                      'register_hypotheses': facts.get('registers', {}),
                                      'before': [_instruction(i) for i in prior],
                                      'after': [_instruction(i) for i in after],
                                      'nearby_backward_edges': edges,
                                      'next_probe': 'At the actual protected selector, stop at this callsite during one original named Save/Load action. Inspect directory argument and stack return; use return_address to observe the parent continuation. A repeating parent loop can supply a separate non-reentrant native-call boundary.'})
                count += 1
                if count >= max_users:
                    return users
            offset = raw.find(b'\xe8', offset+1)
    return users


def _le_objects(source):
    """Read LE enumerated object pages for matching, without applying fixups.

    Unlike the strict analysis loader this does not present an executable image.
    Selector fixups may exist: signatures mask operands, and results explicitly
    identify source windows rather than claiming a fully relocated byte image.
    """
    from .le import _header_offset, _range, _HEADER_FIELDS, HEADER_SIZE, PAGE_SIZE, MAX_OBJECTS, MAX_PAGES
    header = _header_offset(source)
    raw = _range(source, header, HEADER_SIZE, 'header')
    if raw[2:4] != b'\0\0' or struct.unpack_from('<I', raw, 4)[0] != 0:
        raise ValueError('module matching requires little-endian LE level zero')
    if struct.unpack_from('<H', raw, 8)[0] not in (2, 3):
        raise ValueError('module matching requires i386/486 LE')
    fields = dict(zip(_HEADER_FIELDS, struct.unpack_from('<41I', raw, 12)))
    count, pages = fields['object_count'], fields['num_pages']
    if not 1 <= count <= MAX_OBJECTS or not 1 <= pages <= MAX_PAGES or fields['page_size'] != PAGE_SIZE:
        raise ValueError('LE object/page geometry is unsupported')
    object_table = header+fields['object_table_offset']
    page_table = header+fields['page_map_offset']
    _range(source, object_table, count*24, 'object table')
    page_map = _range(source, page_table, pages*4, 'page map')
    physical_last = max((int.from_bytes(page_map[i:i+3], 'big') for i in range(0, len(page_map), 4) if page_map[i+3] == 0), default=0)
    if not 1 <= fields['last_page_size'] <= PAGE_SIZE:
        raise ValueError('LE last page size is unsupported')
    result, total = [], 0
    for index in range(count):
        size, preferred, flags, first, count_pages, _ = struct.unpack_from('<6I', source, object_table+index*24)
        total += size
        if not 1 <= size <= 64*1024*1024 or total > 64*1024*1024 or not flags & 0x2000:
            raise ValueError('LE object exceeds matching budget or is not 32-bit')
        if not 1 <= first <= pages+1 or first-1+count_pages > pages or count_pages > (size+PAGE_SIZE-1)//PAGE_SIZE:
            raise ValueError('LE object page range is invalid')
        payload = bytearray(size)
        file_windows = []
        for local in range(count_pages):
            page = page_map[(first-1+local)*4:(first+local)*4]
            physical, kind = int.from_bytes(page[:3], 'big'), page[3]
            capacity = min(PAGE_SIZE, size-local*PAGE_SIZE)
            if kind == 3 and physical == 0:
                continue
            if kind != 0 or not 1 <= physical <= pages:
                raise ValueError('LE matching supports only enumerated or zero-fill pages')
            stored_size = fields['last_page_size'] if physical == physical_last else PAGE_SIZE
            file_offset = fields['data_pages_offset']+(physical-1)*PAGE_SIZE
            stored = _range(source, file_offset, stored_size, 'enumerated page')
            amount = min(capacity, stored_size)
            payload[local*PAGE_SIZE:local*PAGE_SIZE+amount] = stored[:amount]
            file_windows.append({'object_offset': local*PAGE_SIZE, 'file_offset': file_offset, 'length': amount})
        result.append({'index': index+1, 'preferred_address': preferred, 'size': size,
                       'executable': bool(flags & 4), 'bytes': bytes(payload),
                       'file_windows': file_windows})
    return result


def _signature(decoder, raw, offset, size=80):
    part = raw[offset:offset+size]
    mask = bytearray(b'\xff'*len(part))
    decoded = 0
    for ins in decoder.disasm(part, offset):
        if ins.mnemonic in ('ret', 'retf'):
            break
        decoded = ins.address+ins.size-offset
        # Relocated pointers and selectors can appear in displacement/immediate
        # fields; matching only structural opcode/register bytes avoids an LE
        # fixup-profile dependency. Relative call immediates are also masked.
        for start, length in ((ins.disp_offset, ins.disp_size), (ins.imm_offset, ins.imm_size)):
            if length:
                local = ins.address-offset+start
                mask[local:local+length] = b'\0'*length
    part, mask = part[:decoded], bytes(mask[:decoded])
    if len(part) < 24 or sum(bool(b) for b in mask) < 16:
        return None
    runs = list(re.finditer(b'\xff+', mask))
    longest = max(runs, key=lambda m: m.end()-m.start())
    if longest.end()-longest.start() < 4:
        return None
    return part, mask, longest.start(), longest.end()


def map_le_module(read_bytes, *, source_bytes, ranges, max_bytes=16*1024*1024,
                  max_signatures=24):
    """Locate executable LE objects in live RAM using dispersed masked windows.

    This is a discovery mapping, not a source binding. At least two distinct
    source windows must agree on one object base before ``supported_candidate``
    is returned. Each hit includes source offsets and observed live addresses;
    candidates from shared library code can remain ambiguous. Caller can use
    resulting code ranges for discovery without rebinding the launcher FDB.
    """
    if not callable(read_bytes):
        raise ValueError('read_bytes must be callable')
    _number(max_bytes, 'max_bytes', 1, 64*1024*1024)
    _number(max_signatures, 'max_signatures', 2, 256)
    ranges = _ranges(ranges, max_bytes)
    objects = _le_objects(source_bytes)
    chunks, issues = _snapshot(read_bytes, ranges)
    decoder = _decoder()
    results = []
    for obj in objects:
        if not obj['executable']:
            continue
        raw = obj['bytes']
        starts = [m.start() for m in _PROLOGUE.finditer(raw)]
        # Spread windows through the object; a repeated local helper should not
        # become an apparently independent whole-module mapping.
        if len(starts) > max_signatures:
            starts = [starts[i*(len(starts)-1)//(max_signatures-1)] for i in range(max_signatures)]
        candidates = defaultdict(list)
        signatures = 0
        for offset in starts:
            sig = _signature(decoder, raw, offset)
            if sig is None:
                continue
            signatures += 1
            pattern, mask, anchor_start, anchor_end = sig
            needle = pattern[anchor_start:anchor_end]
            for live_start, live in chunks:
                found = live.find(needle)
                while found >= 0:
                    begin = found-anchor_start
                    if begin >= 0 and begin+len(pattern) <= len(live):
                        actual = live[begin:begin+len(pattern)]
                        if all(not keep or a == b for a, b, keep in zip(actual, pattern, mask)):
                            base = live_start+begin-offset
                            if 0 <= base and base+obj['size'] <= 0x100000000:
                                candidates[base].append({'object_offset': offset,
                                                        'live_address': live_start+begin,
                                                        'length': len(pattern),
                                                        'fixed_bytes': sum(bool(b) for b in mask)})
                    found = live.find(needle, found+1)
        bindings = []
        for base, matches in candidates.items():
            distinct = len({m['object_offset'] for m in matches})
            bindings.append({'live_base': base, 'range': [base, base+obj['size']],
                             'matching_windows': distinct, 'evidence': matches,
                             'status': 'supported_candidate' if distinct >= 2 else 'single_window_candidate'})
        bindings.sort(key=lambda b: (-b['matching_windows'], b['live_base']))
        results.append({'object_index': obj['index'], 'preferred_address': obj['preferred_address'],
                        'size': obj['size'], 'signatures_tested': signatures, 'candidates': bindings})
    return {'format': 'fdisbull-le-runtime-mapping-1', 'status': 'partial' if issues else 'candidates_ready',
            'objects': results, 'issues': issues,
            'scope': 'masked live code-window agreement; no applied fixups, source rebinding, selector or call contract',
            'next_step': 'Use a uniquely supported object range for filename-reference discovery; inspect an actual code selector and candidate routine before native invocation.'}
