"""Bounded named input routes over existing QEMU DOS primitives.

Physical leases retain their native owner and queue semantics. Timed keyboard
operations only arm a plan; this adapter never invents a run, retries a stopped
plan, injects cleanup releases, or claims a completed guest frame.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import time

from .input_macros import expand_macro, _output
from .operation_budget import request_deadline
from .qemu_input import MAX_LEASES, MAX_PENDING_EDGES, _key


_INPUT_FIELDS = {'format', 'context', 'session_id', 'run', 'guest_consumed'}
_EDGE_FIELDS = _INPUT_FIELDS | {'lease', 'key', 'delivery', 'sequence', 'pending_edges', 'claim'}
_PLAN_FIELDS = _INPUT_FIELDS | {'token', 'state', 'clock_domain', 'edge_count',
                              'requires_resolution', 'device_queue_accepted'}
RESULT_PATHS = {
    'keyboard.key-down': _EDGE_FIELDS,
    'keyboard.key-up': _EDGE_FIELDS | {'release'},
    'keyboard.state': _INPUT_FIELDS | {'valid', 'invalid_reason', 'pending_edges'},
    'keyboard.press': _PLAN_FIELDS | {'press.dispatched_count', 'press.undispatched_count'},
    'keyboard.type': _PLAN_FIELDS | {'typing.dispatched_count', 'typing.undispatched_count'},
    'memory': {'context', 'address', 'space', 'hex', 'length'},
    'status': {'context', 'run', 'version', 'state'},
    'registers': {'context', 'architecture', 'cpu_mode', 'instruction_pointer', 'linear_pc'},
    'run': {'context', 'outcome', 'timed_out', 'session.state'},
    'wait': {'run', 'complete', 'matched', 'outcome', 'clock_domain',
             'guest_elapsed_ns', 'guest_elapsed_ms', 'requested_guest_ms', 'clock_progress_complete'},
    'assert': {'matched'},
}
_INPUT_MUTATIONS = {'keyboard.key-down', 'keyboard.key-up', 'keyboard.press', 'keyboard.type'}


@contextmanager
def _macro_scope(session, timeout_ms):
    """Hold the owner lock and one inherited deadline, including admission."""
    vm = session.vm
    channels = [(channel, getattr(channel, 'operation_deadline', None))
                for channel in (getattr(vm, 'qmp', None), getattr(vm, 'gdb', None))
                if channel is not None]
    previous_rpc = getattr(session, '_rpc_deadline', None)
    previous_session = getattr(session, '_deadline', None)
    previous_vm = getattr(vm, 'operation_deadline', None)
    limits = [request_deadline(session, timeout_ms), previous_session, previous_vm,
              *(bound for _, bound in channels)]
    deadline = min(bound for bound in limits if bound is not None)
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0 or not vm.lock.acquire(timeout=remaining):
        raise TimeoutError('QEMU macro could not acquire the machine before its deadline')
    try:
        if time.monotonic() >= deadline:
            raise TimeoutError('QEMU macro host deadline expired before admission')
        session._rpc_deadline = session._deadline = vm.operation_deadline = deadline
        for channel, _ in channels:
            channel.operation_deadline = deadline
        yield deadline
    finally:
        session._rpc_deadline, session._deadline = previous_rpc, previous_session
        vm.operation_deadline = previous_vm
        for channel, bound in channels:
            channel.operation_deadline = bound
        # A read-only primitive may initialize GDB during the composed route.
        for channel in (getattr(vm, 'qmp', None), getattr(vm, 'gdb', None)):
            if channel is not None and not any(channel is old for old, _ in channels):
                channel.operation_deadline = previous_vm
        vm.lock.release()


def _tokens(value):
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(set(), *(_tokens(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(set(), *(_tokens(child) for child in value))
    return set()


def _referenced(value):
    if isinstance(value, str): return value.startswith('$')
    if isinstance(value, dict): return any(_referenced(item) for item in value.values())
    if isinstance(value, (list, tuple)): return any(_referenced(item) for item in value)
    return False


def _literal_preflight(session, step):
    op = step['op']
    params = {key: value for key, value in step.items() if key not in ('op', 'as', 'expect')}
    if op not in ('assert', 'keyboard.key-up') and _referenced(params):
        raise ValueError('QEMU macro primitive parameters must be literal after typed argument expansion')
    if op == 'memory':
        address, length = params['address'], params.get('length', 16)
        if isinstance(address, str):
            address = int(address, 0)
        if (type(address) is not int or not 0 <= address < 2**64 or
                type(length) is not int or not 1 <= length <= 65536 or address + length > 2**64 or
                params.get('space', 'physical') not in ('physical', 'virtual')):
            raise ValueError('Invalid QEMU macro machine memory address, length or space')
    if op == 'screenshot':
        from .external_files import _file_name
        from .screenshot_grid import validate_step
        _file_name(params.get('name', 'machine.png'))
        if type(params.get('grid', False)) is not bool:
            raise ValueError('grid must be boolean')
        if params.get('grid', False): validate_step(params.get('grid_step', 8))
        if not session.capabilities.get('screenshot'):
            raise ValueError('QEMU macro screenshot requires native screendump support')


def _input_preflight(session, steps):
    """Check literal ownership and finite queue transitions without dispatch."""
    state = session._input_storage()
    if not state['valid']:
        raise ValueError('QEMU macro requires valid owned physical input')
    leases = deepcopy(state['leases'])
    pending = len(state['pending'])
    scheduled = session._input_schedule_bound()
    timed_plan = None
    for index, step in enumerate(steps):
        op = step['op']
        _literal_preflight(session, step)
        if op in _INPUT_MUTATIONS:
            if not session.capabilities.get('physical_input'):
                raise ValueError('QEMU macro requires the native physical input capability')
            if scheduled:
                raise ValueError('Resolve scheduled input before another macro input operation')
        if op == 'keyboard.key-down':
            key, _ = _key(step['key'])
            if any(lease['device'] == 'keyboard' and lease['key'] == key for lease in leases.values()):
                raise ValueError('Macro key already has an active lease')
            token = '$' + step['as'] + '.lease' if 'as' in step else '@macro-key-' + str(index)
            leases[token] = dict(device='keyboard', key=key, make='python_pending', release=None)
            pending += 1
        elif op == 'keyboard.key-up':
            lease = leases.get(step['lease'])
            if lease is None or lease['device'] != 'keyboard' or lease['release'] is not None:
                raise ValueError('Macro requires a current owned unused keyboard lease or an earlier key-down binding')
            lease['release'] = 'python_pending'
            pending += 1
        elif op in ('keyboard.press', 'keyboard.type'):
            if pending or leases:
                raise ValueError('Timed macro input requires an empty queue and no held leases')
            params = {key: value for key, value in step.items() if key not in ('op', 'as')}
            if op == 'keyboard.press':
                from .qemu_keyboard_press import validate_keyboard_press_parameters, _plan
                validate_keyboard_press_parameters(**params)
                timed_plan = _plan(params['key'], params.get('modifiers', ()),
                                   params.get('hold_ms', 40), params.get('gap_ms', 40))
            else:
                from .qemu_keyboard_type import validate_keyboard_type_parameters, _plan
                validate_keyboard_type_parameters(**params)
                timed_plan = _plan(params['text'], params.get('hold_ms', 40), params.get('gap_ms', 40))
            pending, scheduled = len(timed_plan['steps']), True
        elif op in ('run', 'wait'):
            if op == 'wait' and timed_plan is not None:
                from .qemu_clock import MAX_CLOCK_BUDGET_NS
                required = sum(edge['delay-ns'] for edge in timed_plan['steps']) + step.get('slice_ms', 50) * 1_000_000
                if required > MAX_CLOCK_BUDGET_NS or required >= step['guest_ms'] * 1_000_000:
                    raise ValueError('Macro timed input plus one wait poll exceeds the requested virtual budget')
            # This is prospective validation, not a delivery receipt. Actual
            # execution must stop if the boundary leaves unresolved input.
            leases = {token: lease for token, lease in leases.items() if lease['release'] is None}
            pending, scheduled, timed_plan = 0, False, None
        if pending > MAX_PENDING_EDGES or len(leases) > MAX_LEASES:
            raise ValueError('Macro input plan exceeds the native queue or lease capacity')


class QemuMacroSessionMixin:
    def _macro_plan(self, macro_set, name, args=None, allowed_authorities=('player-input',)):
        if self.closed or self.vm.qmp is None:
            raise ValueError('QEMU macro requires its live owned machine')
        self._input_no_transaction()
        info = self.project.debug_macro_info(macro_set, version=self.version['id'])
        plan = expand_macro(info['definition'], name, args, allowed_authorities=allowed_authorities,
                            backend='qemu-dos', result_paths=RESULT_PATHS)
        unsupported = {step['op'] for step in plan['script']['steps']} - set(self.script_operations)
        if unsupported:
            raise ValueError('Unsupported QEMU macro primitives: ' + ', '.join(sorted(unsupported)))
        from .debug_script import validate_script
        validate_script(plan['script'], session=self)
        _input_preflight(self, plan['script']['steps'])
        return info, plan

    def macro(self, macro_set, name, *, args=None, allowed_authorities=('player-input',), timeout_ms=10000):
        started = time.monotonic()
        with _macro_scope(self, timeout_ms) as deadline:
            # The complete route is admitted before artifacts, queue changes or
            # execution. Rejection leaves the caller's existing leases intact.
            info, plan = self._macro_plan(macro_set, name, args, allowed_authorities)
            owner = self.vm
            before = deepcopy(self._input_storage())
            input_before = dict(available=True, physical=self.input_state())
            bindings = {}
            def after_step(step, result):
                if self.vm is not owner:
                    raise ValueError('QEMU macro owner changed during execution')
                if time.monotonic() >= deadline:
                    raise TimeoutError('QEMU macro host deadline expired')
                if step['op'] in ('run', 'wait'):
                    delivery = result.get('input_delivery') or {}
                    if (self._input_pending() or self._input_schedule_bound()
                            or delivery.get('delivery') == 'not_dispatched'):
                        raise ValueError('Macro input stopped before complete dispatch; no suffix was replayed')
            report = None
            try:
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining <= 0:
                    raise TimeoutError('QEMU macro host deadline expired before execution')
                from .debug_script import execute_script
                report = execute_script(self, plan['script'], timeout_ms=remaining,
                                        _after_step=after_step, _bindings_out=bindings)
                outputs, error = {}, None
                if report['ok']:
                    try: outputs = _output(plan['outputs'], bindings)
                    except Exception as failure: error = str(failure)
                state = self._input_storage()
                retained = _tokens(outputs) & set(state['leases']) if report['ok'] and error is None else set()
                abandoned = set(state['leases']) - set(before['leases']) - retained
                schedule = state.get('schedule') or {}
                unresolved = (schedule.get('bound') and
                              schedule.get('token') != (before.get('schedule') or {}).get('token'))
                cleanup = [report['input_cleanup']] if report.get('input_cleanup') is not None else []
                if (abandoned or unresolved) and not self.closed:
                    self.close()
                    error = 'Macro left new input ownership or an unresolved timed plan; session closed without resuming guest'
                    cleanup.append(dict(closed=True, reason=error))
                input_after = (dict(available=False, reason='session_closed') if self.closed else
                               dict(available=True, physical=self.input_state()) if time.monotonic() < deadline else
                               dict(available=False, reason='host_time_budget_expired'))
                result = dict(format='fdisbull-macro-result-1', backend='qemu-dos',
                    macro_set=info['id'], macro_sha256=info['sha256'], name=name, args=args or {},
                    ok=report['ok'] and error is None, outputs=outputs,
                    expanded_steps=plan['script']['steps'], lineage=plan['lineage'], execution=report,
                    cleanup=cleanup, error=error, run=self.run_id, input_before=input_before, input_after=input_after,
                    host_elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                    claim='Expanded QEMU input primitives retain their native queue and dispatch receipts; '
                          'guest consumption, action completion and completed guest frames remain unproven.')
                self._event('macro', result)
                artifact = self._artifact('macro-result.json', 'macro-result', json.dumps(result, indent=2).encode(),
                                          dict(ok=result['ok'], macro_set=info['id'], backend='qemu-dos'))
                return dict(result, artifact=artifact['artifact'])
            except BaseException:
                # A publication failure must not strand input whose effects
                # already happened. Preflight and pre-dispatch failures above
                # do not destroy unrelated entry ownership.
                touched = (self._input_storage() != before or report is not None and
                           any(step['op'] in _INPUT_MUTATIONS for step in report['steps']))
                if touched and not self.closed:
                    self.close()
                raise
