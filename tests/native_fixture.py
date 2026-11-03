"""Prepare authored DOS fixtures for checkpoint tests; not a production API.

The video device advances for a bounded guest interval while authored code is
held on a temporary loop. The CPU, sampled fixture bytes, stack and keyboard
are checked on restoration. This does not claim whole-machine equivalence.
"""
import base64

from fdisbull.debug_state import REGISTERS, register_value


def _read(debug, segment, offset, length):
    address = {'space': 'segmented', 'segment': f'0x{segment:04X}', 'offset': f'0x{offset:08X}'}
    return debug.call('memory.read', {'address': address, 'length': length})


def _write(debug, observed, data):
    debug.call('memory.write', {'address': observed['address'], 'expected_sha256': observed['sha256'],
                                'data_base64': base64.b64encode(data).decode('ascii')})


def prepare_native_fixture(debug):
    """Settle pending video before testing a fresh authored program's first instruction."""
    before = debug.registers()
    assert before['cpu_mode'] == 'real'
    cs, ss = (int(before['segments'][name], 16) for name in ('cs', 'ss'))
    ip = int(before['instruction_pointer'], 16)
    sp = int(before['general']['esp'], 16) & 0xffff
    assert ip <= 0xfe00
    keyboard = debug.keyboard.state()['keyboard']
    assert keyboard['pending_events'] == keyboard['owned_keys'] == keyboard['queued_guest_ms'] == 0
    assert not keyboard['frame_keys']
    code = _read(debug, cs, ip, 2)
    fixture = _read(debug, cs, ip, 512)
    lo, hi = max(0, sp - 96), min(0x10000, sp + 32)
    stack = _read(debug, ss, lo, hi - lo)
    # Leave IRQ delivery enabled: deferring timer interrupts changes the first
    # observed instruction in rewind tests. Stop on the authored loop boundary
    # after settling, then restore the program before its first instruction.
    flags = register_value(before, 'flags')
    _write(debug, code, b'\xeb\xfe')
    assert debug.run(guest_ms=300, timeout_ms=10000, fast_forward=True)['outcome'] == 'guest_time'
    breakpoint = debug.call('breakpoints.create', {'kind': 'execution', 'address': code['address'], 'once': False})
    assert debug.run(timeout_ms=10000, fast_forward=True)['outcome'] == 'breakpoint'
    debug.delete_breakpoint(breakpoint['breakpoint_id'])
    current_stack = _read(debug, ss, lo, hi - lo)
    if current_stack['data_base64'] != stack['data_base64']:
        _write(debug, current_stack, base64.b64decode(stack['data_base64'], validate=True))
    current_code = _read(debug, cs, ip, 2)
    _write(debug, current_code, base64.b64decode(code['data_base64'], validate=True))
    # Restore all exposed architectural values, including the original FLAGS.
    for name in sorted(REGISTERS - {'flags'}):
        value = register_value(before, name)
        if register_value(debug.registers(), name) != value:
            debug.call('state.set_register', {'register': name.upper(), 'value': value})
    if register_value(debug.registers(), 'flags') != flags:
        debug.call('state.set_register', {'register': 'FLAGS', 'value': flags})
    after = debug.registers()
    assert all(register_value(after, name) == register_value(before, name) for name in REGISTERS)
    assert _read(debug, cs, ip, 512)['data_base64'] == fixture['data_base64']
    assert _read(debug, ss, lo, hi - lo)['data_base64'] == stack['data_base64']
    final_keyboard = debug.keyboard.state()['keyboard']
    assert all(final_keyboard[name] == keyboard[name] for name in
               ('pending_events', 'owned_keys', 'queued_guest_ms', 'frame_keys'))
