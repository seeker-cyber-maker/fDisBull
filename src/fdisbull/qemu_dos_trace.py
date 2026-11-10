"""Source-bound stopped observations for the native DOS process adapter.

A QEMU GDB step is an observed stop interval, not a retirement certificate.
Each instruction is compared with the original module after DOS relocation and
loader writes. The binding ends at its initial process epoch, allocation, mode
or byte boundary; this adapter never guesses an overlay or a scheduled task.
"""
from __future__ import annotations

from copy import deepcopy
import struct
import time

from .execution_trace import (ExecutionTraceError, MAX_BOUNDARY_BYTES,
                              MAX_TRACE_BYTES, _encoded, _needs_region,
                              validate_trace_until)
from .qemu_machine import machine_trace_operation


def _clock_preflight(session, predicate):
    """Refuse a foreign clock before a live predicate can execute anything."""
    from .execution_clock import clock_predicates
    from .qemu_clock import _configuration
    leaves = clock_predicates(predicate)
    if not leaves:
        return
    if _configuration(session.vm)['profile'] != 'virtual':
        raise ValueError('Live virtual-time-range requires the QEMU virtual clock profile')
    observed = session._clock_snapshot()
    identity = dict(run=session.run_id, epoch=observed['epoch'],
                    native_epoch=observed['virtual_clock']['native']['epoch'])
    if any(any(leaf[key] != value for key, value in identity.items()) for leaf in leaves):
        raise ValueError('Live virtual-time-range differs from the owned run or clock epoch')


def _clock_sample(session):
    observed = session._clock_snapshot()
    return dict(run=observed['run'], epoch=observed['epoch'],
                sequence=observed['sequence'], virtual_ns=observed['virtual_ns'],
                icount=observed['counter']['value'],
                native_epoch=observed['virtual_clock']['native']['epoch'])


def _clock_bracket(session, before, after):
    from .execution_clock import validate_clock
    from .qemu_clock import _invalid
    fields = ('sequence', 'virtual_ns', 'icount', 'native_epoch')
    if any(before[key] != after[key] for key in ('run', 'epoch')):
        _invalid(session.vm, 'Source clock epoch changed during the stopped observation')
    clock = dict(format='fdisbull-source-clock-1', domain='QEMU_CLOCK_VIRTUAL',
        **{key: before[key] for key in ('run', 'epoch', 'native_epoch', 'virtual_ns', 'icount')},
        before={key: before[key] for key in fields}, after={key: after[key] for key in fields})
    try:
        return validate_clock(clock, run=session.run_id)
    except ValueError as error:
        _invalid(session.vm, 'Source clock bracket is not stable: ' + str(error))


def _require_active(session, binding):
    process = session._process
    if (session.closed or session.vm.qmp is None
            or session.vm.process is None or session.vm.process.poll() is not None
            or process['state'] != 'active'
            or process.get('machine_closed') or not process['source_mapping'].get('live')
            or process['capture_epoch'] != binding['capture_epoch']
            or session._runtime_epoch != binding['capture_epoch']):
        raise ValueError('Source tracing requires the active initial DOS process epoch')


def _ownership(session, binding):
    from .qemu_dos_process import observe_mcbs
    _require_active(session, binding)
    process = session._process
    # Inspect the chain, not a possibly freed MCB header left in old RAM.
    blocks = observe_mcbs(session._read, session._ready['first_mcb_segment'])
    allocation = process['allocation']
    current = next((block for block in blocks
                    if block['mcb_segment'] == allocation['mcb_segment']), None)
    if current != allocation:
        raise ValueError('DOS allocation ownership changed during the source capture')
    psp = session._read(process['psp_segment'] * 16, 0x18)
    if (psp[:2] != b'\xcd\x20'
            or struct.unpack_from('<H', psp, 0x16)[0] != process['parent_psp_segment']):
        raise ValueError('DOS PSP or parent identity changed during the source capture')


def _observe(session, binding, sequence, *, clocked=False):
    from iced_x86 import Decoder
    from .qemu_trace_identity import qualify_instruction
    session._remaining()
    before = _clock_sample(session) if clocked else None
    _ownership(session, binding)
    registers = session.registers()
    state = registers['address_state']
    if (registers['cpu_mode'] != 'real' or state.get('code_bits') != 16
            or state.get('paging') is not False
            or state.get('register_context_match') is not True
            or state.get('machine_vcpus') != 1):
        raise ValueError('Source tracing requires one observed, unpaged real-mode DOS CPU')
    values = registers['registers']
    cs, ip = int(values['cs'], 16), int(registers['instruction_pointer'], 16)
    linear = int(registers['linear_pc'], 16)
    if (not 0 <= cs <= 0xffff or not 0 <= ip <= 0xffff
            or linear != cs * 16 + ip or not 0 <= linear < 0x100000):
        raise ValueError('Source trace PC is outside its unwrapped real-mode mapping')
    length = min(15, 0x10000 - ip, 0x100000 - linear)
    layer_view = session.code(linear, length=length, space='linear') if getattr(session, '_layer_exec', None) else None
    raw = bytes.fromhex(layer_view['hex']) if layer_view is not None else session._read(linear, length)
    instruction = Decoder(16, raw, ip=ip).decode()
    if instruction.is_invalid:
        raise ValueError('Stopped DOS bytes do not decode to a complete instruction')
    code = raw[:instruction.len]
    qualification = qualify_instruction(binding, linear, code, segment=cs, offset=ip)
    address = dict(space='segmented', segment=hex(cs), offset=hex(ip))
    identity = dict(source_version=session.version['id'], runtime_address=address,
                    project_address=qualification['project_address'],
                    context=qualification['context'])
    if qualification['source_instruction_sha256'] is not None:
        identity['source_instruction_sha256'] = qualification['source_instruction_sha256']
    # FLAGS and IP change between ordinary instructions. They belong in the
    # register snapshot, not in the address-space identity used by predicates.
    context = dict(cpu_mode='real', code_bits=16, paging_enabled=False,
                   a20=state.get('a20'), cs=deepcopy(state['segments']['cs']),
                   **{key.lower(): value for key, value in state['control'].items()})
    event = dict(sequence=sequence, address=hex(linear), segmented_address=address,
                 bytes=code.hex(), execution_bytes=code.hex(), registers=deepcopy(values),
                 cpu_mode='real', code_bits=16, address_context=context,
                 task_id=session._process['psp_segment'], mapping_id=binding['capture_epoch'],
                 project_address=qualification['project_address'], identity=identity,
                 source_qualification=qualification, active_layers=list(getattr(session, '_layer_active', ())),
                 observation=dict(registers_stage='before-instruction',
                                  instruction_completed=False, flags_materialized=True,
                                  evidence='stopped native snapshot; no retirement claim'))
    if event['active_layers']:
        event['layer_generation'] = session._layer_generation
    stopped = dict(registers=registers, address=address, source_qualification=qualification)
    if clocked:
        event['clock'] = _clock_bracket(session, before, _clock_sample(session))
        stopped['clock'] = deepcopy(event['clock'])
    session._remaining()
    if len(_encoded(event)) > MAX_BOUNDARY_BYTES:
        raise ValueError('Stopped boundary exceeds its 8 KiB observation budget')
    return event, stopped


def _document(session, metadata, events, policy, **fields):
    from .debug_semantics import contract
    semantics = contract('qemu-dos')
    semantics['trace_completion'] = 'stopped instruction boundaries; architectural retirement unqualified'
    epoch = metadata['process']['capture_epoch']
    return dict(run={'run': session.run_id}, version=session.version['id'],
                mapping=metadata, events=events, capture_epoch=epoch,
                native_process_capture=dict(format='fdisbull-qemu-dos-capture-1',
                    capture_epoch=epoch, step_policy=policy,
                    source_scope='initial verified DOS module'),
                observation_contract=semantics, **fields)


def _compiled(session, metadata, raw, policy, regions):
    from .execution_events import normalize_trace
    value = deepcopy(raw)
    value['sequence'] = 1
    document = _document(session, metadata, [value], policy,
                         requested_count=1, complete=False)
    event = normalize_trace(document, regions=regions)['events'][0]
    event.update(index=raw['sequence'] - 1, sequence=raw['sequence'],
                 contiguous=raw['sequence'] > 1)
    return event


def _at_breakpoint(session, event):
    return [identifier for identifier, point in session.breakpoints.items()
            if identifier != session._return_breakpoint and point['access'] == 'x'
            and point['address'] == int(event['address'], 16)]


def _collect(session, *, name, timeout_ms, max_steps, count=None, until=None,
             regions=None, label='trial'):
    from .execution_events import evaluate_predicate, validate_regions
    from .qemu_step_policy import observe_step_policy
    from .qemu_trace_identity import load_trace_binding
    from .qemu_clock import _configuration

    if session.project.db.in_transaction:
        raise ValueError('Source tracing requires a project outside a caller-owned transaction')
    if session._input_pending():
        raise ValueError('Queued physical input requires run() before stepping or tracing')
    session._remaining()
    clocked = _configuration(session.vm)['profile'] == 'virtual'
    _clock_preflight(session, until)
    started = time.monotonic()
    metadata = deepcopy(session.metadata)
    binding = load_trace_binding(session.project, session.version['id'], metadata)
    _require_active(session, binding)
    if regions is None:
        regions = validate_regions([dict(id=region.name, space='project',
            start=region.start, end=region.start + len(region.data))
            for region in session.project.regions(session.version['id']) if region.data])
    if until is not None and _needs_region(until) and not regions:
        raise ValueError('Region-change requires declared regions')

    result = dict(format='fdisbull-trace-until-1', matched=False, exact_stop=False,
                  complete=False, outcome='error', max_steps=max_steps, steps=0,
                  attempted_steps=0, timeout_ms=timeout_ms, current_stop=None,
                  matched_event=None, error=None,
                  budget_unit='observed QEMU debugger stop intervals; not retired instructions',
                  action=dict(requested=None, dispatch='not_requested'), label=label)
    events = []
    policy = None
    interrupted = None
    try:
        remote = session._stopped()
        policy = observe_step_policy(remote, timeout_ms=session._remaining())
        if (policy['status'] != 'observed' or policy['enabled'] is not True
                or policy['unknown_mask'] != 0):
            raise ValueError('Source tracing requires an observed, enabled QEMU step policy')
        header_bytes = len(_encoded(_document(session, metadata, [], policy)))
        if header_bytes + MAX_BOUNDARY_BYTES > MAX_TRACE_BYTES:
            raise ValueError('Source trace metadata exceeds its artifact budget')
        raw, result['current_stop'] = _observe(session, binding, 1, clocked=clocked)
        events.append(raw)
        event_bytes = len(_encoded(raw)) + 1
        current = _compiled(session, metadata, raw, policy, regions)
        initial, previous = current, None
        while True:
            session._remaining()
            points = _at_breakpoint(session, events[-1])
            if points:
                result.update(outcome='foreign_stop', foreign_stop=dict(
                    kind='armed_execution_breakpoint_boundary', breakpoint_ids=points))
                break
            qualified = events[-1]['source_qualification']['qualified']
            if until is not None:
                evaluation = evaluate_predicate(until, current, initial=initial, previous=previous)
                result['evaluation'] = evaluation
                if evaluation['matched'] is True:
                    result.update(matched=True, exact_stop=True, complete=True,
                                  outcome='predicate', matched_event=deepcopy(current))
                    break
            if not qualified:
                result['outcome'] = 'source_boundary'
                break
            if result['attempted_steps'] >= max_steps:
                result['outcome'] = 'step_budget'
                break
            if header_bytes + event_bytes + MAX_BOUNDARY_BYTES > MAX_TRACE_BYTES:
                result['outcome'] = 'artifact_budget'
                break
            result['attempted_steps'] += 1
            # The attempt can affect execution even if the reply or journal
            # fails. Never leave a false not-executed marker on that boundary.
            events[-1]['observation']['instruction_completed'] = None
            result['current_stop'] = None
            native = session.step(timeout_ms=session._remaining())
            result['current_stop'] = native
            if native['outcome'] != 'step':
                result.update(outcome=native['outcome'] if native['outcome'] in
                              ('guest_exit', 'guest_tsr', 'exited', 'timeout') else 'foreign_stop',
                              foreign_stop=deepcopy(native))
                break
            result['steps'] += 1
            following, result['current_stop'] = _observe(session, binding, len(events) + 1,
                                                         clocked=clocked)
            if count is not None and result['steps'] == count:
                # trace(count=N) retains its N attempts / N pre-step snapshots
                # interface; inspect its final endpoint without adding N+1.
                result['outcome'] = ('count' if following['source_qualification']['qualified']
                                     else 'source_boundary')
                result['complete'] = result['outcome'] == 'count'
                break
            previous = current
            current = _compiled(session, metadata, following, policy, regions)
            events.append(following)
            event_bytes += len(_encoded(following)) + 1
    except BaseException as error:
        # A step or DOS-return journal can fail after observing a real stop.
        # Keep that receipt, even when the later source/clock read is missing.
        if result['current_stop'] is None and isinstance(getattr(error, 'result', None), dict):
            result['current_stop'] = deepcopy(error.result)
        if not isinstance(error, Exception):
            interrupted = error
        result.update(outcome='cancelled' if interrupted is not None else
                      'timeout' if isinstance(error, TimeoutError) else 'error',
                      matched=False, exact_stop=False, complete=False,
                      error=dict(type=type(error).__name__, message=str(error)))
        # A normal native timeout interrupts and observes the stopped machine.
        # For an uncertain control channel, close ownership rather than retry
        # the operation or silently resume. GDB itself has a bounded recovery.
        gdb = session.vm.gdb
        qmp = session.vm.qmp
        if (qmp is not None and (not session.vm.machine_stopped
                or getattr(qmp, 'socket', True) is None
                or gdb is not None and gdb.socket is None)):
            session.vm.close()

    all_qualified = bool(events) and all(event['source_qualification']['qualified'] for event in events)
    closed_window = result['outcome'] in ('predicate', 'step_budget', 'count') and all_qualified
    result['host_elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
    result['source_window_closed'] = closed_window
    requested_count = count if count is not None else max_steps + 1
    window = dict(closed=closed_window, reason=result['outcome'],
                  scope='these observed stopped boundaries only; no retirement or input causation claim')
    document = _document(session, metadata, events, policy,
        requested_count=requested_count,
        complete=closed_window and len(events) == requested_count,
        context='dos-process', capture_kind='stopped-boundary-predicate' if until else 'stopped-boundary-count',
        regions=regions, label=label, window=window,
        collector={key: deepcopy(result[key]) for key in
                   ('max_steps', 'steps', 'attempted_steps', 'outcome', 'matched', 'exact_stop',
                    'current_stop', 'error', 'budget_unit', 'host_elapsed_ms')},
        action=deepcopy(result['action']))
    document['collector']['until'] = until
    try:
        session._remaining()
        data = _encoded(document)
        if len(data) > MAX_TRACE_BYTES:
            raise ValueError('Aggregate execution trace exceeds its 16 MiB artifact budget')
        artifact = session._artifact(name, 'trace', data, dict(
            event_count=len(events), complete=document['complete'], context='dos-process',
            window=window, label=label, capture_kind=document['capture_kind'], outcome=result['outcome']))
        result.update(trace_artifact=artifact['artifact'], trace=artifact, observation_count=len(events))
        session._remaining()
        session._event('trace-until' if until else 'dos-process-trace', result)
        session._remaining()
    except Exception as error:
        result['persistence_error'] = dict(type=type(error).__name__, message=str(error))
        if interrupted is not None:
            interrupted.result = result
            raise interrupted from error
        raise ExecutionTraceError(result, error) from error
    if interrupted is not None:
        interrupted.result = result
        raise interrupted
    return result


class QemuDOSSourceTraceMixin:
    """The process adapter's bounded trace API; raw machines remain separate."""

    @machine_trace_operation
    def _trace_clock_preflight(self, until, *, timeout_ms=10000):
        _clock_preflight(self, until)

    @machine_trace_operation
    def trace(self, name='machine-trace.json', *, count=128, timeout_ms=10000, bits=None):
        from .external_files import _file_name
        _file_name(name)
        if type(count) is not int or not 1 <= count <= 10000:
            raise ValueError('Machine trace count must be 1..10000')
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise ValueError('Machine trace timeout must be 1..600000 ms')
        if bits is not None and (type(bits) is not int or bits != 16):
            raise ValueError('Source-bound DOS traces require observed 16-bit real mode')
        return _collect(self, name=name, count=count, max_steps=count,
                        timeout_ms=timeout_ms)['trace']

    @machine_trace_operation
    def trace_until(self, until, *, regions=None, max_steps=1000, timeout_ms=10000,
                    name='trace-until.json', action=None, label='trial'):
        until, regions, action = validate_trace_until(until, regions=regions,
            max_steps=max_steps, timeout_ms=timeout_ms, name=name, action=action, label=label)
        if action is not None:
            raise ValueError('Native DOS trace-until queued input actions require clock/input causal-boundary support; queue physical edges and run to a boundary before tracing')
        return _collect(self, name=name, timeout_ms=timeout_ms, max_steps=max_steps,
                        until=until, regions=regions, label=label)
