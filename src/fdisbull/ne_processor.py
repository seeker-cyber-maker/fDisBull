"""Native x86-16 decoding in a retained NE logical-segment address space."""
from __future__ import annotations

from .ne import following, logical_location
from .processor import DecodedInstruction, Location, ProcessorInfo, Successor


def memory_accesses(raw, address):
    """Retain native memory expressions without fabricating selector bindings."""
    from .memory import instruction_memory_accesses
    facts = instruction_memory_accesses(raw, address & 0xffff, 'x86', 16)
    for fact in facts:
        for field in ('segment_selector', 'concrete_target', 'interval_start', 'interval_end', 'possible_start', 'possible_end'):
            fact[field] = None
        fact['interval_exact'] = False
        fact['unresolved_reasons'] = [reason.replace('real-mode physical address', 'NE logical segment address')
                                     .replace('real-mode segment', 'NE runtime selector')
                                     for reason in fact['unresolved_reasons']]
        fact['unresolved_reasons'].append('NE runtime selector bindings are unavailable in static analysis')
        fact['ne_logical_source'] = logical_location(address)
    return facts


class NEProcessor:
    def __init__(self, metadata):
        self.last_failure = None
        self.info = ProcessorInfo('fdisbull.native.x86.16.ne', '1', 'ne.segment', 'byte',
                                  ('decode', 'static_successors', 'symbolic_ne_fixups'), None)
        self.segments = {s['index']: s for s in metadata['segments']}
        self.sites = {}
        for fixup in metadata['fixups']:
            for source in fixup['sources']:
                self.sites[source['address']] = (fixup, source)

    def decode(self, program: bytes, location: Location) -> DecodedInstruction | None:
        self.last_failure = None
        from .decoder import decode
        address, offset = location.offset, location.offset & 0xffff
        segment = self.segments.get(address >> 16)
        if segment is None or offset >= segment['file_size']:
            return None
        raw = program[:min(15, 65536 - offset, segment['file_size'] - offset)]
        facts = decode(raw, offset, 'x86', 16)
        if facts is None:
            return None
        facts['address'] = address
        facts['logical_location'] = logical_location(address)
        facts['ne_fixups'] = []
        facts['references'] = []
        facts['data_refs'] = []
        facts['immediates'] = []  # A numeric constant is not a packed logical address.
        import iced_x86 as ix
        native = ix.Decoder(16, raw, ip=offset)
        ins = native.decode()
        constants = native.get_constant_offsets(ins)
        operand_bytes = set()
        for begin, size in ((constants.displacement_offset, constants.displacement_size),
                            (constants.immediate_offset, constants.immediate_size),
                            (constants.immediate_offset2, constants.immediate_size2)):
            operand_bytes.update(range(begin, begin + size))
        flow, target = facts['flow'], facts['target']
        evidence = 'native relative branch within the same NE logical segment'
        if target is not None:
            target = (address & ~0xffff) | target if 0 <= target <= 0xffff else None
        # Supported fixups occupy at most four bytes. Include sites beginning
        # before this instruction: entering an operand must not mistake its
        # unrelocated interior bytes for a native opcode.
        for index in range(-3, facts['size']):
            pair = self.sites.get(address + index)
            if pair is None:
                continue
            fixup, source = pair
            width = fixup['source_width']
            overlap = set(range(max(0, index), min(facts['size'], index + width)))
            if not overlap:
                continue
            if fixup['target_kind'] != 'os_fixup' and overlap - operand_bytes:
                self.last_failure = 'unrelocated NE fixup overlaps instruction structure (opcode/prefix/ModRM/SIB); native successors are unknown'
                return None
            original = bytes.fromhex(source['original_bytes'])
            unchanged = 0 <= index and index + width <= facts['size'] and raw[index:index + width] == original
            details = {k: v for k, v in fixup.items() if k != 'sources'}
            details.update(source, operand_bytes_unchanged=unchanged)
            facts['ne_fixups'].append(details)
        if target is not None and facts['ne_fixups']:
            # A relocated branch operand is not its encoded chain/displacement.
            target = None
            flow = 'indirect_call' if flow == 'call' else 'indirect_jump' if flow == 'jump' else flow
        # Iced correctly leaves immediate far calls unresolved. Only a matching
        # source relocation can qualify their cross-segment relationship.
        far = any(ins.op_kind(i) == ix.OpKind.FAR_BRANCH16 for i in range(ins.op_count))
        if far and flow in ('indirect_call', 'indirect_jump'):
            for fixup in facts['ne_fixups']:
                if fixup['target_kind'] != 'internal' or not fixup['operand_bytes_unchanged']:
                    continue
                operand_index = fixup['address'] - address
                consumed = {(fixup['index'], fixup['address'])}
                # NE fixups name the actual far-pointer or selector field. Do
                # not infer a segment from an unfixed operand's numeric value.
                if fixup['source_type_code'] == 3 and operand_index == facts['size'] - 4:
                    off = fixup['target_offset']
                    if fixup['additive']:
                        off = (off + ins.far_branch16) & 0xffff
                elif fixup['source_type_code'] == 2 and operand_index == facts['size'] - 2:
                    if fixup['additive'] and bytes.fromhex(fixup['original_bytes']) != b'\0\0':
                        continue
                    off = ins.far_branch16
                    field_start, field_end = address + facts['size'] - 4, address + facts['size'] - 2
                    offset_fixups = [item for item in facts['ne_fixups']
                                     if item['address'] < field_end and item['address'] + item['source_width'] > field_start]
                    if offset_fixups:
                        if len(offset_fixups) != 1:
                            continue
                        item = offset_fixups[0]
                        if (item['address'] != field_start or item['source_type_code'] != 5
                                or item['target_kind'] != 'internal'
                                or not item['operand_bytes_unchanged']
                                or item['target_segment_index'] != fixup['target_segment_index']):
                            continue
                        consumed.add((item['index'], item['address']))
                        off = item['target_offset']
                        if item['additive']:
                            off = (off + ins.far_branch16) & 0xffff
                else:
                    continue
                if any((item['index'], item['address']) not in consumed for item in facts['ne_fixups']):
                    # Resolve the complete far operand or leave it symbolic.
                    # An ignored low-byte/additive fixup could change either
                    # offset byte despite an otherwise valid selector record.
                    continue
                s = self.segments[fixup['target_segment_index']]
                if off >= s['file_size'] or not s['executable']:
                    continue
                target = s['logical_base'] | off
                flow = 'call' if flow == 'indirect_call' else 'jump'
                evidence = 'validated NE internal far-operand fixup; no runtime selector claimed'
                break
        facts.update(flow=flow, target=target)
        edges = []
        if target is not None:
            facts['references'].append(dict(operand_index=0, role='code', target=target, width=None))
            edges.append(Successor('call' if flow == 'call' else 'branch', Location(location.space, target), evidence))
        elif flow in ('jump', 'conditional', 'call', 'indirect_jump', 'indirect_call'):
            edges.append(Successor('call' if flow in ('call', 'indirect_call') else 'branch', None,
                                   'unresolved NE target; selectors/imports are symbolic'))
        if flow in ('next', 'call', 'conditional', 'indirect_call'):
            next_address = following(address, facts['size'])
            if next_address & 0xffff < segment['file_size']:
                edges.append(Successor('fallthrough', Location(location.space, next_address),
                                       'call return assumed' if flow in ('call', 'indirect_call') else 'NE same-segment fallthrough'))
        return DecodedInstruction(location, facts, tuple(edges))
