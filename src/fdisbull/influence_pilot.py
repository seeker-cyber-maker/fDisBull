"""Finite, path-specific influence and live-state contracts for UDC block pilots.

No CFG, alias, exception, interrupt, or unknown-call claims are made here.
Calls must provide one complete linear path with independent atomic state slots.
"""
from __future__ import annotations

from collections import defaultdict
import re


class InfluenceError(ValueError):
    """Unknown effects and incomplete state models must not imply don't-care."""


_SLOT = re.compile(r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$')


def _slots(items, field):
    if not isinstance(items, list) or len(items) > 256:
        raise InfluenceError(f'Invalid {field} set')
    if any(not isinstance(x, str) or not _SLOT.fullmatch(x) for x in items):
        raise InfluenceError(f'{field} requires normalized atomic state slots')
    if len(items) != len(set(items)):
        raise InfluenceError(f'Duplicate {field} slots')
    return set(items)


def analyze_linear_influence(document):
    """Infer masks and an influence graph for a declared *closed linear* path.

    An absent edge means proven dead only with complete opcode/effect semantics
    AND a complete set of possible observers at the specific boundary.
    """
    if not isinstance(document, dict) or set(document) != {'format', 'scope', 'steps', 'observables', 'closed_semantics', 'closed_observers'}:
        raise InfluenceError('Invalid influence document')
    if document['format'] != 'fdisbull-influence-pilot-1' or document['scope'] != 'linear':
        raise InfluenceError('Only finite linear-path analysis supported')
    if document['closed_semantics'] is not True or document['closed_observers'] is not True:
        raise InfluenceError("Unknown instruction effects/observers prohibit inferred don't-care")
    steps = document['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= 256:
        raise InfluenceError('Step budget 1..256')
    sinks = _slots(document['observables'], 'observable')
    if not sinks:
        raise InfluenceError('At least one explicit observable required')
    available = {}
    edges = []
    records = []
    used_ids = set()
    all_slots = set(sinks)
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'id', 'reads', 'writes', 'dependencies'}:
            raise InfluenceError('Each step needs id/reads/writes/dependencies')
        ident = step['id']
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z_0-9]{0,63}', ident) or ident in used_ids:
            raise InfluenceError('Duplicate/invalid step id')
        used_ids.add(ident)
        reads, writes = _slots(step['reads'], 'read'), _slots(step['writes'], 'write')
        deps = step['dependencies']
        if not isinstance(deps, dict) or set(deps) != writes:
            raise InfluenceError('Each written slot needs an explicit dependency set')
        dep_sets = {slot: _slots(value, 'dependency') for slot, value in deps.items()}
        if any(not value <= reads for value in dep_sets.values()):
            raise InfluenceError('Dependency may only refer to declared reads')
        all_slots |= reads | writes
        incoming = {slot: available.get(slot, f'entry:{slot}') for slot in reads}
        produced = {}
        for slot in sorted(writes):
            dst = f'{ident}:{slot}'
            produced[slot] = dst
            for src in sorted(dep_sets[slot]):
                edges.append({'from':incoming[src], 'to':dst, 'through':ident})
        available.update(produced)
        records.append((ident, reads, writes, dep_sets))
    sink_versions = {slot: available.get(slot, f'entry:{slot}') for slot in sinks}
    live = set(sinks)
    contracts = []
    for ident, reads, writes, deps in reversed(records):
        needed = live & writes
        before = (live - writes) | set().union(*(deps[s] for s in needed)) if needed else live - writes
        contracts.append({'step':ident, 'required_on_entry':sorted(before),
                          'required_on_exit':sorted(live),
                          'produced_live':sorted(needed),
                          'dead_written_candidates':sorted(writes - needed)})
        live = before
    contracts.reverse()
    relevant = set(sink_versions.values())
    incoming_edges = defaultdict(list)
    for e in edges: incoming_edges[e['to']].append(e)
    queue = list(relevant)
    while queue:
        for edge in incoming_edges[queue.pop()]:
            if edge['from'] not in relevant:
                relevant.add(edge['from']);queue.append(edge['from'])
    return {'format':'fdisbull-influence-result-1', 'scope':'one closed linear path',
            'required_entry':sorted(live), 'observables':sorted(sinks),
            'sink_versions':sink_versions, 'contracts':contracts,
            'relevant_edges':[e for e in edges if e['to'] in relevant],
            'dead_candidates_notice':'Only dead for specified sinks, closed semantics and observers; not global CPU equivalence'}


def projected_equal(a, b, required):
    """Compare measured state at a selected boundary; not a proof by itself."""
    required = _slots(list(required), 'required')
    if not isinstance(a, dict) or not isinstance(b, dict) or not required <= set(a) or not required <= set(b):
        raise InfluenceError('Missing required state is unknown, not equal')
    return all(a[s] == b[s] for s in required)
