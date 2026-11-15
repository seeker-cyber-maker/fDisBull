"""Observe QEMU's debugger stepping controls without changing guest policy.

The GDB ``qqemu.sstepbits`` and ``qqemu.sstep`` queries describe whether
single-step masks interrupts or timers. A successful step stop is still not a
retirement certificate: faults and partial REP progress can also return T05.
See https://www.qemu.org/docs/master/system/gdb.html#changing-single-stepping-behaviour.
"""
from __future__ import annotations

import re
import time


FORMAT = 'fdisbull-qemu-step-policy-1'
MAX_REPLY = 256
_BIT = re.compile(r'([A-Z][A-Z0-9_]{0,31})=((?:0x)?[0-9a-fA-F]{1,8})')
_MASK = re.compile(r'0[xX]([0-9a-fA-F]{1,8})')
_KNOWN = frozenset(('ENABLE', 'NOIRQ', 'NOTIMER'))


def observe_step_policy(remote, *, timeout_ms=1000):
    """Return the observed mask, or an explicit unsupported/unknown result.

    Only read-only GDB queries are sent. Replies are bounded and independently
    validated; transport failures propagate to the owning machine's ordinary
    fail-closed guard. Both queries share this budget and are further bounded
    by any absolute operation deadline already carried by ``remote``.

    ``status == 'observed'`` establishes the meanings of the reported mask,
    not that stepping is enabled or that guest execution has natural timing.
    Callers requiring a specific policy must check ``enabled`` and the two
    mask booleans before executing. No restoration is needed: this helper
    never sends ``Qqemu.sstep=...``.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Step-policy timeout must be 1..600000 ms')
    deadline = time.monotonic() + timeout_ms / 1000
    result = dict(format=FORMAT, status='unknown', bits=None, mask=None,
                  enabled=None, interrupts_masked=None, timers_masked=None,
                  unknown_mask=None, raw_replies={}, changed=False,
                  scope='QEMU debugger single-step controls; does not establish instruction retirement or guest-time fidelity')

    def query(command, key):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('QEMU step-policy observation deadline expired')
        raw = remote.request(command, timeout_ms=remaining)
        if time.monotonic() >= deadline:
            raise TimeoutError('QEMU step-policy observation deadline expired')
        if not isinstance(raw, bytes):
            result['reason'] = 'Step-policy reply is not a byte string'
            return None
        # Preserve exact small reply bytes; do not retain an oversized reply in
        # every trace artifact when a stub cannot supply the expected contract.
        result['raw_replies'][key] = dict(size=len(raw), hex=raw[:MAX_REPLY].hex(),
                                         truncated=len(raw) > MAX_REPLY)
        if len(raw) > MAX_REPLY:
            result['reason'] = 'Step-policy reply exceeds its 256-byte budget'
            return None
        if not raw:
            result.update(status='unsupported', reason='QEMU did not implement ' + command)
            return None
        try:
            return raw.decode('ascii')
        except UnicodeDecodeError:
            result['reason'] = 'Step-policy reply is not ASCII'
            return None

    text = query('qqemu.sstepbits', 'bits')
    if text is None:
        return result
    parts = text.split(',')
    if not 1 <= len(parts) <= 8:
        result['reason'] = 'Step-policy bit inventory exceeds its bounded format'
        return result
    bits = {}
    occupied = 0
    for part in parts:
        match = _BIT.fullmatch(part)
        if match is None:
            result['reason'] = 'Malformed step-policy bit inventory'
            return result
        name, encoded = match.groups()
        value = int(encoded, 16)
        if name in bits or value == 0 or value & (value-1) or occupied & value:
            result['reason'] = 'Step-policy bits must be unique, nonzero powers of two'
            return result
        bits[name] = value
        occupied |= value
    result['bits'] = bits

    text = query('qqemu.sstep', 'mask')
    if text is None:
        return result
    match = _MASK.fullmatch(text)
    if match is None:
        result['reason'] = 'Malformed step-policy mask'
        return result
    mask = int(match.group(1), 16)
    result['mask'] = mask
    result['mask_hex'] = hex(mask)
    for name, field in (('ENABLE', 'enabled'), ('NOIRQ', 'interrupts_masked'),
                        ('NOTIMER', 'timers_masked')):
        if name in bits:
            result[field] = bool(mask & bits[name])
    known = sum(bits[name] for name in _KNOWN if name in bits)
    result['unknown_mask'] = mask & ~known
    if not _KNOWN <= bits.keys():
        result['reason'] = 'QEMU did not describe all known step-control meanings'
    elif result['unknown_mask']:
        result['reason'] = 'Step mask selects controls with unknown meanings'
    else:
        result['status'] = 'observed'
    return result
