"""Bounded identity-mapped DOS ownership observations for stopped QEMU.

This admits only the currently observed single CPU address space. It neither
identifies a scheduler task nor establishes arbitrary protected-mode mappings.
"""
from __future__ import annotations

import hashlib
import re

from .dos_memory import translate_386_page


class DosAddressSpace:
    def __init__(self, vm, registers):
        self.vm = vm
        self.remote = vm.debugger()
        self.state = registers['address_state']
        self.mode = registers['cpu_mode']
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
        if not 0 <= address < address + length <= 0x100000:
            raise ValueError('DOS ownership observation requires unwrapped low-memory addresses')
        parts = []
        offset = 0
        while offset < length:
            linear = address + offset
            count = min(length-offset, 4096-(linear & 4095))
            translated = translate_386_page(linear, self.state, self._read_table)
            if translated['status'] != 'mapped' or int(translated['physical_address'], 16) != linear:
                raise ValueError('DOS ownership requires identity-mapped low memory')
            physical = self._read_table(linear, count)
            virtual = self.remote.memory(linear, count, space='virtual')
            if physical != virtual or len(physical) != count:
                raise ValueError('DOS ownership linear and physical reads differ')
            entries = []
            for entry in translated.get('entries', []):
                entries.append(dict(kind=entry['kind'], address=entry['physical_address'],
                                    value=entry['value']))
            page = linear & ~4095
            item = dict(linear=hex(page), physical=hex(page), entries=entries)
            if page in self.pages and self.pages[page] != item:
                raise ValueError('DOS ownership mapping changed during capture')
            self.pages[page] = item
            parts.append(physical)
            offset += count
        return b''.join(parts)

    def evidence(self):
        for table in self.tables.values():
            base, length = int(table['base'], 16), int(table['limit'], 16) + 1
            table['sha256'] = hashlib.sha256(self.read(base, length)).hexdigest()
        return dict(format='fdisbull-dos-identity-address-space-1', mode=self.mode,
                    ownership_scope='selected CPU, bound module and DOS allocations',
                    task_identity=None, descriptors=self.tables,
                    pages=[self.pages[key] for key in sorted(self.pages)])
