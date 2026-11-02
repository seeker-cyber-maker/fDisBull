"""Entry-qualified grouping of captured native instructions.

Grouping retains original source encodings; it does not relocate or lift them.
"""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256

import iced_x86 as ix

from .code_backings import FORMAT, digest, materialize_code_backing


FORMAT_BLOCKS = 'fdisbull-native-block-plan-1'


def materialize_code_block(block):
    """Verify and return an independent block's original local encoding."""
    if not isinstance(block, dict) or digest({k: v for k, v in block.items() if k != 'block_revision'}) != block.get('block_revision'):
        raise ValueError('block revision integrity mismatch')
    try:
        raw = bytes.fromhex(block['bytes'])
        occurrences = block['occurrences']
        instructions = block['instructions']
        revisions = block['instruction_revisions']
        bits = block['bits']
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('invalid block encoding') from error
    if (block.get('isa') != 'x86' or type(bits) is not int or bits not in (16, 32)
            or not isinstance(occurrences, list) or not occurrences
            or not isinstance(instructions, list) or not isinstance(revisions, list)
            or len(occurrences) != len(instructions) or len(occurrences) != len(revisions)
            or len(set(instructions)) != len(instructions)
            or sha256(raw).hexdigest() != block.get('sha256')):
        raise ValueError('invalid block encoding or instruction list')
    cursor = 0
    for index, occurrence in enumerate(occurrences):
        if not isinstance(occurrence, dict):
            raise ValueError('invalid source occurrence')
        size = occurrence.get('size')
        if (occurrence.get('instruction') != instructions[index]
                or occurrence.get('backing_revision') != revisions[index]
                or type(occurrence.get('local_offset')) is not int
                or occurrence['local_offset'] != cursor or type(size) is not int
                or not 1 <= size <= 15 or cursor + size > len(raw)):
            raise ValueError('invalid instruction occurrence boundary')
        instruction = ix.Decoder(bits, raw[cursor:cursor + size]).decode()
        if instruction.is_invalid or instruction.len != size:
            raise ValueError('occurrence is not one complete native instruction')
        cursor += size
    if cursor != len(raw):
        raise ValueError('block has unaccounted encoding bytes')
    return raw


def group_code_backings(document, *, split_at=None):
    """Group a capsule's explicit straight-line paths without inventing edges."""
    if not isinstance(document, dict) or document.get('format') != FORMAT:
        raise ValueError('expected a code-backing capsule')
    if digest({k: v for k, v in document.items() if k != 'sha256'}) != document.get('sha256'):
        raise ValueError('code-backing capsule integrity mismatch')
    atoms = document.get('blocks')
    entries = document.get('entries')
    if not isinstance(atoms, list) or not isinstance(entries, list):
        raise ValueError('invalid capsule graph')
    by_id = {}
    for atom in atoms:
        if not isinstance(atom, dict) or not isinstance(atom.get('id'), str) or atom['id'] in by_id:
            raise ValueError('invalid or duplicate atom identity')
        materialize_code_backing(atom)
        if not isinstance(atom.get('context'), str) or not isinstance(atom.get('address'), str):
            raise ValueError('invalid atom context or address')
        try:
            addr = int(atom['address'], 16)
        except ValueError as error:
            raise ValueError('invalid atom address') from error
        if addr < 0 or atom['address'] != hex(addr):
            raise ValueError('invalid atom address')
        if not isinstance(atom.get('exits'), list) or not isinstance(atom.get('incoming'), list):
            raise ValueError('invalid atom edges')
        by_id[atom['id']] = atom
    if any(not isinstance(entry, str) for entry in entries) or len(set(entries)) != len(entries):
        raise ValueError('invalid entries')
    if split_at is None:
        split_at = []
    if (not isinstance(split_at, (list, tuple)) or any(not isinstance(x, str) or x not in by_id for x in split_at)
            or len(set(split_at)) != len(split_at)):
        raise ValueError('split_at requires distinct captured instruction IDs')
    split_at = sorted(split_at)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    problems = deepcopy(document.get('unresolved', []))
    if not isinstance(problems, list) or type(document.get('complete')) is not bool:
        raise ValueError('invalid capsule completeness')
    for atom in atoms:
        for edge in atom['exits']:
            if not isinstance(edge, dict) or not isinstance(edge.get('kind'), str) or not isinstance(edge.get('target'), str):
                raise ValueError('invalid explicit exit')
            outgoing[atom['id']].append(edge)
            incoming[edge['target']].append((atom['id'], edge))
            if edge['target'] not in by_id:
                problems.append({'kind': 'missing_target', 'source': atom['id'], 'target': edge['target']})
        for edge in atom['incoming']:
            if not isinstance(edge, dict) or not isinstance(edge.get('source'), str) or not isinstance(edge.get('kind'), str) or edge.get('target') != atom['id']:
                raise ValueError('invalid incoming evidence')
        if atom.get('flow') == 'next' and (len(atom['exits']) != 1 or atom['exits'][0]['kind'] != 'fallthrough'):
            problems.append({'kind': 'incomplete_fallthrough', 'instruction': atom['id']})
        kinds = ['branch' if edge['kind'] == 'resolved_branch' else edge['kind'] for edge in atom['exits']]
        expected = {'jump': ['branch'], 'conditional': ['branch', 'fallthrough']}.get(atom.get('flow'))
        if expected is not None and sorted(kinds) != sorted(expected):
            problems.append({'kind': 'incomplete_control_flow', 'instruction': atom['id']})
    leaders = set(entries) | set(split_at)
    for atom in atoms:
        ident = atom['id']
        arriving = incoming[ident]
        if len(arriving) != 1 or any(edge['kind'] != 'fallthrough' for _, edge in arriving):
            leaders.add(ident)
        if any(edge['source'] not in by_id for edge in atom['incoming']):
            leaders.add(ident)
        if atom.get('flow') != 'next' or len(outgoing[ident]) != 1:
            leaders.update(edge['target'] for edge in outgoing[ident])
    for entry in entries:
        if entry not in by_id:
            problems.append({'kind': 'missing_entry', 'entry': entry})

    def order_key(ident):
        atom = by_id[ident]
        return (atom['context'], int(atom['address'], 16), ident)

    assigned, groups = {}, []
    def consume(first):
        members, current = [], first
        while current not in assigned:
            atom = by_id[current]
            assigned[current] = 'block:' + first
            members.append(current)
            edges = outgoing[current]
            if atom.get('flow') != 'next' or len(edges) != 1 or edges[0]['kind'] != 'fallthrough':
                break
            target = edges[0]['target']
            if target not in by_id or target in leaders or target in assigned:
                break
            next_atom = by_id[target]
            if (atom['context'] != next_atom['context'] or atom['bits'] != next_atom['bits']
                    or int(atom['address'], 16) + atom['instruction']['size'] != int(next_atom['address'], 16)):
                break
            current = target
        groups.append(members)
    for ident in sorted((set(by_id) & leaders), key=order_key):
        if ident not in assigned:
            consume(ident)
    for ident in sorted(by_id, key=order_key):
        if ident not in assigned:
            consume(ident)
    result = []
    for members in groups:
        first = by_id[members[0]]
        chunks, occurrences, exits, inbound = [], [], [], []
        offset = 0
        internal = set(zip(members, members[1:]))
        for ident in members:
            atom = by_id[ident]
            raw = materialize_code_backing(atom)
            chunks.append(raw)
            occurrences.append({'instruction': ident, 'backing_revision': atom['backing_revision'],
                                'source_address': atom['address'], 'local_offset': offset,
                                'size': len(raw), 'provenance': deepcopy(atom['provenance'])})
            offset += len(raw)
            for edge in atom['incoming']:
                if (edge['source'], ident) not in internal or edge['kind'] != 'fallthrough':
                    inbound.append(deepcopy(edge))
            for edge in outgoing[ident]:
                if (ident, edge['target']) not in internal or edge['kind'] != 'fallthrough':
                    exits.append({'source_instruction': ident, 'kind': edge['kind'],
                                  'target_instruction': edge['target'], 'target_block': assigned.get(edge['target']),
                                  'evidence': deepcopy(edge.get('evidence')), 'provenance': deepcopy(edge.get('provenance'))})
        raw = b''.join(chunks)
        block = {'id': 'block:' + members[0], 'entry': members[0], 'context': first['context'],
                 'isa': first['isa'], 'bits': first['bits'], 'instructions': members,
                 'instruction_revisions': [by_id[ident]['backing_revision'] for ident in members],
                 'bytes': raw.hex(), 'sha256': sha256(raw).hexdigest(), 'occurrences': occurrences,
                 'incoming': inbound, 'exits': exits}
        block['block_revision'] = digest(block)
        materialize_code_block(block)
        result.append(block)
    plan = {'format': FORMAT_BLOCKS, 'source_document_sha256': document['sha256'],
            'entries': {entry: assigned.get(entry) for entry in entries}, 'atom_blocks': assigned,
            'blocks': result, 'complete': document['complete'] and not problems,
            'unresolved': problems, 'split_at': split_at,
            'source_layout_modified': False, 'group_placement': 'unplaced'}
    plan['sha256'] = digest(plan)
    return plan
