"""Bounded, source-bound feedback for the existing Windows native harness.

Each case is a fresh owned guest run. This module scores retained observations;
it does not mutate game bytes, restart an uncertain action, or drive a VM.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    operations: tuple[str, ...]
    debug_probes: bool
    trace_farcall: bool
    gpr_probe: bool


WIN16_CASES = (
    Case('bootstrap-only', ('bootstrap', 'register-edit-restore', 'physical-n', 'physical-r', 'named-scene', 'spectator'), False, False, True),
    Case('entry-step', ('bootstrap', 'register-edit-restore', 'entry-jmp-step', 'breakpoint-hit', 'physical-n', 'physical-r', 'named-scene', 'spectator'), True, False, True),
    Case('full-debugger', ('bootstrap', 'register-edit-restore', 'entry-jmp-step', 'breakpoint-hit', 'far-call-trace', 'physical-n', 'physical-r', 'named-scene', 'spectator'), True, True, True),
)


_COMPLETED_STAGE_OPERATIONS = {
    'actual-original-ne-entry': ('bootstrap',),
    'actual-ne-checked-register-edit-restored-before-continuation': ('register-edit-restore',),
    'controlled-entry-jmp-step-and-breakpoint-without-far-call-trace': ('entry-jmp-step','breakpoint-hit'),
    'actual-ne-memory-execution-breakpoint-step-trace': ('entry-jmp-step','breakpoint-hit','far-call-trace'),
    'physical-ne-key-produced-observed-body-pixel': ('physical-n',),
    'actual-ne-ordinary-r-reset': ('physical-r',),
    'actual-ne-named-scene-replayed-physical-transition': ('named-scene',),
    'actual-ne-dot-mode-retained-frame-http-no-host-input': ('spectator',),
}


def fault_family(snapshot: dict) -> tuple | None:
    """Group the *same observed failure*, never just exception code + PC."""
    native = snapshot.get('native_contexts')
    if not isinstance(native, dict):
        return None
    event = native.get('pending_event', {}).get('exception')
    if not isinstance(event, dict) or event.get('parameter_count') != 2:
        return None
    parameters = event.get('parameters')
    if not isinstance(parameters, list) or len(parameters) != 2:
        return None
    stop = snapshot.get('stop', {})
    registers = snapshot.get('registers', {})
    descriptor = snapshot.get('stack_descriptor', {})
    try:
        access_kind = int(parameters[0], 0)
        fault_address = int(parameters[1], 0)
        code = int(event['code'])
        cs = int(registers['cs'], 0)
        ss = int(registers['ss'], 0)
    except (KeyError, TypeError, ValueError):
        return None
    if code != 0xC0000005 or access_kind not in (0, 1, 8):
        return None
    project_address = stop.get('project_address')
    # A mapped NE source location is stable across relocated selectors. A raw
    # unmapped PC remains an unknown runtime address, except the exact null PC.
    try:
        raw_is_null = int(str(stop.get('raw_address', '-1')), 0) == 0
    except ValueError:
        raw_is_null = False
    location = ('source', project_address) if project_address else (
        'null' if raw_is_null else 'unmapped-runtime')
    return (code, access_kind, fault_address, location,
            'ldt' if cs & 4 else 'gdt', 'ldt' if ss & 4 else 'gdt',
            descriptor.get('type'), descriptor.get('default_big'))


def observe(case: Case, receipt: dict, fault: dict | None = None) -> dict:
    """A stage edge is feedback; a failure signature is separate evidence."""
    source = receipt.get('source_sha256')
    if source is None or receipt.get('status') not in ('passed', 'failed'):
        raise ValueError('Campaign case requires an identified, terminal native receipt')
    if (receipt.get('debug_probes') is not case.debug_probes or
            receipt.get('trace_farcall') is not case.trace_farcall or
            receipt.get('gpr_probe') is not case.gpr_probe):
        raise ValueError('Case flags differ from the native operation sequence')
    if case.gpr_probe and receipt.get('gpr_probe_kind')!='paired-integer-edit-restore':
        raise ValueError('Case requires the native paired integer edit and restore path')
    runtime = receipt.get('runtime_inputs', {}).get('initramfs', {}).get('sha256')
    adapter = receipt.get('adapter_sha256')
    if not all(isinstance(value, str) and len(value) == 64 and
               all(character in '0123456789abcdef' for character in value)
               for value in (source, runtime, adapter)):
        raise ValueError('Campaign observation requires exact source, runtime and adapter identities')
    stages = tuple(row['stage'] for row in receipt['checks'])
    edges = tuple(zip(('start',) + stages, stages + ('end',)))
    completed = tuple(op for stage in stages for op in _COMPLETED_STAGE_OPERATIONS.get(stage, ()))
    if any(op not in case.operations for op in completed):
        raise ValueError('Observed operation lies outside the declared native case')
    family = fault_family(fault) if fault is not None else None
    if receipt['status'] == 'failed' and receipt.get('first_unknown_av') and family is None:
        raise ValueError('First-fault family lacks authoritative exception context')
    return {'case': case.name, 'source_sha256': source,
            'runtime_sha256': runtime, 'adapter_sha256': adapter,
            'status': receipt['status'], 'operations': list(case.operations),
            'completed_operations': list(completed),
            'stage_edges': [list(edge) for edge in edges],
            'fault_family': list(family) if family else None,
            'original_reaped': receipt.get('owned_process_reaped') is True}


def select_corpus(observations: list[dict]) -> dict:
    """Retain new feedback and the shortest declared failed case per family.

    A stopped fault proves only the completed operation prefix. The remaining
    declared operations are an intended test route, not a reproducer.
    """
    seen_edges: set[tuple] = set()
    seen_faults: set[tuple] = set()
    novel = []
    for observation in observations:
        identity = tuple(observation[name] for name in
                         ('source_sha256', 'runtime_sha256', 'adapter_sha256'))
        edges = {(identity, tuple(edge)) for edge in observation['stage_edges']}
        family = (identity, tuple(_freeze(observation['fault_family']))) if observation['fault_family'] else None
        new_edges = edges - seen_edges
        new_fault = family is not None and family not in seen_faults
        if new_edges or new_fault:
            novel.append({'case': observation['case'], 'new_stage_edges': len(new_edges),
                          'new_fault_family': new_fault,
                          'source_sha256': identity[0], 'runtime_sha256': identity[1],
                          'adapter_sha256': identity[2]})
        seen_edges.update(edges)
        if family is not None: seen_faults.add(family)
    shortest = {}
    for observation in observations:
        if observation['status'] != 'failed' or not observation['fault_family']: continue
        key = json.dumps((observation['source_sha256'], observation['runtime_sha256'],
                          observation['adapter_sha256'], observation['fault_family']), separators=(',', ':'))
        if key not in shortest or len(observation['operations']) < len(shortest[key]['operations']):
            shortest[key] = observation
    return {'schema': 'fdisbull-windows-sequence-campaign-2', 'novel_cases': novel,
            'shortest_declared_failure_cases': [
                {'source_sha256': v['source_sha256'], 'runtime_sha256': v['runtime_sha256'],
                 'adapter_sha256': v['adapter_sha256'], 'fault_family': v['fault_family'],
                 'case': v['case'], 'declared_operations': v['operations'],
                 'completed_operations': v['completed_operations']}
                for v in shortest.values()]}


def _freeze(value):
    if isinstance(value, list): return tuple(_freeze(v) for v in value)
    return value


def retain_campaign(output: Path, observations: list[dict]) -> dict:
    """Write only the sanitized operation and feedback summary outside Git."""
    output = Path(output)
    if not output.parent.is_dir() or output.exists():
        raise ValueError('Campaign output needs a fresh file in an existing private parent')
    result = select_corpus(observations)
    data = (json.dumps(result, indent=2) + '\n').encode()
    output.write_bytes(data)
    return {'path': str(output), 'sha256': hashlib.sha256(data).hexdigest(),
            'cases': len(observations), 'fault_families': len(result['shortest_declared_failure_cases'])}


def run_bounded(cases: tuple[Case, ...], run_fresh_case, *, max_cases: int = 3) -> tuple[list[dict], dict]:
    """Execute at most three fresh cases through the caller's existing harness.

    The callback must return (terminal receipt, optional stopped fault). A
    failed/uncertain cleanup ends the campaign; it is never replay permission.
    """
    if type(max_cases) is not int or not 1 <= max_cases <= 3 or len(cases) < max_cases:
        raise ValueError('Campaign requires one to three declared fresh cases')
    if len({case.name for case in cases}) != len(cases) or any(not case.operations for case in cases):
        raise ValueError('Campaign cases need distinct names and ordered operations')
    observations = []
    for case in cases[:max_cases]:
        receipt, fault = run_fresh_case(case)
        observation = observe(case, receipt, fault)
        observations.append(observation)
        if not observation['original_reaped']:
            break
    return observations, select_corpus(observations)
