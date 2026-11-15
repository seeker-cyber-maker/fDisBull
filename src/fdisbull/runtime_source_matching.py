"""Bounded passive DOS source matching, separate from task/ownership evidence.

No guest calls, writes, source edits or registry mutations occur here.  Returned
spans qualify only compared bytes at the supplied stopped CPU context.  A
source match is not a process lifetime, selector binding or relocation proof.
QEMU comparisons use virtual/linear reads; physical placement needs separate
address-space evidence and is never certified by this matcher alone.
"""
from __future__ import annotations

import base64
import hashlib
import re
import struct

from iced_x86 import Decoder, FlowControl, InstructionInfoFactory, MemorySizeExt, Mnemonic, OpAccess, OpKind, Register

MAX_COMPARE = 512 * 1024
MAX_SCAN = 16 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_FILES = 128
MAX_SPANS = 512
_MACHINE_BACKENDS = frozenset({'qemu-machine', 'qemu-dos'})


class SourceMatchError(ValueError):
    """Ambiguous, changed, unsupported or over-budget passive evidence."""


def _require(value, message):
    if not value:
        raise SourceMatchError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _int(value):
    try:
        result=int(value,0) if isinstance(value,str) else value
    except ValueError as error:
        raise SourceMatchError('invalid observed integer') from error
    _require(type(result) is int and 0<=result<2**64,'invalid observed integer')
    return result


def _ranges(offsets):
    result = []
    for value in sorted(set(offsets)):
        if result and result[-1][0] + result[-1][1] == value:
            result[-1][1] += 1
        else:
            result.append([value, 1])
    return result


class _Budget:
    def __init__(self, session, compare, scan):
        for value, maximum in ((compare, MAX_COMPARE), (scan, MAX_SCAN)):
            _require(type(value) is int and 1 <= value <= maximum, 'invalid source matching budget')
        self.session, self.compare, self.scan = session, compare, scan
        self.compared = self.scanned = 0

    def charge(self, count):
        self.scanned += count
        _require(self.scanned <= self.scan, 'source scan budget exceeded; no partial match published')

    def read(self, address, length, segment=None):
        _require(type(address) is int and 0 <= address < 2**32 and
                 0 < length <= MAX_COMPARE and address + length <= 2**32, 'invalid runtime extent')
        self.compared += length
        _require(self.compared <= self.compare, 'runtime comparison budget exceeded; no partial match published')
        chunks = []
        for offset in range(0, length, 65536):
            size = min(65536, length - offset)
            if self.session.metadata.get('backend') in _MACHINE_BACKENDS:
                _require(segment is None,'machine segmented reads require observed CS cache')
                raw = bytes.fromhex(self.session.memory(address + offset, length=size, space='virtual')['hex'])
            else:
                selected=dict(space='linear',offset=f'0x{address+offset:08X}') if segment is None else dict(space='segmented',segment=f'0x{segment:04X}',offset=f'0x{address+offset:08X}')
                row = self.session.call('memory.read', dict(address=selected, length=size, view='ram'))
                raw = base64.b64decode(row['data_base64'], validate=True)
            _require(len(raw) == size, 'short runtime memory read')
            chunks.append(raw)
        return b''.join(chunks)


def _cpu(regs):
    mode = regs.get('cpu_mode')
    state = regs.get('address_state', {})
    if state:
        _require(state.get('register_context_match') is not False, 'CPU register contexts disagree')
        cs = state.get('segments', {}).get('cs')
        _require(cs is not None, 'observed CS cache required')
        selector = _int(cs['selector']) if 'selector' in cs else _int(regs['registers']['cs'])
        ip = _int(regs['registers'].get('eip', regs.get('instruction_pointer')))
        base = _int(cs['base'])
        result = dict(mode=mode, bits=state.get('code_bits', 16 if mode in ('real', 'v86') else None),
                      cs=selector, ip=ip, linear=base + ip, cs_base=base)
        if cs.get('limit') is not None: result['cs_limit'] = _int(cs['limit'])
        if cs.get('attributes') is not None: result['cs_attributes'] = _int(cs['attributes'])
        return result
    selector = _int(regs.get('segments', {}).get('cs'))
    ip = _int(regs.get('instruction_pointer'))
    _require(type(selector) is int and type(ip) is int, 'current CPU CS/IP required')
    return dict(mode=mode, bits=regs.get('code_bits', 16 if mode in ('real', 'v86') else None),
                cs=selector, ip=ip, linear=selector * 16 + ip if mode in ('real', 'v86') else None,
                cs_base=selector * 16 if mode in ('real', 'v86') else None)


def _descriptors(session, budget):
    if session.metadata.get('backend') in _MACHINE_BACKENDS:
        text = session.vm.qmp.call('human-monitor-command', {'command-line': 'info registers'})
        found = re.search(r'\bGDT\s*=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)', text)
    else:
        text = session.call('debugger.execute_command', {'command': 'CPU'})['raw_output']
        found = re.search(r'GDT base=([0-9A-Fa-f]+) limit=([0-9A-Fa-f]+)', text)
    _require(found is not None, 'observed GDT required for protected source discovery')
    base, limit = (int(part, 16) for part in found.groups())
    _require(limit <= 65535, 'GDT exceeds bounded descriptor budget')
    raw = budget.read(base, limit + 1)
    result = []
    for offset in range(0, len(raw) - 7, 8):
        row = raw[offset:offset + 8]
        if row[5] & 0x98 != 0x98:
            continue
        address = int.from_bytes(row[2:4], 'little') | row[4] << 16 | row[7] << 24
        bound = int.from_bytes(row[:2], 'little') | (row[6] & 15) << 16
        if row[6] & 128:
            bound = (bound << 12) | 4095
        result.append(dict(value=offset, base=address, limit=bound, bits=32 if row[6] & 64 else 16,
                           raw_hex=row.hex()))
    return result


def _code16(data, entry, segment_origin=0):
    """Conservative direct-control-flow code candidates, never data classification."""
    queue, seen, covered, unresolved, writes = [entry], set(), set(), [], []
    factory = InstructionInfoFactory()
    while queue:
        offset = queue.pop()
        ax = ah = None
        while 0 <= offset < len(data) and offset not in seen:
            _require(len(seen) < 4096, '16-bit code discovery instruction budget exceeded')
            seen.add(offset)
            instruction = Decoder(16, data[offset:offset + 15], ip=offset-segment_origin).decode()
            _require(not instruction.is_invalid and offset + instruction.len <= len(data), 'invalid reachable source instruction')
            covered.update(range(offset, offset + instruction.len))
            info = factory.info(instruction)
            for operand in range(instruction.op_count):
                if instruction.op_kind(operand) == OpKind.MEMORY and info.op_access(operand) in (OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE):
                    if instruction.memory_segment == Register.CS and instruction.memory_base == Register.NONE and instruction.memory_index == Register.NONE:
                        target=segment_origin+instruction.memory_displacement
                        writes.append(dict(instruction_offset=offset,source_offset=target,length=MemorySizeExt.size(instruction.memory_size),qualification='explicit CS absolute write target; not proof the write executed'))
                    else:
                        writes.append(dict(instruction_offset=offset,source_offset=None,qualification='indirect or unqualified-segment write target'))
            # Only an immediately established DOS termination service is a
            # terminator. Unknown INT services retain ordinary fallthrough.
            interrupt = instruction.immediate8 if instruction.mnemonic == Mnemonic.INT else None
            terminating = interrupt == 0x20 or interrupt == 0x21 and ah in (0, 0x31, 0x4c)
            if instruction.mnemonic == Mnemonic.MOV and instruction.op0_register == Register.AX and instruction.op1_kind == OpKind.IMMEDIATE16:
                ax = instruction.immediate16; ah = ax >> 8
            elif instruction.mnemonic == Mnemonic.MOV and instruction.op0_register == Register.AH and instruction.op1_kind == OpKind.IMMEDIATE8:
                ah = instruction.immediate8
            elif any(r.register in (Register.AX,Register.AH,Register.EAX) and r.access in (OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE) for r in info.used_registers()):
                ax = ah = None
            flow = instruction.flow_control
            next_offset = offset + instruction.len
            if terminating or flow in (FlowControl.RETURN, FlowControl.EXCEPTION, FlowControl.INDIRECT_BRANCH):
                if flow == FlowControl.INDIRECT_BRANCH:
                    unresolved.append(offset)
                break
            if flow in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH, FlowControl.CALL):
                if instruction.op0_kind in (OpKind.NEAR_BRANCH16, OpKind.NEAR_BRANCH32):
                    target = segment_origin + instruction.near_branch_target
                    if 0 <= target < len(data):
                        queue.append(target)
                    else:
                        unresolved.append(offset)
                else:
                    unresolved.append(offset)
                if flow == FlowControl.UNCONDITIONAL_BRANCH:
                    break
            if flow in (FlowControl.CALL, FlowControl.INDIRECT_CALL, FlowControl.INTERRUPT):
                ax = ah = None
            offset = next_offset
    return covered, unresolved, writes


def _span(name, kind, address, expected, actual, object_id, object_offset, fixups=(), fragments=None):
    excluded = set()
    for offset, width in fixups:
        excluded.update(range(max(0, offset), min(len(expected), offset + width)))
    comparable = [i for i in range(len(expected)) if i not in excluded]
    _require(comparable and all(expected[i] == actual[i] for i in comparable), 'changed source bytes in qualified span')
    result = dict(name=name, kind=kind, address=address, length=len(expected), object_id=object_id,
                  object_offset=object_offset, expected_sha256=_sha(expected), observed_sha256=_sha(actual),
                  compared_bytes=len(comparable), fixups=[dict(offset=a, length=b) for a, b in fixups],
                  comparable_sha256=_sha(bytes(expected[i] for i in comparable)))
    if fragments is not None:
        result['fragments'] = fragments
    return result


def _slice_fragments(fragments, offset, length):
    result = []
    for fragment in fragments:
        low = max(offset, fragment['snapshot_offset'])
        high = min(offset + length, fragment['snapshot_offset'] + fragment['length'])
        if low < high:
            result.append(dict(snapshot_offset=low - offset,
                               object_offset=fragment['object_offset'] + low - fragment['snapshot_offset'], length=high - low))
    _require(sum(f['length'] for f in result) == length, 'source fragment coverage is incomplete')
    return result


def _fat_members(raw, budget):
    from .qemm_runtime import _FATVolume
    volume = _FATVolume(raw)
    pending, seen_dirs, directory_clusters, count, files = [((), volume.root, 0)], set(), set(), 0, []

    def chain(cluster, length=None):
        chunks, fragments, seen, total = [], [], set(), 0
        while True:
            reserved = 0xff0 if volume.bits == 12 else 0xfff0
            _require(2 <= cluster < min(volume.clusters + 2, reserved) and cluster not in seen, 'invalid or cyclic FAT member')
            seen.add(cluster)
            if length is None:
                _require(cluster not in directory_clusters,'crosslinked FAT directory chains')
                directory_clusters.add(cluster)
            address = volume.data_offset + (cluster - 2) * volume.cluster_size
            n = volume.cluster_size if length is None else min(volume.cluster_size, length - total)
            _require(0 < n and address + n <= len(raw), 'FAT source fragment outside image')
            budget.charge(n)  # Directory and program materialization share one global bound.
            chunks.append(raw[address:address + n]);fragments.append(dict(snapshot_offset=total, object_offset=address, length=n));total += n
            _require(total <= MAX_SCAN, 'FAT member exceeds bounded source size')
            next_cluster = volume._next(cluster)
            if length is not None and total == length:
                _require(next_cluster >= (0xff8 if volume.bits == 12 else 0xfff8), 'FAT chain exceeds declared member extent')
                break
            if next_cluster >= (0xff8 if volume.bits == 12 else 0xfff8):
                _require(length is None, 'short FAT member')
                break
            cluster = next_cluster
        return b''.join(chunks), fragments

    while pending:
        parts, directory, depth = pending.pop()
        _require(depth <= 8, 'FAT directory depth exceeds budget')
        names = set()
        for at in range(0, len(directory), 32):
            row = directory[at:at + 32]
            if len(row) < 32 or row[0] == 0:
                break
            count += 1;_require(count <= MAX_ENTRIES, 'FAT entry budget exceeded')
            if row[0] == 0xe5 or row[11] & 8 or row[11] == 15 or row[:11].rstrip() in (b'.', b'..'):
                continue
            try:
                base, ext = row[:8].decode('ascii').rstrip(), row[8:11].decode('ascii').rstrip()
            except UnicodeError as error:
                raise SourceMatchError('non-ASCII FAT short name unsupported') from error
            name = base + ('.' + ext if ext else '')
            _require(name and name.upper() not in names and re.fullmatch(r"[A-Za-z0-9!#$%&'()@^_`{}~+\-]+(?:\.[A-Za-z0-9!#$%&'()@^_`{}~+\-]+)?", name), 'duplicate or unsupported FAT short name')
            names.add(name.upper());cluster = struct.unpack_from('<H', row, 26)[0]
            if row[11] & 16:
                _require(cluster not in seen_dirs, 'aliased or cyclic FAT directories')
                seen_dirs.add(cluster);child, _ = chain(cluster);pending.append((parts + (name,), child, depth + 1))
            elif ext.upper() in ('COM', 'EXE'):
                size = struct.unpack_from('<I', row, 28)[0]
                if not size:
                    continue
                _require(len(files) < MAX_FILES and size <= MAX_SCAN, 'FAT program catalog budget exceeded')
                data, fragments = chain(cluster, size)
                files.append(dict(path='\\' + '\\'.join(parts + (name,)), data=data, fragments=fragments))
    return files


def _signature(data, observed, fixups, budget):
    from .qemu_dos_le_match import masked_window_offsets, SourceMatchError as WindowMatchError
    try:
        return masked_window_offsets(data, observed, fixups, budget)
    except WindowMatchError as error:
        raise SourceMatchError(str(error)) from error


def _prefilter(data, observed, fixups, budget):
    """One bounded pass before decoding an unrelated catalog member.

    A hit is only a reason to investigate, not a placement or uniqueness proof.
    Mutable non-code bytes elsewhere in the observed window do not prevent it.
    """
    needles={observed[at:at+16] for at in range(0,len(observed)-15,8)
             if len(set(observed[at:at+16]))>=3}
    if not needles:
        return False
    excluded={i for a,b in fixups for i in range(a,b)}
    budget.charge(len(data))
    for offset in range(len(data)-15):
        if data[offset:offset+16] in needles and not any(i in excluded for i in range(offset,offset+16)):
            return True
    return False


def _dos_match(budget, cpu, carrier, object_id, preferred, expected, entry, fixups, runtime_base=None, source_expected=None):
    raw = carrier['data'];com = carrier['format'] == 'COM'
    source_expected=expected if source_expected is None else source_expected
    observed=None
    if runtime_base is None:
        _require(cpu['linear'] is not None, 'real/v86 source discovery requires observed linear PC')
        length = min(96, len(expected), 0x10000 - cpu['ip'])
        if length < 16:
            return None
        observed = budget.read(cpu['linear'], length)
        if not _prefilter(expected,observed,fixups,budget):
            return None
    covered, unresolved, writes = _code16(expected, entry, carrier['code_segment_origin'])
    if runtime_base is None:
        signature_exclusions=fixups+[(a,a+b) for a,b in _ranges(set(range(len(expected)))-covered)]
        positions = _signature(expected, observed, signature_exclusions, budget)
        if not positions:
            return None
        position = next(iter(positions));runtime_base = cpu['linear'] - position
        if position not in covered or runtime_base < 0 or com and runtime_base != cpu['cs_base'] + 0x100:
            return None
    if cpu['linear'] is None or cpu['linear']-runtime_base not in covered:
        return None
    actual = budget.read(runtime_base, len(expected))
    changed = {i for i, (a, b) in enumerate(zip(expected, actual)) if a != b}
    excluded = {i for a, b in fixups for i in range(a, b)}
    _require(not (changed & covered - excluded), 'changed reachable source code')
    spans = []
    for index, (start, n) in enumerate(_ranges(covered)):
        local = [(max(a, start) - start, min(b, start + n) - max(a, start)) for a, b in fixups if a < start + n and b > start]
        fragments = _slice_fragments(carrier['module_fragments'], start, n) if carrier.get('module_fragments') is not None else None
        if fragments is None:
            spans.append(_span('code-' + str(index), 'code', runtime_base + start, source_expected[start:start+n], actual[start:start+n], object_id, start, local))
        else:
            # Raw disk objects have no relocation mask: retain the exclusion
            # metadata and publish only fully comparable source subspans.
            for part, (low, size) in enumerate(_ranges(set(range(start, start+n)) - excluded)):
                f = _slice_fragments(carrier['module_fragments'], low, size)
                spans.append(_span(f'code-{index}-{part}', 'code', runtime_base+low, expected[low:low+size], actual[low:low+size], object_id, f[0]['object_offset'], fragments=f))
    _require(len(spans) <= MAX_SPANS, 'source span budget exceeded')
    return dict(source_identity={k:v for k,v in carrier.items() if k not in ('data','module_fragments')},
                identity_evidence=dict(kind='passive-source-match', lifetime_qualified=False, runtime_base=runtime_base, cpu=cpu,
                                       whole_file_equal=com and not changed, runtime_module_equal=not changed,
                                       changed_data=[dict(offset=a,length=b) for a,b in _ranges(changed-excluded)],
                                       changed_data_scope='changed bytes outside bounded instruction candidates; no complete data/type classification',
                                       source_write_candidates=writes,
                                       unresolved_control_offsets=unresolved, code_coverage='bounded recursive direct-control-flow candidates',
                                       excluded_loader_fixups=[dict(offset=a,length=b-a) for a,b in fixups]), source_spans=spans)


def _le_match(session, budget, cpu, carrier, objects, metadata, descriptors):
    _require(0 < cpu['cs'] <= 65535 and not cpu['cs'] & 4 and cpu['cs'] & ~7,
             'protected source discovery requires a non-null GDT selector; LDT is unsupported')
    current = next((d for d in descriptors if d['value'] == cpu['cs'] & ~7), None)
    if current is None or current['bits'] != 32:
        return None
    _require(cpu['ip']+95<=current['limit'] and (cpu['cs_base'] is None or cpu['cs_base']==current['base']),
             'observed CS cache/GDT disagree or current source window exceeds the segment')
    if 'cs_limit' in cpu:
        _require(cpu['cs_limit'] == current['limit'], 'observed CS limit and GDT disagree')
    if 'cs_attributes' in cpu:
        raw = bytes.fromhex(current['raw_hex'])
        attributes = raw[5] << 8 | (raw[6] & 0xf0) << 16
        _require(cpu['cs_attributes'] & 0xf0ff00 == attributes and not attributes & 0x200000,
                 'observed CS attributes and GDT disagree')
    linear = current['base'] + cpu['ip'];observed = budget.read(linear, 96)
    if cpu['cs_base'] is None:
        _require(budget.read(cpu['ip'],96,segment=cpu['cs'])==observed,'observed segmented and GDT linear code differ')
    choices = []
    for obj in objects:
        if obj['bits'] != 32 or not obj['executable']:
            continue
        for offset in _signature(obj['data'], observed, obj['fixups'], budget):
            if any(a <= offset and offset+96 <= b for a,b in obj['backed']):
                choices.append((obj,offset,linear-offset))
    _require(len(choices) <= 1, 'ambiguous protected source placement')
    if not choices:
        return None
    code, offset, codebase = choices[0];spans = []
    def add(obj, off, size, address, actual, name, kind):
        excluded = {i for a,b in obj['fixups'] for i in range(max(off,a),min(off+size,b))}
        expected = obj['data'][off:off+size]
        if carrier.get('fragments') is None:
            local = [(max(off,a)-off,min(off+size,b)-max(off,a)) for a,b in obj['fixups'] if a<off+size and b>off]
            spans.append(_span(name,kind,address,expected,actual,obj['id'],off,local))
        else:
            for index,(low,n) in enumerate(_ranges(set(range(off,off+size))-excluded)):
                fragments=[]
                for mapping in metadata['file_mappings']:
                    left=max(obj['start']+low,mapping['virtual_address']);right=min(obj['start']+low+n,mapping['virtual_address']+mapping['file_size'])
                    if left<right:
                        foff=mapping['file_offset']+left-mapping['virtual_address']
                        for f in _slice_fragments(carrier['fragments'],foff,right-left):
                            fragments.append(dict(f,snapshot_offset=f['snapshot_offset']+left-(obj['start']+low)))
                _require(sum(f['length'] for f in fragments)==n,'LE/FAT source fragment coverage incomplete')
                spans.append(_span(name+'-'+str(index),kind,address+low-off,obj['data'][low:low+n],actual[low-off:low-off+n],'region:0',fragments[0]['object_offset'],fragments=fragments))
    discovery_span=_span('current-code','code',linear,code['data'][offset:offset+96],observed,code['id'],offset,
                         [(max(offset,a)-offset,min(offset+96,b)-max(offset,a)) for a,b in code['fixups'] if a<offset+96 and b>offset])
    if carrier.get('fragments') is not None:
        discovery_span.pop('object_id');discovery_span['nested_object_index']=code['index']
    entry=metadata['le']['entry_offset'];stable=metadata['le']['entry_object']==code['index'] and any(a<=entry and entry+96<=b for a,b in code['backed'])
    if stable:
        entry_actual=budget.read(codebase+entry,96)
        add(code,entry,96,codebase+entry,entry_actual,'entry-code','code')
    else:
        add(code,offset,96,linear,observed,'current-code','code')
    proofs=[]
    for obj in objects:
        if obj['executable']:
            continue
        sites={f['source_offset']:f for f in metadata['le']['fixups'] if f['source_object']==code['index'] and f['source_type']=='offset32' and f['target_object']==obj['index'] and f.get('addend') is None}
        if len(sites)<8:
            continue
        bases=set();proof=[]
        for site,f in sorted(sites.items())[:8]:
            value=int.from_bytes(budget.read(codebase+site,4),'little');base=value-f['target_offset'];bases.add(base);proof.append(dict(source_offset=site,target_offset=f['target_offset'],value=value))
        _require(len(bases)==1,'inconsistent LE data relocation sites')
        base=bases.pop();matched=False
        for low,high in obj['backed']:
            for off in range(low,max(low,high-31),32):
                budget.charge(32)
                candidate=obj['data'][off:off+32]
                if len(set(candidate))<8 or sum(v!=0 for v in candidate)<16 or any(a<off+32 and b>off for a,b in obj['fixups']):
                    continue
                actual=budget.read(base+off,32)
                if actual==candidate:
                    add(obj,off,32,base+off,actual,'initialized-data-'+str(obj['index']),'data');matched=True;break
            if matched:break
        _require(matched,'no unchanged initialized LE data witness within budget')
        proofs.append(dict(object_index=obj['index'],runtime_base=base,offset32_sites=proof))
    for obj in objects:
        if obj['bits']!=16 or not obj['executable']:
            continue
        size=min(len(obj['data']),256)
        if not any(a==0 and b>=size for a,b in obj['backed']):
            continue
        matches=[]
        excluded={i for a,b in obj['fixups'] for i in range(a,b)}
        for descriptor in descriptors:
            if descriptor['bits']!=16 or descriptor['limit']+1<size:
                continue
            actual=budget.read(descriptor['base'],size)
            if all(actual[i]==obj['data'][i] for i in range(size) if i not in excluded):
                matches.append((descriptor,actual))
        _require(len(matches)<=1,'ambiguous 16-bit LE descriptor/source match')
        if matches:
            descriptor,actual=matches[0];add(obj,0,size,descriptor['base'],actual,'bridge-'+str(obj['index']),'code')
            proofs.append(dict(object_index=obj['index'],descriptor=descriptor,execution_observed=False,symbolic_operands_qualified=False))
    _require(len(spans)<=MAX_SPANS,'source span budget exceeded')
    return dict(source_identity={k:v for k,v in carrier.items() if k not in ('data','fragments')},
                identity_evidence=dict(kind='passive-source-match',lifetime_qualified=False,cpu=cpu,current_descriptor=current,code_object=code['index'],runtime_code_base=codebase,object_proofs=proofs,
                                       current_pc_source_match=discovery_span,stable_code_extent=stable,
                                       excluded_loader_fixups=[dict(object_index=o['index'],offset=a,length=b-a) for o in objects for a,b in o['fixups']]),source_spans=spans)


def _le_objects(image):
    result=[];meta=image.metadata['le']
    for obj in meta['objects']:
        region=next(r for r in image.regions if r.start==obj['virtual_address'])
        result.append(dict(id='le:'+str(obj['index']),index=obj['index'],start=region.start,data=region.data,bits=obj['bits'],executable=region.executable,
                           backed=[(p['object_offset'],p['object_offset']+p['file_size']) for p in meta['pages'] if p['object']==obj['index'] and p['file_size']],
                           fixups=[(f['source_offset'],f['source_offset']+f['width']) for f in meta['fixups'] if f['source_object']==obj['index']]))
    return result


def discover(session, *, max_compare_bytes=MAX_COMPARE, max_scan_bytes=MAX_SCAN):
    """Return source candidates; caller owns stopped-state and lifetime policy.

    Ambiguity, mutation of reachable code, incomplete provenance and budget stops
    raise SourceMatchError. An unrelated current PC returns an empty list. Normal
    MZ/COM sessions use their already-qualified load placement. Raw FAT searches
    bounded named COM/MZ members without binary-specific offsets or path hashes.
    """
    project=session.project;version=session.version['id'];v=project.version(version)
    _require(project.meta['arch']=='x86' and project.meta['format'] in ('raw','MZ','COM','LE'),'passive DOS source discovery requires x86 DOS/raw input')
    _require(v['parent'] is None,'passive discovery requires an original source version')
    source=project.source_info(version);_require(source.get('verified'),'verified retained source required')
    row=project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(version,)).fetchone()
    raw=bytes(row[0]);_require(len(raw)<=64*1024*1024 and _sha(raw)==project.source_sha256(version),'retained source identity differs')
    _require(session.metadata['source_sha256']==project.source_sha256(version),'session/project source mismatch')
    budget=_Budget(session,max_compare_bytes,max_scan_bytes);before=session.registers();cpu=_cpu(before)
    records=[];fmt=project.meta['format']
    carriers=[dict(data=raw,carrier_sha256=_sha(raw),project_source_sha256=_sha(raw))]
    if fmt=='raw':
        carriers=[dict(member,carrier_sha256=_sha(member['data']),project_source_sha256=_sha(raw)) for member in _fat_members(raw,budget)]
    descriptors=_descriptors(session,budget) if cpu['mode']=='protected' and cpu['bits']==32 else []
    for carrier in carriers:
        data=carrier['data']
        if cpu['mode']=='protected' and cpu['bits']==32:
            from .le import load_runtime_le_carrier
            try:image=load_runtime_le_carrier(data)
            except ValueError:continue
            record=_le_match(session,budget,cpu,carrier,_le_objects(image),image.metadata,descriptors)
        elif cpu['mode'] in ('real','v86') and cpu['bits']==16:
            from .dos import load_com,load_mz
            is_mz=data[:2]==b'MZ'
            if not is_mz and len(data)>0xff00:continue
            try:image=load_mz(data,allow_secondary=True) if is_mz else load_com(data)
            except ValueError:continue
            dos=image.metadata['dos'];region=image.regions[0];size=dos['module_size'];expected=bytes(region.data[:size]);fixups=[(f['linear_address']-region.start,f['linear_address']-region.start+2) for f in dos['relocations']]
            carrier['format']='MZ' if is_mz else 'COM'
            carrier['code_segment_origin']=dos['header_fields']['e_cs']*16 if is_mz else -0x100
            if fmt=='raw':
                carrier['module_fragments']=_slice_fragments(carrier['fragments'],dos['header_size'],size)
                expected=data[dos['header_size']:dos['header_size']+size]
            runtime_base=getattr(session,'runtime_base',None) if fmt in ('MZ','COM') else None
            if runtime_base is not None:
                expected=bytes(session.expected[:size])
                oid=next(o['id'] for o in project.runtime_objects(version)['objects'] if o['preferred_start']==session.static_base)
                original_object=project._mapping_catalog(version)[0][oid]
                source_expected=original_object['data'][:size]
            else:oid='region:0';source_expected=expected
            record=_dos_match(budget,cpu,carrier,oid,region.start,expected,image.entry-region.start,fixups,runtime_base,source_expected)
        else:record=None
        if record is not None:records.append(record)
    _require(len(records)<=1,'ambiguous source carrier candidates')
    _require(session.registers()==before,'CPU context changed during passive source discovery')
    for record in records:
        record['budget']=dict(compared_bytes=budget.compared,scanned_bytes=budget.scanned,source_container_bytes=len(raw),
                              scan_scope='candidate search/catalog; retained container verification separately bounded at64MiB')
        record['source_identity'].update(version=version,version_sha256=v['sha256'])
        record['identity_evidence'].update(memory_comparison_scope='stopped virtual/linear bytes only; physical placement requires separate address-space evidence',
                                           physical_mapping_qualified=False)
    return records
