"""Conservative structural COM16 code placement and declared reference repair.

This pure routine produces a private byte value, never writes a host file, and
makes no behavioral-equivalence claim for a selected implementation.
"""
from copy import deepcopy
from hashlib import sha256
import re

import iced_x86 as ix

from .code_backings import digest
from .code_blocks import group_code_backings
from .decoder import decode

_REQUIRED = ('no_code_reads', 'no_code_writes', 'no_computed_entries',
             'address_identity_unobserved', 'timing_unobserved')
_HEX = re.compile(r'(?:[0-9a-f]{2})+\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_LIMIT = 0xf000


def _bytes(value, size=None):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError('expected nonempty lowercase hexadecimal bytes')
    raw = bytes.fromhex(value)
    if size is not None and len(raw) != size:
        raise ValueError('unexpected field size')
    return raw


def _near(target, end):
    delta = target - end
    if not -32768 <= delta <= 32767:
        raise ValueError('near displacement outside signed 16-bit range')
    return delta.to_bytes(2, 'little', signed=True)


def _inspect(raw, ip, data_ranges, allow_dynamic, *, replacement=False):
    """Decode one instruction and enforce the admitted environmental profile."""
    dec = ix.Decoder(16, raw, ip=ip)
    ins = dec.decode()
    if ins.is_invalid or ins.len != len(raw):
        raise ValueError('instruction must decode exactly')
    if ins.is_privileged and ins.mnemonic != ix.Mnemonic.HLT:
        raise ValueError('privileged instruction unsupported in real-mode COM profile')
    info = ix.InstructionInfoFactory().info(ins)
    writes = {ix.OpAccess.WRITE, ix.OpAccess.COND_WRITE, ix.OpAccess.READ_WRITE,
              ix.OpAccess.READ_COND_WRITE}
    protected = {ix.Register.CS, ix.Register.DS, ix.Register.ES, ix.Register.SS,
                 ix.Register.SP, ix.Register.ESP, ix.Register.RSP}
    terminal_ret = ins.mnemonic == ix.Mnemonic.RET and raw[0] in (0xc2, 0xc3)
    if any(reg.register in protected and reg.access in writes for reg in info.used_registers()) and not terminal_ret:
        raise ValueError('segment or stack-pointer mutation unsupported')
    facts = decode(raw, ip, 'x86', 16)
    flow = facts['flow']
    if ins.mnemonic == ix.Mnemonic.HLT:
        flow = 'stop'
    if replacement and flow != 'next':
        raise ValueError('replacement body must be straight-line NEXT instructions')
    if flow not in ('next', 'jump', 'conditional', 'return', 'stop'):
        raise ValueError('unsupported control flow')
    if ins.flow_control in (ix.FlowControl.INTERRUPT, ix.FlowControl.XBEGIN_XABORT_XEND):
        raise ValueError('interrupt or transactional flow unsupported')
    if flow == 'return' and not terminal_ret:
        raise ValueError('only near return supported')
    if flow == 'stop' and ins.mnemonic != ix.Mnemonic.HLT:
        raise ValueError('unsupported stop instruction')
    if flow == 'jump' and not (raw[0] in (0xeb, 0xe9) and len(raw) in (2, 3)):
        raise ValueError('only direct near jump supported')
    if flow == 'conditional' and not ((0x70 <= raw[0] <= 0x7f and len(raw) == 2) or
                                     (len(raw) == 4 and raw[:1] == b'\x0f' and 0x80 <= raw[1] <= 0x8f)):
        raise ValueError('only direct near conditional jump supported')
    fixed, dynamic = [], False
    for mem in info.used_memory():
        if terminal_ret and mem.base in (ix.Register.SP, ix.Register.ESP):
            continue
        if mem.segment not in (ix.Register.CS, ix.Register.DS, ix.Register.ES, ix.Register.SS):
            raise ValueError('unsupported memory segment')
        width = ix.MemorySizeExt.size(mem.memory_size) or 1
        if mem.base == ix.Register.NONE and mem.index == ix.Register.NONE:
            if mem.address_size != ix.CodeSize.CODE16:
                raise ValueError('32-bit absolute memory addressing unsupported')
            address = mem.displacement
            if address > 0xffff or not any(lo <= address and address + width <= hi for lo, hi in data_ranges):
                raise ValueError('absolute memory target is not declared fixed data')
            fixed.append({'old_ip': address, 'new_ip': address, 'size': width})
        else:
            dynamic = True
            if not allow_dynamic or not data_ranges:
                raise ValueError('register memory requires fixed-data target assertion')
    # LEA computes an address but has no UsedMemory entry. Do not let a
    # statically visible source-code pointer bypass the fixed-data contract.
    if ins.mnemonic == ix.Mnemonic.LEA:
        if ins.memory_base == ix.Register.NONE and ins.memory_index == ix.Register.NONE:
            address = ins.memory_displacement
            offsets = dec.get_constant_offsets(ins)
            if offsets.displacement_size != 2:
                raise ValueError('32-bit absolute address unsupported')
            if not any(lo <= address < hi for lo, hi in data_ranges):
                raise ValueError('absolute address target is not declared fixed data')
            fixed.append({'old_ip':address, 'new_ip':address, 'size':0, 'kind':'address'})
        else:
            dynamic = True
            if not allow_dynamic or not data_ranges:
                raise ValueError('register address requires fixed-data target assertion')
    return ins, dec.get_constant_offsets(ins), flow, fixed, dynamic


def compile_dos_com(capsule, plan, data, *, references=None, replacements=None,
                    entry=None, block_order=None, assumptions=None, code_base=None):
    """Emit an explicitly selected COM16 layout; inputs are caller-owned values."""
    if not isinstance(plan, dict) or plan != group_code_backings(capsule, split_at=plan.get('split_at')):
        raise ValueError('group plan differs from capsule')
    if not plan['complete'] or not capsule['complete']:
        raise ValueError('complete source graph required')
    source = capsule.get('source', {})
    if source.get('arch') != 'x86' or source.get('bits') != 16:
        raise ValueError('COM requires 16-bit x86 source')
    groups = plan['blocks']; atoms = {a['id']: a for a in capsule['blocks']}
    if not groups or len(groups) > 4096:
        raise ValueError('invalid group count')
    if any(edge['source'] not in atoms for group in groups for edge in group['incoming']):
        raise ValueError('known incoming control edge originates outside captured graph')
    contexts = {g['context'] for g in groups}
    if len(contexts) != 1 or not re.fullmatch(r'x86:16:little:cs=[0-9a-fA-F]{4}', next(iter(contexts))):
        raise ValueError('single DOS CS context required')
    segment = int(next(iter(contexts))[-4:], 16) * 16
    by_group = {g['id']: g for g in groups}
    group_ids = list(by_group)
    old_ports = {g['id']: int(atoms[g['entry']]['address'], 16) - segment for g in groups}
    if any(not 0x100 <= ip < _LIMIT for ip in old_ports.values()):
        raise ValueError('source entry outside COM address range')
    if entry is None:
        roots = list(dict.fromkeys(plan['entries'].values()))
        if len(roots) != 1 or roots[0] not in by_group:
            raise ValueError('multiple or missing roots require an explicit boot entry')
        entry = roots[0]
    if entry not in by_group or entry not in plan['entries'].values():
        raise ValueError('entry must be a captured root group')
    if block_order is None: block_order = group_ids
    if not isinstance(block_order, list) or len(block_order) != len(group_ids) or len(set(block_order)) != len(group_ids) or set(block_order) != set(group_ids):
        raise ValueError('block_order must contain every group exactly once')
    if not isinstance(assumptions, dict) or any(assumptions.get(k) is not True for k in _REQUIRED) or set(assumptions) - set(_REQUIRED) - {'register_memory_targets_fixed_data'}:
        raise ValueError('required environmental assumptions missing')
    allow_dynamic = assumptions.get('register_memory_targets_fixed_data') is True
    if not isinstance(data, list) or len(data) > 4096:
        raise ValueError('invalid data declarations')
    data_by_id = {}; ranges = []; old_code = set()
    for atom in atoms.values():
        start = int(atom['address'], 16) - segment
        raw = _bytes(atom['bytes'])
        if start < 0x100 or start + len(raw) > _LIMIT: raise ValueError('source instruction outside COM range')
        old_code.update(range(start, start + len(raw)))
    for d in data:
        if not isinstance(d, dict) or set(d) != {'id', 'ip', 'bytes', 'sha256'} or not isinstance(d['id'], str) or not d['id'] or d['id'] in data_by_id or type(d['ip']) is not int:
            raise ValueError('invalid data declaration')
        raw = _bytes(d['bytes']); start = d['ip']; end = start + len(raw)
        if start < 0x103 or end > _LIMIT or sha256(raw).hexdigest() != d['sha256'] or any(start < hi and lo < end for lo, hi in ranges) or any(i in old_code for i in range(start, end)):
            raise ValueError('data overlaps source code/data or fails bounds/hash')
        ranges.append((start, end)); data_by_id[d['id']] = {'id': d['id'], 'ip': start, 'raw': raw}
    base = ((max([0x103] + [hi for _, hi in ranges]) + 15) // 16) * 16 if code_base is None else code_base
    if type(base) is not int or not 0x103 <= base < _LIMIT or any(lo <= base < hi for lo, hi in ranges):
        raise ValueError('invalid code base')
    if replacements is None: replacements = {}
    if not isinstance(replacements, dict) or any(k not in by_group for k in replacements):
        raise ValueError('unknown replacement group')
    dynamic_seen = False; prepared = {}; atom_offsets = {}; replacement_offsets = {}; fixed_reads = []
    for gid in block_order:
        g = by_group[gid]; selected = replacements.get(gid); chunks = []
        last_atom = atoms[g['instructions'][-1]]
        source_ip = int(last_atom['address'], 16) - segment
        last_raw = _bytes(last_atom['bytes'])
        source_ins, _, source_flow, _, _ = _inspect(last_raw, source_ip, ranges, allow_dynamic)
        if source_flow != last_atom['flow']:
            raise ValueError('source flow differs from decoded instruction')
        for edge in g['exits']:
            target = edge['target_block']
            if target not in old_ports:
                raise ValueError('missing source target port')
            if edge['kind'] == 'fallthrough' and old_ports[target] != source_ip + len(last_raw):
                raise ValueError('source fallthrough differs from decoded instruction')
            if edge['kind'] in ('branch', 'resolved_branch') and (source_flow not in ('jump', 'conditional') or source_ins.near_branch_target != old_ports[target]):
                raise ValueError('source branch differs from decoded instruction')
        if selected is not None:
            if not isinstance(selected, dict) or set(selected) - {'id','bytes','sha256','expected_block_revision','references','qualification'} or not isinstance(selected.get('id'), str) or not selected['id'] or not isinstance(selected.get('qualification'), dict) or selected.get('expected_block_revision') != g['block_revision']:
                raise ValueError('invalid replacement identity or revision')
            for ident in g['instructions']:
                source_atom = atoms[ident]
                source_raw = _bytes(source_atom['bytes'])
                _, _, actual_flow, _, dynamic = _inspect(
                    source_raw, int(source_atom['address'], 16)-segment, ranges, allow_dynamic)
                if actual_flow != source_atom['flow']:
                    raise ValueError('source flow differs from decoded instruction')
                dynamic_seen |= dynamic
            body = _bytes(selected.get('bytes'))
            if len(body) > 4096 or sha256(body).hexdigest() != selected.get('sha256'):
                raise ValueError('replacement hash or size mismatch')
            if len(g['exits']) != 1 or g['exits'][0]['kind'] not in ('fallthrough','branch','resolved_branch'):
                raise ValueError('replacement needs exactly one continuation')
            decoder = ix.Decoder(16, body, ip=0)
            while decoder.can_decode:
                offset = decoder.position; ins = decoder.decode()
                if ins.is_invalid: raise ValueError('invalid replacement instruction')
                raw = body[offset:decoder.position]
                _, off, _, fixed, dynamic = _inspect(raw, offset, ranges, allow_dynamic, replacement=True)
                dynamic_seen |= dynamic; fixed_reads.extend(fixed)
                replacement_offsets[(gid, offset)] = (raw, off)
                chunks.append((None, raw, 'next'))
        else:
            for ident in g['instructions']:
                atom = atoms[ident]; raw = _bytes(atom['bytes']); ip = int(atom['address'],16)-segment
                ins, off, flow, fixed, dynamic = _inspect(raw, ip, ranges, allow_dynamic)
                if flow != atom['flow'] and not (flow == 'stop' and atom['flow'] == 'stop'):
                    raise ValueError('source flow differs from decoded instruction')
                dynamic_seen |= dynamic; fixed_reads.extend(fixed)
                atom_offsets[ident] = (gid, raw, off)
                chunks.append((ident, raw, flow))
        terminal = chunks[-1][2]
        if selected is not None: terminal = 'replacement'
        if terminal in ('next','replacement','jump'):
            if len(g['exits']) != 1 or g['exits'][0]['target_block'] not in by_group:
                raise ValueError('missing continuation')
            if terminal == 'jump' and g['exits'][0]['kind'] not in ('branch','resolved_branch'): raise ValueError('invalid branch port')
            if terminal == 'next' and g['exits'][0]['kind'] != 'fallthrough': raise ValueError('invalid fallthrough port')
        elif terminal == 'conditional':
            if len(g['exits']) != 2 or {e['kind'] for e in g['exits']} != {'branch','fallthrough'} or any(e['target_block'] not in by_group for e in g['exits']):
                raise ValueError('invalid conditional ports')
        elif g['exits']:
            raise ValueError('terminal group has exits')
        if any(c[2] != 'next' for c in chunks[:-1]): raise ValueError('control transfer inside logical group')
        length = sum(len(c[1]) for c in chunks)
        if terminal == 'jump': length += 3-len(chunks[-1][1])
        elif terminal == 'conditional': length += 7-len(chunks[-1][1])
        elif terminal in ('next','replacement'): length += 3
        prepared[gid] = {'chunks': chunks, 'terminal': terminal, 'size': length, 'selected': selected}
    ports = {}; cursor = base
    for gid in block_order:
        size = prepared[gid]['size']; ports[gid] = cursor
        if cursor + size > _LIMIT or any(cursor < hi and lo < cursor + size for lo,hi in ranges):
            raise ValueError('emitted code collides with data or stack')
        cursor += size
    out = bytearray(max(cursor, max([0x103] + [hi for _,hi in ranges])) - 0x100)
    out[:3] = b'\xe9' + _near(ports[entry], 0x103)
    for d in data_by_id.values(): out[d['ip']-0x100:d['ip']-0x100+len(d['raw'])] = d['raw']
    fixups = [{'kind':'bootstrap','site_ip':0x100,'file_offset':0,'target_port':entry,'target_ip':ports[entry]}]
    occurrences = []; atom_sites = {}; replacement_sites = {}; emitted_branches = []
    for gid in block_order:
        p = prepared[gid]; pos = ports[gid]; body_offset = 0
        for ident, raw, flow in p['chunks']:
            if ident is not None: atom_sites[ident] = pos
            else: replacement_sites[(gid, body_offset)] = pos
            emitted = raw
            if flow in ('jump','conditional'):
                edge = next(e for e in by_group[gid]['exits'] if e['kind'] in ('branch','resolved_branch'))
                target = edge['target_block']; expected = old_ports[target]
                ins = ix.Decoder(16, raw, ip=int(atoms[ident]['address'],16)-segment).decode()
                if ins.near_branch_target != expected: raise ValueError('branch target differs from source port')
                prefix = b'\xe9' if flow == 'jump' else bytes((0x0f,0x80+(raw[0]&15 if raw[0]!=0x0f else raw[1]&15)))
                emitted = prefix + _near(ports[target],pos+len(prefix)+2)
                fixups.append({'kind':'branch','site_ip':pos,'file_offset':pos-0x100,'target_port':target,'target_ip':ports[target],'expected_hex':raw.hex(),'new_hex':emitted.hex()})
                emitted_branches.append((pos,emitted,ports[target]))
            out[pos-0x100:pos-0x100+len(emitted)] = emitted
            occurrences.append({'group':gid,'source_instruction':ident,'backing_revision':atoms[ident]['backing_revision'] if ident else None,'source_ip':int(atoms[ident]['address'],16)-segment if ident else None,'implementation':p['selected']['id'] if p['selected'] else None,'output_ip':pos,'size':len(emitted),'source_bytes':raw.hex() if ident else None,'bytes':emitted.hex(),'kind':'replacement' if ident is None else 'source'})
            pos += len(emitted); body_offset += len(raw)
        if p['terminal'] in ('next','replacement','conditional'):
            edge = next(e for e in by_group[gid]['exits'] if e['kind']=='fallthrough') if p['terminal']=='conditional' else by_group[gid]['exits'][0]
            target = edge['target_block']; glue = b'\xe9'+_near(ports[target],pos+3)
            out[pos-0x100:pos-0x100+3] = glue
            fixups.append({'kind':'continuation','site_ip':pos,'file_offset':pos-0x100,'target_port':target,'target_ip':ports[target],'new_hex':glue.hex()})
            emitted_branches.append((pos,glue,ports[target]))
    emitted_branches.append((0x100,bytes(out[:3]),ports[entry]))
    for at, raw, target in emitted_branches:
        if ix.Decoder(16,raw,ip=at).decode().near_branch_target != target:
            raise ValueError('final branch validation failed')
    refs = [] if references is None else deepcopy(references)
    if not isinstance(refs, list): raise ValueError('references must be a list')
    # Stored operand evidence is not an inference from a random immediate.
    # Every known pointer occurrence must have an admitted native repair, and
    # known memory references must agree with the independently decoded field.
    for ident, atom in atoms.items():
        source_raw = _bytes(atom['bytes'])
        decoder = ix.Decoder(16, source_raw, ip=int(atom['address'], 16)-segment)
        ins = decoder.decode(); offsets = decoder.get_constant_offsets(ins)
        for evidence in atom.get('references', []):
            if not isinstance(evidence, dict): raise ValueError('invalid stored operand evidence')
            role, index = evidence.get('role'), evidence.get('operand_index')
            if role not in ('code', 'address', 'memory') or type(index) is not int or not 0 <= index < ins.op_count:
                raise ValueError('unsupported stored operand evidence')
            try:
                value = int(evidence['target'], 0) - segment
            except (KeyError, ValueError, TypeError) as error:
                raise ValueError('invalid stored operand target') from error
            kind = ins.op_kind(index)
            if role == 'code' and kind in (ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32):
                if ins.near_branch_target != value: raise ValueError('stored branch reference differs from decoded target')
                continue
            if kind == ix.OpKind.MEMORY and role in ('memory', 'address'):
                if (ins.memory_base != ix.Register.NONE or ins.memory_index != ix.Register.NONE
                        or offsets.displacement_size != 2 or ins.memory_displacement != value
                        or not any(lo <= value < hi for lo,hi in ranges)):
                    raise ValueError('stored memory reference lacks a matching fixed-data native field')
                width = evidence.get('width')
                if width is not None and (type(width) is not int or width < 1 or not any(lo <= value and value+width <= hi for lo,hi in ranges)):
                    raise ValueError('stored memory reference escapes fixed data')
                continue
            if role not in ('address', 'code') or ins.mnemonic != ix.Mnemonic.MOV or index != 1 or kind != ix.OpKind.IMMEDIATE16 or offsets.immediate_size != 2:
                raise ValueError('stored pointer evidence has unsupported native field')
            if ident not in atom_sites:
                raise ValueError('known source pointer belongs to a replaced block')
            matching = []
            for ref in refs:
                if not isinstance(ref, dict) or ref.get('instruction') != ident or ref.get('field_offset') != offsets.immediate_offset:
                    continue
                target = ref.get('target'); addend = ref.get('addend', 0)
                if ref.get('kind') == 'code-immediate' and target in old_ports and addend == 0:
                    wanted = old_ports[target]
                elif ref.get('kind') == 'data-immediate' and target in data_by_id and type(addend) is int:
                    wanted = data_by_id[target]['ip'] + addend
                else:
                    continue
                if wanted == value: matching.append(ref)
            if len(matching) != 1:
                raise ValueError('known source pointer requires a matching declared immediate fixup')
    for gid,p in prepared.items():
        if p['selected'] is not None:
            candidate_refs = p['selected'].get('references', [])
            if not isinstance(candidate_refs, list): raise ValueError('replacement references must be a list')
            for ref in candidate_refs:
                if not isinstance(ref, dict) or '_replacement' in ref or 'instruction' in ref:
                    raise ValueError('invalid replacement reference')
                refs.append({**ref, '_replacement':gid})
    used_sites = set()
    for ref in refs:
        if not isinstance(ref, dict): raise ValueError('invalid reference')
        kind = ref.get('kind'); target = ref.get('target'); addend = ref.get('addend',0)
        if type(addend) is not int: raise ValueError('invalid reference addend')
        if kind == 'near-code-pointer':
            if set(ref) != {'kind','data','offset','target','expected_hex'} or target not in ports or ref.get('data') not in data_by_id or type(ref.get('offset')) is not int: raise ValueError('invalid pointer table reference')
            d = data_by_id[ref['data']]; offset = ref['offset']; site = d['ip'] + offset
            if offset < 0 or offset+2 > len(d['raw']): raise ValueError('pointer table field outside data')
            expected, new = old_ports[target], ports[target]
        elif kind in ('data-immediate','code-immediate'):
            replacement_gid = ref.get('_replacement')
            allowed = {'kind','field_offset','target','expected_hex','addend'} | ({'_replacement'} if replacement_gid else {'instruction'})
            if set(ref) - allowed or type(ref.get('field_offset')) is not int: raise ValueError('invalid immediate reference')
            field = ref['field_offset']
            if replacement_gid:
                found = [(o,raw,off) for (gid,o),(raw,off) in replacement_offsets.items() if gid == replacement_gid and o+off.immediate_offset == field and off.immediate_size == 2]
                if len(found)!=1: raise ValueError('replacement reference is not native immediate field')
                off0, raw, offs = found[0]; site = replacement_sites[(replacement_gid,off0)] + offs.immediate_offset
            else:
                ident = ref.get('instruction')
                if ident not in atom_offsets: raise ValueError('unknown or replaced source instruction')
                gid, raw, offs = atom_offsets[ident]
                if field != offs.immediate_offset or offs.immediate_size != 2: raise ValueError('reference is not native immediate field')
                site = atom_sites[ident] + field
            ins = ix.Decoder(16,raw).decode()
            if ins.mnemonic != ix.Mnemonic.MOV or ins.op0_kind != ix.OpKind.REGISTER or ins.op1_kind != ix.OpKind.IMMEDIATE16 or ins.op0_register not in (ix.Register.AX,ix.Register.BX,ix.Register.CX,ix.Register.DX,ix.Register.SI,ix.Register.DI,ix.Register.BP): raise ValueError('only MOV reg16,imm16 pointer fields supported')
            if kind == 'data-immediate':
                if target not in data_by_id or not 0 <= addend < len(data_by_id[target]['raw']): raise ValueError('data reference target/addend invalid')
                expected = new = data_by_id[target]['ip'] + addend
            else:
                if target not in ports or addend != 0: raise ValueError('code reference target/addend invalid')
                expected,new = old_ports[target],ports[target]
        else: raise ValueError('unknown reference kind')
        expected_bytes = _bytes(ref.get('expected_hex'),2)
        if site in used_sites or site+1 in used_sites: raise ValueError('duplicate or overlapping reference site')
        if expected_bytes != expected.to_bytes(2,'little') or out[site-0x100:site-0x100+2] != expected_bytes:
            raise ValueError('reference expected word differs from source or target')
        used_sites.update((site,site+1)); new_bytes = new.to_bytes(2,'little');out[site-0x100:site-0x100+2] = new_bytes
        fixups.append({'kind':kind,'site_ip':site,'file_offset':site-0x100,'expected_hex':expected_bytes.hex(),'new_hex':new_bytes.hex(),'target_port':target if kind != 'data-immediate' else None,'target_ip':new})
    raw = bytes(out)
    for occurrence in occurrences:
        start = occurrence['output_ip'] - 0x100
        occurrence['bytes'] = raw[start:start + occurrence['size']].hex()
    result = {'format':'fdisbull-dos-com-compilation-1','target':'dos-com16-i386','bytes':raw.hex(),'sha256':sha256(raw).hexdigest(),'entry_ip':0x100,'entry_port':entry,'ports':ports,
              'data':[{'id':d['id'],'ip':d['ip'],'file_offset':d['ip']-0x100,'size':len(d['raw']),'sha256':sha256(d['raw']).hexdigest()} for d in data_by_id.values()],
              'occurrences':occurrences,'fixups':fixups,'fixed_memory_accesses':fixed_reads,'register_memory_obligation':dynamic_seen,
              'qualification':'structural_only','native_execution':False,'assumptions':deepcopy(assumptions),
              'abi':{'cpu':'i386+','cs_ds_es_ss':'equal','stack_reserved':[0xf000,0x10000],'file_offset_to_ip':0x100},
              'source_capsule_sha256':capsule['sha256'],'plan_sha256':plan['sha256']}
    result['output_ranges'] = ([{'kind':'bootstrap','start_ip':0x100,'end_ip':0x103}]
        + [{'kind':'data','id':d['id'],'start_ip':d['ip'],'end_ip':d['ip']+len(d['raw'])} for d in data_by_id.values()]
        + [{'kind':'code','group':gid,'start_ip':ports[gid],'end_ip':ports[gid]+prepared[gid]['size']} for gid in block_order])
    occupied = sorted(result['output_ranges'], key=lambda item: item['start_ip'])
    cursor = 0x100
    for item in occupied:
        if cursor < item['start_ip']:
            result['output_ranges'].append({'kind':'zero_padding','start_ip':cursor,'end_ip':item['start_ip']})
        cursor = item['end_ip']
    result['output_ranges'].sort(key=lambda item: item['start_ip'])
    result['layout_sha256'] = digest(result)
    return result
