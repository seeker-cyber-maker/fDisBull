"""Bounded read-only legacy x86 translation and descriptor observations.

Readers are supplied by the caller, so the same routines operate on stopped
QEMU memory or on independently retained physical-memory evidence. They do not
establish process ownership, a stable snapshot, access rights, or source identity.
"""
import re


def _u32(value, name):
    if type(value) is not int or not 0 <= value < 2**32:
        raise ValueError('Invalid ' + name)
    return value


def parse_hmp(text):
    """Parse exactly one HMP register observation; missing or ambiguous fields fail."""
    if not isinstance(text, str):
        raise ValueError('Missing HMP register observation')

    text = text.replace('\r\n', '\n')

    def one(pattern, label):
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous HMP ' + label)
        return matches[0]

    result = {}
    for name in ('CR0', 'CR3', 'CR4', 'EFER'):
        result[name.lower()] = _u32(int(one(r'\b' + name + r'\s*=\s*([0-9a-f]+)\b', name), 16), name)
    gdt = one(r'^\s*GDT\s*=\s*([0-9a-f]+)\s+([0-9a-f]+)\s*$', 'GDT')
    ldt = one(r'^\s*LDT\s*=\s*([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)(?:[ \t]+DPL=[0-3][ \t]+LDT)?[ \t]*$', 'LDT')
    result['gdt'] = dict(zip(('base', 'limit'), (int(x, 16) for x in gdt)))
    result['ldtr'] = dict(zip(('selector', 'base', 'limit', 'attributes'), (int(x, 16) for x in ldt)))
    for table in (result['gdt'], result['ldtr']):
        for key, value in table.items():
            _u32(value, key)
    if result['gdt']['limit'] > 0xffff or result['ldtr']['selector'] > 0xffff:
        raise ValueError('Invalid HMP descriptor table')
    return result


def _mode(context):
    try:
        cr0, cr3, cr4, efer = (_u32(context[k], k) for k in ('cr0', 'cr3', 'cr4', 'efer'))
    except (KeyError, TypeError):
        raise ValueError('Missing paging context') from None
    if not cr0 & 1:
        raise ValueError('Requires protected mode')
    if not cr0 & 0x80000000:
        return False
    if cr4 & ((1 << 5) | (1 << 12)) or efer & ((1 << 8) | (1 << 10)):
        raise ValueError('PAE and long mode are unsupported')
    if cr3 & 0xfe7:
        raise ValueError('Unsupported CR3 reserved bits')
    return True


def _read(reader, address, length):
    data = reader(address, length)
    if not isinstance(data, bytes) or len(data) != length:
        raise ValueError('Incomplete memory observation')
    return data


def translate_linear(context, address, length, read_physical, read_linear=None):
    """Return bytes and 4 KiB walk evidence, optionally checking QEMU linear bytes."""
    paging = _mode(context)
    from .dos_memory import translate_386_page
    state = dict(control={key.upper(): context[key] for key in ('cr0', 'cr3', 'cr4', 'efer')},
                 a20=True, machine_vcpus=1, register_context_match=True)
    _u32(address, 'linear address')
    if type(length) is not int or not 1 <= length <= 524288 or address + length > 2**32:
        raise ValueError('Invalid linear extent')
    result, walks = [], []
    offset = 0
    while offset < length:
        linear = address + offset
        count = min(length - offset, 4096 - (linear & 0xfff))
        observed = translate_386_page(linear, state, read_physical)
        if observed['status'] != 'mapped' or (paging and observed.get('page_size') != 4096):
            raise ValueError(observed.get('reason', 'Unsupported page translation'))
        if not paging:
            data = _read(read_physical, linear, count)
            if read_linear is not None and _read(read_linear, linear, count) != data:
                raise ValueError('Linear and translated physical bytes differ')
            result.append(data)
            walks.append(dict(linear=linear, length=count, physical=linear, paging=False))
            offset += count
            continue
        directory_entry, table_entry = observed['entries']
        pde_address = int(directory_entry['physical_address'], 16)
        pte_address = int(table_entry['physical_address'], 16)
        pde, pte = int(directory_entry['value'], 16), int(table_entry['value'], 16)
        pde_raw, pte_raw = pde.to_bytes(4, 'little'), pte.to_bytes(4, 'little')
        physical = int(observed['physical_address'], 16)
        data = _read(read_physical, physical, count)
        if read_linear is not None and _read(read_linear, linear, count) != data:
            raise ValueError('Linear and translated physical bytes differ')
        result.append(data)
        walks.append(dict(linear=linear, length=count, physical=physical, paging=True,
                          pde_address=pde_address, pde=pde, pde_bytes=pde_raw.hex(),
                          pte_address=pte_address, pte=pte, pte_bytes=pte_raw.hex()))
        offset += count
    return b''.join(result), walks


def decode_descriptor(raw):
    if not isinstance(raw, bytes) or len(raw) != 8:
        raise ValueError('Invalid descriptor bytes')
    value = int.from_bytes(raw, 'little')
    base = ((value >> 16) & 0xffff) | ((value >> 32) & 0xff) << 16 | ((value >> 56) & 0xff) << 24
    limit = (value & 0xffff) | ((value >> 48) & 0xf) << 16
    access = (value >> 40) & 0xff
    flags = (value >> 52) & 0xf
    if flags & 8:
        limit = (limit << 12) | 0xfff
    return dict(base=base, limit=limit, access=access, flags=flags,
                present=bool(access & 0x80), system=not bool(access & 0x10),
                type=access & 0xf, raw=raw.hex())


def observe_descriptor(context, selector, read_linear):
    """Observe selector's descriptor from the live cached GDT or LDTR table."""
    if type(selector) is not int or not 0 <= selector <= 0xffff or selector & 0xfffc == 0:
        raise ValueError('Invalid or null selector')
    try:
        is_ldt = bool(selector & 4)
        table = context['ldtr' if is_ldt else 'gdt']
        base, limit = _u32(table['base'], 'table base'), _u32(table['limit'], 'table limit')
        if is_ldt:
            ldtr_selector = table['selector']
            attributes = _u32(table['attributes'], 'LDTR attributes')
            if (type(ldtr_selector) is not int or not 0 < ldtr_selector <= 0xffff
                    or not ldtr_selector & 0xfff8 or ldtr_selector & 4
                    or (attributes >> 8) & 0x9f != 0x82):
                raise ValueError('LDTR cache is not a present LDT')
    except (KeyError, TypeError):
        raise ValueError('Missing descriptor table context') from None
    parent = None
    if is_ldt:
        parent = observe_descriptor(context, ldtr_selector, read_linear)
        actual = parent['descriptor']
        if (not actual['present'] or not actual['system'] or actual['type'] != 2
                or actual['base'] != base or actual['limit'] != limit
                or actual['access'] != ((attributes >> 8) & 0xff)
                or actual['flags'] != ((attributes >> 20) & 0xf)):
            raise ValueError('LDTR cache differs from GDT descriptor')
    index = selector & 0xfff8
    if index + 7 > limit or base + index + 8 > 2**32:
        raise ValueError('Descriptor outside observed table')
    descriptor = decode_descriptor(_read(read_linear, base + index, 8))
    result = dict(selector=selector, table='ldt' if is_ldt else 'gdt', table_base=base,
                  table_limit=limit, address=base + index, descriptor=descriptor)
    if parent is not None:
        result['ldtr_parent'] = parent
    return result
