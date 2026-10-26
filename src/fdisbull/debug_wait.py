"""Bounded, observation-driven waits. No screen names or game-specific readiness."""
from __future__ import annotations

import re
import time

from .debugger import bounded, _file_name

_COMPARISONS = {'equals', 'not_equals', 'lt', 'le', 'gt', 'ge', 'greater_than_initial'}


def validate_wait(observations, until, *, guest_ms, slice_ms=50, timeout_ms=10000,
                  fast_forward=True, max_polls=1000, timeout_screenshot='wait-timeout.png'):
    bounded(guest_ms, 'guest_ms', 1, 3600000)
    bounded(slice_ms, 'slice_ms', 1, 10000)
    bounded(timeout_ms, 'timeout_ms', 1, 600000)
    bounded(max_polls, 'max_polls', 1, 1000)
    if type(fast_forward) is not bool:
        raise ValueError('fast_forward must be boolean')
    if timeout_screenshot is not None:
        _file_name(timeout_screenshot)
    if not isinstance(observations, dict) or not 1 <= len(observations) <= 16:
        raise ValueError('wait requires 1..16 named observations')
    for name, spec in observations.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}', name):
            raise ValueError('Observation names must be simple identifiers')
        if not isinstance(spec, dict):
            raise ValueError('Observation requires a descriptor')
        kind = spec.get('kind')
        if kind == 'memory':
            if not {'kind', 'address', 'length'} <= spec.keys() or set(spec) - {'kind', 'address', 'length', 'cs'}:
                raise ValueError('memory observation requires address and length, optional cs')
            bounded(spec['length'], 'observation length', 1, 256)
        elif kind in ('register', 'status'):
            if set(spec) != {'kind', 'path'} or not isinstance(spec['path'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*){0,7}', spec['path']):
                raise ValueError('register/status observation requires an explicit field path')
        else:
            raise ValueError('Observation kind must be memory, register or status')

    predicate_count = 0
    def predicate(p, depth=0):
        nonlocal predicate_count
        predicate_count += 1
        if predicate_count > 256:
            raise ValueError('wait exceeds 256 predicate nodes')
        if not isinstance(p, dict) or depth > 8:
            raise ValueError('Invalid wait predicate')
        if set(p) in ({'all'}, {'any'}):
            children = next(iter(p.values()))
            if not isinstance(children, list) or not 1 <= len(children) <= 16:
                raise ValueError('all/any requires 1..16 predicates')
            for child in children:
                predicate(child, depth + 1)
            return
        ops = set(p) & _COMPARISONS
        if len(ops) != 1 or 'observation' not in p or set(p) - (_COMPARISONS | {'observation', 'mask'}):
            raise ValueError('Predicate requires one comparison and a named observation')
        if p['observation'] not in observations:
            raise ValueError('Predicate refers to an unknown observation')
        op = next(iter(ops))
        if op == 'greater_than_initial' and p[op] is not True:
            raise ValueError('greater_than_initial must be true')
        memory = observations[p['observation']]['kind'] == 'memory'
        for key in ('mask', op):
            if key not in p or key == 'greater_than_initial':
                continue
            value = p[key]
            if memory:
                try:
                    if len(bytes.fromhex(value)) != observations[p['observation']]['length']:
                        raise ValueError('Memory comparison/mask length differs from capture length')
                except (TypeError, ValueError) as error:
                    raise ValueError('Memory comparison/mask must be exact-length hexadecimal bytes') from error
            elif type(value) is not int and not (isinstance(value, str) and (value.startswith('$') or re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)', value))):
                raise ValueError('Register/status comparisons must be integers')
    predicate(until)


def _integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 16 if value.lower().startswith('0x') else 10)
    raise ValueError('Observation is not an integer')


def _matches(predicate, values, initial, observations):
    for key in ('all', 'any'):
        if key in predicate:
            matches = [_matches(p, values, initial, observations) for p in predicate[key]]
            return all(matches) if key == 'all' else any(matches)
    name = predicate['observation']
    op = next(iter(set(predicate) & _COMPARISONS))
    memory = observations[name]['kind'] == 'memory'
    convert = (lambda v: int.from_bytes(bytes.fromhex(v), 'little')) if memory else _integer
    left = convert(values[name])
    right = convert(initial[name] if op == 'greater_than_initial' else predicate[op])
    if 'mask' in predicate:
        mask = convert(predicate['mask'])
        left, right = left & mask, right & mask
    return {'equals': left == right, 'not_equals': left != right, 'lt': left < right,
            'le': left <= right, 'gt': left > right, 'ge': left >= right,
            'greater_than_initial': left > right}[op]


def wait_until(session, observations, until, *, guest_ms, slice_ms=50, timeout_ms=10000,
               fast_forward=True, max_polls=1000, timeout_screenshot='wait-timeout.png'):
    validate_wait(observations, until, guest_ms=guest_ms, slice_ms=slice_ms, timeout_ms=timeout_ms,
                  fast_forward=fast_forward, max_polls=max_polls, timeout_screenshot=timeout_screenshot)
    # A guest clock is a required capability, never inferred from host duration.
    if not session.rpc.capabilities.get('timing', {}).get('fast_forward'):
        raise ValueError('Observation waits require a backend with measured DOS guest time')
    start = time.monotonic()
    deadline = start + timeout_ms / 1000
    result = dict(format='fdisbull-wait-result-1', complete=False, matched=False, outcome='incomplete',
                  requested_guest_ms=guest_ms, guest_elapsed_ms=0, polls=[], runs=[],
                  last_observation=None, initial_observation=None, diagnostic_frame=None, error=None)
    try:
        while True:
            values, captures = {}, {}
            result['last_observation'] = values
            for name, spec in observations.items():
                if spec['kind'] == 'memory':
                    capture = session.memory(**{k: v for k, v in spec.items() if k != 'kind'})
                    value = capture['hex']
                    if len(bytes.fromhex(value)) != spec['length']:
                        raise ValueError('Required memory capture is incomplete: ' + name)
                else:
                    capture = session.registers() if spec['kind'] == 'register' else session.status()
                    value = capture
                    for part in spec['path'].split('.'):
                        value = value[part]
                    value = _integer(value)
                captures[name], values[name] = capture, value
            result['polls'].append(dict(values=dict(values), captures=captures,
                                        guest_elapsed_ms=result['guest_elapsed_ms'],
                                        host_elapsed_ms=round((time.monotonic() - start) * 1000, 3)))
            if result['initial_observation'] is None:
                result['initial_observation'] = dict(values)
            if time.monotonic() >= deadline:
                result['outcome'] = 'timeout'
                break
            if result['guest_elapsed_ms'] > guest_ms:
                result['outcome'] = 'guest_budget'
                break
            if _matches(until, values, result['initial_observation'], observations):
                result.update(complete=True, matched=True, outcome='predicate')
                break
            if time.monotonic() >= deadline:
                result['outcome'] = 'timeout'
                break
            if result['guest_elapsed_ms'] >= guest_ms:
                result['outcome'] = 'guest_budget'
                break
            if len(result['polls']) >= max_polls:
                result['outcome'] = 'poll_budget'
                break
            run = session.run(guest_ms=min(slice_ms, guest_ms-result['guest_elapsed_ms']),
                              timeout_ms=max(1, int((deadline-time.monotonic())*1000)),
                              fast_forward=fast_forward, stop_on_hook=True)
            result['runs'].append(run)
            progress = run.get('guest_elapsed_ms')
            if type(progress) not in (int, float) or progress < 0:
                raise ValueError('Run did not supply measured guest progress')
            result['guest_elapsed_ms'] += progress
            # Stops take precedence even if a subsequent memory read would match.
            if run.get('outcome') != 'guest_time' or run.get('hook_hits'):
                result['outcome'] = 'hook' if run.get('hook_hits') else run.get('outcome', 'incomplete')
                result['stop'] = run
                break
            if progress == 0:
                raise ValueError('Run made no measured guest progress')
    except Exception as error:
        result.update(complete=False, matched=False, outcome='incomplete',
                      error=dict(type=type(error).__name__, message=str(error)))
    if not result['complete'] and timeout_screenshot is not None:
        try:
            result['diagnostic_frame'] = session.screenshot(timeout_screenshot)
        except Exception as error:
            result['capture_error'] = dict(type=type(error).__name__, message=str(error))
    result['host_elapsed_ms'] = round((time.monotonic()-start)*1000, 3)
    result['last_observed_guest_ms'] = result['polls'][-1]['guest_elapsed_ms'] if result['polls'] else None
    result['guest_budget_overshoot_ms'] = max(0,result['guest_elapsed_ms']-guest_ms)
    session._event('wait', result)
    return result
