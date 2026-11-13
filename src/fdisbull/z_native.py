"""Bounded original near calls for a retained Z controller's flat32 DOS guest.

The caller must qualify a non-reentrant boundary, flat code/data/stack selectors,
a normal near-return callee, and a 32-byte boundary window that the callee never
executes. This helper checks byte identity and restoration, not that contract.
Only the temporary code, general registers, flags and 4 KiB stack window are
restored. The callee's intended game/file effects remain. A failure preserves the
stop and recovery information; it never retries or resumes a foreign stop.
"""

import base64
import hashlib
import struct

from .z_dos import read_linear, write_linear_guarded, reach_flat32_boundary


_ARGUMENT_REGISTERS = frozenset(('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP'))


def _address(value, label):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f'{label} must be a 32-bit integer address')
    return value


def _read(session, address, size):
    data = base64.b64decode(read_linear(session, address, size)['data_base64'], validate=True)
    if len(data) != size:
        raise RuntimeError(f'short native memory read at {address:#x}: {len(data)} of {size}')
    return data


def _write(session, address, expected, value):
    return write_linear_guarded(session, address, hashlib.sha256(expected).hexdigest(), value)


def _set_register(session, name, value):
    return session.call('state.set_register', {'register': name.upper(), 'value': value})


def invoke_native(ctx, entry, boundary, code_selector, expected_hex, directory=None, args=None):
    """Call an identified flat32 near-return function without UI input.

``args`` maps general-register names (except ESP) to unsigned 32-bit values.
``directory`` is an optional ASCII C string of at most 15 bytes, placed in the
temporary window and passed in EAX. It is only appropriate for a recovered EAX
directory ABI. ``expected_hex`` identifies 8..256 current callee bytes.

An existing ``ctx.state['native_call_pending']`` must be investigated/recovered
before another call. On failure it records the original registers, code and
bounded stack bytes plus the last completed phase. It is not a whole-guest undo.
"""
    entry = _address(entry, 'entry')
    boundary = _address(boundary, 'boundary')
    if boundary > 0xFFFFFFDF:
        raise ValueError('boundary window wraps the linear address space')
    if type(code_selector) is not int or not 1 <= code_selector <= 0xFFFF:
        raise ValueError('code_selector must be 1..65535')
    if not isinstance(expected_hex, str):
        raise ValueError('expected_hex must contain 8..256 signature bytes')
    try:
        signature = bytes.fromhex(expected_hex)
    except ValueError as error:
        raise ValueError('expected_hex must contain hexadecimal signature bytes') from error
    if not 8 <= len(signature) <= 256 or entry + len(signature) > 0x100000000:
        raise ValueError('expected_hex must contain 8..256 non-wrapping signature bytes')
    if entry < boundary + 32 and boundary < entry + len(signature):
        raise ValueError('callee signature overlaps the temporary boundary window')
    if args is not None and not isinstance(args, dict):
        raise ValueError('args must map register names to unsigned 32-bit values')
    values = {}
    for name, value in (args or {}).items():
        if not isinstance(name, str) or name.upper() not in _ARGUMENT_REGISTERS:
            raise ValueError('args may set EAX, EBX, ECX, EDX, ESI, EDI or EBP only')
        if name.upper() in values:
            raise ValueError('argument register was supplied more than once')
        values[name.upper()] = _address(value, f'argument {name}')
    encoded = None
    if directory is not None:
        if not isinstance(directory, str) or '\0' in directory:
            raise ValueError('directory must be an ASCII string without NUL')
        try:
            encoded = directory.encode('ascii') + b'\0'
        except UnicodeEncodeError as error:
            raise ValueError('directory must be ASCII') from error
        if len(encoded) > 16:
            raise ValueError('directory argument must fit in 16 bytes including NUL')
        if 'EAX' in values:
            raise ValueError('directory and an explicit EAX argument conflict')
        values['EAX'] = boundary + 16
    if ctx.state.get('native_call_pending'):
        raise ValueError('previous native call needs recovery before another invocation')

    session = ctx.d
    regs = reach_flat32_boundary(session, boundary, code_selector)['registers']
    # reach_flat32_boundary verifies mode, VM flag, selector and exact CS:EIP.
    if _read(session, entry, len(signature)) != signature:
        raise ValueError('callee signature differs at the qualified boundary')
    original = _read(session, boundary, 32)
    sp = int(regs['general']['esp'], 16)
    if not 4096 <= sp <= 0xFFFFFFF0:
        raise ValueError('stack preservation window wraps the linear address space')
    stack_address, stack_size = sp - 4096, 4112
    if boundary < stack_address + stack_size and stack_address < boundary + 32:
        raise ValueError('temporary boundary window overlaps the preserved stack')
    stack = _read(session, stack_address, stack_size)
    stub = bytearray(original)
    # rel32 displacement is modulo 2**32 in flat32 mode, including wraparound.
    stub[:7] = b'\xe8' + struct.pack('<I', (entry - (boundary + 5)) & 0xFFFFFFFF) + b'\xeb\xf9'
    if encoded is not None:
        stub[16:16 + len(encoded)] = encoded
    stub = bytes(stub)
    pending = {'entry': entry, 'boundary': boundary, 'code_selector': code_selector,
               'registers': regs, 'original_hex': original.hex(), 'stub_hex': stub.hex(),
               'stack_address': stack_address, 'stack_hex': stack.hex(), 'phase': 'prepared'}
    ctx.state['native_call_pending'] = pending
    _write(session, boundary, original, stub)
    pending['phase'] = 'trampoline_installed'
    for name, value in values.items():
        _set_register(session, name, value)
    pending['phase'] = 'arguments_installed'
    returned = reach_flat32_boundary(session, boundary + 5, code_selector, guest_ms=5000)['registers']
    pending['phase'] = 'callee_returned'
    pending['returned_registers'] = returned
    if int(returned['general']['esp'], 16) != sp or returned['segments'] != regs['segments']:
        raise RuntimeError('callee returned with a changed stack or segment context')
    for name, value in regs['general'].items():
        _set_register(session, name, int(value, 16))
    _set_register(session, 'FLAGS', int(regs['flags'], 16))
    pending['phase'] = 'registers_restored'
    reach_flat32_boundary(session, boundary, code_selector, guest_ms=100)
    pending['phase'] = 'boundary_reacquired'
    _write(session, boundary, stub, original)
    pending['phase'] = 'code_restored'
    _write(session, stack_address, _read(session, stack_address, stack_size), stack)
    ctx.state.pop('native_call_pending')
    return {'entry': hex(entry), 'boundary': hex(boundary),
            'returned_eax': returned['general']['eax'], 'code_restored': True,
            'stack_restored': True, 'stack_window_bytes': stack_size,
            'registers_restored': True, 'ui_input': False,
            'callee_effects': 'retained; scene continuation is caller-defined'}
