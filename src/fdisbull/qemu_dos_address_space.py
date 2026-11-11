"""Bounded DOS ownership observations through the selected native page tables.

This admits only the currently observed single CPU address space. It neither
identifies a scheduler task nor establishes arbitrary protected-mode mappings.
"""
from __future__ import annotations

import hashlib
import re

from .dos_memory import translate_386_page


class DosAddressSpace:
    def __init__(self, vm, registers, *, task_binding=None):
        from .qemu_dos_tasks import read_task_context, validate_register_context
        self.vm = vm
        self.remote = vm.debugger()
        self.state = registers['address_state']
        self.mode = registers['cpu_mode']
        self.task_binding = task_binding
        self.native_context = read_task_context(vm, task_binding)
        validate_register_context(self.native_context, registers)
        state = self.state
        if (self.mode not in ('real', 'protected', 'v86') or state.get('machine_vcpus') != 1
                or state.get('register_context_match') is not True
                or type(state.get('a20')) is not bool or type(state.get('paging')) is not bool):
            raise ValueError('DOS ownership requires one observed supported CPU and A20 context')
        if self.mode != 'real':
            if any(key not in state.get('control', {}) for key in ('CR0', 'CR3', 'CR4', 'EFER')):
                raise ValueError('DOS ownership requires observed protected-mode control registers')
            if state['paging'] and state.get('paging_mode') != 'legacy-32':
                raise ValueError('DOS ownership supports only non-PAE 4-KiB paging')
            if any(name not in state.get('segments', {}) for name in ('cs', 'ss', 'ds', 'es')):
                raise ValueError('DOS ownership requires observed segment caches')
        monitor = vm.qmp.call('human-monitor-command', {'command-line': 'info registers'})
        if not isinstance(monitor, str):
            raise ValueError('DOS ownership requires native descriptor-table observations')
        self.tables = {}
        for name in ('GDT', 'IDT'):
            match = re.search(r'\b' + name + r'=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)', monitor)
            if not match:
                raise ValueError('DOS ownership requires observed ' + name + ' base and limit')
            self.tables[name] = {'base': hex(int(match.group(1), 16)), 'limit': hex(int(match.group(2), 16))}
        self.pages = {}

    def _read_table(self, address, length):
        ram_end = min(self.vm.machine_configuration['memory_mib'] << 20, 0xc0000000)
        end = address + length
        if not (0 <= address < end <= 0xa0000 or 0x100000 <= address < end <= ram_end):
            raise ValueError('DOS page table must reside in conventional or extended PC RAM')
        return self.remote.memory(address, length, space='physical')

    def read(self, address, length):
        if type(address) is not int or type(length) is not int or not 1 <= length <= 64*1024*1024:
            raise ValueError('Invalid DOS ownership read')
        if not 0 <= address < address + length <= 0x100000000:
            raise ValueError('DOS ownership observation requires unwrapped 32-bit linear addresses')
        parts = []
        offset = 0
        while offset < length:
            linear = address + offset
            count = min(length-offset, 4096-(linear & 4095))
            translated = translate_386_page(linear, self.state, self._read_table)
            if translated['status'] != 'mapped':
                raise ValueError('DOS ownership requires a qualified RAM mapping: ' + translated['status'])
            backing = int(translated['physical_address'], 16)
            if backing != linear and self.native_context is None:
                raise ValueError('Remapped DOS ownership requires the native task-context extension')
            physical = self._read_table(backing, count)
            virtual = self.remote.memory(linear, count, space='virtual')
            if physical != virtual or len(physical) != count:
                raise ValueError('DOS ownership linear and physical reads differ')
            entries = []
            for entry in translated.get('entries', []):
                entries.append(dict(kind=entry['kind'], address=entry['physical_address'],
                                    value=entry['value']))
            page = linear & ~4095
            item = dict(linear=hex(page), physical=hex(backing & ~4095), entries=entries)
            if page in self.pages and self.pages[page] != item:
                raise ValueError('DOS ownership mapping changed during capture')
            self.pages[page] = item
            parts.append(physical)
            offset += count
        return b''.join(parts)

    def evidence(self):
        from .qemu_dos_tasks import read_task_context, stable_context
        for table in self.tables.values():
            base, length = int(table['base'], 16), int(table['limit'], 16) + 1
            table['sha256'] = hashlib.sha256(self.read(base, length)).hexdigest()
        if read_task_context(self.vm, self.task_binding) != self.native_context:
            raise ValueError('Native task context changed during DOS ownership observation')
        result = dict(format='fdisbull-dos-identity-address-space-1', mode=self.mode,
                    ownership_scope='selected CPU, bound module and DOS allocations',
                    task_identity=None, descriptors=self.tables,
                    pages=[self.pages[key] for key in sorted(self.pages)])
        if self.native_context is not None:
            result.update(format='fdisbull-dos-remapped-address-space-2',
                          architectural_context=stable_context(self.native_context))
        if self.task_binding is not None:
            result['task_identity'] = dict(self.task_binding)
            result['ownership_scope'] = 'cooperating monitor task lifetime, module and DOS allocations'
        return result
