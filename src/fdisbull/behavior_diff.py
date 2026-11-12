"""Bounded topology and observed-effect comparison for two captured traces.

Sites establish path correspondence, not semantic equivalence. In particular,
the same PC can execute different bytes, and a shared PC can carry different
register state. Cross-version sites require an explicit, evidenced mapping.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter


def normalized_trace_event(event):
    """Ignore DOS lookahead bytes beyond the currently decoded instruction."""
    result = {key: event[key] for key in (
        'project_address', 'project_segmented_address', 'address', 'instruction',
        'bytes', 'ram_bytes', 'execution_bytes', 'registers', 'register_changes',
        'completed', 'cpu_mode', 'code_bits', 'stack_bits') if key in event}
    if isinstance(event.get('address'), dict) and event.get('execution_bytes'):
        from iced_x86 import Decoder
        from .debug_semantics import trace_decode_bits
        bits = trace_decode_bits(event)
        if bits is None:
            return result
        raw = bytes.fromhex(event['execution_bytes'])
        instruction = Decoder(bits, raw, ip=int(event['address']['offset'], 16)).decode()
        if not instruction.is_invalid:
            for name in ('ram_bytes', 'execution_bytes'):
                if name in result:
                    result[name] = result[name][:instruction.len * 2]
    return result


def _site(event):
    identity = event.get('identity')
    if not isinstance(identity, dict):
        return None
    version, context, address = (identity.get(key) for key in
                                 ('source_version', 'context', 'project_address'))
    if (type(version) not in (int, str) or not isinstance(context, (str, type(None)))
            or type(address) not in (int, str)):
        return None
    return (version, context, _address(address))


def _address(value):
    if type(value) is int:
        return hex(value)
    try:
        return hex(int(value, 16)) if value.lower().startswith('0x') else value.lower()
    except ValueError:
        return value.lower()


def _correspondences(entries):
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError('Cross-version correspondence must be a bounded list')
    left, right = {}, {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {'baseline', 'layer', 'evidence'}:
            raise ValueError('Correspondence needs baseline, layer and evidence')
        if not isinstance(entry['evidence'], str) or not entry['evidence'].strip():
            raise ValueError('Correspondence needs provenance evidence')
        sites = []
        for side in ('baseline', 'layer'):
            site = entry[side]
            if not isinstance(site, dict) or set(site) != {'source_version', 'context', 'project_address'}:
                raise ValueError('Correspondence site needs version, context and address')
            if (type(site['source_version']) not in (int, str)
                    or not isinstance(site['context'], (str, type(None)))
                    or type(site['project_address']) not in (int, str)):
                raise ValueError('Correspondence needs a known version and address')
            sites.append((site['source_version'], site['context'], _address(site['project_address'])))
        if sites[0] in left or sites[1] in right:
            raise ValueError('Correspondence must be one-to-one')
        left[sites[0]] = right[sites[1]] = ('mapped', index)
    return left, right


def _unique_anchors(left, right):
    """Monotone unique-site anchors; repeated loop PCs are never guessed joins."""
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    if prefix == len(left) == len(right):
        return [(i, i) for i in range(prefix)]
    counts_left, counts_right = Counter(left[prefix:]), Counter(right[prefix:])
    right_pos = {key: j for j, key in enumerate(right[prefix:], prefix)
                 if counts_right[key] == 1}
    candidates = [(i, right_pos[key]) for i, key in enumerate(left[prefix:], prefix)
                  if counts_left[key] == 1 and key in right_pos
                  and key[0] != 'unmapped']
    tails, tail_indexes, previous = [], [], [-1] * len(candidates)
    for index, (_, position) in enumerate(candidates):
        slot = bisect_left(tails, position)
        if slot == len(tails):
            tails.append(position)
            tail_indexes.append(index)
        else:
            tails[slot] = position
            tail_indexes[slot] = index
        if slot:
            previous[index] = tail_indexes[slot - 1]
    anchors = []
    cursor = tail_indexes[-1] if tail_indexes else -1
    while cursor >= 0:
        anchors.append(candidates[cursor])
        cursor = previous[cursor]
    anchors.reverse()
    pairs = [(i, i) for i in range(prefix)] + anchors
    expanded = []
    for next_pair in pairs + [(len(left), len(right))]:
        old_i, old_j = expanded[-1] if expanded else (-1, -1)
        gap_left, gap_right = left[old_i + 1:next_pair[0]], right[old_j + 1:next_pair[1]]
        if gap_left == gap_right and len(gap_left) == len(gap_right):
            expanded.extend((old_i + 1 + k, old_j + 1 + k) for k in range(len(gap_left)))
        if next_pair != (len(left), len(right)) and (not expanded or expanded[-1] != next_pair):
            expanded.append(next_pair)
    return expanded


def _segments(pairs, left, right):
    segments = []
    previous = (-1, -1)
    for pair in pairs + [(len(left), len(right))]:
        if pair[0] > previous[0] + 1 or pair[1] > previous[1] + 1:
            terminal = pair == (len(left), len(right))
            left_tail = left[previous[0] + 1:pair[0]]
            right_tail = right[previous[1] + 1:pair[1]]
            open_tail = terminal and (not left_tail or not right_tail or left_tail[0] == right_tail[0])
            unmapped = any(site[0] == 'unmapped' for site in left_tail + right_tail)
            segments.append({'kind': 'unresolved' if unmapped else 'open_tail' if open_tail else 'divergent',
                             'baseline': [previous[0] + 1, pair[0]],
                             'layer': [previous[1] + 1, pair[1]],
                             'rejoin': None if terminal else {
                                 'baseline_index': pair[0], 'layer_index': pair[1],
                                 'site': list(left[pair[0]])}})
        if pair != (len(left), len(right)):
            if (segments and segments[-1]['kind'] == 'common'
                    and previous[0] + 1 == pair[0] and previous[1] + 1 == pair[1]):
                segments[-1]['baseline'][1] = pair[0] + 1
                segments[-1]['layer'][1] = pair[1] + 1
            else:
                segments.append({'kind': 'common', 'baseline': [pair[0], pair[0] + 1],
                                 'layer': [pair[1], pair[1] + 1]})
        previous = pair
    return segments


def _flat_registers(value, prefix=''):
    result = {}
    for name, item in value.items():
        path = prefix + name
        if isinstance(item, dict):
            result.update(_flat_registers(item, path + '.'))
        elif name not in ('run', 'version', 'state_revision'):
            result[path] = item
    return result


def _register_relation(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {'relation': 'unobserved'}
    a, b = _flat_registers(left), _flat_registers(right)
    fields = sorted(key for key in a.keys() & b.keys() if a[key] != b[key])
    if a.keys() != b.keys():
        return {'relation': 'partial', 'shared_fields': len(a.keys() & b.keys()),
                'different_fields': fields[:64], 'fields_truncated': len(fields) > 64}
    return {'relation': 'different' if fields else 'equal', 'different_fields': fields[:64],
            'fields_truncated': len(fields) > 64}


def compare_trace_topology(baseline, layer, *, same_source=False, correspondence=None, max_events=10000,
                           max_examples=64):
    """Compare observed paths and sampled state without inferring unseen effects.

    Inputs are trace records with ``events`` and ``semantics``. ``same_source``
    is an explicit assertion that both captures came from one project version;
    the saved-experiment caller can establish it. Other callers need evidenced
    site correspondences even if both projects call their version "1".
    """
    if type(max_events) is not int or not 1 <= max_events <= 10000:
        raise ValueError('max_events must be 1..10000')
    if type(max_examples) is not int or not 1 <= max_examples <= 256:
        raise ValueError('max_examples must be 1..256')
    if type(same_source) is not bool:
        raise ValueError('same_source must be boolean')
    if same_source and correspondence is not None:
        raise ValueError('Choose same_source or explicit correspondence')
    events = []
    for trace in (baseline, layer):
        if not isinstance(trace, dict) or not isinstance(trace.get('events'), list):
            raise ValueError('Trace requires events')
        if len(trace['events']) > max_events or any(not isinstance(e, dict) for e in trace['events']):
            raise ValueError('Trace exceeds event budget or contains a malformed event')
        events.append(trace['events'])
    a, b = events
    if not a or not b or baseline.get('semantics') != layer.get('semantics'):
        reason = ('At least one trace has no observed sites' if not a or not b else
                  'Trace observation semantics differ')
        return {'alignment': 'unknown', 'segments': [], 'code_difference': None,
                'control_flow_difference': None, 'observed_register_difference': None,
                'code_changes': [], 'register_changes': [], 'presentation_changes': [],
                'code_change_count': 0, 'register_change_count': 0,
                'presentation_change_count': 0, 'segments_truncated': False,
                'unknown': [reason],
                'coverage': {'baseline_events': len(a), 'layer_events': len(b),
                             'aligned_pairs': 0, 'all_events_paired': False,
                             'observed_path_overlap': None,
                             'baseline_semantics': baseline.get('semantics'),
                             'layer_semantics': layer.get('semantics')}}
    left_sites, right_sites = [_site(e) for e in a], [_site(e) for e in b]
    versions = [{s[0] for s in sites if s is not None} for sites in (left_sites, right_sites)]
    if any(s is None for s in left_sites + right_sites):
        # A missing address is not a missing version. Preserve an available
        # version assertion without allowing the unknown site to align.
        for side_index, side in enumerate((a, b)):
            for event in side:
                identity = event.get('identity')
                if isinstance(identity, dict) and type(identity.get('source_version')) in (int, str):
                    versions[side_index].add(identity['source_version'])
    if any(len(v) > 1 for v in versions):
        raise ValueError('Trace mixes source versions')
    if same_source and (not versions[0] or not versions[1] or versions[0] != versions[1]
                        or None in versions[0]):
        raise ValueError('Same-source traces require one matching source version')
    left_map, right_map = _correspondences(correspondence or [])
    unknown = []
    if not same_source and not left_map:
        unknown.append('Separate-source path alignment requires evidenced correspondence')
    if any(s is None for s in left_sites + right_sites):
        unknown.append('Unmapped trace sites are not aligned by runtime address')
    if baseline.get('semantics') == 'pre_execution_fetch_last_pending' or layer.get('semantics') == 'pre_execution_fetch_last_pending':
        unknown.append('DOS fetch observations do not certify instruction retirement')
    if (baseline.get('requested_count') == len(a) or layer.get('requested_count') == len(b)):
        unknown.append('At least one trace reached its requested event budget')
    if not same_source and not left_map:
        return {'alignment': 'unknown', 'segments': [], 'code_difference': None,
                'control_flow_difference': None, 'observed_register_difference': None,
                'code_changes': [], 'register_changes': [], 'presentation_changes': [],
                'code_change_count': 0, 'register_change_count': 0,
                'presentation_change_count': 0, 'segments_truncated': False,
                'unknown': unknown,
                'coverage': {'baseline_events': len(a), 'layer_events': len(b),
                             'aligned_pairs': 0, 'all_events_paired': False,
                             'observed_path_overlap': None,
                             'baseline_semantics': baseline.get('semantics'),
                             'layer_semantics': layer.get('semantics')}}
    left = [left_map.get(s, ('unmapped', 'baseline', i)) if not same_source else
            ('unmapped', 'baseline', i) if s is None else ('site', *s[1:])
            for i, s in enumerate(left_sites)]
    right = [right_map.get(s, ('unmapped', 'layer', i)) if not same_source else
             ('unmapped', 'layer', i) if s is None else ('site', *s[1:])
             for i, s in enumerate(right_sites)]
    unaligned_unknown = any(key[0] == 'unmapped' for key in left + right)
    if unaligned_unknown and not any('Unmapped trace sites' in reason for reason in unknown):
        unknown.append('Sites without established correspondence cannot prove path divergence')
    pairs = _unique_anchors(left, right)
    all_paired = len(pairs) == len(a) == len(b)
    if not all_paired:
        unknown.append('Unpaired trace events cannot establish code or register equality')
    segments = _segments(pairs, left, right)
    for segment in segments:
        if segment['kind'] == 'common':
            for label, offset in (('entry', 0), ('exit', -1)):
                i = segment['baseline'][0] if offset == 0 else segment['baseline'][1] - 1
                j = segment['layer'][0] if offset == 0 else segment['layer'][1] - 1
                segment[label + '_registers'] = _register_relation(a[i].get('registers'), b[j].get('registers'))
        elif segment['rejoin'] is not None:
            i, j = segment['rejoin']['baseline_index'], segment['rejoin']['layer_index']
            segment['rejoin']['registers'] = _register_relation(a[i].get('registers'), b[j].get('registers'))
    code_changes, register_changes, presentation_changes = [], [], []
    code_count = register_count = presentation_count = 0
    code_observed = bool(pairs)
    registers_observed = bool(pairs)
    for i, j in pairs:
        x, y = normalized_trace_event(a[i]), normalized_trace_event(b[j])
        code_fields = []
        for field in ('bytes', 'ram_bytes', 'execution_bytes'):
            if (field in x) != (field in y):
                code_observed = False
                if 'Code bytes are missing on one side of an aligned site' not in unknown:
                    unknown.append('Code bytes are missing on one side of an aligned site')
            elif field in x and x[field] != y[field]:
                code_fields.append(field)
        if not any(field in x and field in y for field in ('bytes', 'ram_bytes', 'execution_bytes')):
            code_observed = False
        if 'instruction' in x and 'instruction' in y and x['instruction'] != y['instruction']:
            presentation_count += 1
            if len(presentation_changes) < max_examples:
                presentation_changes.append({'baseline_index': i, 'layer_index': j})
        if code_fields:
            code_count += 1
            if len(code_changes) < max_examples:
                code_changes.append({'baseline_index': i, 'layer_index': j, 'fields': code_fields})
        if isinstance(x.get('registers'), dict) and isinstance(y.get('registers'), dict):
            left_regs, right_regs = _flat_registers(x['registers']), _flat_registers(y['registers'])
            if not left_regs and not right_regs:
                registers_observed = False
                if 'Empty register snapshots provide no state comparison' not in unknown:
                    unknown.append('Empty register snapshots provide no state comparison')
            if left_regs.keys() != right_regs.keys():
                registers_observed = False
                if 'Register field sets differ at an aligned site' not in unknown:
                    unknown.append('Register field sets differ at an aligned site')
            fields = sorted(key for key in left_regs.keys() & right_regs.keys()
                            if left_regs[key] != right_regs[key])
            if fields:
                register_count += 1
                if len(register_changes) < max_examples:
                    register_changes.append({'baseline_index': i, 'layer_index': j,
                                             'fields': fields[:64], 'fields_truncated': len(fields) > 64})
        else:
            registers_observed = False
            if 'Register snapshots are missing on one side of an aligned site' not in unknown:
                unknown.append('Register snapshots are missing on one side of an aligned site')
    return {'alignment': 'partial' if unaligned_unknown else 'evidenced',
            'segments': segments[:256], 'segments_truncated': len(segments) > 256,
            'code_difference': True if code_count else False if code_observed and all_paired else None,
            'control_flow_difference': (None if unaligned_unknown else True if
                                        any(s['kind'] == 'divergent' for s in segments) else None if
                                        any(s['kind'] == 'open_tail' for s in segments) else False),
            'observed_register_difference': (True if register_count else
                                             False if registers_observed and all_paired else None),
            'code_changes': code_changes, 'code_change_count': code_count,
            'presentation_changes': presentation_changes,
            'presentation_change_count': presentation_count,
            'register_changes': register_changes, 'register_change_count': register_count,
            'unknown': unknown,
            'coverage': {'baseline_events': len(a), 'layer_events': len(b),
                         'aligned_pairs': len(pairs), 'baseline_semantics': baseline.get('semantics'),
                         'layer_semantics': layer.get('semantics'),
                         'all_events_paired': all_paired,
                         'observed_path_overlap': len(pairs) / max(len(a), len(b), 1)}}
