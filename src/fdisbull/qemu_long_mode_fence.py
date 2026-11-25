"""Strict four-level long-mode page walks for owned checkpoint RAM fences."""


def canonical(value):
    return (type(value) is int and 0 <= value < 2**64
            and (value >> 48) == (0xffff if value & (1 << 47) else 0))


def walk(state, linear, read, *, execute=False, write=False, allow_high=False):
    """Observe one 4 KiB page, refusing unsupported architectural features."""
    if type(allow_high) is not bool:
        raise ValueError('Invalid high-physical RAM fence option')
    if not canonical(linear) or linear & 4095:
        raise ValueError('Invalid canonical long-mode RAM fence')
    try:
        cr0, cr3, cr4, efer = (int(state['control'][key], 0) if isinstance(state['control'][key], str)
                               else state['control'][key] for key in ('CR0', 'CR3', 'CR4', 'EFER'))
        selector = state['segments']['cs']['selector']
        selector = int(selector, 0) if isinstance(selector, str) else selector
    except (KeyError, TypeError, ValueError):
        raise ValueError('Long-mode RAM fence controls are unavailable') from None
    if (any(type(v) is not int or not 0 <= v < 2**64 for v in (cr0, cr3, cr4, efer, selector))
            or cr0 & 0x80000001 != 0x80000001 or not cr4 & 0x20
            or cr4 & ((1 << 12) | (1 << 17)) or efer & 0x500 != 0x500
            or cr3 & ~0xfffff018):
        raise ValueError('Unsupported long-mode paging controls')
    table = cr3 & 0xfffff000
    entries = []
    writable = user = True
    nx = False
    for level, shift in (('pml4', 39), ('pdpt', 30), ('directory', 21), ('table', 12)):
        address = table + ((linear >> shift) & 511) * 8
        raw = read(address, 8)
        if not isinstance(raw, bytes) or len(raw) != 8:
            raise ValueError('Incomplete long-mode page entry')
        value = int.from_bytes(raw, 'little')
        entries.append(dict(kind=level, physical_address=address, value=value, raw=raw.hex()))
        reserved_address_bits = 0x7fffff0000000000 if allow_high else 0x7fffffff00000000
        address_mask = 0x000000fffffff000 if allow_high else 0xfffff000
        if (not value & 1 or value & reserved_address_bits
                or value & (1 << 63) and not efer & (1 << 11)):
            raise ValueError('Unsupported or absent long-mode page entry')
        writable &= bool(value & 2)
        user &= bool(value & 4)
        nx |= bool(value & (1 << 63))
        large = level in ('pdpt', 'directory') and bool(value & 0x80)
        if level == 'pml4' and value & 0x80:
            raise ValueError('Reserved long-mode PML4 page-size bit')
        if large or level == 'table':
            size = 1 << shift
            # Bit 12 is PAT for large pages, not part of their address.
            if large and value & ((size - 1) & ~0x1fff):
                raise ValueError('Reserved long-mode large-page address bits')
            physical = (value & address_mask & ~(size - 1)) | (linear & (size - 1))
            if execute and nx or write and not writable or selector & 3 == 3 and not user:
                raise ValueError('Long-mode RAM fence permissions deny access')
            return dict(status='mapped', physical_address=hex(physical), page_size=size,
                        walk=dict(linear=linear, physical=physical, length=4096,
                                  paging_mode='long-4-level', entries=entries,
                                  page_attributes=dict(writable=writable, user=user, execute_disable=nx)),
                        scope='stopped table walk and byte comparison; active backing identity is not proven')
        table = value & address_mask
    raise ValueError('Incomplete long-mode page walk')
