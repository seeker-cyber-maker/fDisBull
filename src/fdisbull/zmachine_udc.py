"""Bounded, source-backed Z-machine v3 scalar experiments; no VM execution."""
from __future__ import annotations

import hashlib
import json
from .processor import Location
from .zmachine_processor import ZMachineV3Processor
from .zmachine import MAX_STORY_FILE

_FORMAT = 'fdisbull-zmachine-udc-1'
_ALLOWED = frozenset(('add', 'sub', 'mul', 'div', 'mod', 'or', 'and'))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _hex_bytes(value, label, *, max_bytes=4):
    if (not isinstance(value, str) or len(value) > 2 * max_bytes
            or len(value) % 2 or any(c not in '0123456789abcdef' for c in value)):
        raise ValueError(f'{label} must be canonical lowercase hex')
    return bytes.fromhex(value)


def _catalog(processor, limit):
    info = processor.story_info
    data = processor.program
    dictionary = info['dictionary']
    pos = dictionary + 1 + data[dictionary]
    count = abs(int.from_bytes(data[pos + 1:pos + 3], 'big', signed=True))
    protected = [(info['abbreviations'], info['abbreviations'] + 192),
                 (dictionary, pos + 3 + count * data[pos])]
    rows = []
    offset = info['initial_pc']
    for _ in range(limit):
        if offset < info['high_memory'] or offset >= info['declared_bytes']:
            break
        try:
            ins = processor.decode(processor.program, Location(processor.info.address_space, offset))
        except ValueError:
            break
        if ins is None:
            break
        row = ins.facts
        if any(offset < end and start < row['end'] for start, end in protected):
            break
        rows.append({'offset': offset, 'bytes': row['bytes']})
        if row['flow'] != 'next':
            break
        offset = row['end']
    return rows


def capture_zmachine_definition(story: bytes, *, max_instructions: int = 10000) -> dict:
    """Capture a checksum-qualified story and bounded initial fallthrough evidence."""
    if type(max_instructions) is not int or not 1 <= max_instructions <= 10000:
        raise ValueError('max_instructions must be in 1..10000')
    p = ZMachineV3Processor(story)
    doc = {'format': _FORMAT, 'source_sha256': p.story_info['sha256'],
           'version': 3, 'story_hex': story.hex(), 'max_instructions': max_instructions,
           'instructions': _catalog(p, max_instructions)}
    doc['sha256'] = _digest(doc)
    return doc


def _validate(definition):
    if not isinstance(definition, dict) or set(definition) != {
            'format', 'source_sha256', 'version', 'story_hex', 'max_instructions', 'instructions', 'sha256'}:
        raise ValueError('invalid definition')
    try:
        content = {k: v for k, v in definition.items() if k != 'sha256'}
        if _digest(content) != definition['sha256']:
            raise ValueError('definition digest differs')
        story = _hex_bytes(definition['story_hex'], 'story', max_bytes=MAX_STORY_FILE)
        actual = capture_zmachine_definition(story, max_instructions=definition['max_instructions'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('invalid or corrupt definition') from exc
    if definition != actual:
        raise ValueError('stale or corrupt definition')
    return story


def compile_zmachine_definition(definition: dict, *, edits=None, mode='original-layout', assumptions=None) -> dict:
    """Emit exact bytes or apply explicit, same-footprint scalar experiments.

    This proves no runtime behavior and writes no host file. Expected and
    replacement bytes cover whole instructions, not arbitrary byte ranges.
    """
    source = _validate(definition)
    if mode not in ('original-layout', 'experiment'):
        raise ValueError('unsupported mode')
    if mode == 'original-layout' and (edits is not None or assumptions is not None):
        raise ValueError('original-layout does not accept edit arguments')
    if mode == 'experiment':
        if (not isinstance(assumptions, dict) or set(assumptions) != {'no_code_data_alias', 'scalar_values_not_addresses'}
                or any(value is not True for value in assumptions.values())):
            raise ValueError('experiment requires no_code_data_alias and scalar_values_not_addresses assertions')
        if not isinstance(edits, list) or not 1 <= len(edits) <= 256:
            raise ValueError('experiment requires 1..256 edits')
    else:
        edits = []
    p = ZMachineV3Processor(source)
    catalog = {row['offset']: row['bytes'] for row in definition['instructions']}
    out = bytearray(source)
    seen = set()
    selected = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'offset', 'expected_hex', 'replacement_hex'}:
            raise ValueError('invalid edit')
        offset = edit['offset']
        if type(offset) is not int or offset not in catalog or offset in seen:
            raise ValueError('edit must select a distinct captured instruction')
        old = _hex_bytes(edit['expected_hex'], 'expected bytes')
        new = _hex_bytes(edit['replacement_hex'], 'replacement bytes')
        if old.hex() != catalog[offset] or len(new) != len(old):
            raise ValueError('stale expected bytes or changed footprint')
        row = p.decode(p.program, Location(p.info.address_space, offset)).facts
        # Only 2OP long-form scalar operations: opcode and store byte remain fixed;
        # small-constant operand bytes may change, while variable operands may not.
        if row['op'] not in _ALLOWED or old[0] >= 0x80 or len(old) != 4 or old[0] != new[0] or old[-1] != new[-1]:
            raise ValueError('unsupported instruction or encoding change')
        if any(old[i + 1] != new[i + 1] and operand['kind'] != 'small'
               for i, operand in enumerate(row['operands'])):
            raise ValueError('only scalar small constants may change')
        if old == new:
            raise ValueError('replacement must change a scalar constant')
        out[offset:offset + len(old)] = new
        seen.add(offset)
        selected.append(dict(edit, replacement_sha256=hashlib.sha256(new).hexdigest()))
    if edits:
        length = p.story_info['declared_bytes']
        out[28:30] = (sum(out[64:length]) & 0xffff).to_bytes(2, 'big')
        final = ZMachineV3Processor(bytes(out))
        for edit in selected:
            at = edit['offset']
            before = p.decode(p.program, Location(p.info.address_space, at)).facts
            after = final.decode(final.program, Location(final.info.address_space, at)).facts
            for key in ('op', 'offset', 'end', 'flow', 'store'):
                if before.get(key) != after.get(key):
                    raise ValueError('replacement changed instruction interface')
            if [v['kind'] for v in before['operands']] != [v['kind'] for v in after['operands']]:
                raise ValueError('replacement changed operand kinds')
    result = bytes(out)
    return {'format': 'fdisbull-zmachine-udc-compilation-1', 'mode': mode,
            'definition_sha256': definition['sha256'], 'source_sha256': definition['source_sha256'],
            'output_sha256': hashlib.sha256(result).hexdigest(), 'bytes': result.hex(),
            'byte_identity': result == source, 'edits': selected,
            'qualification': 'original_bytes_only' if not edits else 'unverified_experiment',
            'native_execution': False, 'equivalence_proven': False,
            'bounds': 'Initial straight-line decoded candidates only; code/data alias assertion is caller supplied.'}
