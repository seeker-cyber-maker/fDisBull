"""Bounded real-mode CALL fallthrough control, separate from native stepping.

The supported CALL is an unprefixed E8 rel16 in ordinary conventional RAM.
An owned fallthrough stop with the original CS, SS and SP is evidence of a
returned call, not proof that an arbitrary instruction retired. The actual
native breakpoint/hook/watchpoint/exit result is never renamed to "step".
"""
from copy import deepcopy
import re
import time
import uuid

from .dosbox_rpc import DebuggerError


FORMAT = 'fdisbull-machine-step-over-1'
MODEL = 'real16-direct-near-call-v1'
_OWNER = 'call-step-over'
_RAM_START, _RAM_END = 0x500, 0xa0000


class _AdmissionRefusal(ValueError):
    """A fully observed unsupported profile; no control has been installed."""


def validate_step_mode(mode, count):
    if type(mode) is not str or mode not in ('into', 'over'):
        raise ValueError('Machine step mode must be into or over')
    if mode == 'over' and (type(count) is not int or count != 1):
        raise ValueError('Machine step mode over requires count=1')


def require_no_step_over(vm, operation):
    if getattr(vm, '_active_step_over', None) is not None:
        raise ValueError('Resolve CALL step-over before ' + operation)


def step_over_vm(session):
    """Keep nested cleanup on the captured owner, even after a bad callback."""
    context = getattr(session, '_step_over_context', None)
    return context['vm'] if context is not None else session.vm


def guard_step_over_owner(session, *, check_deadline=True, allow_exited=False):
    context = getattr(session, '_step_over_context', None)
    if context is not None:
        _owner_current(session, context, check_deadline=check_deadline,
                       allow_exited=allow_exited,
                       allow_process_exit=allow_exited or context.get('guest_exit', False))


def step_over_stopped(session):
    """Observe/connect only the captured stopped owner during nested calls."""
    context = session._step_over_context
    _owner_current(session, context)
    status = context['qmp'].call('query-status')
    _owner_current(session, context)
    if not isinstance(status, dict) or type(status.get('running')) is not bool:
        raise DebuggerError('CALL step-over lacks an actual native running-state receipt')
    if status['running']:
        raise _AdmissionRefusal('Pause the original machine before CALL step-over')
    context['vm'].machine_stopped = True
    if context['remote'] is None:
        remote = context['vm'].debugger()
        # Only this explicitly captured owner may create the first channel.
        context['remote'] = remote
        if remote is None:
            raise DebuggerError('CALL step-over did not establish its native debugger')
        _owner_current(session, context)
    return context['remote']


def admit_step_over(session):
    """Passive conflicts also run before the operation lock or source guard."""
    from .qemu_steps import admit_step_sequence_input
    from .qemu_video_control import require_no_video_frame_fence
    vm = session.vm
    require_no_step_over(vm, 'another step-over')
    require_no_video_frame_fence(vm, 'CALL step-over')
    admit_step_sequence_input(session)
    if getattr(vm, '_active_frame_fence', None) is not None:
        raise ValueError('Resolve the renderer-frame fence before CALL step-over')
    if getattr(vm, '_active_clock_budget', None) is not None:
        raise ValueError('Resolve the clock budget before CALL step-over')
    sync = getattr(vm, '_clock_sync', None)
    if sync is not None and sync.get('state') != 'stopped':
        raise ValueError('Stop host clock synchronization before CALL step-over')
    if any(getattr(session, name, None) for name in ('_layer_active', '_layer_exec',
            '_layer_ram_applied', '_dos_task_binding', '_dos_task_monitor',
            '_dos_task_views', '_dos_scheduler', '_le_source')):
        raise ValueError('CALL step-over requires ordinary RAM without active layers or task/source views')
    project = getattr(session, 'project', None)
    if project is not None and project.db.in_transaction:
        raise ValueError('CALL step-over requires a project outside a caller-owned transaction')


def _remaining(vm):
    bound = getattr(vm, 'operation_deadline', None)
    amount = int((bound - time.monotonic()) * 1000) if bound is not None else 0
    if amount < 1:
        raise TimeoutError('CALL step-over host deadline expired')
    return amount


def _number(value, name):
    try:
        result = int(value, 0) if type(value) is str else value
    except ValueError:
        result = None
    if type(result) is not int or result < 0:
        raise _AdmissionRefusal('CALL step-over lacks observed ' + name)
    return result


def _span(address, length):
    if not _RAM_START <= address < address + length <= _RAM_END:
        raise _AdmissionRefusal('CALL step-over requires unwrapped ordinary conventional RAM')


def _read(session, context, address, length, *, ordinary=True):
    if ordinary:
        _span(address, length)
    elif not 0 <= address < address + length <= 0x100000:
        raise _AdmissionRefusal('DOS ownership read exceeds the unpaged first MiB')
    _owner_current(session, context)
    try:
        data = context['remote'].memory(address, length, space='physical')
    except ValueError as error:
        raise DebuggerError('CALL memory transport failed') from error
    _owner_current(session, context)
    if type(data) is not bytes or len(data) != length:
        raise DebuggerError('Incomplete stopped CALL memory observation')
    return data


def _registers(session, context):
    from .qemu_machine import _machine_registers
    step_over_stopped(session)
    result = _machine_registers(context['vm'], context['remote'], qmp=context['qmp'])
    _owner_current(session, context)
    return result


def _cpu(registers):
    state = registers.get('address_state', {})
    if (registers.get('cpu_mode') != 'real' or state.get('cpu_mode') != 'real'
            or state.get('code_bits') != 16 or state.get('stack_bits') != 16
            or state.get('paging') is not False
            or state.get('register_context_match') is not True
            or state.get('machine_vcpus') != 1):
        raise _AdmissionRefusal('CALL step-over requires one observed unpaged real-mode 16-bit code/stack context')
    values, segments = registers.get('registers', {}), state.get('segments', {})
    observed = {}
    for name in ('cs', 'ss'):
        descriptor = segments.get(name, {})
        selected = _number(values.get(name), name)
        selector = _number(descriptor.get('selector'), name + ' selector')
        base = _number(descriptor.get('base'), name + ' base')
        limit = _number(descriptor.get('limit'), name + ' limit')
        attributes = _number(descriptor.get('attributes'), name + ' attributes')
        if (selector != selected or selector > 0xffff or base != selector * 16
                or limit != 0xffff or attributes & 0x600000):
            raise _AdmissionRefusal('CALL step-over requires ordinary observed real-mode segment caches')
        observed[name] = dict(selector=selector, base=base, limit=limit, attributes=attributes)
    ip = _number(registers.get('instruction_pointer'), 'IP')
    linear = _number(registers.get('linear_pc'), 'linear PC')
    sp = next((values[name] for name in ('rsp', 'esp', 'sp') if name in values), None)
    sp = _number(sp, 'SP')
    if ip > 0xffff or linear != observed['cs']['base'] + ip or not 2 <= sp <= 0xfffe:
        raise _AdmissionRefusal('CALL step-over has an unsupported code or stack offset')
    _span(linear, 1)
    _span(observed['ss']['base'] + sp - 2, 2)
    return dict(**observed, ip=ip, linear=linear, sp=sp,
                a20=state.get('a20'), control=deepcopy(state.get('control')))


class _SourceOwner:
    """Reuse DOS allocation validation with an explicitly captured RAM reader."""
    def __init__(self, session, context):
        self._session, self._context, self.vm = session, context, context['vm']

    def __getattr__(self, name):
        return getattr(self._session, name)

    def _read(self, address, length):
        return _read(self._session, self._context, address, length, ordinary=False)


def _source(session, context):
    _owner_current(session, context)
    process = getattr(session, '_process', None)
    if process is None:
        return None
    from .qemu_dos_trace import _ownership
    try:
        _ownership(_SourceOwner(session, context), {'capture_epoch': context['owner']['runtime_epoch']})
    except ValueError as error:
        raise _AdmissionRefusal(str(error)) from error
    _owner_current(session, context)
    if getattr(session, '_process', None) is not process:
        raise DebuggerError('DOS process owner changed during CALL source observation')
    if not isinstance(process, dict) or process.get('state') != 'active':
        raise _AdmissionRefusal('CALL step-over requires the active DOS process source epoch')
    return dict(capture_epoch=process['capture_epoch'], psp_segment=process['psp_segment'],
                parent_psp_segment=process['parent_psp_segment'],
                allocation=deepcopy(process['allocation']),
                source_mapping=deepcopy(process['source_mapping']),
                version=deepcopy(getattr(session, 'version', None)))


def _source_sites(source, cpu, sites):
    if source is None:
        return
    allocation = source['allocation']
    stack = cpu['ss']['base'] + cpu['sp'] - 2
    if not allocation['start'] <= stack < stack + 2 <= allocation['end']:
        raise _AdmissionRefusal('CALL return slot is outside the current DOS allocation')
    ranges = source['source_mapping'].get('live_ranges', [])
    for address, length in sites:
        if not any(row['runtime_address'] <= address
                   and address + length <= row['runtime_address'] + row['length'] for row in ranges):
            raise _AdmissionRefusal('CALL code is outside the current DOS source mapping')


def _instruction(session, context, cpu, address, ip):
    from iced_x86 import Decoder
    count = min(15, 0x10000 - ip, _RAM_END - address)
    if count < 1:
        raise _AdmissionRefusal('CALL instruction crosses the supported code boundary')
    raw = _read(session, context, address, count)
    instruction = Decoder(16, raw, ip=ip).decode()
    if instruction.is_invalid:
        raise _AdmissionRefusal('Stopped bytes do not decode to one complete instruction')
    return instruction, raw[:instruction.len]


def _entry(session, context):
    from iced_x86 import FlowControl, Mnemonic, OpKind
    registers = _registers(session, context)
    cpu, source = _cpu(registers), _source(session, context)
    instruction, code = _instruction(session, context, cpu, cpu['linear'], cpu['ip'])
    if instruction.has_rep_prefix or instruction.has_repne_prefix or instruction.mnemonic == Mnemonic.HLT:
        raise _AdmissionRefusal('REP and HLT are unsupported by step mode over; use explicit native stepping')
    call = instruction.flow_control == FlowControl.CALL
    result = dict(kind='call' if call else 'native-step', cpu=cpu, source=source,
                  instruction=dict(address=cpu['linear'], ip=cpu['ip'], bytes=code.hex(),
                                   size=len(code)), fallthrough=None, callee=None)
    if not call:
        if instruction.flow_control != FlowControl.NEXT:
            raise _AdmissionRefusal('Unsupported control-transfer instruction in step mode over')
        _source_sites(source, cpu, [(cpu['linear'], len(code))])
        return result
    if len(code) != 3 or code[0] != 0xe8 or instruction.op0_kind != OpKind.NEAR_BRANCH16:
        raise _AdmissionRefusal('CALL step-over supports only unprefixed direct E8 rel16 calls')
    fallthrough = cpu['ip'] + 3
    target = fallthrough + int.from_bytes(code[1:], 'little', signed=True)
    if not 0 <= target <= 0xffff or fallthrough > 0xffff or cpu['ip'] <= target <= fallthrough:
        raise _AdmissionRefusal('CALL target or fallthrough has an ambiguous or wrapping return identity')
    address, target_address = cpu['cs']['base'] + fallthrough, cpu['cs']['base'] + target
    _, following = _instruction(session, context, cpu, address, fallthrough)
    _, callee = _instruction(session, context, cpu, target_address, target)
    slot = cpu['ss']['base'] + cpu['sp'] - 2
    result.update(fallthrough=dict(address=address, ip=fallthrough, bytes=following.hex()),
                  callee=dict(address=target_address, ip=target, bytes=callee.hex()),
                  return_slot=dict(address=slot, before_hex=_read(session, context, slot, 2).hex(),
                                   expected_hex=fallthrough.to_bytes(2, 'little').hex()))
    _source_sites(source, cpu, [(cpu['linear'], len(code)), (address, len(following)),
                               (target_address, len(callee))])
    return result


def _owner_current(session, context, *, allow_process_exit=False,
                   allow_exited=False, check_deadline=True):
    vm, owner = context['vm'], context['owner']
    allow_process_exit = allow_process_exit or context.get('guest_exit', False)
    channels_match = (getattr(vm, 'qmp', None) is context['qmp']
                      and getattr(vm, 'gdb', None) is context['remote'])
    if allow_exited:
        channels_match = ((getattr(vm, 'qmp', None) is None or getattr(vm, 'qmp', None) is context['qmp'])
                          and (getattr(vm, 'gdb', None) is None or getattr(vm, 'gdb', None) is context['remote']))
    if (session.vm is not vm or getattr(vm, 'process', None) is not context['process']
            or not channels_match
            or not allow_exited and context['process'].poll() is not None
            or session.run_id != owner['run']
            or not allow_process_exit and getattr(session, '_runtime_epoch', None) != owner['runtime_epoch']
            or getattr(vm, '_active_step_over', None) != owner
            or getattr(session, '_step_over_context', None) is not context):
        raise DebuggerError('CALL step-over original owner or source epoch changed')
    if check_deadline:
        _remaining(vm)


def _native_stop(result, kind, identifiers):
    if (not isinstance(result, dict) or result.get('outcome') != kind
            or result.get('timed_out') is not False or result.get('hook_hits') or result.get('automatic_breakpoints')
            or result.get('layer_conflict') or result.get('save_boundary_conflict')
            or any(key in result for key in ('native_machine_stop', 'guest_exit', 'guest_tsr'))):
        return False
    state = result.get('session', {})
    stop = state.get('stop_reason', {})
    native = stop.get('native_reply', '')
    return (state.get('state') == 'stopped' and stop.get('kind') == kind
            and stop.get('classification_complete', True) is True
            and stop.get('breakpoint_ids') == identifiers
            and result.get('breakpoints') == identifiers
            and isinstance(result.get('registers'), dict)
            and isinstance(native, str) and re.fullmatch(r'S05|T05(?:;.*|thread:.*)?', native) is not None
            and not re.search(r'(?:^|;)(?:watch|rwatch|awatch):', native))


def _live_result(result):
    if (not isinstance(result, dict) or type(result.get('outcome')) is not str
            or type(result.get('timed_out')) is not bool
            or not isinstance(result.get('session'), dict)):
        raise DebuggerError('CALL execution did not retain a complete native stop receipt')
    session = result['session']
    stop = session.get('stop_reason', {})
    guest = result['outcome'] in ('guest_exit', 'guest_tsr')
    if guest:
        process = result.get('process', {})
        native_stop = result.get('native_machine_stop', {})
        if (not isinstance(process, dict) or process.get('state') !=
                ('exited' if result['outcome']=='guest_exit' else 'resident')
                or not isinstance(process.get('termination'), dict)
                or not isinstance(stop, dict) or stop.get('kind') != result['outcome']
                or not isinstance(native_stop, dict)):
            raise DebuggerError('CALL execution lacks authoritative DOS return evidence')
        stop = native_stop
    native = stop.get('native_reply') if isinstance(stop, dict) else None
    if (session.get('state') != 'stopped' or type(native) is not str
            or re.match(r'^[TS][0-9a-fA-F]{2}', native) is None
            or stop.get('classification_complete', True) is not True
            or not isinstance(result.get('registers'), dict)):
        raise DebuggerError('CALL execution did not establish an actual stopped native owner')
    return guest


def observe_step_over_guest_return(session, result):
    """Adopt only the DOS helper's already-validated terminal process report."""
    context = getattr(session, '_step_over_context', None)
    if context is not None:
        _owner_current(session, context, allow_process_exit=True)
        if not _live_result(result):
            raise DebuggerError('CALL source retirement lacks an authoritative DOS return')
        context['guest_exit'] = True


def _return_identity(session, context, result):
    before = context['entry']
    current = _registers(session, context)
    if current != result['registers']:
        return None, 'stopped register receipt changed'
    cpu = _cpu(current)
    expected = dict(before['cpu'], ip=before['fallthrough']['ip'],
                    linear=before['fallthrough']['address'])
    if cpu != expected:
        return cpu, 'CALL returned with a different code, stack or address context'
    if _source(session, context) != before['source']:
        return cpu, 'CALL returned with a different source/allocation identity'
    for item in (before['instruction'], before['fallthrough']):
        if _read(session, context, item['address'], len(bytes.fromhex(item['bytes']))).hex() != item['bytes']:
            return cpu, 'CALL or fallthrough instruction bytes changed'
    slot = before['return_slot']
    if _read(session, context, slot['address'], 2).hex() != slot['expected_hex']:
        return cpu, 'CALL return stack slot does not retain the expected fallthrough'
    return cpu, None


def _cleanup(session, context):
    control = context.get('control')
    if control is None:
        return None
    _owner_current(session, context, allow_process_exit=context.get('guest_exit', False))
    identifier, record = control['breakpoint_id'], context['control_record']
    if session.breakpoints.get(identifier) != record:
        raise DebuggerError('CALL fallthrough control changed before cleanup')
    aliases = {key: deepcopy(row) for key, row in session.breakpoints.items()
               if key != identifier and (row['kind'], row['address'], row['length']) ==
               (record['kind'], record['address'], record['length'])}
    session.delete_breakpoint(identifier)
    _owner_current(session, context, allow_process_exit=context.get('guest_exit', False))
    if identifier in session.breakpoints or any(session.breakpoints.get(key) != row for key, row in aliases.items()):
        raise DebuggerError('CALL cleanup did not preserve existing breakpoint aliases')
    return dict(control, released=True, disposition='alias-preserved' if aliases else 'native-removed')


def execute_step_over(session, *, timeout_ms=10000):
    """Caller installs one inherited lock/deadline before any native access."""
    admit_step_over(session)
    vm = session.vm
    process = getattr(vm, 'process', None)
    if process is None or not callable(getattr(process, 'poll', None)) or process.poll() is not None:
        raise ValueError('CALL step-over requires its live original native process owner')
    owner = dict(token=uuid.uuid4().hex, run=session.run_id,
                 runtime_epoch=getattr(session, '_runtime_epoch', None),
                 native_pid=getattr(process, 'pid', None))
    context = dict(vm=vm, process=process, owner=owner, entry=None,
                   qmp=getattr(vm, 'qmp', None), remote=getattr(vm, 'gdb', None))
    entry, result, released, returned, reason = None, None, None, None, None
    stage, owner_exited, healthy_refusal = 'admission', False, False

    def envelope(completed=False):
        return dict(format=FORMAT, model=MODEL, mode='over', count=1,
            outcome=result.get('outcome') if isinstance(result, dict) else 'error',
            timed_out=result.get('timed_out') if isinstance(result, dict) else None,
            step_over_completed=completed, kind=entry['kind'] if entry else None, owner=deepcopy(owner),
            owner_exited=owner_exited, native_result=deepcopy(result),
            before=deepcopy(entry), after=deepcopy(returned),
            control=deepcopy(released or context.get('control')), reason=reason,
            instruction_completed=None,
            completion='verified CALL fallthrough and original stack' if completed and entry['kind']=='call'
                       else 'observed native step stop' if completed else 'interrupted or unverified')

    try:
        session._step_over_context = context
        vm._active_step_over = deepcopy(owner)
        try:
            entry = _entry(session, context)
            if entry['kind'] == 'call' and len(session.breakpoints) >= 256:
                raise _AdmissionRefusal('CALL fallthrough control exceeds the machine breakpoint budget')
        except _AdmissionRefusal as error:
            _owner_current(session, context)
            healthy_refusal = True
            raise ValueError(str(error)) from error
        context['entry'] = entry
        stage = 'intent'
        if session.project:
            session._event('machine-step-over-intent', dict(owner=owner, before=entry))
        _owner_current(session, context)
        if _entry(session, context) != entry:
            raise DebuggerError('Stopped CALL instruction or source identity changed before arm')
        stage = 'arm'
        if entry['kind'] == 'call':
            point = session._create_machine_breakpoint(entry['fallthrough']['address'], access='x', length=1,
                owner=_OWNER + ':' + owner['token'], identifier='machine-call-over-' + owner['token'])
            identifier = point['breakpoint_id']
            context['control_record'] = deepcopy(session.breakpoints[identifier])
            context['control'] = dict(breakpoint_id=identifier, address=point['address'],
                                      owner=_OWNER, token=owner['token'], released=False)
        _owner_current(session, context)
        stage = 'execute'
        if entry['kind'] == 'call' and getattr(session, '_qemu_hooks', None):
            result = session._run_with_hooks(timeout_ms=_remaining(vm), stop_on_hook=True)
        else:
            result = session._execute('c' if entry['kind'] == 'call' else 's', _remaining(vm))
        stage = 'observe'
        guest = isinstance(result, dict) and result.get('outcome') in ('exited', 'guest_exit', 'guest_tsr')
        _owner_current(session, context, allow_process_exit=guest, allow_exited=guest,
                       check_deadline=False)
        from .qemu_video_control import _known_owner_exit
        owner_exited = _known_owner_exit(vm, result)
        if owner_exited:
            reason = 'original native owner exited; no post-exit state observation'
            if context.get('control') is not None:
                released = dict(context['control'], released=True, disposition='owner-reaped')
                identifier = context['control']['breakpoint_id']
                if session.vm is vm and session.breakpoints.get(identifier) == context['control_record']:
                    del session.breakpoints[identifier]
            output = envelope()
        else:
            context['guest_exit'] = _live_result(result)
            _owner_current(session, context, allow_process_exit=context['guest_exit'])
            completed = _native_stop(result, 'step', []) if entry['kind'] == 'native-step' else False
            if entry['kind'] == 'call' and _native_stop(result, 'breakpoint', [context['control']['breakpoint_id']]):
                try:
                    returned, reason = _return_identity(session, context, result)
                except _AdmissionRefusal as error:
                    reason = str(error)
                completed = reason is None
            if not completed and reason is None:
                reason = 'first native stop did not establish the owned CALL return' if entry['kind']=='call' else 'first native stop was not an ordinary step'
            stage = 'release'
            released = _cleanup(session, context)
            output = envelope(completed)
        stage = 'publish'
        _owner_current(session, context, allow_exited=owner_exited,
                       allow_process_exit=owner_exited or context.get('guest_exit', False))
        if session.project:
            session._event('machine-step-over', output)
        _owner_current(session, context, allow_exited=owner_exited,
                       allow_process_exit=owner_exited or context.get('guest_exit', False))
        return output
    except BaseException as error:
        if healthy_refusal:
            raise
        if result is None and isinstance(getattr(error, 'result', None), dict):
            result = deepcopy(error.result)
        reason = str(error)
        error.result = envelope()
        error.result['failure_stage'] = stage
        try:
            vm.close()
        except BaseException as cleanup:
            error.machine_cleanup_error = type(cleanup).__name__
        raise
    finally:
        if getattr(vm, '_active_step_over', None) == owner:
            vm._active_step_over = None
        if getattr(session, '_step_over_context', None) is context:
            session._step_over_context = None
