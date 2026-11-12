"""Bounded entry-qualified x86 layout. Structural output, not a proof or executable writer."""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import re

import iced_x86 as ix

from .decoder import decode

_REQUIRED = ('no_code_reads', 'no_code_writes', 'no_computed_entries',
             'address_identity_unobserved', 'timing_unobserved')
_HEX = re.compile(r'[0-9a-f]{64}\Z')


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('document must contain finite JSON') from exc


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _address(value):
    if not isinstance(value, str):
        raise ValueError('address must be canonical hexadecimal')
    try:
        n = int(value, 16)
    except ValueError as exc:
        raise ValueError('invalid address') from exc
    if n < 0 or hex(n) != value:
        raise ValueError('address must be canonical hexadecimal')
    return n


def _identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError('invalid node identity')
    return value


def _source_target(address, value, context, bits):
    match = re.search(r':cs=([0-9a-fA-F]{4})\Z', context)
    if match:
        if bits != 16:
            raise ValueError('CS context is supported only in 16-bit mode')
        return int(match.group(1), 16) * 16 + (value & 0xffff)
    return value & ((1 << bits) - 1)


def compile_code_backings(document, *, order=None, base=0, assumptions=None, entry_references=None):
    """Lay out admitted entries with explicit jumps; returns structural evidence only.

    Caller assumptions are assertions, not observations or proven invariants.
    The result is raw code, not a container, emulator result, or semantic proof.
    """
    if not isinstance(document, dict) or document.get('format') != 'fdisbull-code-backings-1':
        raise ValueError('invalid backing document')
    claimed = document.get('sha256')
    if not isinstance(claimed, str) or not _HEX.fullmatch(claimed) or _hash(_canonical({k: v for k, v in document.items() if k != 'sha256'})) != claimed:
        raise ValueError('backing document digest mismatch')
    if document.get('complete') is not True or document.get('unresolved') != []:
        raise ValueError('incomplete or unresolved graph')
    source = document.get('source')
    if not isinstance(source, dict) or source.get('arch') != 'x86' or source.get('bits') not in (16, 32) or type(source.get('bits')) is not int or type(source.get('version')) is not int or source['version'] < 1:
        raise ValueError('unsupported source profile')
    if any(not isinstance(source.get(k), str) or not _HEX.fullmatch(source[k]) for k in ('source_sha256', 'version_sha256')):
        raise ValueError('invalid source identity')
    bits = source['bits']; limit = 1 << bits
    if type(base) is not int or not 0 <= base < limit:
        raise ValueError('base outside output address space')
    if not isinstance(assumptions, dict) or set(assumptions) != set(_REQUIRED) or any(assumptions[k] is not True for k in _REQUIRED):
        raise ValueError('all explicit layout assumptions must be true')
    blocks = document.get('blocks'); entries = document.get('entries')
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 4096 or not isinstance(entries, list) or not entries or len(entries) > 4096:
        raise ValueError('invalid graph size')
    nodes = {}; context = None; source_bytes = {}
    for block in blocks:
        if not isinstance(block, dict): raise ValueError('invalid block')
        ident = _identifier(block.get('id'))
        if ('isa' in block and block['isa'] != 'x86') or ('bits' in block and (type(block['bits']) is not int or block['bits'] != bits)):
            raise ValueError('block ISA or mode mismatch')
        revision = block.get('backing_revision')
        if revision is not None and (not isinstance(revision, str) or not _HEX.fullmatch(revision) or _hash(_canonical({k: v for k, v in block.items() if k != 'backing_revision'})) != revision):
            raise ValueError('backing revision digest mismatch')
        if ident in nodes: raise ValueError('duplicate node')
        addr = _address(block.get('address')); ctx = block.get('context')
        if not isinstance(ctx, str) or len(ctx) > 256 or not (ctx == f'x86:{bits}:little' or (bits == 16 and re.fullmatch(r'x86:16:little:cs=[0-9a-fA-F]{4}', ctx))): raise ValueError('invalid or mixed-mode context')
        if context is None: context = ctx
        if ctx != context: raise ValueError('mixed contexts unsupported')
        value = block.get('bytes')
        if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-f]{2}){1,15}', value): raise ValueError('invalid instruction bytes')
        raw = bytes.fromhex(value)
        if block.get('sha256') != _hash(raw): raise ValueError('instruction digest mismatch')
        prov = block.get('provenance')
        if not isinstance(prov, dict) or prov.get('address') != hex(addr) or type(prov.get('size')) is not int or prov.get('size') != len(raw) or prov.get('source_sha256') != source['source_sha256'] or prov.get('version_sha256') != source['version_sha256'] or prov.get('context') != ctx:
            raise ValueError('source provenance mismatch')
        for i, byte in enumerate(raw):
            if addr+i in source_bytes and source_bytes[addr+i] != byte: raise ValueError('conflicting overlapping source bytes')
            source_bytes[addr+i] = byte
        match = re.search(r':cs=([0-9a-fA-F]{4})\Z', ctx)
        if ':cs=' in ctx and not match: raise ValueError('invalid CS context')
        if match:
            if bits != 16 or not 0 <= addr - int(match.group(1),16)*16 <= 0xffff or addr - int(match.group(1),16)*16 + len(raw) > 0x10000: raise ValueError('address outside nonwrapping CS context')
            ip = addr - int(match.group(1),16)*16
        else:
            if addr >= limit or addr + len(raw) > limit: raise ValueError('source address outside nonwrapping mode')
            ip = addr
        facts = decode(raw, ip, 'x86', bits)
        ins = ix.Decoder(bits, raw, ip=ip).decode()
        if facts is None or facts['size'] != len(raw): raise ValueError('instruction bytes are not one complete decode')
        instruction = block.get('instruction')
        if not isinstance(instruction, dict) or not isinstance(instruction.get('mnemonic'),str) or not isinstance(instruction.get('operands'),str) or type(instruction.get('size')) is not int or instruction['size'] != facts['size'] or block.get('flow') != facts['flow']:
            raise ValueError('instruction facts differ from native decoder')
        if ins.is_ip_rel_memory_operand: raise ValueError('IP-relative memory unsupported')
        flow = facts['flow']
        if flow not in ('next','jump','conditional','return','stop') or ins.flow_control in (ix.FlowControl.INTERRUPT, ix.FlowControl.XBEGIN_XABORT_XEND):
            raise ValueError('unsupported control flow')
        kind = None
        if flow == 'jump':
            if raw[0] not in (0xeb, 0xe9) or len(raw) != (2 if raw[0] == 0xeb else 1 + bits//8): raise ValueError('unsupported jump encoding')
            kind = 'jump'
        elif flow == 'conditional':
            if 0x70 <= raw[0] <= 0x7f and len(raw) == 2: cc = raw[0] & 15
            elif len(raw) == 2 + bits//8 and raw[0] == 0x0f and 0x80 <= raw[1] <= 0x8f: cc = raw[1] & 15
            else: raise ValueError('unsupported conditional encoding')
            kind = 'conditional'
        elif flow == 'return' and raw[0] not in (0xc2, 0xc3):
            raise ValueError('far or unsupported return')
        exits = block.get('exits'); refs = block.get('references')
        if not isinstance(exits, list) or not isinstance(refs, list): raise ValueError('invalid edges or references')
        edges = {}
        for edge in exits:
            if not isinstance(edge, dict): raise ValueError('invalid edge')
            k = edge.get('kind'); k = 'branch' if k == 'resolved_branch' else k
            if not isinstance(k,str) or k not in ('branch','fallthrough') or k in edges: raise ValueError('invalid or duplicate exit')
            edges[k] = _identifier(edge.get('target'))
        expected = {'next': {'fallthrough'}, 'jump': {'branch'}, 'conditional': {'branch','fallthrough'}, 'return': set(), 'stop': set()}[flow]
        if set(edges) != expected: raise ValueError('exit ports do not match decoded flow')
        nodes[ident] = {'block': block, 'raw': raw, 'address': addr, 'facts': facts, 'ins': ins, 'flow': flow, 'kind': kind, 'edges': edges, 'cc': cc if kind == 'conditional' else None}
    if any(_identifier(e) not in nodes for e in entries) or len(set(entries)) != len(entries): raise ValueError('invalid entries')
    for node in nodes.values():
        for k, target in node['edges'].items():
            if target not in nodes: raise ValueError('missing edge target')
            expected = node['facts']['target'] if k == 'branch' else (node['address'] + len(node['raw']))
            if k == 'branch': expected = _source_target(node['address'], expected, context, bits)
            elif ':cs=' in context:
                match = re.search(r':cs=([0-9a-fA-F]{4})\Z', context)
                if not match: raise ValueError('invalid CS context')
                seg = int(match.group(1),16)*16; expected = seg + ((node['address']-seg+len(node['raw'])) & 0xffff)
            else: expected &= limit-1
            if nodes[target]['address'] != expected: raise ValueError('edge target differs from decoded control flow')
        ins = node['ins']
        if any(ins.op_kind(i) == ix.OpKind.MEMORY for i in range(ins.op_count)) and ins.memory_base == ix.Register.NONE and ins.memory_index == ix.Register.NONE:
            width = ix.MemorySizeExt.size(ins.memory_size) or 1
            target = ins.memory_displacement
            segmatch = re.search(r':cs=([0-9a-fA-F]{4})\Z', context)
            if segmatch and ins.memory_segment == ix.Register.CS: target += int(segmatch.group(1), 16) * 16
            if any(target + i in source_bytes for i in range(width)): raise ValueError('direct memory reference aliases source code')
        for ref in node['block']['references']:
            if not isinstance(ref, dict): raise ValueError('invalid reference')
            if ref.get('role') in ('memory','address','data') and ref.get('target') is not None:
                v = ref['target']; v = _address(v) if isinstance(v,str) else v
                if type(v) is not int or v < 0: raise ValueError('invalid reference target')
                width=ref.get('width') or 1
                if type(width) is not int or not 1 <= width <= 64: raise ValueError('invalid reference width')
                if any(v + i in source_bytes for i in range(width)): raise ValueError('direct reference aliases source code')
    sequence = list(nodes) if order is None else order
    if not isinstance(sequence, list) or len(sequence) != len(nodes) or any(not isinstance(x,str) for x in sequence) or len(set(sequence)) != len(nodes) or set(sequence) != set(nodes): raise ValueError('order must contain every node exactly once')
    jump_size = 1 + bits//8; locations = {}; cursor = base
    for ident in sequence:
        n = nodes[ident]; locations[ident] = cursor
        n['length'] = (jump_size if n['kind']=='jump' else 2+bits//8 if n['kind']=='conditional' else len(n['raw'])) + (jump_size if n['flow'] in ('next','conditional') else 0)
        cursor += n['length']
        if cursor > limit: raise ValueError('output crosses nonwrapping address boundary')
    def jump(dest, end):
        delta = locations[dest] - end; low = -(1 << (bits-1)); high = (1 << (bits-1))-1
        if not low <= delta <= high: raise ValueError('branch displacement out of range')
        return delta.to_bytes(bits//8,'little',signed=True)
    result = bytearray(); occurrences = []; glue = []; fixups = []
    for ident in sequence:
        n=nodes[ident]; at=locations[ident]; flow=n['flow']
        if n['kind']=='jump': code=b'\xe9'+jump(n['edges']['branch'],at+jump_size)
        elif n['kind']=='conditional': code=bytes((0x0f,0x80+n['cc']))+jump(n['edges']['branch'],at+2+bits//8)
        else: code=n['raw']
        occurrences.append({'node':ident,'source_address':hex(n['address']),'source_size':len(n['raw']),'source_provenance':deepcopy(n['block']['provenance']),'backing_revision':n['block'].get('backing_revision') or _hash(_canonical(n['block'])),'output_address':hex(at),'output_size':len(code),'mapping':'copied' if code==n['raw'] else 'rewritten_control_transfer'})
        result.extend(code)
        if n['kind'] in ('jump','conditional'):
            fixups.append({'node':ident,'kind':'branch','instruction_address':hex(at),'target':n['edges']['branch'],'target_address':hex(locations[n['edges']['branch']]),'encoding':code.hex()})
        if flow in ('next','conditional'):
            end=at+len(code)+jump_size; glue_code=b'\xe9'+jump(n['edges']['fallthrough'],end); result.extend(glue_code)
            glue.append({'node':ident,'address':hex(at+len(code)),'size':len(glue_code),'bytes':glue_code.hex(),'target':n['edges']['fallthrough'],'target_address':hex(locations[n['edges']['fallthrough']]),'effects':'unconditional near jump; flags and stack unchanged'})
            fixups.append({'node':ident,'kind':'fallthrough','instruction_address':hex(at+len(code)),'target':n['edges']['fallthrough'],'target_address':hex(locations[n['edges']['fallthrough']]),'encoding':glue_code.hex()})
    references=[];seen=set()
    if entry_references is not None:
        if not isinstance(entry_references,list) or len(entry_references)>4096: raise ValueError('invalid entry references')
        for ref in entry_references:
            if not isinstance(ref,dict) or set(ref)!={'id','kind','target','width'}: raise ValueError('invalid entry reference')
            name=_identifier(ref['id']); target=_identifier(ref['target']); width=ref['width']
            if name in seen or ref['kind'] not in ('pointer','table') or type(width) is not int or width not in (2,4) or target not in nodes or locations[target] >= 1 << (8*width): raise ValueError('unresolved or out-of-range entry reference')
            seen.add(name);references.append({**ref,'value':hex(locations[target]),'bytes':locations[target].to_bytes(width,'little').hex()})
    artifact={'format':'fdisbull-code-layout-1','source_document_sha256':claimed,'arch':'x86','bits':bits,'base':base,'bytes':result.hex(),'entries':{e:locations[e] for e in entries},'occurrences':occurrences,'glue':glue,'fixups':fixups,'source_coverage_bytes':len(source_bytes),'entry_references':references,'assumptions':dict(assumptions),'qualification':'structural_only','bounds':['Caller assumptions are not proved.','No semantic or native execution equivalence is established.','Raw code only; container metadata, external references and computed entries are not repaired.']}
    artifact['sha256']=_hash(_canonical(artifact));return artifact
