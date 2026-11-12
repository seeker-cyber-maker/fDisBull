"""Provenance-bound PE import roles alongside a behavioral patch topology.

Import identity is context for a possible intent, not evidence that arguments,
effects, or the whole divergent span agree. This module never changes topology
alignment or its code/path/observed-effect verdicts.
"""
from __future__ import annotations

import hashlib
import json
import re

from iced_x86 import Decoder, FlowControl

from .debug_semantics import PE_TRACE_SEMANTICS
from .behavior_diff import compare_trace_topology


_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def _trace_digest(trace):
    fields = {key: trace.get(key) for key in ('mapping', 'version', 'semantics', 'events')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _address(value):
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def observed_pe_import_roles(project, function_address, trace):
    """Project non-stale static import bindings onto completed PE call sites.

    ``trace`` is a raw ``debug.trace`` document with its source-hash mapping.
    ``project`` owns the non-stale function analysis and both byte identities.
    A match remains conditional on static binding stability; no
    runtime DLL provider or call arguments are inferred.
    """
    if not isinstance(trace, dict):
        raise ValueError('Raw PE trace is required')
    mapping = trace.get('mapping')
    if not isinstance(mapping, dict) or mapping.get('backend') != 'wine-qemu':
        raise ValueError('Raw Wine/QEMU PE trace mapping is required')
    source_sha = mapping.get('source_sha256')
    if not isinstance(source_sha, str) or not _SHA256.fullmatch(source_sha):
        raise ValueError('Trace requires an exact source SHA-256')
    bits, version = mapping.get('bits'), trace.get('version')
    if type(bits) is not int or bits not in (32, 64) or type(version) is not int:
        raise ValueError('Trace architecture and version are required')
    if (project.meta.get('format') != 'PE' or project.arch != 'x86' or project.bits != bits
            or project.meta.get('source_sha256') != source_sha
            or project.version(version).get('sha256') != mapping.get('version_sha256')):
        raise ValueError('Trace does not match the owning PE project and code version')
    analysis = project.function_analysis(function_address, version=version)
    if (trace.get('semantics') != PE_TRACE_SEMANTICS or analysis.get('stale') is not False
            or analysis.get('state') != 'done' or analysis.get('version') != version
            or analysis.get('context') != f'x86:{bits}:little'):
        raise ValueError('Trace and non-stale PE analysis do not share a qualified context')
    result = analysis.get('result')
    events = trace.get('events')
    if (not isinstance(result, dict) or result.get('version') != version
            or result.get('context') != analysis['context']
            or result.get('budget_exhausted') is not False
            or not isinstance(events, list) or len(events) > 10000
            or not isinstance(result.get('import_calls'), list)
            or len(result['import_calls']) > 10000):
        raise ValueError('Bounded completed import analysis and trace events are required')
    bindings = {}
    for item in result['import_calls']:
        if not isinstance(item, dict) or item.get('source_context') != analysis['context']:
            raise ValueError('Import binding context is malformed')
        address = _address(item.get('source_address'))
        if address is None:
            raise ValueError('Import binding site is malformed')
        bindings.setdefault(address, []).append(item)
    stored_bytes = {}
    roles = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError('Trace event is malformed')
        identity = event.get('identity')
        if (not isinstance(identity, dict) or identity.get('context') != 'flat'
                or identity.get('source_version') != version
                or identity.get('project_address') != event.get('project_address')
                or identity.get('runtime_address') != event.get('address')):
            raise ValueError('Trace site identity differs from the selected analysis')
        site = _address(identity.get('project_address'))
        if site not in bindings:
            continue
        matches = bindings[site]
        raw_hex = event.get('execution_bytes', event.get('bytes'))
        if site not in stored_bytes:
            disassembly = project.disassembly(address=site, lines=1, version=version)
            instructions = disassembly.get('instructions', [])
            stored = instructions[0] if instructions else {}
            stored_bytes[site] = (stored.get('bytes') if _address(stored.get('address')) == site
                                  and stored.get('context', analysis['context']) == analysis['context'] else None)
        try:
            if not isinstance(raw_hex, str) or not 2 <= len(raw_hex) <= 30 or len(raw_hex) % 2:
                raise ValueError('PE instruction bytes must fit one x86 instruction')
            raw = bytes.fromhex(raw_hex)
            instruction = Decoder(bits, raw, ip=int(event['address'], 16)).decode()
            is_call = (not instruction.is_invalid and instruction.len == len(raw)
                       and instruction.flow_control in (FlowControl.CALL, FlowControl.INDIRECT_CALL))
        except (TypeError, ValueError, KeyError):
            is_call = False
        execution_hex, ram_hex = event.get('execution_bytes'), event.get('ram_bytes')
        code_changed = (execution_hex is not None and ram_hex is not None
                        and (not isinstance(execution_hex, str) or not isinstance(ram_hex, str)
                             or execution_hex.lower() != ram_hex.lower()))
        matches_stored_code = (isinstance(stored_bytes[site], str)
                               and isinstance(raw_hex, str)
                               and stored_bytes[site].lower() == raw_hex.lower())
        item = matches[0] if len(matches) == 1 else {}
        module, name = item.get('module'), item.get('name')
        qualified = (is_call and matches_stored_code and not code_changed and len(matches) == 1
                     and isinstance(module, str) and bool(module)
                     and isinstance(name, str) and bool(name)
                     and item.get('identity_basis') == 'declared_import_metadata'
                     and item.get('binding_unchanged_under_static_state') is True)
        roles.append({'event_index': index, 'project_address': hex(site),
                      'source_version': version, 'source_sha256': source_sha,
                      'status': 'candidate' if qualified else 'unresolved',
                      'api': {'module': module, 'name': name} if qualified else None,
                      'binding_count': len(matches), 'observed_call_instruction': is_call,
                      'execution_matches_analyzed_code': matches_stored_code,
                      'execution_layer_changed_code': code_changed,
                      'binding_unchanged_under_static_state': item.get('binding_unchanged_under_static_state'),
                      'slot': item.get('slot'), 'stub': item.get('stub'),
                      'evidence': item.get('evidence'),
                      'scope': 'Static import role at an observed call site; runtime provider, arguments and effects unverified'})
    return {'format': 'fdisbull-pe-import-roles-1', 'source_sha256': source_sha,
            'version': version, 'version_sha256': mapping['version_sha256'],
            'analysis_entry': analysis.get('address'), 'trace_digest': _trace_digest(trace),
            'roles': roles,
            'coverage': {'trace_events': len(events), 'binding_sites': len(bindings),
                         'observed_binding_sites': len(roles)},
            'semantic_equivalence': None}


def compare_divergent_import_roles(baseline_trace, layer_trace, baseline, layer,
                                   *, same_source=False, correspondence=None):
    """Highlight a shared API role only for one qualified call per divergent side."""
    for trace, side in ((baseline_trace, baseline), (layer_trace, layer)):
        if not isinstance(trace, dict) or not isinstance(side, dict) or side.get('trace_digest') != _trace_digest(trace):
            raise ValueError('PE roles must match the exact supplied traces')
    topology = compare_trace_topology(baseline_trace, layer_trace,
                                      same_source=same_source, correspondence=correspondence)
    if (not isinstance(topology, dict) or topology.get('alignment') != 'evidenced'
            or not isinstance(topology.get('segments'), list)
            or topology.get('segments_truncated') is not False
            or not isinstance(topology.get('coverage'), dict)
            or any(not isinstance(side, dict) or side.get('format') != 'fdisbull-pe-import-roles-1'
                   or not isinstance(side.get('roles'), list)
                   or not isinstance(side.get('coverage'), dict)
                   or not isinstance(side.get('source_sha256'), str)
                   or not _SHA256.fullmatch(side['source_sha256'])
                   or not isinstance(side.get('version_sha256'), str)
                   or not _SHA256.fullmatch(side['version_sha256'])
                   for side in (baseline, layer))):
        raise ValueError('Complete topology and PE role projections are required')
    lengths = [topology['coverage'].get('baseline_events'), topology['coverage'].get('layer_events')]
    for side, length in zip((baseline, layer), lengths, strict=True):
        if (type(length) is not int or not 0 <= length <= 10000
                or side['coverage'].get('trace_events') != length
                or any(not isinstance(role, dict) or type(role.get('event_index')) is not int
                       or not 0 <= role['event_index'] < length
                       or role.get('source_sha256') != side['source_sha256']
                       or role.get('source_version') != side.get('version')
                       for role in side['roles'])):
            raise ValueError('PE role projection does not cover the topology trace')
    result = []
    for index, segment in enumerate(topology['segments']):
        if not isinstance(segment, dict):
            raise ValueError('Topology segment is malformed')
        if segment.get('kind') != 'divergent':
            continue
        try:
            ranges = [segment['baseline'], segment['layer']]
            if any(not isinstance(bounds, list) or len(bounds) != 2
                   or any(type(x) is not int for x in bounds)
                   or not 0 <= bounds[0] <= bounds[1] <= length
                   for bounds, length in zip(ranges, lengths, strict=True)):
                raise ValueError('Topology segment range is malformed')
            selected = [[role for role in side['roles'] if bounds[0] <= role['event_index'] < bounds[1]]
                        for side, bounds in zip((baseline, layer), ranges, strict=True)]
        except (KeyError, TypeError, IndexError):
            raise ValueError('Topology segment range is malformed') from None
        if not selected[0] and not selected[1]:
            continue
        left, right = selected
        if len(left) == len(right) == 1 and all(role.get('status') == 'candidate' for role in (left[0], right[0])):
            a, b = left[0]['api'], right[0]['api']
            same = a['module'].casefold() == b['module'].casefold() and a['name'] == b['name']
            relation = 'shared_api_role_candidate' if same else 'different_api_role'
        else:
            relation = 'unresolved'
        result.append({'segment_index': index, 'relation': relation,
                       'baseline_event_indices': [role['event_index'] for role in left],
                       'layer_event_indices': [role['event_index'] for role in right],
                       'arguments': 'uncompared', 'ordered_effects': 'uncompared',
                       'semantic_equivalence': None})
    return {'format': 'fdisbull-pe-import-role-comparison-1', 'segments': result,
            'scope': 'API role candidates in observed divergent spans; no behavior or intent equivalence verdict'}
