"""Bounded read-only legacy x86 translation and descriptor observations.

Readers are supplied by the caller, so the same routines operate on stopped
QEMU memory or on independently retained physical-memory evidence. They do not
establish process ownership, a stable snapshot, access rights, or source identity.
"""
import re

QEMU_TCG_QUALIFIED_IMAGE = '863b36b07648d55f52f8d0bf8df6a592a46f1deed21415527a0f89f912329d25'
QEMU_TCG_PAE_ACCESSED_IMAGE = QEMU_TCG_QUALIFIED_IMAGE
QEMU_TCG_PHYSICAL64_IMAGE = '7a9f04b14e74caf83d74c1ebb160f0f3d130b04a3b094a176091ad33a50b7f1e'
QEMU_TCG_OVERLAY_WRITE_IMAGE = '71bdaef65a9241d2d4ff451fbd3e44a9a5cc93cb437b4adc51026ad211db8bd1'
QEMU_TCG_CMPXCHG_IMAGE = 'a25557c5d811fc2aa83abcd0eb472291bac72a593ac7862396691012501f7a87'
QEMU_TCG_QUALIFIED_IMAGES = frozenset((QEMU_TCG_QUALIFIED_IMAGE, QEMU_TCG_PHYSICAL64_IMAGE, QEMU_TCG_OVERLAY_WRITE_IMAGE, QEMU_TCG_CMPXCHG_IMAGE))


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
    if cr4 & (1 << 12) or efer & ((1 << 8) | (1 << 10)):
        raise ValueError('Long mode is unsupported')
    if not cr4 & 0x20 and cr3 & 0xfe7:
        raise ValueError('Unsupported CR3 reserved bits')
    return True


def _read(reader, address, length):
    data = reader(address, length)
    if not isinstance(data, bytes) or len(data) != length:
        raise ValueError('Incomplete memory observation')
    return data


def _extended_walk(context, linear, reader, qemu_image_sha256, high_ram_end, pse36):
    """Walk PSE/PAE tables, admitting bit 32 only inside the verified high RAM bank."""
    cr0, cr3, cr4, efer = (context[k] for k in ('cr0', 'cr3', 'cr4', 'efer'))
    pae = bool(cr4 & 0x20)
    entries = []

    def entry(kind, address, size):
        raw = _read(reader, address, size)
        value = int.from_bytes(raw, 'little')
        entries.append(dict(kind=kind, physical_address=address, value=value, raw=raw.hex()))
        if not value & 1:
            raise ValueError(('PAE ' if pae else '') + 'Page entry is not present')
        if size == 8:
            if value & 0x7fffffff00000000:
                frame = value & 0x7ffffffffffff000
                if high_ram_end is None or frame >= high_ram_end:
                    raise ValueError('Unsupported PAE high physical address or reserved bits')
            if value & (1 << 63) and not efer & (1 << 11):
                raise ValueError('NX bit requires EFER.NXE')
        return value

    if pae:
        pdpt = entry('pdpt', (cr3 & 0xffffffe0) + (linear >> 30) * 8, 8)
        qemu_accessed = qemu_image_sha256 in QEMU_TCG_QUALIFIED_IMAGES and bool(pdpt & 0x20)
        if pdpt & (0x1c6 if qemu_accessed else 0x1e6) or pdpt & (1 << 63):
            raise ValueError('Unsupported PAE PDPTE reserved bits')
        if qemu_accessed:
            entries[-1]['qemu_tcg_accessed'] = True
        pde = entry('directory', (pdpt & 0x1fffff000) + ((linear >> 21) & 0x1ff) * 8, 8)
        large = bool(pde & 0x80)
        if large:
            if pde & 0x1fe000:
                raise ValueError('Unsupported PAE large-page reserved bits')
            size, physical = 0x200000, (pde & 0x1ffe00000) | (linear & 0x1fffff)
            leaf = pde
        else:
            leaf = entry('table', (pde & 0x1fffff000) + ((linear >> 12) & 0x1ff) * 8, 8)
            size, physical = 4096, (leaf & 0x1fffff000) | (linear & 0xfff)
        attrs = dict(writable=bool(pde & leaf & 2), user=bool(pde & leaf & 4),
                     supervisor_write_protect=bool(cr0 & 0x10000),
                     execute_disable=bool((pde | leaf) & (1 << 63)))
        mode = 'pae'
    else:
        pde = entry('directory', (cr3 & 0xfffff000) + (linear >> 22) * 4, 4)
        if not pde & 0x80:
            return None
        if not cr4 & 0x10:
            raise ValueError('Large PDE requires CR4.PSE')
        if pde & 0x3fc000 or (pde & 0x2000 and not pse36):
            raise ValueError('PSE-36 or reserved large-page bits are unsupported')
        size, physical = 0x400000, (pde & 0xffc00000) | ((pde & 0x2000) << 19) | (linear & 0x3fffff)
        attrs = dict(writable=bool(pde & 2), user=bool(pde & 4),
                     supervisor_write_protect=bool(cr0 & 0x10000))
        mode = 'legacy-32'
    return dict(physical=physical, page_size=size, paging_mode=mode,
                entries=entries, page_attributes=attrs,
                translation_scope='stopped table walk; active backing identity is not proven')


def require_executable_walks(walks, length):
    """Reject an NX mapping only for the bytes of the current instruction."""
    for walk in walks:
        if length <= 0:
            break
        if walk.get('page_attributes', {}).get('execute_disable'):
            raise ValueError('Current instruction is mapped execute-disabled')
        length -= walk['length']
    if length > 0:
        raise ValueError('Incomplete instruction page walks')


def translate_linear(context, address, length, read_physical, read_linear=None, *,
                     qemu_image_sha256=None, high_ram_end=None, pse36=False):
    """Return bytes and 4 KiB walk evidence, optionally checking QEMU linear bytes."""
    if high_ram_end is not None and (
        type(high_ram_end) is not int or not 2**32 < high_ram_end <= 2**33 or high_ram_end % 4096
    ):
        raise ValueError('Invalid PAE high RAM extent')
    if type(pse36) is not bool or (pse36 and high_ram_end is None):
        raise ValueError('Invalid PSE-36 capability')
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
        if not paging:
            data = _read(read_physical, linear, count)
            if read_linear is not None and _read(read_linear, linear, count) != data:
                raise ValueError('Linear and translated physical bytes differ')
            result.append(data)
            walks.append(dict(linear=linear, length=count, physical=linear, paging=False))
            offset += count
            continue
        initial = {}
        def first_read(a, n):
            data = read_physical(a, n)
            if not initial:
                initial[a, n] = data
            return data

        extended = _extended_walk(context, linear, first_read, qemu_image_sha256, high_ram_end, pse36)
        if extended is not None:
            physical = extended['physical']
            if physical >= 2**32 and physical + count > high_ram_end:
                raise ValueError('Physical read exceeds high RAM extent')
            data = _read(read_physical, physical, count)
            if read_linear is not None and _read(read_linear, linear, count) != data:
                raise ValueError('Linear and translated physical bytes differ')
            result.append(data)
            walks.append(dict(linear=linear, length=count, paging=True, **extended))
            offset += count
            continue
        def legacy_read(a, n):
            key = (a, n)
            if key in initial:
                return initial.pop(key)
            return read_physical(a, n)

        observed = translate_386_page(linear, state, legacy_read)
        if observed['status'] != 'mapped' or observed.get('page_size') != 4096:
            raise ValueError(observed.get('reason', 'Unsupported page translation'))
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
