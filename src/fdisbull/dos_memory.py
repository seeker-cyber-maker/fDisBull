"""Observed x86 machine address context and bounded 386 page-table walks.

Neither a translation nor a QEMM configuration establishes an allocation's
identity or lifetime. These helpers do not infer DOS paragraphs from selectors.
"""
from __future__ import annotations

import re
import struct


def _number(value):
    if isinstance(value, str):
        return int(value, 0)
    return value if type(value) is int else None


def machine_address_state(registers, monitor):
    """Combine GDB values with QEMU's observed segment caches/control state."""
    control = {name: hex(int(value, 16)) for name, value in re.findall(
        r'\b(CR0|CR2|CR3|CR4|EFER)=([0-9a-fA-F]+)', monitor)}
    segments = {}
    for name, selector, base, limit, attributes in re.findall(
            r'\b(CS|SS|DS|ES|FS|GS)\s*=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)', monitor):
        segments[name.lower()] = dict(selector=hex(int(selector, 16)), base=hex(int(base, 16)),
                                      limit=hex(int(limit, 16)), attributes=hex(int(attributes, 16)))
    flags_match = re.search(r'\b(?:EFL|RFL|EFLAGS|RFLAGS)=([0-9a-fA-F]+)', monitor)
    flags = int(flags_match.group(1), 16) if flags_match else _number(registers.get('eflags', registers.get('rflags')))
    cr0 = _number(control.get('CR0'))
    cr4 = _number(control.get('CR4'))
    efer = _number(control.get('EFER'))
    long_active = bool(efer & 0x400) if efer is not None else False
    mode = 'unknown'
    if cr0 is not None:
        if not cr0 & 1:
            mode = 'real'
        elif long_active:
            mode = 'long'
        elif flags is not None:
            mode = 'v86' if flags & 0x20000 else 'protected'
    paging = bool(cr0 & 0x80000000) if cr0 is not None else None
    a20_match = re.search(r'\bA20=([01])\b', monitor)
    a20 = bool(int(a20_match.group(1))) if a20_match else None
    code_bits = stack_bits = None
    cs = segments.get('cs')
    ss = segments.get('ss')
    if mode == 'v86':
        code_bits = stack_bits = 16
    elif mode != 'unknown':
        if cs is not None:
            attributes = int(cs['attributes'], 16)
            code_bits = 64 if long_active and attributes & 0x200000 else 32 if attributes & 0x400000 else 16
        if code_bits == 64:
            stack_bits = 64
        elif ss is not None:
            stack_bits = 32 if int(ss['attributes'], 16) & 0x400000 else 16
    ip = _number(registers.get('rip', registers.get('eip')))
    monitor_ip = re.search(r'\b(?:RIP|EIP)=([0-9a-fA-F]+)', monitor)
    same_context = ip == int(monitor_ip.group(1), 16) if monitor_ip and ip is not None else None
    pc = None
    if cs is not None and ip is not None and same_context is not False:
        # Use the observed hidden descriptor base, never selector * 16.
        # CS.D controls default operand/address size, not the observed EIP.
        # A 32-bit transfer can leave EIP > FFFF in a 16-bit code segment.
        effective_ip = ip & 0xffffffff if code_bits in (16, 32) else ip
        pc = hex(int(cs['base'], 16) + effective_ip)
    if paging is False:
        paging_mode = 'disabled'
    elif paging is None or cr4 is None:
        paging_mode = 'unknown'
    elif long_active:
        paging_mode = 'ia32e'
    else:
        paging_mode = 'pae' if cr4 & 0x20 else 'legacy-32'
    state = dict(cpu_mode=mode, paging=paging, paging_mode=paging_mode, a20=a20,
                 code_bits=code_bits, stack_bits=stack_bits, segments=segments,
                 control=control, flags=hex(flags) if flags is not None else None,
                 register_context_match=same_context,
                 segment_semantics='v86-segment' if mode == 'v86' else 'real-segment' if mode == 'real' else 'selector',
                 provenance='QEMU GDB registers and HMP observed segment caches/control registers')
    return dict(cpu_mode=mode, control=control, instruction_pointer=hex(ip) if ip is not None else None,
                linear_pc=pc, address_state=state)


def translate_386_page(address, address_state, read_physical):
    """Read at most two 32-bit entries in an observed, non-PAE 4-KiB map.

    The caller must keep all vCPUs paused. Physical reads must return exactly
    the requested bytes; permission bits are reported, not a complete CPU
    privilege/access verdict. PAE, large pages and unknown A20 refuse.
    """
    linear = _number(address)
    if linear is None or not 0 <= linear <= 0xffffffff:
        raise ValueError('386 translation requires a 32-bit linear address')
    result = dict(linear_address=hex(linear), physical_address=None, page_size=None,
                  status='unknown', entries=[],
                  scope='paused machine page-table observation; not allocation identity or a retained binding')
    control = address_state.get('control', {})
    result['control'] = dict(control)
    result['a20'] = address_state.get('a20')
    if address_state.get('machine_vcpus') not in (None, 1):
        return dict(result, status='unsupported',
                    reason='GDB/QMP page-walk CPU identity is qualified only for a single-vCPU machine')
    if address_state.get('register_context_match') is False:
        return dict(result, reason='GDB and QMP instruction pointers identify different CPU contexts')
    cr0, cr3, cr4 = (_number(control.get(key)) for key in ('CR0', 'CR3', 'CR4'))
    efer = _number(control.get('EFER'))
    if cr0 is None:
        return dict(result, reason='CR0 was not observed')
    if type(address_state.get('a20')) is not bool:
        return dict(result, reason='A20 state was not observed')
    if not cr0 & 0x80000000:
        physical = linear if address_state['a20'] else linear & ~(1 << 20)
        return dict(result, status='mapped', physical_address=hex(physical), paging=False,
                    translation='unpaged linear address with observed A20 gate')
    result['paging'] = True
    if not cr0 & 1:
        return dict(result, status='unsupported', reason='Paging without protected-mode enable is not a qualified CPU state')
    if cr3 is None or cr4 is None:
        return dict(result, reason='CR3 and CR4 must be observed for a non-PAE page walk')
    if not 0 <= cr3 <= 0xffffffff:
        return dict(result, status='unsupported', reason='CR3 is outside the 32-bit non-PAE address space')
    if efer is not None and efer & 0x400 or cr4 & 0x20:
        return dict(result, status='unsupported', reason='PAE/IA-32e page tables require a different walker')
    if not address_state['a20']:
        return dict(result, status='unsupported', reason='Paged translation with A20 disabled is not qualified')

    def entry(kind, location):
        data = read_physical(location, 4)
        if not isinstance(data, bytes) or len(data) != 4:
            raise ValueError('Page-table observation requires an exact four-byte physical read')
        value = struct.unpack('<I', data)[0]
        result['entries'].append(dict(kind=kind, physical_address=hex(location), value=hex(value),
                                      present=bool(value & 1), writable=bool(value & 2), user=bool(value & 4)))
        return value

    pde = entry('directory', (cr3 & 0xfffff000) + (linear >> 22) * 4)
    if not pde & 1:
        return dict(result, status='not-present', reason='Page-directory entry is not present')
    if pde & 0x80:
        return dict(result, status='unsupported', reason='Large-page/reserved PDE bit is outside the 386 4-KiB walker')
    pte = entry('table', (pde & 0xfffff000) + ((linear >> 12) & 0x3ff) * 4)
    if not pte & 1:
        return dict(result, status='not-present', reason='Page-table entry is not present')
    return dict(result, status='mapped', physical_address=hex((pte & 0xfffff000) + (linear & 0xfff)),
                page_size=4096, translation='observed non-PAE 386 two-level page tables',
                page_attributes=dict(writable=bool(pde & pte & 2), user=bool(pde & pte & 4),
                                     supervisor_write_protect=bool(cr0 & 0x10000)),
                permissions_scope='combined PDE/PTE attributes; not an access or allocation-lifetime guarantee')
