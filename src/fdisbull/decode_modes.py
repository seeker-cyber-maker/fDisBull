"""Versioned object decode modes; preferred addresses are not runtime selectors."""
from __future__ import annotations

from .processor import DecodedInstruction, Location, ProcessorInfo, Successor


def validate_regions(items, regions, objects=None):
    """Admit complete, nonoverlapping object mode declarations, never guesses."""
    if not isinstance(items, list):
        raise ValueError('decode_regions must be a list')
    expected = {(r.start, r.start + len(r.data)) for r in regions if r.data}
    seen, result = set(), []
    for original in items:
        if not isinstance(original, dict):
            raise ValueError('invalid decode region')
        item = dict(original)
        if any(type(item.get(k)) is not int for k in ('start', 'end', 'bits', 'object_index', 'object_offset')):
            raise ValueError('decode region fields must be integers')
        start, end = item['start'], item['end']
        if ((start, end) not in expected or (start, end) in seen
                or item['bits'] not in (16, 32) or item['object_index'] < 1
                or item['object_offset'] != 0):
            raise ValueError('invalid or incomplete LE decode region mapping')
        seen.add((start, end))
        result.append(item)
    if seen != expected or len({x['object_index'] for x in result}) != len(result):
        raise ValueError('decode regions must cover each mapped object exactly once')
    if objects is not None:
        declarations = {obj['index']: obj for obj in objects}
        for item in result:
            obj = declarations.get(item['object_index'])
            if obj is None or (item['start'], item['end'], item['bits']) != (
                    obj['virtual_address'], obj['virtual_address'] + obj['virtual_size'], obj['bits']):
                raise ValueError('decode region disagrees with its declared LE object')
    return sorted(result, key=lambda x: x['start'])


def memory_accesses(raw, address, mode, fixups=()):
    """LE-16 accesses retain expressions but no real-mode selector arithmetic."""
    from .memory import instruction_memory_accesses
    bits = mode['bits']
    ip = address - mode['start'] if bits == 16 else address
    facts = instruction_memory_accesses(raw, ip, 'x86', bits)
    if bits == 16:
        for fact in facts:
            for field in ('segment_selector', 'concrete_target', 'interval_start', 'interval_end', 'possible_start', 'possible_end'):
                fact[field] = None
            fact['interval_exact'] = False
            fact['unresolved_reasons'] = [reason.replace('real-mode physical address', 'LE object address')
                                         .replace('real-mode segment', 'LE runtime selector')
                                         for reason in fact['unresolved_reasons']]
            fact['unresolved_reasons'].append('LE runtime selector bindings are unavailable in static analysis')
            fact['le_object_index'] = mode['object_index']
    for fact in facts:
        fact['decoder_bits'] = bits
        if any(item.get('applied') is False for item in fixups):
            for field in ('segment_selector', 'concrete_target', 'interval_start', 'interval_end', 'possible_start', 'possible_end'):
                fact[field] = None
            fact['interval_exact'] = False
            fact['operand_status'] = 'symbolic_unapplied_fixup'
            fact['le_fixups'] = list(fixups)
            fact['unresolved_reasons'].append('Original operand overlaps an unapplied symbolic LE fixup; encoded value is not a resolved address')
    return facts


class LEProcessor:
    """Decode one LE object at a time, rebasing only qualified near targets."""
    def __init__(self, metadata, modes):
        self.info = ProcessorInfo('fdisbull.native.x86.le.objects', '1', 'le.preferred', 'byte',
                                  ('decode', 'static_successors', 'object_decode_modes'), None)
        self.metadata, self.modes = metadata, modes
        self.objects = {x['index']: x for x in metadata['objects']}
        self.fixup_sites = {}
        for index, fixup in enumerate(metadata['fixups']):
            for byte in range(fixup['address'], fixup['address'] + fixup['width']):
                self.fixup_sites.setdefault(byte, []).append(index)
        intervals = []
        for page in metadata['pages']:
            if page['file_size']:
                start = self.objects[page['object']]['virtual_address'] + page['object_offset']
                intervals.append((start, start + page['file_size']))
        self.backed = []
        for start, end in sorted(intervals):
            if self.backed and self.backed[-1][1] == start and self.mode_at(self.backed[-1][0]) == self.mode_at(start):
                self.backed[-1] = (self.backed[-1][0], end)
            else:
                self.backed.append((start, end))
        self.last_failure = None

    def mode_at(self, address):
        return next((x for x in self.modes if x['start'] <= address < x['end']), None)

    def fixups_for(self, address, size):
        indices = {index for byte in range(address, address + size)
                   for index in self.fixup_sites.get(byte, ())}
        return [dict(self.metadata['fixups'][index]) for index in sorted(indices)]

    def following(self, address, size):
        mode = self.mode_at(address)
        following = address + size
        if mode is None or not address < following < mode['end']:
            return None
        if mode['bits'] == 16 and following - mode['start'] >= 65536:
            return None
        if not any(start <= following < end for start, end in self.backed):
            return None
        return following

    def decode(self, program, location):
        from .decoder import decode
        self.last_failure = None
        address = location.offset
        mode = self.mode_at(address)
        if mode is None:
            return None
        backed_end = next((end for start, end in self.backed if start <= address < end), address)
        remaining = min(mode['end'] - address, backed_end - address)
        if remaining <= 0:
            self.last_failure = 'LE object has no file-backed instruction bytes at this address'
            return None
        raw = program[:min(15, remaining)]
        bits = mode['bits']
        offset = address - mode['start']
        facts = decode(raw, offset if bits == 16 else address, 'x86', bits)
        if facts is None:
            return None
        facts.update(address=address, decoder_bits=bits, decoder_context=f'x86:{bits}:little',
                     le_object_index=mode['object_index'], le_object_offset=offset,
                     next_address=self.following(address, facts['size']))
        facts['le_fixups'] = self.fixups_for(address, facts['size'])
        symbolic = [item for item in facts['le_fixups'] if item.get('applied') is False]
        if symbolic:
            # An unfixed operand is preserved source text, not a known target.
            # If it occupies instruction structure, even instruction identity
            # is unresolved; do not reinterpret the source bytes as an opcode.
            import iced_x86 as ix
            native = ix.Decoder(bits, raw, ip=offset if bits == 16 else address)
            instruction = native.decode()
            constants = native.get_constant_offsets(instruction)
            operands = set()
            for begin, size in ((constants.displacement_offset, constants.displacement_size),
                                (constants.immediate_offset, constants.immediate_size),
                                (constants.immediate_offset2, constants.immediate_size2)):
                operands.update(range(address + begin, address + begin + size))
            for item in symbolic:
                overlap = set(range(max(address,item['address']),min(address+facts['size'],item['address']+item['width'])))
                if overlap - operands:
                    self.last_failure = 'unapplied symbolic LE fixup overlaps instruction structure; decoder identity and successors are unknown'
                    return None
            facts['operand_status'] = 'symbolic_unapplied_fixup'
            facts['issue'] = 'operand overlaps unapplied symbolic LE fixup; encoded operand is not a resolved runtime value'
        target = facts['target']
        evidence = 'decoded relative transfer in LE preferred object address space'
        if bits == 16:
            # An immediate/data offset is not a preferred linear address.
            facts['immediates'], facts['data_refs'] = [], []
            facts['references'] = [r for r in facts['references'] if r['role'] == 'code']
            target = mode['start'] + target if target is not None else None
            if target is not None and not mode['start'] <= target < mode['end']:
                target = None
                facts['issue'] = 'LE16 near target is outside its declared object; runtime selector remains unknown'
            evidence = 'native object-local LE16 relative target rebased within the same declared object; no runtime selector claimed'
        destination = self.mode_at(target) if target is not None else None
        if target is not None and destination is not None and destination['bits'] != bits:
            target = None
            facts['issue'] = 'LE near transfer does not qualify a change of runtime code-selector mode'
        if target is None and facts['flow'] in ('call', 'jump'):
            facts['flow'] = 'indirect_call' if facts['flow'] == 'call' else 'indirect_jump'
        if symbolic:
            target = None
            facts['references'], facts['data_refs'], facts['immediates'] = [], [], []
            if facts['flow'] in ('call', 'jump'):
                facts['flow'] = 'indirect_call' if facts['flow'] == 'call' else 'indirect_jump'
        facts['target'] = target
        facts['references'] = [r for r in facts['references'] if r['role'] != 'code']
        edges = []
        if target is not None:
            facts['references'].append(dict(operand_index=0, role='code', target=target, width=bits // 8))
            edges.append(Successor('call' if facts['flow'] == 'call' else 'branch', Location(location.space, target), evidence))
        elif facts['flow'] in ('call', 'jump', 'conditional', 'indirect_call', 'indirect_jump'):
            edges.append(Successor('call' if facts['flow'] in ('call', 'indirect_call') else 'branch', None,
                                   'unresolved LE target; runtime selectors and mode changes are not inferred'))
        if facts['flow'] in ('next', 'call', 'conditional', 'indirect_call') and facts['next_address'] is not None:
            edges.append(Successor('fallthrough', Location(location.space, facts['next_address']), 'LE same-object fallthrough; call return assumed where applicable'))
        return DecodedInstruction(location, facts, tuple(edges))
