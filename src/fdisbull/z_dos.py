"""Small native DOS helpers for retained investigation controllers.

The mouse recipe requires the built-in INT33 driver and a guest that returns to
real/v8086 mode. It is qualified on the original X-COM games, not every DOS
input driver. A queued click is input delivery, not proof of a scene transition.
"""

import base64
import struct
import time


def read_linear(session, address, length):
    if type(address) is not int or not 0 <= address <= 0xFFFFFFFF:
        raise ValueError("address must be a 32-bit linear address")
    if type(length) is not int or not 1 <= length <= 65536:
        raise ValueError("length must be 1..65536")
    if address + length > 0x100000000:
        raise ValueError("read wraps the linear address space")
    return session.call("memory.read", {
        "address": {"space": "linear", "offset": f"0x{address:08X}"},
        "length": length, "view": "ram",
    })


def write_linear_guarded(session, address, expected_sha256, data):
    if type(address) is not int or not 0 <= address <= 0xFFFFFFFF:
        raise ValueError("address must be a 32-bit linear address")
    if not isinstance(data, bytes) or not 1 <= len(data) <= 65536:
        raise ValueError("data must contain 1..65536 bytes")
    if address + len(data) > 0x100000000:
        raise ValueError("write wraps the linear address space")
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)):
        raise ValueError("expected_sha256 must identify the current bytes")
    return session.call("memory.write", {
        "address": {"space": "linear", "offset": f"0x{address:08X}"},
        "expected_sha256": expected_sha256,
        "data_base64": base64.b64encode(data).decode("ascii"),
    })


def _delete_owned_temporary_breakpoint(session, breakpoint_id):
    """Remove only this helper's temporary ID, allowing an already-consumed one.

    A once breakpoint can disappear before a failed rendezvous finishes its
    cleanup. Its absence must not mask the actual stop or register-read error.
    Other backend/transport failures remain errors; this never retries or
    removes any observed foreign breakpoint.
    """
    from .dosbox_rpc import DebuggerError
    try:
        return session.call('breakpoints.delete', {'breakpoint_id': breakpoint_id})
    except DebuggerError as error:
        if not str(error).endswith('(BREAKPOINT_NOT_FOUND)'):
            raise
        return {'breakpoint_id': breakpoint_id, 'already_absent': True}


def sample_execution_contexts(session, probes=12, guest_ms=1, timeout_ms=5000, *, linear_bytes=0):
    """Observe short normal-speed intervals without guessing a call-safe selector.

    Includes the initial stopped context, then at most ``probes`` advances. Any
    encountered breakpoint, hook or other non-budget stop is retained without
    another resume. An existing breakpoint/hook is also retained. Normal-speed
    sampling can reveal contexts hidden by repeated fast-forward stop phases.

    ``linear_bytes`` optionally reads 0..64 bytes at the numeric IP as an
    explicitly *unqualified* linear-address hypothesis. It never translates a
    selector or claims those bytes are the instruction stream. Probe-read errors
    are isolated. The host deadline is checked between RPCs and passed to every
    run; an in-flight transport RPC remains subject to its transport timeout.
    """
    for label, value, low, high in (
            ('probes', probes, 1, 64), ('guest_ms', guest_ms, 1, 100),
            ('timeout_ms', timeout_ms, 1, 60000), ('linear_bytes', linear_bytes, 0, 64)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{label} must be {low}..{high}')
    started = time.monotonic()
    deadline = started + timeout_ms / 1000
    result = {'format': 'fdisbull-execution-context-samples-1', 'status': 'sampled',
              'requested_probes': probes, 'completed_probes': 0,
              'guest_ms_per_probe': guest_ms, 'fast_forward': False,
              'observations': [], 'selector_candidates': [], 'errors': [],
              'scope': 'Observed contexts and selector hypotheses only; no flat mapping, application identity or safe native-call contract is established.'}

    def remaining_ms():
        return max(0, int((deadline-time.monotonic())*1000))

    def compact_stop(value):
        reason = value.get('session', {}).get('stop_reason',
            value.get('stop_reason', value.get('last_stop', {})))
        stop = {key: reason[key] for key in ('kind', 'breakpoint_id', 'address') if key in reason}
        stop['trigger'] = value.get('stop', {}).get('trigger', reason.get('kind'))
        stop['hook_count'] = len(value.get('hook_hits', []))
        return stop

    def observe(index, run=None):
        if remaining_ms() == 0:
            result['status'] = 'deadline'
            return False
        try:
            regs = session.registers()
        except Exception as error:
            result['errors'].append({'phase': 'registers', 'probe': index,
                                     'reason': type(error).__name__+': '+str(error)[:240]})
            result['status'] = 'error'
            return False
        sample = {'index': index, 'phase': 'initial' if index == 0 else 'after_normal_run',
                  'cpu_mode': regs.get('cpu_mode'), 'cs': regs.get('segments', {}).get('cs'),
                  'ip': regs.get('instruction_pointer'), 'flags': regs.get('flags'),
                  'esp': regs.get('general', {}).get('esp')}
        if run is not None:
            sample['stop'] = compact_stop(run)
            sample['requested_guest_ms'] = guest_ms
            sample['observed_guest_ms'] = run.get('guest_elapsed_ms')
        result['observations'].append(sample)
        if linear_bytes and remaining_ms() > 0:
            probe = {'mapping': 'unqualified numeric-IP-as-linear hypothesis; selector translation unknown',
                     'requested_bytes': linear_bytes}
            sample['linear_ip_probe'] = probe
            try:
                address = int(sample['ip'], 16)
                probe['address'] = hex(address)
                reply = read_linear(session, address, linear_bytes)
                raw = base64.b64decode(reply['data_base64'], validate=True)
                if len(raw) != linear_bytes:
                    raise ValueError('linear probe returned a short read')
                probe.update(status='observed_bytes', hex=raw.hex())
            except Exception as error:
                probe.update(status='unresolved', reason=type(error).__name__+': '+str(error)[:240])
        return True

    try:
        initial = session.call('session.status')
    except Exception as error:
        result['status'] = 'error'
        result['errors'].append({'phase': 'initial_status', 'reason': type(error).__name__+': '+str(error)[:240]})
        initial = None
    if initial is not None:
        initial_stop = compact_stop(initial)
        result['initial_stop'] = initial_stop
        if initial.get('state') != 'stopped':
            result['status'] = 'not_stopped'
            result['stop'] = {'state': initial.get('state'), **initial_stop}
        elif observe(0):
            if initial_stop['hook_count'] or initial_stop.get('kind') not in ('pause', 'step', 'entry', 'start'):
                result['status'] = 'stopped'
                result['stop'] = initial_stop
            else:
                for index in range(1, probes+1):
                    left = remaining_ms()
                    if left == 0:
                        result['status'] = 'deadline'
                        break
                    try:
                        run = session.run(guest_ms=guest_ms, timeout_ms=left,
                                          fast_forward=False, stop_on_hook=True)
                    except Exception as error:
                        result['status'] = 'error'
                        result['errors'].append({'phase': 'run', 'probe': index,
                                                 'reason': type(error).__name__+': '+str(error)[:240]})
                        break
                    result['completed_probes'] += 1
                    stop = compact_stop(run)
                    terminal = (stop['hook_count'] or stop['trigger'] != 'guest_time'
                                or stop.get('kind') not in (None, 'pause'))
                    observed = observe(index, run)
                    if terminal:
                        # A foreign stop takes precedence even if its readback
                        # reached the host deadline. No subsequent run occurs.
                        result['status'] = 'stopped'
                        result['stop'] = stop
                        break
                    if not observed:
                        break
    candidates = {}
    for observation in result['observations']:
        try:
            selector = int(observation['cs'], 16)
            flags = int(observation['flags'], 16)
            ip = int(observation['ip'], 16)
        except (TypeError, ValueError):
            continue
        if observation['cpu_mode'] != 'protected' or flags & 0x20000 or not 0 < selector <= 65535:
            continue
        candidate = candidates.setdefault(selector, {'selector': hex(selector), 'observation_indices': [],
                                                     'observed_ips': [], 'qualified': False,
                                                     'basis': 'Observed with protected mode and VM flag clear; role and descriptor base remain unknown.'})
        candidate['observation_indices'].append(observation['index'])
        if hex(ip) not in candidate['observed_ips']:
            candidate['observed_ips'].append(hex(ip))
    result['selector_candidates'] = list(candidates.values())
    result['elapsed_ms'] = round((time.monotonic()-started)*1000, 3)
    if result['elapsed_ms'] >= timeout_ms and result['status'] == 'sampled':
        result['status'] = 'deadline'
    return result


def reach_flat32_boundary(session, address, selector, *, guest_ms=5000,
                          qualification_guest_ms=1000, timeout_ms=10000):
    """Reach an identified boundary in a previously qualified flat32 selector.

    Native DOS execution breakpoints freeze the segmented address translation
    when created. Registering a protected-mode offset during real/v8086 service
    therefore targets the wrong address. First reacquire the actual selector in
    protected mode, then arm one owned breakpoint. This does not establish the
    target-specific stack/callee contract; its action must check that at the hit.
    """
    for label, value, low, high in (
            ('address', address, 0, 0xFFFFFFFF), ('selector', selector, 1, 65535),
            ('guest_ms', guest_ms, 1, 3600000),
            ('qualification_guest_ms', qualification_guest_ms, 1, 60000),
            ('timeout_ms', timeout_ms, 1, 600000)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{label} must be {low}..{high}')
    deadline = time.monotonic() + timeout_ms / 1000

    def remaining_ms():
        left = int((deadline - time.monotonic()) * 1000)
        if left <= 0:
            raise RuntimeError('flat32 boundary host deadline expired')
        return left

    def qualified(regs):
        return (regs.get('cpu_mode') == 'protected'
                and int(regs['segments']['cs'], 16) == selector
                and not int(regs['flags'], 16) & 0x20000)

    def location(regs):
        return {'cpu_mode': regs.get('cpu_mode'), 'cs': regs['segments']['cs'],
                'ip': regs['instruction_pointer']}

    regs = session.registers()
    initial = location(regs)
    used = 0
    probes = 0
    while not qualified(regs):
        if used >= qualification_guest_ms:
            raise RuntimeError(f'flat32 selector not reached: {location(regs)}')
        # Periodic fast-forward slices can repeatedly stop in the same DPMI
        # callback. Occasionally sample a shorter normal-speed interval instead.
        probes += 1
        normal_probe = probes % 8 == 0
        budget = min(1 if normal_probe else 10, qualification_guest_ms - used)
        run = session.run(guest_ms=budget, timeout_ms=remaining_ms(),
                          fast_forward=not normal_probe, stop_on_hook=True)
        if run.get('hook_hits') or run.get('stop', {}).get('trigger') != 'guest_time':
            raise RuntimeError('another debugger stop interrupted selector qualification')
        used += max(budget, run.get('guest_elapsed_ms', budget))
        regs = session.registers()
    if int(regs['instruction_pointer'], 16) == address:
        return {'registers': regs, 'initial': initial, 'qualification_guest_ms': used,
                'already_at_boundary': True, 'breakpoint_owned': False}
    remaining_ms()
    created = session.call('breakpoints.create', {
        'kind': 'execution', 'once': True,
        'address': {'space': 'segmented', 'segment': f'0x{selector:04X}',
                    'offset': f'0x{address:08X}'},
    })
    owned = created['breakpoint_id']
    hit = False
    try:
        run = session.run(guest_ms=guest_ms, timeout_ms=remaining_ms(),
                          fast_forward=True, stop_on_hook=True)
        regs = session.registers()
        observed = run.get('session', {}).get('stop_reason', {}).get('breakpoint_id')
        hit = (not run.get('hook_hits')
               and run.get('stop', {}).get('trigger') == 'breakpoint'
               and observed == owned and qualified(regs)
               and int(regs['instruction_pointer'], 16) == address)
        if not hit:
            raise RuntimeError(f'flat32 boundary not reached: {location(regs)}; '
                               f'stop={run.get("stop", {}).get("trigger")}; '
                               f'observed_breakpoint={observed}; owned_breakpoint={owned}')
        return {'registers': regs, 'initial': initial, 'qualification_guest_ms': used,
                'already_at_boundary': False, 'breakpoint_owned': True}
    finally:
        if not hit:
            _delete_owned_temporary_breakpoint(session, owned)


def _real_mode(session, limit):
    for index in range(limit):
        regs = session.registers()
        if regs.get("cpu_mode") in ("real", "v8086"):
            return index
        normal_probe = (index + 1) % 8 == 0
        result = session.run(guest_ms=1 if normal_probe else 10, timeout_ms=1000,
                             fast_forward=not normal_probe,
                             stop_on_hook=True)
        if result.get("hook_hits") or result.get("stop", {}).get("trigger") not in (
                "guest_time", "timeout"):
            raise RuntimeError("another debugger stop interrupted the mouse rendezvous")
    raise RuntimeError(f"no real/v8086 mouse rendezvous within {limit} slices")


def _settle(session, guest_ms, timeout_ms):
    result = session.run(guest_ms=guest_ms, timeout_ms=timeout_ms,
                         fast_forward=True, stop_on_hook=True)
    if result.get("hook_hits") or result.get("stop", {}).get("trigger") != "guest_time":
        reason = result.get('session', {}).get('stop_reason', {})
        raise RuntimeError("mouse delivery interrupted; target retained at debugger stop; "
                           f"trigger={result.get('stop', {}).get('trigger')}; "
                           f"breakpoint={reason.get('breakpoint_id')}; "
                           f"hooks={len(result.get('hook_hits', []))}")
    return result


def click_at_dos_mouse_poll(session, x, y, *, max_slices=96, hold_ms=200,
                            settle_guest_ms=4000):
    """Move, rendezvous with INT33, deliver one left click, then settle.

    Return a compact delivery receipt. The calling Z action observes its actual
    resulting scene. It may keep a working input recipe while discovering a
    direct semantic operation for the same verb.
    """
    for name, value, low, high in (("x", x, 0, 65535), ("y", y, 0, 65535),
                                  ("max_slices", max_slices, 1, 1000),
                                  ("hold_ms", hold_ms, 1, 1000),
                                  ("settle_guest_ms", settle_guest_ms, 2000, 10000)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} must be {low}..{high}")
    first = _real_mode(session, max_slices)
    session.call("input.mouse.move", {"x": x, "y": y})
    _settle(session, 250, 3000)
    second = _real_mode(session, max_slices)
    raw = base64.b64decode(read_linear(session, 0xCC, 4)["data_base64"], validate=True)
    offset, segment = struct.unpack("<HH", raw)
    if not offset or not segment:
        raise RuntimeError("INT33 vector is null")
    bp = session.call("breakpoints.create", {
        "kind": "execution", "once": True,
        "address": {"space": "segmented", "segment": f"0x{segment:04X}",
                    "offset": f"0x{offset:08X}"},
    })
    hit = False
    try:
        for index in range(max_slices):
            result = session.run(guest_ms=10, timeout_ms=1000,
                                 fast_forward=True, stop_on_hook=True)
            stop = result.get("stop", {})
            if result.get("hook_hits"):
                raise RuntimeError("another hook interrupted the INT33 wait")
            if stop.get("trigger") == "breakpoint":
                observed_id = result.get("session", {}).get("stop_reason", {}).get("breakpoint_id")
                if observed_id is not None and observed_id != bp.get("breakpoint_id"):
                    raise RuntimeError("another breakpoint interrupted the INT33 wait; "
                                       f"observed={observed_id}; owned={bp.get('breakpoint_id')}")
                regs = session.registers()
                actual = (int(regs["segments"]["cs"], 16),
                          int(regs["instruction_pointer"], 16))
                if actual != (segment, offset):
                    raise RuntimeError("another breakpoint interrupted the INT33 wait")
                hit = True
                break
            if stop.get("trigger") not in ("guest_time", "timeout"):
                raise RuntimeError(f"unexpected mouse wait stop: {stop.get('trigger')}")
        if not hit:
            raise RuntimeError(f"INT33 poll not reached within {max_slices} slices")
    finally:
        if not hit and bp.get("breakpoint_id"):
            _delete_owned_temporary_breakpoint(session, bp['breakpoint_id'])
    session.click(x, y, hold_ms=hold_ms)
    _settle(session, 2000, 30000)
    if settle_guest_ms > 2000:
        _settle(session, settle_guest_ms - 2000, 30000)
    return {"input_delivered": True, "button": "left", "x": x, "y": y,
            "hold_ms": hold_ms, "settle_guest_ms": settle_guest_ms,
            "rendezvous_slices": first + second, "poll_slices": index + 1,
            "int33": {"segment": segment, "offset": offset},
            "scene_effect": "observe in the calling action"}
