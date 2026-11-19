"""Bounded held-key movement over witnessed RAM and native virtual time.

No source-address, scene, map, renderer or completed-frame authority is inferred.
The public macro adapter retains ownership of its own cleanup rules.
"""
from copy import deepcopy
import json
import re
import time

from .movement import validate_movement, validate_predicate, matches, _bounded, _call, _refs
from .qemu_macros import _macro_scope, RESULT_PATHS
from .qemu_clock import clock_timer_stop_is_ordinary
from .scene_values import ObservationReads, runtime_memory_ref, scalar_type


_LOCAL = re.compile(r'\$start\.outputs\.([A-Za-z_][A-Za-z_0-9]*)\Z')
_NAME = re.compile(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}\Z')
_MAX_EVIDENCE = 8 * 1024**2
_INPUT_DELAY_NS = 1


def local_lease_reference(value):
    return isinstance(value, str) and _LOCAL.fullmatch(value) is not None


def _reference(value):
    return isinstance(value, str) and value.startswith('$')


def _unknown(value, *, local=False):
    if _reference(value): return not (local and local_lease_reference(value))
    if isinstance(value, dict): return any(_unknown(v, local=local) for v in value.values())
    if isinstance(value, list): return any(_unknown(v, local=local) for v in value)
    return False


def _predicate(value, fields, partial, depth=0):
    if partial and _reference(value): return
    if not isinstance(value, dict) or depth > 8: raise ValueError('Invalid movement predicate')
    if set(value) in ({'all'}, {'any'}):
        children = next(iter(value.values()))
        if partial and _reference(children): return
        if not isinstance(children, list) or not 1 <= len(children) <= 32:
            raise ValueError('Invalid predicate operands')
        for child in children: _predicate(child, fields, partial, depth + 1)
        return
    if set(value) == {'not'}:
        _predicate(value['not'], fields, partial, depth + 1)
        return
    if set(value) != {'field', 'op', 'value'}: raise ValueError('Invalid movement predicate fields')
    field, op, operand = value['field'], value['op'], value['value']
    if not (partial and _reference(field)) and (not isinstance(field, str) or not field or fields is not None and field not in fields):
        raise ValueError('Movement predicate requires a known field')
    if not (partial and _reference(op)) and op not in ('eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in_range'):
        raise ValueError('Invalid movement predicate operator')
    if partial and _reference(operand): return
    if op == 'in_range' or partial and _reference(op) and isinstance(operand, list):
        if not isinstance(operand, list) or len(operand) != 2:
            raise ValueError('Invalid movement range')
        known = [not (partial and _reference(v)) for v in operand]
        if any(k and type(v) is not int for k, v in zip(known, operand)) or all(known) and operand[0] > operand[1]:
            raise ValueError('Invalid movement range')
    elif type(operand) not in (int, str, bool): raise ValueError('Invalid movement comparison')


def validate_parameters(macro_set, *, start, stop, observations, until, progress, settle,
        guest_ms=10000, timeout_ms=10000, slice_ms=50, cleanup_guest_ms=250, max_polls=1000,
        context=None, scene=None, position=None, target=None, boundary_tolerance=1,
        spatial_map=None, map_conditions=None, room_field='room', target_tolerance=0,
        allow_references=False):
    """Check known literals independently; no native observation during admission."""
    partial = allow_references
    if not isinstance(macro_set, str) or not macro_set: raise ValueError('Movement requires a macro set')
    for value in (start, stop):
        if partial and _reference(value): continue
        _call(value)
        if not value['name'] or 'args' in value and not isinstance(value['args'], dict) and not (partial and _reference(value['args'])):
            raise ValueError('Movement controls require a name and argument object')
    for key, value, low, high in (
            ('guest_ms', guest_ms, 1, 3600000), ('timeout_ms', timeout_ms, 1, 600000),
            ('slice_ms', slice_ms, 1, 1000), ('cleanup_guest_ms', cleanup_guest_ms, 1, 10000),
            ('max_polls', max_polls, 1, 10000), ('boundary_tolerance', boundary_tolerance, 0, 64),
            ('target_tolerance', target_tolerance, 0, 64)):
        if not (partial and _reference(value)): _bounded(value, key, low, high)
    for name, value in (('scene', scene), ('position', position), ('target', target),
                        ('spatial_map', spatial_map), ('map_conditions', map_conditions)):
        if value is not None and not (partial and _reference(value)):
            raise ValueError('QEMU witnessed movement does not support ' + name)
    fields = None
    if not (partial and _reference(observations)):
        if not isinstance(observations, dict) or not 1 <= len(observations) <= 16:
            raise ValueError('Expected 1..16 named movement observations')
        fields = set(observations)
        for name, spec in observations.items():
            if not isinstance(name, str) or not _NAME.fullmatch(name): raise ValueError('Invalid named observation')
            if partial and _reference(spec): continue
            if not isinstance(spec, dict) or set(spec) != {'runtime_memory'}:
                raise ValueError('QEMU movement requires witnessed runtime_memory scalar observations')
            ref = spec['runtime_memory']
            if partial and _reference(ref): continue
            if not isinstance(ref, dict) or not {'binding', 'type'} <= set(ref) <= {'binding', 'type', 'offset', 'endian'}:
                raise ValueError('Invalid typed runtime memory reference')
            if not isinstance(ref['binding'], str) or not ref['binding']: raise ValueError('Invalid runtime binding')
            if not (partial and _reference(ref.get('offset', 0))): _bounded(ref.get('offset', 0), 'runtime offset', 0, 65535)
            if not (partial and _reference(ref['type'])): scalar_type(ref['type'])
            if not (partial and _reference(ref.get('endian'))) and ref.get('endian', 'little') not in ('little', 'big'):
                raise ValueError('Invalid scene byte order')
            if not _unknown(ref): runtime_memory_ref(ref)
    for predicate in (until, settle): _predicate(predicate, fields, partial)
    if context is not None: _predicate(context, fields, partial)
    if not (partial and _reference(progress)):
        if not isinstance(progress, dict) or set(progress) != {'fields', 'samples'}:
            raise ValueError('QEMU movement requires sample progress; frame progress is unsupported')
        selected = progress['fields']
        if not (partial and _reference(selected)):
            if not isinstance(selected, list) or not selected or any(not isinstance(v, str) or not v for v in selected):
                raise ValueError('Progress needs known fields')
            known = [v for v in selected if not (partial and _reference(v))]
            if len(set(selected)) != len(selected) or fields is not None and any(v not in fields for v in known):
                raise ValueError('Progress needs unique known fields')
        if not (partial and _reference(progress['samples'])): _bounded(progress['samples'], 'progress window', 1, 1000)
    if not partial:
        # Reuse the established concrete contract and scalar/predicate meanings.
        validate_movement(observations, until, progress, settle, guest_ms=guest_ms, timeout_ms=timeout_ms,
            slice_ms=slice_ms, cleanup_guest_ms=cleanup_guest_ms, max_polls=max_polls, context=context,
            scene=scene, position=position, target=target, boundary_tolerance=boundary_tolerance,
            spatial_map=spatial_map, map_conditions=map_conditions, room_field=room_field,
            target_tolerance=target_tolerance)


def _admit(session):
    from .qemu_wait import validate_qemu_wait_session
    from .qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
    validate_qemu_wait_session(session)
    session._runtime_admit()
    if not session.capabilities.get('physical_input'):
        raise ValueError('QEMU movement requires owned physical keyboard input')
    if (not session.capabilities.get('virtual_input_schedule')
            or not INPUT_SCHEDULE_COMMANDS <= session.vm.qmp_commands):
        raise ValueError('QEMU movement requires the native virtual input schedule')
    if (getattr(session, '_qemu_cpu_delta_history', None) or {}).get('frozen'):
        raise ValueError('Selected CPU/RAM partial state is frozen')


def control_plans(session, macro_set, start, stop, *, allow_references=False):
    """Prove only the stop leases emitted by this exact typed start expansion."""
    from .input_macros import expand_macro
    from .qemu_input import MAX_LEASES, MAX_PENDING_EDGES, _key
    _admit(session)
    if (_unknown(macro_set) or _unknown(start) or _unknown(stop, local=True)
            or not isinstance(stop, dict) or _reference(stop.get('name'))):
        raise ValueError('Movement controls must be literal except proven local stop lease references')
    info = session.project.debug_macro_info(macro_set, version=session.version['id'])
    first, last = [expand_macro(info['definition'], call['name'], call.get('args', {}),
        backend='qemu-dos', result_paths=RESULT_PATHS) for call in (start, stop)]
    down, up = first['script']['steps'], last['script']['steps']
    if (not 1 <= len(down) <= MAX_LEASES or len(down) + len(up) > MAX_PENDING_EDGES
            or any(step['op'] != 'keyboard.key-down' or 'as' not in step for step in down)
            or any(step['op'] != 'keyboard.key-up' for step in up)):
        raise ValueError('QEMU movement controls require held key-down and matching key-up only; timed press is unsupported')
    keys = [_key(step['key'])[0] for step in down]
    if len(set(keys)) != len(keys): raise ValueError('Movement start duplicates a held key')
    produced = {'$' + step['as'] + '.lease' for step in down}
    outputs = first['outputs']
    if (not outputs or any(not isinstance(value, str) or value not in produced for value in outputs.values())
            or set(outputs.values()) != produced or len(outputs) != len(produced)):
        raise ValueError('Movement start must return each acquired lease exactly once')
    expected = {'$start.outputs.' + name for name in outputs}
    actual = [step['lease'] for step in up]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('Movement stop must release exactly the leases returned by this start')
    return info, first, last


def _identity(session):
    return (session.vm, session.vm.process, session.project, session.run_id, session._runtime_epoch,
            deepcopy(session.version), session.metadata.get('source_sha256'), session.metadata.get('version_sha256'))


class QemuMovementMixin:
    def move(self, macro_set, *, start, stop, observations, until, progress, settle,
             guest_ms=10000, timeout_ms=10000, slice_ms=50, cleanup_guest_ms=250, max_polls=1000,
             context=None, scene=None, position=None, target=None, boundary_tolerance=1,
             spatial_map=None, map_conditions=None, room_field='room', target_tolerance=0):
        started = time.monotonic()
        options = dict(start=start, stop=stop, observations=observations, until=until, progress=progress,
            settle=settle, guest_ms=guest_ms, timeout_ms=timeout_ms, slice_ms=slice_ms,
            cleanup_guest_ms=cleanup_guest_ms, max_polls=max_polls, context=context, scene=scene,
            position=position, target=target, boundary_tolerance=boundary_tolerance,
            spatial_map=spatial_map, map_conditions=map_conditions, room_field=room_field,
            target_tolerance=target_tolerance)
        validate_parameters(macro_set, **options)
        info, _, _ = control_plans(self, macro_set, start, stop)
        owner, seed = self.vm, _identity(self)
        result = dict(format='fdisbull-movement-result-1', backend='qemu-dos', run=self.run_id,
            version=self.version['id'], macro_set=info['id'], macro_sha256=info['sha256'],
            **{name: deepcopy(options[name]) for name in ('start', 'stop', 'observations', 'until', 'progress', 'settle', 'context')},
            requested_guest_ms=guest_ms, reserved_cleanup_guest_ms=cleanup_guest_ms, max_polls=max_polls,
            guest_elapsed_ms=0, guest_elapsed_ns=0, cleanup_guest_elapsed_ms=0, cleanup_guest_elapsed_ns=0,
            polls=[], runs=[], ok=False, complete=False, outcome='incomplete',
            cleanup=dict(attempted=False, settled=False), diagnostic_frame=None,
            clock_domain='QEMU_CLOCK_VIRTUAL', clock_progress_complete=True, capture_epoch=self._runtime_epoch,
            claim='Observed bounded held-key route under caller-witnessed RAM predicates; no source/task lifetime, collision, deterministic replay or completed-frame claim.')
        touched = False
        terminal = False
        evidence_size = 0

        def close(primary=None):
            try:
                if self.vm is owner: self.close()
                else: owner.close()
            except BaseException as failure:
                result['cleanup']['close_error'] = type(failure).__name__
                if primary is not None: primary.movement_cleanup_error = type(failure).__name__
                try: owner.close()
                except BaseException as owner_failure:
                    result['cleanup']['owner_close_error'] = type(owner_failure).__name__

        remaining_admission = int(timeout_ms - (time.monotonic()-started)*1000)
        if remaining_admission <= 0: raise TimeoutError('Movement host deadline expired during admission')
        with _macro_scope(self, remaining_admission) as deadline:
            if _identity(self) != seed:
                raise ValueError('Movement owner changed during lock admission')
            def remaining():
                value = int((deadline - time.monotonic()) * 1000)
                if value <= 0: raise TimeoutError('Movement host-time budget expired')
                return min(value, 600000)

            def stable():
                remaining()
                if _identity(self) != seed or self.closed or owner.qmp is None:
                    raise ValueError('Movement owner, source or capture epoch changed')
                self._runtime_admit()

            def retain(value):
                nonlocal evidence_size
                evidence_size += len(json.dumps(value, allow_nan=False).encode())
                if evidence_size > _MAX_EVIDENCE: raise ValueError('Movement evidence exceeds 8 MiB')

            def keyboard():
                value = self.keyboard_state()
                if value.get('valid') is not True: raise ValueError('Movement input ownership is uncertain')
                return dict(pending_events=value['pending_edges'], owned_keys=len(value['leases']),
                    frame_keys=value.get('keyboard', {}).get('frame_keys', []), physical=value)

            def observe():
                stable()
                before = self.clock_observe()
                reads, values = ObservationReads(self), {}
                for name, spec in observations.items(): values[name] = reads.runtime_scalar(spec['runtime_memory'])
                after = self.clock_observe()
                stable()
                if before['epoch'] != after['epoch'] or before['virtual_ns'] != after['virtual_ns']:
                    raise ValueError('Movement clock changed across stopped observations')
                sample = dict(values=values, captures=list(reads.captures.values()), complete=True, errors={},
                    context=dict(run=self.run_id, version=self.version['id'], capture_epoch=self._runtime_epoch,
                                 clock=after), guest_elapsed_ms=result['guest_elapsed_ms'],
                    host_elapsed_ms=round((time.monotonic()-started)*1000, 3))
                retain(sample)
                if context is not None and not matches(context, values): raise ValueError('Movement context changed')
                return sample

            def arm(leases, pressed):
                stable()
                state = self._input_storage()
                records = state['pending']
                if (self._input_schedule_bound() or not records or len(records) != len(leases)
                        or {record['lease'] for record in records} != set(leases)
                        or any(record['event']['type'] != 'key' or
                               record['event']['data']['down'] is not pressed for record in records)):
                    raise ValueError('Movement input arm differs from its newly owned control edges')
                # A positive native delay avoids racing a host QMP send against
                # a fast virtual cutoff. The existing schedule owns one attempt.
                receipt = self.input_schedule(_INPUT_DELAY_NS)
                retain(receipt)
                return receipt

            def advance(milliseconds, cleanup=False):
                nonlocal terminal
                stable()
                before = self.clock_observe()
                try:
                    run = self._clock_advance_with_hooks(milliseconds * 1_000_000, timeout_ms=remaining())
                except BaseException:
                    result['clock_progress_complete'] = False
                    raise
                (result['cleanup'].setdefault('runs', []) if cleanup else result['runs']).append(run)
                retain(run)
                budget = run.get('clock_budget', {})
                measured = (budget.get('epoch') == before['epoch'] and budget.get('start_ns') == before['virtual_ns']
                    and type(budget.get('stopped_ns')) is int and budget['stopped_ns'] >= budget['start_ns'])
                if measured:
                    key = 'cleanup_guest_elapsed_ns' if cleanup else 'guest_elapsed_ns'
                    result[key] += budget['stopped_ns'] - budget['start_ns']
                    result[key.replace('_ns', '_ms')] = result[key] / 1_000_000
                else: result['clock_progress_complete'] = False
                # Preserve the first stop before any further guest observation.
                if run.get('hook_hits') or not clock_timer_stop_is_ordinary(run):
                    terminal = True
                    result.update(outcome='stopped', stop_result=run)
                    result['cleanup']['stop'] = run
                    return False
                if not measured or budget['stopped_ns'] <= budget['start_ns']:
                    raise ValueError('Movement native clock interval is incomplete or changed')
                delivery = run.get('input_delivery') or {}
                if (self._input_pending() or self._input_schedule_bound()
                        or delivery.get('delivery') == 'not_dispatched' or delivery.get('requires_resolution')):
                    terminal = True
                    result.update(outcome='input_interrupted', stop_result=run)
                    return False
                stable()
                return True

            try:
                stable()
                _admit(self)
                from .qemu_machine import _machine_operation_guard
                _machine_operation_guard(owner, 'move', (macro_set,), options)
                initial = observe()
                result['polls'].append(initial)
                result['initial_observation'] = result['last_observation'] = initial
                entry = keyboard()
                result['cleanup']['keyboard'] = entry
                if entry['pending_events'] or entry['owned_keys'] or entry['frame_keys'] or self._input_schedule_bound():
                    result['outcome'] = 'initial_input_not_clear'
                elif matches(until, initial['values']):
                    settled = matches(settle, initial['values'])
                    result.update(ok=settled, complete=settled, outcome='already_arrived' if settled else 'initial_motion_not_settled')
                    result['cleanup']['settled'] = settled
                elif not matches(settle, initial['values']):
                    result['outcome'] = 'initial_motion_not_settled'
                else:
                    touched = True
                    started_control = self.macro(macro_set, start['name'], args=start.get('args', {}), timeout_ms=remaining())
                    result['start_result'] = started_control
                    if not started_control['ok']: raise ValueError('Movement start macro failed')
                    leases = list(started_control['outputs'].values())
                    result['start_input_schedule'] = arm(leases, True)
                    last, unchanged = initial['values'], 0
                    while True:
                        remaining()
                        if len(result['polls']) >= max_polls:
                            result['outcome'] = 'poll_budget'; break
                        left = guest_ms * 1_000_000 - result['guest_elapsed_ns']
                        if left < 1_000_000:
                            result['outcome'] = 'guest_budget'; break
                        if not advance(min(slice_ms, left // 1_000_000)): break
                        if result['guest_elapsed_ns'] > guest_ms * 1_000_000:
                            result['outcome'] = 'guest_budget'; break
                        sample = observe()
                        result['polls'].append(sample)
                        result['last_observation'] = sample
                        values = sample['values']
                        if matches(until, values): result['outcome'] = 'arrived'; break
                        changed = any(values[field] != last[field] for field in progress['fields'])
                        unchanged = 0 if changed else unchanged + 1
                        if changed: result['last_changing_observation'] = sample
                        last = values
                        if unchanged >= progress['samples']:
                            result.update(outcome='blocked', classification='blocked_unknown'); break
                    result['cleanup']['attempted'] = True
                    if terminal:
                        result['cleanup']['reason'] = 'First native stop preserved; no cleanup guest execution or injected release'
                        close()
                    else:
                        stopped = self.macro(macro_set, stop['name'], args=_refs(stop.get('args', {}), started_control), timeout_ms=remaining())
                        result['cleanup']['macro'] = stopped
                        if not stopped['ok']: raise ValueError('Movement stop macro failed')
                        result['cleanup']['input_schedule'] = arm(leases, False)
                        while True:
                            sample, keys = observe(), keyboard()
                            result['cleanup'].update(last_observation=sample, keyboard=keys)
                            if (matches(settle, sample['values']) and not keys['pending_events']
                                    and not keys['owned_keys'] and not keys['frame_keys'] and not self._input_schedule_bound()):
                                result['cleanup']['settled'] = True
                                if result['outcome'] == 'arrived':
                                    retained = matches(until, sample['values'])
                                    result.update(ok=retained, complete=retained,
                                        outcome='arrived' if retained else 'destination_not_retained')
                                break
                            left = cleanup_guest_ms * 1_000_000 - result['cleanup_guest_elapsed_ns']
                            if left < 1_000_000 or not advance(min(slice_ms, left // 1_000_000), True): break
                            if result['cleanup_guest_elapsed_ns'] > cleanup_guest_ms * 1_000_000: break
                        if not result['cleanup']['settled']:
                            result['cleanup']['reason'] = 'Physical release and declared settled state were not qualified'
                            close()
            except BaseException as error:
                result.update(ok=False, complete=False, error=str(error), error_type=type(error).__name__)
                if getattr(error, 'result', None) is not None:
                    result['failure_result'] = error.result
                if result['outcome'] in ('incomplete', 'arrived', 'already_arrived'): result['outcome'] = 'observation_error'
                if touched:
                    result['cleanup'].update(attempted=True, reason='Uncertain composed movement; no further guest execution')
                    close(error)
                else:
                    channels = (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None))
                    if any(channel is not None and hasattr(channel, 'socket') and channel.socket is None for channel in channels): close(error)
                if isinstance(error, TimeoutError): result['outcome'] = 'timeout'
                if isinstance(error, TimeoutError) or not isinstance(error, Exception):
                    error.movement_result = result
                    if getattr(error, 'result', None) is None: error.result = result
                    raise
            try:
                remaining()
                result['host_elapsed_ms'] = round((time.monotonic()-started)*1000, 3)
                self._event('movement', result)
                remaining()
                artifact = self._artifact('movement-result.json', 'movement-result', json.dumps(result, indent=2).encode(),
                    dict(ok=result['ok'], outcome=result['outcome']))
                remaining()
                return dict(result, artifact=artifact['artifact'])
            except BaseException as error:
                if getattr(error, 'result', None) is None: error.result = result
                if touched: close(error)
                raise
