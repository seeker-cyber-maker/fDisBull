"""Bounded, deterministic debugger-route fuzzing with fresh-run callbacks.

The planner mutates only explicit physical-input or named-scene fields in a
validated script. The runner never owns or reuses a guest: its callback must
execute one case in a fresh owned session and return a terminal receipt. Full
script results and target data belong in the private project, not this summary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Callable


FORMAT = 'fdisbull-fuzz-1'
RESULT_FORMAT = 'fdisbull-fuzz-result-1'
_MAX_DOCUMENT_BYTES = 64 * 1024
_MAX_STEPS = 64
_MAX_SITES = 16
_MAX_CHOICES = 16
_MAX_VARIANTS = 128
_MAX_CASES = 32
_SAFE_OPERATIONS = frozenset({
    'keyboard.press', 'keyboard.type', 'click', 'scene-act',
    'wait', 'run', 'status', 'frame-probe', 'scene-check', 'scene-wait',
})
_MUTABLE_FIELDS = {
    'keyboard.press': frozenset({'key'}),
    'keyboard.type': frozenset({'text'}),
    'click': frozenset({'x', 'y', 'button'}),
    'scene-act': frozenset({'scene', 'object'}),
}
_IDENTIFIER = re.compile(r'[A-Za-z0-9._:-]+\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_RUN_ID = re.compile(r'[0-9a-f]{32}\Z')


@dataclass(frozen=True)
class FuzzMutation:
    step_index: int
    field: str
    choice_index: int


@dataclass(frozen=True)
class FuzzCase:
    index: int
    script_sha256: str
    mutation: FuzzMutation | None
    timeout_ms: int
    _script_json: str = field(repr=False)

    @property
    def script(self) -> dict:
        """Return a fresh script value; callers cannot change the saved plan."""
        return json.loads(self._script_json)


def _json_value(value, depth=0) -> None:
    if depth > 32:
        raise ValueError('Campaign JSON nesting exceeds 32 levels')
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('Campaign JSON object keys must be strings')
            _json_value(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _json_value(item, depth + 1)
    elif isinstance(value, str):
        if value.startswith('$'):
            raise ValueError('Fuzz scripts and choices cannot use result references')
    elif value is not None and type(value) not in (bool, int, float):
        raise ValueError('Campaign requires JSON values only')


def _canonical(value) -> str:
    _json_value(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError('Campaign requires finite JSON values') from error


def _bounded_int(value, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def _safe_script(script: dict) -> None:
    if not isinstance(script, dict) or script.get('format') != 'fdisbull-script-1':
        raise ValueError('Fuzz base_script must be fdisbull-script-1')
    steps = script.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= _MAX_STEPS:
        raise ValueError('Fuzz script requires 1 to 64 flat steps')
    for step in steps:
        if (not isinstance(step, dict) or not isinstance(step.get('op'), str)
                or step['op'] not in _SAFE_OPERATIONS):
            raise ValueError('Fuzz script contains an unsupported or mutating operation')
    from .debug_script import validate_script
    validate_script(script)


def _choice_value(op: str, name: str, value) -> None:
    if name in ('key', 'text', 'scene', 'object'):
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise ValueError('Fuzz input/scene choices require short nonempty text')
    elif name == 'button':
        if value not in ('left', 'right', 'middle'):
            raise ValueError('Fuzz button must be left, right or middle')
    elif name == 'x':
        _bounded_int(value, 'x choice', 0, 1919)
    elif name == 'y':
        _bounded_int(value, 'y choice', 0, 1079)
    else:
        raise ValueError(f'Fuzz cannot mutate {op}.{name}')


def plan_campaign(document: dict) -> tuple[FuzzCase, ...]:
    """Validate all candidates and return baseline plus seeded single edits.

    Case order is stable for the same canonical manifest and seed. The planner
    performs no debugger action and does not write files.
    """
    if not isinstance(document, dict) or document.get('format') != FORMAT:
        raise ValueError('Campaign requires format=fdisbull-fuzz-1')
    if set(document) - {'format', 'base_script', 'mutation_sites', 'seed', 'max_cases', 'timeout_ms'}:
        raise ValueError('Unknown campaign field')
    encoded = _canonical(document)
    if len(encoded.encode()) > _MAX_DOCUMENT_BYTES:
        raise ValueError('Campaign exceeds 64 KiB')
    seed = _bounded_int(document.get('seed', 0), 'seed', 0, 2**32 - 1)
    max_cases = _bounded_int(document.get('max_cases', 3), 'max_cases', 1, _MAX_CASES)
    timeout_ms = _bounded_int(document.get('timeout_ms', 60000), 'timeout_ms', 1, 600000)
    script = document.get('base_script')
    _safe_script(script)
    sites = document.get('mutation_sites')
    if not isinstance(sites, list) or not 1 <= len(sites) <= _MAX_SITES:
        raise ValueError('Campaign requires 1 to 16 finite mutation sites')
    baseline = _canonical(script)
    variants: list[tuple[str, FuzzMutation]] = []
    seen_sites: set[tuple[int, str]] = set()
    seen_scripts = {hashlib.sha256(baseline.encode()).hexdigest()}
    total_choices = 0
    for site in sites:
        if not isinstance(site, dict) or set(site) != {'index', 'field', 'choices'}:
            raise ValueError('Mutation site requires index, field and choices')
        index = _bounded_int(site['index'], 'mutation step index', 0, len(script['steps']) - 1)
        name = site['field']
        step = script['steps'][index]
        op = step['op']
        if not isinstance(name, str) or name not in _MUTABLE_FIELDS.get(op, ()) or name not in step:
            raise ValueError('Mutation site must select an existing physical input or scene action field')
        if (index, name) in seen_sites:
            raise ValueError('Duplicate mutation site')
        seen_sites.add((index, name))
        choices = site['choices']
        if not isinstance(choices, list) or not 1 <= len(choices) <= _MAX_CHOICES:
            raise ValueError('Mutation site requires 1 to 16 literal choices')
        total_choices += len(choices)
        if total_choices > _MAX_VARIANTS:
            raise ValueError('Campaign exceeds 128 declared choices')
        _choice_value(op, name, step[name])
        seen_choices: set[str] = set()
        for choice_index, value in enumerate(choices):
            _choice_value(op, name, value)
            canonical_choice = _canonical(value)
            if canonical_choice in seen_choices:
                raise ValueError('Duplicate mutation choice')
            seen_choices.add(canonical_choice)
            if value == step[name]:
                continue
            candidate = json.loads(baseline)
            candidate['steps'][index][name] = value
            _safe_script(candidate)
            candidate_json = _canonical(candidate)
            digest = hashlib.sha256(candidate_json.encode()).hexdigest()
            if digest in seen_scripts:
                continue
            seen_scripts.add(digest)
            variants.append((candidate_json, FuzzMutation(index, name, choice_index)))
    if not variants:
        raise ValueError('Campaign has no distinct mutated case')
    # A digest-derived shuffle is stable across Python versions and machines.
    variants.sort(key=lambda item: hashlib.sha256(
        seed.to_bytes(4, 'big') + item[0].encode()).digest())
    chosen = [(baseline, None), *variants[:max_cases - 1]]
    return tuple(FuzzCase(index, hashlib.sha256(body.encode()).hexdigest(), mutation,
                          timeout_ms, body)
                 for index, (body, mutation) in enumerate(chosen))


def _safe_id(value, name: str, limit: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f'{name} must be a bounded portable identifier')
    return value


def _receipt(receipt, case: FuzzCase) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError('Fuzz runner must return a terminal receipt object')
    status = receipt.get('status')
    if status not in ('passed', 'failed', 'unknown'):
        raise ValueError('Fuzz receipt status must be passed, failed or unknown')
    script_sha = receipt.get('script_sha256')
    if not isinstance(script_sha, str) or script_sha != case.script_sha256:
        raise ValueError('Fuzz receipt script SHA-256 differs from the planned case')
    run_id = receipt.get('run_id')
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError('Fuzz receipt requires a live 32-character run ID')
    identities = {}
    for name in ('source_sha256', 'runtime_sha256', 'adapter_sha256'):
        value = receipt.get(name)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError('Fuzz receipt requires exact source, runtime and adapter SHA-256 identities')
        identities[name] = value
    completed = _bounded_int(receipt.get('completed_steps'), 'completed_steps',
                             0, len(case.script['steps']))
    if status == 'passed' and completed != len(case.script['steps']):
        raise ValueError('Fuzz pass lacks completed script steps')
    stages = receipt.get('stage_ids')
    if not isinstance(stages, list) or len(stages) > 128:
        raise ValueError('Fuzz receipt requires at most 128 stage identifiers')
    stages = [_safe_id(stage, 'stage', 64) for stage in stages]
    family = receipt.get('fault_family')
    if family is not None:
        family = _safe_id(family, 'fault family', 160)
        if status != 'failed':
            raise ValueError('Only a failed case can have a fault family')
    reaped = receipt.get('owned_process_reaped')
    if type(reaped) is not bool:
        raise ValueError('Fuzz receipt requires an exact process-reaped boolean')
    kind = ('fault' if family is not None else
            'nonfault_failure' if status == 'failed' else
            'unknown' if status == 'unknown' else 'none')
    return {**identities, 'script_sha256': script_sha, 'run_id': run_id,
            'status': status, 'failure_kind': kind,
            'completed_steps': completed, 'stage_ids': stages,
            'fault_family': family, 'owned_process_reaped': reaped}


def run_campaign(document: dict, run_case: Callable[[FuzzCase], dict]) -> dict:
    """Run a prevalidated finite plan through a fresh-case callback.

    This is a protocol, not evidence that a callback really reaped its guest.
    The host adapter must establish that fact before returning its receipt.
    Callback exceptions and malformed receipts stop the campaign immediately.
    """
    if not callable(run_case):
        raise ValueError('Campaign requires a fresh-case callback')
    cases = plan_campaign(document)  # Validate every candidate before any run.
    campaign_sha = hashlib.sha256(_canonical(document).encode()).hexdigest()
    observed: list[dict] = []
    corpus: list[int] = []
    seen_edges: set[tuple] = set()
    seen_faults: set[tuple] = set()
    seen_runs: set[str] = set()
    stop_reason = 'completed'
    for case in cases:
        item = _receipt(run_case(case), case)
        if item['run_id'] in seen_runs:
            raise ValueError('Fuzz runner reused a live run ID across cases')
        seen_runs.add(item['run_id'])
        identity = tuple(item[name] for name in
                         ('source_sha256', 'runtime_sha256', 'adapter_sha256'))
        # A nonfault failure after the same milestones is still a new terminal
        # transition relative to a pass. Unknown outcomes are never retained.
        stage_sequence = ('start', *item['stage_ids'], 'end:' + item['status'])
        edges = {(identity, left, right) for left, right in
                 zip(stage_sequence, stage_sequence[1:])}
        eligible = item['owned_process_reaped'] and item['status'] != 'unknown'
        new_edges = edges - seen_edges if eligible else set()
        fault_key = (identity, item['fault_family']) if item['fault_family'] else None
        new_fault = eligible and fault_key is not None and fault_key not in seen_faults
        if eligible:
            seen_edges.update(edges)
            if fault_key is not None:
                seen_faults.add(fault_key)
        if new_edges or new_fault:
            corpus.append(case.index)
        mutation = case.mutation
        observed.append({
            'index': case.index,
            'mutation': None if mutation is None else {
                'step_index': mutation.step_index, 'field': mutation.field,
                'choice_index': mutation.choice_index},
            **item, 'new_stage_edges': len(new_edges),
            'new_fault_family': new_fault, 'retained': bool(new_edges or new_fault),
        })
        if not item['owned_process_reaped']:
            stop_reason = 'cleanup_unverified'
            break
        if item['status'] == 'unknown':
            stop_reason = 'outcome_unknown'
            break
    return {'format': RESULT_FORMAT, 'campaign_sha256': campaign_sha,
            'planned_cases': len(cases), 'executed_cases': len(observed),
            'stop_reason': stop_reason, 'cases': observed,
            'corpus_case_indices': corpus}
