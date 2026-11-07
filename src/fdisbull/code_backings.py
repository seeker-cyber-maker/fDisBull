"""Entry-qualified native encodings, without claiming recovered UIL meaning.

Each backing owns one complete stored instruction. Source coverage is a union;
local encodings and source occurrences remain many-to-many. No query here
decodes additional project bytes, queues work, or changes an earlier version.
"""
from copy import deepcopy
import hashlib
import json

import iced_x86 as ix


FORMAT = 'fdisbull-code-backings-1'


def digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _union(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _arm_macho_source(project, version):
    """Identify the selected ARM64 slice in the retained file byte version."""
    from .macho_slices import macho_slices

    selection = project.meta['loader_metadata'].get('macho_slice')
    row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',
                             (version,)).fetchone()
    if not isinstance(selection, dict) or row is None or row[0] is None:
        raise ValueError('ARM64 Mach-O backings require retained source bytes and slice identity')
    source_bytes = bytes(row[0])
    slices = macho_slices(source_bytes)
    matches = [item for item in slices if item['index'] == selection.get('slice_index')
               and item['offset'] == selection.get('slice_offset')
               and item['size'] == selection.get('slice_size')
               and item['selector'] == 'arm64' and item['bits'] == 64]
    if len(matches) != 1:
        raise ValueError('selected ARM64 Mach-O slice differs from retained source bytes')
    selected = matches[0]
    identity = {'index': selected['index'], 'offset': selected['offset'],
                'size': selected['size'], 'selector': 'arm64',
                'sha256': hashlib.sha256(source_bytes[selected['offset']:selected['end_exclusive']]).hexdigest()}
    return identity, source_bytes, project._document(version).get('file_mappings', [])


def _arm_file_offset(address, raw, slice_identity, source_bytes, mappings):
    """Reject unmapped or ambiguous native bytes instead of guessing file offsets."""
    candidates = []
    for mapping in mappings:
        va, offset, size = (mapping.get(key) for key in
                            ('virtual_address', 'file_offset', 'file_size'))
        if all(type(value) is int for value in (va, offset, size)) and size >= len(raw) \
                and va <= address and address + len(raw) <= va + size:
            candidates.append(offset + address - va)
    if len(candidates) != 1:
        raise ValueError('ARM64 instruction needs one exact file mapping')
    offset = candidates[0]
    start, end = slice_identity['offset'], slice_identity['offset'] + slice_identity['size']
    if not start <= offset or offset + len(raw) > end or source_bytes[offset:offset + len(raw)] != raw:
        raise ValueError('ARM64 instruction differs from selected Mach-O file bytes')
    return offset


def materialize_code_backing(backing):
    """Return complete local bytes without consulting any sibling's storage."""
    if not isinstance(backing, dict):
        raise ValueError('expected an entry-qualified backing')
    record = {key: value for key, value in backing.items() if key != 'backing_revision'}
    if digest(record) != backing.get('backing_revision'):
        raise ValueError('backing revision integrity mismatch')
    try:
        raw = bytes.fromhex(backing['bytes'])
        size = backing['instruction']['size']
        bits = backing['bits']
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('invalid backing encoding') from error
    isa = backing.get('isa')
    if (type(bits) is not int or type(size) is not int or len(raw) != size
            or hashlib.sha256(raw).hexdigest() != backing.get('sha256')):
        raise ValueError('invalid or incomplete backing encoding')
    if isa == 'x86' and bits in (16, 32) and 1 <= size <= 15:
        instruction = ix.Decoder(bits, raw).decode()
        if instruction.is_invalid or instruction.len != len(raw):
            raise ValueError('backing must contain exactly one complete instruction')
    elif isa == 'arm64' and bits == 64 and size == 4:
        from .decoder import decode
        try:
            address = int(backing['address'], 16)
            native = decode(raw, address, 'arm64', 64)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('invalid ARM64 backing address') from error
        if (native is None or native['size'] != 4 or native['bytes'] != backing['bytes']
                or any(native[field] != backing['instruction'][field]
                       for field in ('size', 'mnemonic', 'operands'))
                or native['flow'] != backing.get('flow')):
            raise ValueError('backing must contain exactly one complete native ARM64 instruction')
    else:
        raise ValueError('invalid or incomplete backing encoding')
    return raw


def validate_source(project, document, *, version=None):
    """Check a capsule against a selected immutable project byte version.

    The default checks the project's current version. An old capsule can still
    be checked explicitly against its retained parent after a shared-byte patch.
    This is source validity, never a semantic-equivalence qualification.
    """
    if not isinstance(document, dict) or document.get('format') != FORMAT:
        raise ValueError('expected a code-backing capsule')
    if digest({key: value for key, value in document.items() if key != 'sha256'}) != document.get('sha256'):
        raise ValueError('code-backing capsule integrity mismatch')
    with project.transaction():
        selected = project.version(version)
        source = document.get('source', {})
        if (selected['id'] != source.get('version') or selected['sha256'] != source.get('version_sha256')
                or project.meta['source_sha256'] != source.get('source_sha256')
                or project.arch != source.get('arch') or project.bits != source.get('bits')
                or project.digest(project.regions(selected['id'])) != selected['sha256']):
            raise ValueError('code backings are stale for the selected source version')
        arm_source = None
        if project.arch == 'arm64' and project.meta['format'] == 'Mach-O':
            arm_source = _arm_macho_source(project, selected['id'])
            slice_identity, source_bytes, mappings = arm_source
            if (source.get('file_sha256') != hashlib.sha256(source_bytes).hexdigest()
                    or source.get('slice') != slice_identity):
                raise ValueError('code backings are stale for the selected Mach-O slice')
        for block in document['blocks']:
            raw = materialize_code_backing(block)
            address = int(block['address'], 16)
            region = project._mapping(selected['id'], address)
            if region is None or region.data[address-region.start:address-region.start+len(raw)] != raw:
                raise ValueError('backing bytes differ from their source occurrence')
            if arm_source is not None:
                file_offset = _arm_file_offset(address, raw, slice_identity, source_bytes, mappings)
                if (block['provenance'].get('file_offset') != file_offset
                        or block['provenance'].get('slice_relative_offset') != file_offset - slice_identity['offset']):
                    raise ValueError('ARM64 backing file offset differs from source occurrence')
        # A public content digest is not an authentication token. Re-query the
        # selected entries rather than accepting a caller's relabeling of a
        # budget-incomplete capture or an altered set of instruction edges.
        requests = document.get('requested_entries')
        budget = document.get('budget', {}).get('limit')
        fresh = project.code_backings(requests, version=selected['id'], max_instructions=budget)

        def facts(capsule):
            return {'entries': capsule['entries'], 'complete': capsule['complete'],
                    'visits': capsule['budget']['visits'],
                    'blocks': sorted((b['id'], b['context'], b['address'], b['bytes'], b['flow'],
                                      sorted((e['kind'], e['target']) for e in b['exits']),
                                      sorted((e['source'], e['kind'], e['target']) for e in b['incoming']))
                                     for b in capsule['blocks'])}
        if facts(fresh) != facts(document):
            raise ValueError('capture graph differs from selected project facts')
    return {'status': 'source_valid', 'version': selected['id'], 'sha256': document['sha256'],
            'graph_complete': fresh['complete'], 'metadata_authenticated': False,
            'semantic_qualification': 'unverified'}


class CodeBackingsMixin:
    def code_backings(self, entries, version=None, cs=None, max_instructions=10000):
        """Capture complete stored instruction backings from explicit entries.

        Entry values are addresses or {address, cs?} objects. The shared budget
        counts CFG visits, including repeated visits between requested roots.
        Missing facts, unresolved transfers and frontier remain explicit. Calls
        are not recursively captured or silently assumed to be local code.
        """
        from .project import integer, number
        x86 = self.arch == 'x86' and self.bits in (16, 32)
        arm_macho = self.arch == 'arm64' and self.bits == 64 and self.meta['format'] == 'Mach-O'
        if not (x86 or arm_macho):
            raise ValueError('code backings support x86 16/32-bit or ARM64 Mach-O projects')
        if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= 64:
            raise ValueError('entries must contain 1..64 exact instruction addresses')
        budget = integer(max_instructions, 'max_instructions', 1, 100000)
        requests = []
        for item in entries:
            if isinstance(item, dict):
                if set(item) - {'address', 'cs'} or 'address' not in item:
                    raise ValueError('entry objects require address and optional cs')
                address, selector = item['address'], item.get('cs', cs)
            else:
                address, selector = item, cs
            if self.meta['format'] in ('MZ', 'COM', 'SYS'):
                a, selector = self._dos_parse_address(address, selector)
            else:
                a = number(address)
                if selector is not None:
                    raise ValueError('CS selection applies only to DOS projects')
            requests.append({'address': hex(a), 'cs': selector})
        with self.transaction():
            selected = self.version(version)
            v = selected['id']
            if self.digest(self.regions(v)) != selected['sha256']:
                raise ValueError('source image version digest mismatch')
            arm_source = _arm_macho_source(self, v) if arm_macho else None
            blocks, roots, incoming, problems, root_evidence = {}, [], {}, [], []
            used = 0
            for index, item in enumerate(requests):
                address, selector = item['address'], item['cs']
                if used >= budget:
                    problems.append({'kind': 'budget', 'entry_index': index, 'reason': 'capture_budget_exhausted'})
                    continue
                graph = self.cfg(address, version=v, cs=selector, max_instructions=budget-used)
                used += graph['instruction_count']
                roots.append(graph['entry'])
                root_evidence.append({'entry': graph['entry'], 'source': 'caller_selected_exact_entry',
                                      'graph_closed': graph['graph_closed'], 'runtime_observed': False})
                # Preserve stored incoming evidence even when its source is
                # outside this selected reachable slice. Selection is not a
                # substitute for evidence that another path targets an operand.
                if graph['context'] is not None:
                    target_key = f'{int(graph["address"], 16):016x}'
                    if self.meta['format'] in ('MZ', 'COM', 'SYS'):
                        incoming_rows = self.db.execute(
                            "SELECT source,source_context,kind,evidence FROM dos_edges WHERE version=? AND target_context=? AND target=? AND kind IN ('branch','resolved_branch','fallthrough','call','resolved_call') LIMIT 1025",
                            (v, graph['context'], target_key)).fetchall()
                    else:
                        incoming_rows = self.db.execute(
                            "SELECT source,context AS source_context,kind,evidence FROM xrefs WHERE version=? AND context=? AND target=? AND kind IN ('branch','resolved_branch','fallthrough','call','resolved_call') LIMIT 1025",
                            (v, graph['context'], target_key)).fetchall()
                    if len(incoming_rows) > 1024:
                        problems.append({'kind': 'incoming_budget', 'entry_index': index})
                    for row in incoming_rows[:1024]:
                        source_id = f'{row["source_context"]}@{hex(int(row["source"], 16))}'
                        incoming.setdefault(graph['entry'], {})[(source_id, row['kind'])] = {
                            'source': source_id, 'target': graph['entry'], 'kind': row['kind'],
                            'evidence': row['evidence'], 'provenance': 'stored'}
                for field in ('gaps', 'unresolved', 'frontier', 'calls'):
                    for detail in graph[field]:
                        problems.append({'kind': field, 'entry_index': index, 'detail': deepcopy(detail)})
                if graph['budget_exhausted'] and not graph['frontier']:
                    problems.append({'kind': 'budget', 'entry_index': index})
                for edge in graph['edges']:
                    incoming.setdefault(edge['target'], {})[(edge['source'], edge['kind'])] = deepcopy(edge)
                by_source = {}
                for edge in graph['edges']:
                    by_source.setdefault(edge['source'], []).append(edge)
                for node in graph['nodes']:
                    exits = [{'kind': edge['kind'], 'target': edge['target'],
                              'evidence': edge['evidence'], 'provenance': edge['provenance']}
                             for edge in by_source.get(node['id'], [])]
                    if node['id'] in blocks:
                        # A second bounded root may see less of the same graph.
                        known = {(e['kind'], e['target']) for e in blocks[node['id']]['exits']}
                        blocks[node['id']]['exits'].extend(e for e in exits if (e['kind'], e['target']) not in known)
                        continue
                    raw = bytes.fromhex(node['bytes'])
                    a = int(node['address'], 16)
                    region = self._mapping(v, a)
                    if region is None or region.data[a-region.start:a-region.start+len(raw)] != raw:
                        raise ValueError('stored instruction bytes differ from source version')
                    if x86:
                        decoder = ix.Decoder(self.bits, raw)
                        instruction = decoder.decode()
                        if instruction.is_invalid or instruction.len != len(raw) or len(raw) != node['size']:
                            raise ValueError('stored instruction is not a complete native encoding')
                        offsets = decoder.get_constant_offsets(instruction)
                        roles = ['instruction_encoding'] * len(raw)
                        for offset, size, role in ((offsets.immediate_offset, offsets.immediate_size, 'immediate'),
                                                   (offsets.immediate_offset2, offsets.immediate_size2, 'immediate'),
                                                   (offsets.displacement_offset, offsets.displacement_size, 'displacement')):
                            roles[offset:offset+size] = [role] * size
                    else:
                        from .decoder import decode
                        native = decode(raw, a, 'arm64', 64)
                        if (native is None or len(raw) != 4 or node['size'] != 4
                                or any(native[field] != node[field]
                                       for field in ('mnemonic', 'operands', 'flow'))):
                            raise ValueError('stored instruction is not a complete native ARM64 encoding')
                        roles = ['instruction_encoding'] * 4
                        slice_identity, source_bytes, mappings = arm_source
                        file_offset = _arm_file_offset(a, raw, slice_identity, source_bytes, mappings)
                    provenance = {'address': node['address'], 'size': len(raw), 'local_offset': 0,
                                  'source_sha256': self.meta['source_sha256'],
                                  'version_sha256': selected['sha256'], 'context': node['context'],
                                  'byte_roles': roles}
                    if arm_macho:
                        provenance.update(file_offset=file_offset,
                                          slice_relative_offset=file_offset - slice_identity['offset'])
                    blocks[node['id']] = {
                        'id': node['id'], 'isa': self.arch, 'bits': self.bits,
                        'address': node['address'], 'context': node['context'],
                        'bytes': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'flow': node['flow'], 'instruction': {k: node[k] for k in ('size', 'mnemonic', 'operands')},
                        'exits': exits, 'references': deepcopy(node['references']),
                        'provenance': provenance,
                        'effects': {'status': 'native_backing_residual',
                                    'scope': 'Complete original native instruction, with its architectural effects retained; no UIL meaning inferred.'}}
            for block in blocks.values():
                block['incoming'] = list(incoming.get(block['id'], {}).values())
                block['exits'].sort(key=lambda edge: (edge['kind'], edge['target']))
                block['backing_revision'] = digest(block)
                materialize_code_backing(block)
            ordered = sorted(blocks.values(), key=lambda b: (b['context'], int(b['address'], 16)))
            spans = _union((int(b['address'], 16), int(b['address'], 16)+b['instruction']['size']) for b in ordered)
            occurrences = sum(b['instruction']['size'] for b in ordered)
            physical = sum(end-start for start, end in spans)
            document = {
                'format': FORMAT,
                'source': {'arch': self.arch, 'bits': self.bits, 'version': v,
                           'version_sha256': selected['sha256'], 'source_sha256': self.meta['source_sha256']},
                'entries': list(dict.fromkeys(roots)), 'entry_evidence': root_evidence,
                'requested_entries': requests,
                'blocks': ordered, 'complete': not problems and bool(ordered), 'unresolved': problems,
                'coverage': {'physical_bytes': physical, 'encoding_bytes': occurrences,
                             'shared_occurrence_bytes': occurrences-physical,
                             'physical_ranges': [{'start': hex(start), 'end': hex(end)} for start, end in spans]},
                'budget': {'limit': budget, 'visits': used},
                'qualification': 'native_backings_only',
                'scope': 'Entry-qualified stored encodings and explicit edges; no recovered intent, reachability or equivalence claim.'}
            if arm_macho:
                slice_identity, source_bytes, _ = arm_source
                document['source']['slice'] = slice_identity
                document['source']['file_sha256'] = hashlib.sha256(source_bytes).hexdigest()
            document['sha256'] = digest(document)
            return document

    def code_layout(self, entries, version=None, cs=None, max_instructions=10000,
                    order=None, base=0, assumptions=None, entry_references=None):
        """Emit a bounded raw-code layout from the selected project version.

        No file/container is written and no native execution or equivalence is
        inferred. The required layout assumptions are explicit caller assertions.
        """
        from .code_layout import compile_code_backings
        document = self.code_backings(entries, version=version, cs=cs,
                                      max_instructions=max_instructions)
        return compile_code_backings(document, order=order, base=base,
                                     assumptions=assumptions, entry_references=entry_references)

    def code_blocks(self, entries, version=None, cs=None, max_instructions=10000,
                    split_at=None):
        """Project stored instructions into logical blocks without placing bytes."""
        from .code_blocks import group_code_backings
        document = self.code_backings(entries, version=version, cs=cs,
                                      max_instructions=max_instructions)
        return group_code_backings(document, split_at=split_at)

    def udc_native_capture(self, name, entries, version=None, cs=None,
                           max_instructions=10000, split_at=None, parent=None,
                           author='agent'):
        """Persist entry-qualified native UDL without requiring a UIL lift."""
        from .native_udc import capture_native_definition
        return capture_native_definition(self, name, entries, version=version, cs=cs,
                                         max_instructions=max_instructions, split_at=split_at,
                                         parent=parent, author=author)

    def udc_native_info(self, definition, include_blocks=False):
        from .native_udc import native_definition_info
        return native_definition_info(self, definition, include_blocks=include_blocks)

    def udc_native_compile(self, definition, mode='original-layout', assumptions=None,
                           base=0, order=None, block_order=None, entry_references=None):
        """Select exact source pass-through or explicitly admitted raw relayout."""
        from .native_udc import compile_native_definition
        return compile_native_definition(self, definition, mode=mode, assumptions=assumptions,
                                         base=base, order=order, block_order=block_order,
                                         entry_references=entry_references)
