"""Observe original flat32 E8 calls and replay their bounded CPU/stack portal.

Captured arguments are observations, not an inferred ABI. Reentry is explicitly
same-runtime assistance: it restores an observed caller CPU/stack window, runs
the unchanged original near call, then restores the interrupted CPU/window while
retaining the callee's global/file effects. It is not whole-machine restoration,
an arbitrary-state safety proof, or fresh-owner scene initialization.
"""

import base64
from copy import deepcopy
import struct
import time
import uuid

from .z_dos import read_linear, write_linear_guarded, reach_flat32_boundary
from .z_dos import _delete_owned_temporary_breakpoint


REGISTERS = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP')


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be {low}..{high}')
    return value


def _number(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def _identity(ctx):
    # Provider labels such as ses-1 can be reused after a fresh guest. The token
    # belongs to this actual live session object, not a serialized ctx.state.
    token = getattr(ctx.d, '_fdisbull_native_contract_token', None)
    if token is None:
        token = uuid.uuid4().hex
        setattr(ctx.d, '_fdisbull_native_contract_token', token)
    return {'token': token, 'run_id': getattr(ctx.d, 'run_id', None),
            'session_id': getattr(ctx.d, 'session_id', None)}


def _read(session, address, size):
    _integer(address, 'memory address', 0, 0xFFFFFFFF)
    if address + size > 0x100000000:
        raise ValueError('memory window wraps the linear address space')
    data = base64.b64decode(read_linear(session, address, size)['data_base64'], validate=True)
    if len(data) != size:
        raise RuntimeError(f'short memory read at {address:#x}: {len(data)} of {size}')
    return data


def _write(session, address, expected, value):
    import hashlib
    return write_linear_guarded(session, address, hashlib.sha256(expected).hexdigest(), value)


def _qualified(regs, selector):
    return (regs.get('cpu_mode') == 'protected'
            and _number(regs['segments']['cs']) == selector
            and not _number(regs['flags']) & 0x20000)


def _at(regs, address, selector):
    return _qualified(regs, selector) and _number(regs['instruction_pointer']) == address


def _set_cpu(session, regs, pending=None):
    for name, value in regs['general'].items():
        session.call('state.set_register', {'register': name.upper(), 'value': _number(value)})
    session.call('state.set_register', {'register': 'FLAGS', 'value': _number(regs['flags'])})
    target = _number(regs['instruction_pointer'])
    current = _number(session.registers()['instruction_pointer'])
    if current == target:
        return
    if target <= 0xFFFF:
        session.call('state.set_register', {'register': 'EIP', 'value': target})
        return
    # Older native adapters bound the EIP setter to16bits even in flat32 mode.
    # One temporary JMP moves the paused CPU; restore its bytes before running
    # the observed call. This does not patch the original E8 or callee.
    if current > 0xFFFFFFFA or current < target < current + 5:
        raise ValueError('program-counter redirect window overlaps its destination or wraps')
    original = _read(session, current, 5)
    jump = b'\xe9' + struct.pack('<I', (target - current - 5) & 0xFFFFFFFF)
    redirect = {'source': current, 'target': target, 'original_hex': original.hex(),
                'jump_hex': jump.hex(), 'phase': 'prepared'}
    if pending is not None:
        pending['redirect'] = redirect
    _write(session, current, original, jump)
    redirect['phase'] = 'installed'
    reach_flat32_boundary(session, target, _number(regs['segments']['cs']))
    redirect['phase'] = 'arrived'
    _write(session, current, jump, original)
    redirect['phase'] = 'restored'


def _stack_window(regs, size):
    sp = _number(regs['general']['esp'])
    below = min(4096, size - 16)
    start = sp - below
    if start < 0 or start + size > 0x100000000:
        raise ValueError('stack capture window wraps the linear address space')
    return start, size


def _arguments(session, regs, selected, size):
    rows = []
    for name in selected:
        value = _number(regs['general'][name.lower()])
        row = {'register': name, 'value': value, 'pointer_hypothesis': None}
        if 0x1000 <= value <= 0x100000000 - size:
            try:
                raw = _read(session, value, size)
                sample = {'address': value, 'hex': raw.hex(), 'bytes': size,
                          'claim': 'Pointed bytes under a numeric linear-address hypothesis.'}
                end = raw.find(b'\0')
                if end >= 0 and all(32 <= b < 127 for b in raw[:end]):
                    sample.update(c_string=raw[:end].decode('ascii'), c_string_bytes=end + 1)
                row['pointer_hypothesis'] = sample
            except Exception as error:
                row['pointer_read_error'] = f'{type(error).__name__}: {error}'
        rows.append(row)
    return rows


def _decode(session, address):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    raw = _read(session, address, min(15, 0x100000000 - address))
    instruction = next(iter(Cs(CS_ARCH_X86, CS_MODE_32).disasm(raw, address, 1)), None)
    if instruction is None:
        raise ValueError(f'no x86-32 instruction at {address:#x}')
    return {'address': address, 'size': instruction.size, 'hex': instruction.bytes.hex(),
            'mnemonic': instruction.mnemonic, 'operands': instruction.op_str}


def _step(session, deadline):
    result = session.call('execution.step', {'mode': 'over'})
    if result.get('operation_id'):
        left = max(1, int((deadline - time.monotonic()) * 1000))
        result = session.call('execution.wait', {'operation_id': result['operation_id'], 'timeout_ms': left})
        if result.get('running'):
            # Pause only our still-running step; never resume an intervening stop.
            paused = session.call('execution.pause')
            session.call('execution.wait', {'operation_id': paused['operation_id'], 'timeout_ms': 1000})
            raise RuntimeError('continuation step deadline expired; owned step paused')
    reason = result.get('stop_reason') or {}
    if result.get('hook_hits') or reason.get('kind') not in (None, 'step'):
        raise RuntimeError('another debugger stop interrupted continuation observation')
    return result


def _trace(session, selector, count, deadline, *, expected=None, trace=None):
    trace = [] if trace is None else trace
    for index in range(count):
        if time.monotonic() >= deadline:
            raise RuntimeError('continuation host deadline expired')
        regs = session.registers()
        if not _qualified(regs, selector):
            raise RuntimeError('continuation left the qualified code context')
        instruction = _decode(session, _number(regs['instruction_pointer']))
        if expected is not None and instruction != expected[index]['instruction']:
            raise RuntimeError('continuation diverged from the observed instruction path')
        row = {'instruction': instruction, 'before_registers': deepcopy(regs)}
        trace.append(row)
        row['step_result'] = _step(session, deadline)
        row['after_registers'] = deepcopy(session.registers())
    return trace


def _trigger_has_stop(value):
    if isinstance(value, dict):
        if value.get('hook_hits') or (value.get('stop') or {}).get('trigger') not in (None, 'guest_time'):
            return True
        return any(_trigger_has_stop(v) for v in value.values())
    if isinstance(value, list):
        return any(_trigger_has_stop(v) for v in value)
    return False


def _reach_with_trigger(session, callsite, selector, trigger, guest_ms, deadline):
    used = 0
    regs = session.registers()
    status = session.call('session.status')
    reason = status.get('session', {}).get('stop_reason',
        status.get('stop_reason', status.get('last_stop', {})))
    if (status.get('state') != 'stopped' or status.get('hook_hits')
            or reason.get('kind') not in ('pause', 'step', 'entry', 'start')):
        raise RuntimeError('initial foreign debugger stop retained before capture trigger')
    while not _qualified(regs, selector):
        if used >= 1000 or time.monotonic() >= deadline:
            raise RuntimeError('qualified selector not reached before arming capture')
        step = 1 if (used // 10) % 8 == 7 else 10
        run = session.run(guest_ms=step, timeout_ms=max(1, int((deadline-time.monotonic())*1000)),
                          fast_forward=step != 1, stop_on_hook=True)
        if run.get('hook_hits') or run.get('stop', {}).get('trigger') != 'guest_time':
            raise RuntimeError('another debugger stop interrupted capture qualification')
        used += max(step, run.get('guest_elapsed_ms', step))
        regs = session.registers()
    if _at(regs, callsite, selector):
        raise ValueError('trigger supplied while already at callsite; omit trigger to observe this stop')
    created = session.call('breakpoints.create', {'kind': 'execution', 'once': True,
        'address': {'space': 'segmented', 'segment': f'0x{selector:04X}',
                    'offset': f'0x{callsite:08X}'}})
    owned = created['breakpoint_id']
    try:
        try:
            result = trigger()
        except Exception:
            if not _at(session.registers(), callsite, selector):
                raise
            return session.registers()
        regs = session.registers()
        if _at(regs, callsite, selector):
            return regs
        if _trigger_has_stop(result):
            raise RuntimeError('trigger retained another debugger stop')
        run = session.run(guest_ms=guest_ms, timeout_ms=max(1, int((deadline-time.monotonic())*1000)),
                          fast_forward=True, stop_on_hook=True)
        regs = session.registers()
        observed = run.get('session', {}).get('stop_reason', {}).get('breakpoint_id')
        if (run.get('hook_hits') or run.get('stop', {}).get('trigger') != 'breakpoint'
                or observed != owned or not _at(regs, callsite, selector)):
            raise RuntimeError('capture callsite not reached; current debugger stop retained')
        return regs
    finally:
        _delete_owned_temporary_breakpoint(session, owned)


def capture_native_call(ctx, name, callsite, code_selector, *, argument_registers=None,
                        argument_bytes=64, stack_bytes=4112, execute=True,
                        continuation_steps=0, guest_ms=5000, timeout_ms=10000,
                        trigger=None, replace=False):
    """Observe E8 call inputs/return; an optional trigger runs after the breakpoint is armed.

The trigger is a trusted local callable (normally one existing named action).
It may be interrupted at the capture breakpoint. Any other stop remains local
failure. Captures and partial phases stay in ctx.state; caller retains artifacts.
"""
    if not isinstance(name, str) or not name.strip() or len(name) > 128:
        raise ValueError('name must contain 1..128 characters')
    _integer(callsite, 'callsite', 0, 0xFFFFFFFA)
    _integer(code_selector, 'code_selector', 1, 65535)
    _integer(argument_bytes, 'argument_bytes', 1, 256)
    _integer(stack_bytes, 'stack_bytes', 32, 16384)
    _integer(continuation_steps, 'continuation_steps', 0, 32)
    _integer(guest_ms, 'guest_ms', 1, 3600000)
    _integer(timeout_ms, 'timeout_ms', 1, 600000)
    if type(execute) is not bool or type(replace) is not bool:
        raise ValueError('execute and replace must be boolean')
    if continuation_steps and not execute:
        raise ValueError('continuation observation requires execute=true')
    if trigger is not None and not callable(trigger):
        raise ValueError('trigger must be a trusted callable')
    selected = list(REGISTERS if argument_registers is None else argument_registers)
    if (not selected or len(selected) > 7 or any(not isinstance(n, str) or n.upper() not in REGISTERS for n in selected)
            or len({n.upper() for n in selected}) != len(selected)):
        raise ValueError('argument_registers must be unique general registers excluding ESP')
    selected = [n.upper() for n in selected]
    contracts = ctx.state.setdefault('native_call_contracts', {})
    if name in contracts and not replace:
        raise ValueError('capture already exists; use replace=true for another observation')
    if ctx.state.get('native_call_pending') or ctx.state.get('native_contract_pending'):
        raise ValueError('a previous native invocation needs recovery')
    deadline = time.monotonic() + timeout_ms / 1000
    contract = {'format': 'fdisbull-native-call-contract-1', 'name': name, 'status': 'capturing',
                'runtime': _identity(ctx), 'callsite': callsite, 'code_selector': code_selector,
                'phase': 'reaching_callsite', 'scope': 'One observed flat32 original near call; argument roles and arbitrary-state reentry are not inferred.'}
    ctx.state['native_capture_pending'] = contract
    try:
        regs = (_reach_with_trigger(ctx.d, callsite, code_selector, trigger, guest_ms, deadline)
                if trigger is not None else reach_flat32_boundary(ctx.d, callsite, code_selector,
                    guest_ms=guest_ms, timeout_ms=timeout_ms)['registers'])
        raw = _read(ctx.d, callsite, 5)
        if raw[0] != 0xE8:
            raise ValueError('capture supports an original x86-32 E8 rel32 near call only')
        entry = (callsite + 5 + struct.unpack('<i', raw[1:])[0]) & 0xFFFFFFFF
        stack_address, size = _stack_window(regs, stack_bytes)
        contract.update(phase='inputs_captured', call_hex=raw.hex(), entry=entry,
            return_address=callsite + 5, signature_hex=_read(ctx.d, entry, 16).hex(),
            entry_conditions={'cpu_mode': regs['cpu_mode'], 'code_selector': code_selector,
                'scope': 'Observed caller CPU immediately before the original E8 near call.',
                'vm_flag_clear': not bool(_number(regs['flags']) & 0x20000),
                'segments': deepcopy(regs['segments']), 'registers': deepcopy(regs),
                'stack': {'address': stack_address, 'bytes': size, 'hex': _read(ctx.d, stack_address, size).hex()}},
            arguments=_arguments(ctx.d, regs, selected, argument_bytes), continuation=[])
        contract['return_instruction'] = _decode(ctx.d, callsite + 5)
        if execute:
            contract['phase'] = 'executing_original_call'
            returned = reach_flat32_boundary(ctx.d, callsite + 5, code_selector,
                guest_ms=guest_ms, timeout_ms=max(1, int((deadline-time.monotonic())*1000)))['registers']
            contract.update(return_registers=deepcopy(returned),
                returned_stack_matches=_number(returned['general']['esp']) == _number(regs['general']['esp']),
                returned_segments_match=returned['segments'] == regs['segments'], phase='returned')
            contract['post_arguments'] = _arguments(ctx.d, regs, selected, argument_bytes)
            _trace(ctx.d, code_selector, continuation_steps, deadline, trace=contract['continuation'])
            contract['status'] = 'returned'
        else:
            contract['status'] = 'inputs_observed'
        contract['phase'] = 'complete'
        contracts[name] = contract
        ctx.state.pop('native_capture_pending', None)
        return contract
    except Exception as error:
        contract.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise


def invoke_captured_call(ctx, contract, *, args=None, string_args=None, reentry=True,
                         continuation_steps=0, guest_ms=5000, timeout_ms=10000,
                         qualification_guest_ms=1000):
    """Replay an observed CPU/stack portal in the same live runtime, without UI input.

Only a call that returned with matching ESP and segments can be replayed. The
caller opts into reentry and must choose a compatible game state. String overrides
are bounded by an observed ASCII C string's capacity and are restored afterward.
Continuation steps can replay only a captured instruction path; divergence stops.
"""
    if type(reentry) is not bool or not reentry:
        raise ValueError('reentry=true explicitly opts into the observed CPU/stack portal')
    if (not isinstance(contract, dict) or contract.get('format') != 'fdisbull-native-call-contract-1'
            or contract.get('status') != 'returned' or not contract.get('returned_stack_matches')
            or not contract.get('returned_segments_match')):
        raise ValueError('contract needs an observed near return with matching stack and segments')
    if contract.get('runtime') != _identity(ctx):
        raise ValueError('captured pointers/stack belong to a different live runtime; capture again')
    _integer(continuation_steps, 'continuation_steps', 0, min(32, len(contract.get('continuation', []))))
    _integer(guest_ms, 'guest_ms', 1, 3600000)
    _integer(timeout_ms, 'timeout_ms', 1, 600000)
    _integer(qualification_guest_ms, 'qualification_guest_ms', 0, 60000)
    if ctx.state.get('native_call_pending') or ctx.state.get('native_contract_pending'):
        raise ValueError('a previous native invocation needs recovery')
    values = {}
    if not isinstance(args or {}, dict):
        raise ValueError('args must map general-register names to integer values')
    for name, value in (args or {}).items():
        if not isinstance(name, str) or name.upper() not in REGISTERS or name.upper() in values:
            raise ValueError('args need unique general-register names excluding ESP')
        values[name.upper()] = _integer(value, 'argument value', 0, 0xFFFFFFFF)
    if not isinstance(string_args or {}, dict):
        raise ValueError('string_args must map captured registers to ASCII strings')
    current = deepcopy(ctx.d.registers())
    selector = contract['code_selector']
    deadline = time.monotonic() + timeout_ms / 1000
    used = 0
    if not _qualified(current, selector) and qualification_guest_ms:
        status = ctx.d.call('session.status')
        reason = status.get('session', {}).get('stop_reason',
            status.get('stop_reason', status.get('last_stop', {})))
        if (status.get('state') != 'stopped' or status.get('hook_hits')
                or reason.get('kind') not in ('pause', 'step', 'entry', 'start')):
            raise RuntimeError('current foreign debugger stop retained before replay qualification')
        while not _qualified(current, selector) and used < qualification_guest_ms:
            left = int((deadline - time.monotonic()) * 1000)
            if left <= 0:
                raise RuntimeError('native replay selector qualification deadline expired')
            budget = min(1 + used % 3, qualification_guest_ms - used)
            run = ctx.d.run(guest_ms=budget, timeout_ms=left, fast_forward=False, stop_on_hook=True)
            if run.get('hook_hits') or run.get('stop', {}).get('trigger') != 'guest_time':
                raise RuntimeError('another debugger stop interrupted replay qualification')
            used += max(budget, run.get('guest_elapsed_ms', budget))
            current = deepcopy(ctx.d.registers())
    if (not _qualified(current, selector)
            or current['segments'] != contract['entry_conditions']['segments']):
        raise ValueError('current stopped CPU must have the captured qualified segment context')
    if _read(ctx.d, contract['callsite'], 5).hex() != contract['call_hex']:
        raise ValueError('original call bytes differ from the capture')
    signature = bytes.fromhex(contract['signature_hex'])
    if _read(ctx.d, contract['entry'], len(signature)) != signature:
        raise ValueError('callee signature differs from the capture')
    stack = contract['entry_conditions']['stack']
    captured_stack = bytes.fromhex(stack['hex'])
    original_stack = _read(ctx.d, stack['address'], stack['bytes'])
    patches = []
    for name, value in (string_args or {}).items():
        if not isinstance(name, str) or name.upper() not in REGISTERS or name.upper() in values:
            raise ValueError('string_args conflict with args or use an unsupported register')
        name = name.upper()
        observed = next((a.get('pointer_hypothesis') for a in contract['arguments'] if a['register'] == name), None)
        if not observed or 'c_string_bytes' not in observed or not isinstance(value, str) or '\0' in value:
            raise ValueError('string override needs a captured NUL-terminated ASCII argument')
        try:
            encoded = value.encode('ascii') + b'\0'
        except UnicodeEncodeError as error:
            raise ValueError('string overrides must be ASCII') from error
        if len(encoded) > observed['c_string_bytes']:
            raise ValueError('string override exceeds the observed string capacity')
        address = observed['address']
        if any(address < p['address'] + len(p['replacement']) and p['address'] < address + len(encoded) for p in patches):
            raise ValueError('string argument overrides overlap')
        patches.append({'register': name, 'address': address,
            'original': _read(ctx.d, address, len(encoded)), 'replacement': encoded})
    pending = {'phase': 'prepared', 'name': contract['name'], 'current_registers': current,
               'stack_address': stack['address'], 'original_stack_hex': original_stack.hex(),
               'string_patches': [{**p, 'original': p['original'].hex(), 'replacement': p['replacement'].hex()} for p in patches]}
    ctx.state['native_contract_pending'] = pending
    _write(ctx.d, stack['address'], original_stack, captured_stack)
    pending['phase'] = 'captured_stack_installed'
    for patch in patches:
        # A selected input string can itself be a caller local. Install it
        # after the captured stack, then restore strings before the saved stack.
        _write(ctx.d, patch['address'], _read(ctx.d, patch['address'], len(patch['replacement'])), patch['replacement'])
    pending['phase'] = 'string_arguments_installed'
    caller = deepcopy(contract['entry_conditions']['registers'])
    caller['instruction_pointer'] = hex(contract['callsite'])
    caller['general'].update({name.lower(): hex(value) for name, value in values.items()})
    _set_cpu(ctx.d, caller, pending)
    pending['phase'] = 'captured_cpu_installed'
    returned = reach_flat32_boundary(ctx.d, contract['return_address'], selector,
        guest_ms=guest_ms, timeout_ms=max(1, int((deadline-time.monotonic())*1000)))['registers']
    pending.update(phase='callee_returned', returned_registers=deepcopy(returned))
    if (_number(returned['general']['esp']) != _number(caller['general']['esp'])
            or returned['segments'] != caller['segments']):
        raise RuntimeError('replayed call changed the captured stack or segment context')
    pending['continuation'] = []
    continuation = _trace(ctx.d, selector, continuation_steps, deadline,
                          expected=contract.get('continuation', []), trace=pending['continuation'])
    pending['phase'] = 'continuation_complete'
    for patch in patches:
        _write(ctx.d, patch['address'], _read(ctx.d, patch['address'], len(patch['replacement'])), patch['original'])
    _write(ctx.d, stack['address'], _read(ctx.d, stack['address'], stack['bytes']), original_stack)
    pending['phase'] = 'temporary_memory_restored'
    _set_cpu(ctx.d, current, pending)
    pending['phase'] = 'cpu_restored'
    ctx.state.pop('native_contract_pending')
    return {'name': contract['name'], 'ui_input': False,
            'code_patched': bool(pending.get('redirect')), 'temporary_code_restored': True,
            'original_call_unchanged': True,
            'qualification_guest_ms': used,
            'entry': contract['entry'], 'return_address': contract['return_address'],
            'returned_registers': returned, 'returned_eax': returned['general']['eax'],
            'cpu_restored': True, 'stack_window_restored': True, 'string_arguments_restored': True,
            'continuation': continuation,
            'scope': 'Same-runtime observed CPU/stack portal; callee global/file effects retained. Caller chooses compatible game state; no redraw or fresh scene is inferred.'}
