"""Retain an owned original-call watch across separate UI requests.

The watch records explicit E8 candidates, not guessed scene transitions. Arming
does not operate the UI; status never runs the CPU. Finishing consumes only a
currently observed candidate and delegates the original call to the normal
capture wrapper, including its artifacts and dependency facts.
"""

from copy import deepcopy
import struct
import time

from .z_call_contract import _identity, _integer, _number, _qualified, _read
from .z_dos import _delete_owned_temporary_breakpoint


_KEY = 'native_capture_watch'
_FORMAT = 'fdisbull-native-capture-watch-1'
_OPTIONS = frozenset(('argument_registers', 'argument_bytes', 'stack_bytes',
    'execute', 'continuation_steps', 'guest_ms', 'timeout_ms', 'replace',
    'summary', 'output'))
_INACTIVE = frozenset(('finished', 'cancelled', 'arm_failed'))


def _stop(session):
    status = session.call('session.status')
    reason = status.get('session', {}).get('stop_reason',
        status.get('stop_reason', status.get('last_stop', {}))) or {}
    return status, reason


def _cleanup(ctx, watch):
    remaining, errors = [], []
    for owned in watch['breakpoints']:
        try:
            _delete_owned_temporary_breakpoint(ctx.d, owned['breakpoint_id'])
        except Exception as error:
            remaining.append(owned)
            errors.append({'breakpoint_id': owned['breakpoint_id'],
                           'error': f'{type(error).__name__}: {error}'})
    watch['breakpoints'] = remaining
    watch['cleanup_errors'] = errors
    if errors:
        watch['phase'] = 'cleanup_failed'
        raise RuntimeError('owned capture-watch breakpoint cleanup incomplete; inspect watch status')


def _snapshot(ctx, watch):
    if watch is None:
        return {'format': _FORMAT, 'phase': 'absent', 'active': False,
                'candidate_hit': False, 'breakpoints': []}
    result = {key: deepcopy(value) for key, value in watch.items()
              if key not in ('capture_options', 'runtime')}
    result['active'] = watch['phase'] not in _INACTIVE
    result['candidate_hit'] = False
    if watch['runtime'] != _identity(ctx):
        result['runtime_matches'] = False
        result['reason'] = 'watch belongs to another live owner; no breakpoint IDs were touched'
        return result
    result['runtime_matches'] = True
    if not result['active']:
        return result
    regs = ctx.d.registers()
    status, reason = _stop(ctx.d)
    ip = _number(regs['instruction_pointer'])
    at = next((row for row in watch['candidates']
               if row['callsite'] == ip and _qualified(regs, watch['code_selector'])), None)
    result['current'] = {'cpu_mode': regs.get('cpu_mode'),
                         'cs': regs['segments']['cs'], 'ip': regs['instruction_pointer'],
                         'state': status.get('state'), 'stop': deepcopy(reason)}
    result['at_candidate'] = at is not None
    owned = {row['breakpoint_id'] for row in watch['breakpoints']}
    foreign = (status.get('hook_hits') or reason.get('kind') not in
               ('pause', 'step', 'entry', 'start', 'breakpoint')
               or reason.get('kind') == 'breakpoint'
               and reason.get('breakpoint_id') not in owned)
    if at and status.get('state') == 'stopped' and not foreign:
        result['candidate_hit'] = True
        result['hit_callsite'] = at['callsite']
    elif foreign:
        result['reason'] = 'foreign debugger stop retained'
    return result


def native_capture_watch(ctx, op='status', name=None, callsites=None,
                         code_selector=None, **capture_options):
    """Arm, inspect, finish or cancel one same-owner multi-candidate call watch.

``arm`` takes 1..16 explicit original E8 linear callsites and a qualified flat32
code selector. UI navigation occurs through ordinary later requests. A delivered
input or input exception neither finishes nor discards this watch. ``finish``
requires an observed candidate; it cleans all owned IDs before capturing the
original call. A failed finish is never silently retried. ``cancel`` cleans only
owned IDs and never resumes the CPU. No target-specific addresses are included.
"""
    if op not in ('arm', 'status', 'finish', 'cancel'):
        raise ValueError('op must be arm, status, finish or cancel')
    watch = ctx.state.get(_KEY)
    if op == 'status':
        if name is not None or callsites is not None or code_selector is not None or capture_options:
            raise ValueError('status takes no extra arguments')
        return _snapshot(ctx, watch)
    if op == 'arm':
        if watch and watch['phase'] not in _INACTIVE:
            raise ValueError('a capture watch is already active; finish or cancel it explicitly')
        if ctx.state.get('native_call_pending') or ctx.state.get('native_contract_pending'):
            raise ValueError('a previous native invocation needs recovery before arming a watch')
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError('name must contain 1..128 characters')
        _integer(code_selector, 'code_selector', 1, 65535)
        if (not isinstance(callsites, (list, tuple)) or not 1 <= len(callsites) <= 16
                or any(type(value) is not int for value in callsites)
                or len(set(callsites)) != len(callsites)):
            raise ValueError('callsites must contain 1..16 distinct integer addresses')
        qualification = capture_options.pop('qualification_guest_ms', 1000)
        _integer(qualification, 'qualification_guest_ms', 0, 60000)
        timeout = capture_options.get('timeout_ms', 10000)
        _integer(timeout, 'timeout_ms', 1, 600000)
        if set(capture_options) - _OPTIONS:
            raise ValueError('unsupported capture option; trigger belongs in later UI requests')
        candidates = []
        for address in callsites:
            _integer(address, 'callsite', 0, 0xFFFFFFFA)
            raw = _read(ctx.d, address, 5)
            if raw[0] != 0xE8:
                raise ValueError(f'candidate {address:#x} is not an original E8 rel32 call')
            target = (address + 5 + struct.unpack('<i', raw[1:])[0]) & 0xFFFFFFFF
            candidates.append({'callsite': address, 'call_hex': raw.hex(), 'entry': target,
                               'signature_hex': _read(ctx.d, target, 16).hex()})
        status, reason = _stop(ctx.d)
        if (status.get('state') != 'stopped' or status.get('hook_hits')
                or reason.get('kind') not in ('pause', 'step', 'entry', 'start')):
            raise RuntimeError('initial foreign debugger stop retained before arming capture watch')
        regs, used = ctx.d.registers(), 0
        deadline = time.monotonic() + timeout / 1000
        while not _qualified(regs, code_selector):
            left = int((deadline - time.monotonic()) * 1000)
            if used >= qualification or left <= 0:
                raise RuntimeError('capture-watch selector qualification budget expired')
            budget = min(1 + used % 3, qualification - used)
            run = ctx.d.run(guest_ms=budget, timeout_ms=left, fast_forward=False, stop_on_hook=True)
            if run.get('hook_hits') or run.get('stop', {}).get('trigger') != 'guest_time':
                raise RuntimeError('another debugger stop interrupted capture-watch qualification')
            used += max(budget, run.get('guest_elapsed_ms', budget))
            regs = ctx.d.registers()
        watch = {'format': _FORMAT, 'name': name, 'runtime': _identity(ctx),
                 'code_selector': code_selector, 'candidates': candidates,
                 'breakpoints': [], 'capture_options': deepcopy(capture_options),
                 'qualification_guest_ms': used, 'phase': 'arming',
                 'scope': 'Original callsite event watch; no scene or argument semantics inferred.'}
        ctx.state[_KEY] = watch
        try:
            for row in candidates:
                created = ctx.d.call('breakpoints.create', {'kind': 'execution', 'once': True,
                    'address': {'space': 'segmented', 'segment': f'0x{code_selector:04X}',
                                'offset': f'0x{row["callsite"]:08X}'}})
                watch['breakpoints'].append({'callsite': row['callsite'],
                                             'breakpoint_id': created['breakpoint_id']})
            watch['phase'] = 'armed'
            return _snapshot(ctx, watch)
        except Exception as error:
            watch['error'] = f'{type(error).__name__}: {error}'
            _cleanup(ctx, watch)
            watch['phase'] = 'arm_failed'
            raise
    if watch is None:
        raise ValueError('no capture watch exists')
    if watch['runtime'] != _identity(ctx):
        raise ValueError('watch belongs to another live owner; its breakpoint IDs were not touched')
    if op == 'cancel':
        if name is not None or callsites is not None or code_selector is not None or capture_options:
            raise ValueError('cancel takes no extra arguments')
        _cleanup(ctx, watch)
        watch['phase'] = 'cancelled'
        return _snapshot(ctx, watch)
    if name is not None or callsites is not None or code_selector is not None:
        raise ValueError('finish uses the armed name and candidates')
    if set(capture_options) - _OPTIONS:
        raise ValueError('unsupported capture option')
    if watch['phase'] != 'armed':
        raise ValueError('watch cannot finish in this phase; inspect partial capture before explicit cancellation')
    observed = _snapshot(ctx, watch)
    if not observed['candidate_hit']:
        raise RuntimeError('no owned candidate is currently stopped; watch and current stop retained')
    callsite = observed['hit_callsite']
    row = next(row for row in watch['candidates'] if row['callsite'] == callsite)
    if _read(ctx.d, callsite, 5).hex() != row['call_hex']:
        raise RuntimeError('watched original call bytes changed; stop and watch retained')
    if _read(ctx.d, row['entry'], 16).hex() != row['signature_hex']:
        raise RuntimeError('watched callee signature changed; stop and watch retained')
    _cleanup(ctx, watch)
    watch['phase'] = 'finishing'
    options = {**watch['capture_options'], **capture_options}
    try:
        result = ctx.capture_native_call(watch['name'], callsite, watch['code_selector'], **options)
        watch.update(phase='finished', hit_callsite=callsite,
                     capture_path=result.get('path'), capture_status=result.get('status'))
        return {'watch': _snapshot(ctx, watch), 'capture': result}
    except Exception as error:
        watch.update(phase='finish_failed', hit_callsite=callsite,
                     error=f'{type(error).__name__}: {error}')
        raise


ACTIONS = {'native-capture-watch': {'handler': native_capture_watch,
    'description': 'Persist owned E8 event candidates across separate UI requests, then finish observed capture',
    'entry': 'One owned original DOS guest; caller identifies flat32 candidates',
    'next_state': 'Armed event predicate or captured original call'}}
