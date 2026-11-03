"""Bounded selected-thread PE deltas; a partial undo never resumes execution."""
from contextlib import nullcontext
from functools import wraps
import hashlib
import json

from .debug_cpu_deltas import CpuDeltaSessionMixin, _sha, validate_ranges
from .wine_state import REGISTERS, checked_runtime_rip, get_state, integer, validate_edits


def pe_delta_locked(function):
    @wraps(function)
    def locked(self, *args, **kwargs):
        lock = getattr(self, '_delta_lock', None) or getattr(self.rpc, 'lock', None)
        with lock if lock is not None else nullcontext():
            return function(self, *args, **kwargs)
    return locked


class WineCpuDeltaSessionMixin(CpuDeltaSessionMixin):
    _delta_registers = REGISTERS
    _delta_read_only = frozenset({'identity', 'status', 'registers', 'read', 'code',
                                 'screenshot', 'state.save', 'machine.status'})
    _delta_frozen_read_only = frozenset({'identity', 'status', 'registers', 'read',
                                        'close', 'machine.status'})
    _delta_max_bytes = 2 * 1024**3
    _delta_unit = 'completed selected-thread instruction'
    _delta_instruction_completion = 'completed'
    _delta_scope = 'selected writable main-image RAM and exposed selected-thread x86-64 registers'

    def _cpu_delta_bind_rpc(self, rpc):
        # One stable lock survives VM replacement; cached machine handles share it.
        lock = getattr(self, '_delta_lock', None) or rpc.lock
        self._delta_lock = rpc.lock = lock
        if getattr(rpc, 'vm', None) is not None:
            rpc.vm.lock = lock
            rpc.vm.operation_guard = self._cpu_delta_before_machine_operation
        return rpc

    def _cpu_delta_before_machine_operation(self, name):
        self._cpu_delta_before_call('machine.' + name)

    def _cpu_delta_native(self):
        if self.closed:
            raise ValueError('Debugger session is closed')
        if self.backend_name != 'wine-qemu' or not all(self.rpc.capabilities.get(k)
                for k in ('save_states', 'register_edit', 'instruction_trace')):
            raise ValueError('PE CPU deltas require the native Wine/QEMU backend')

    def _cpu_delta_identity(self):
        return dict(run=self.run_id, version=self.version['id'], backend=self.backend_name,
                    source_sha256=self.metadata['source_sha256'],
                    version_sha256=self.metadata['version_sha256'],
                    runtime_profile=self.metadata['runtime_profile'],
                    runtime_inputs={k: v['sha256'] for k, v in self.rpc.inputs.items()},
                    runtime_image_base=hex(self.runtime_base), game_dir=str(self.game_dir))

    def _disk_manifest(self):
        result = []
        for entry in self.metadata['files']:
            source = self.game_dir / entry['path']
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(self.game_dir):
                raise ValueError('PE delta input file is missing or changed identity')
            with source.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            result.append(dict(path=entry['path'], sha256=digest))
        return result

    def _cpu_delta_cpu(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get('cpu_mode', 'long64') != 'long64':
            raise ValueError('PE CPU deltas require long64 registers')
        thread = snapshot.get('thread')
        if type(thread) is not int or not 0 < thread <= 0xffffffff:
            raise ValueError('PE CPU deltas require a selected Windows thread')
        cpu = {name: self._cpu_delta_value(name, snapshot.get(name) if name in ('rip', 'rflags')
                    else snapshot.get('general', {}).get(name)) for name in sorted(REGISTERS)}
        return dict(cpu, thread=thread)

    def _cpu_delta_value(self, name, value):
        value = integer(value)
        if name == 'rflags' and value > 0xffffffff:
            raise ValueError('PE delta RFLAGS must fit 32 bits')
        return value

    def _cpu_delta_pc(self, cpu):
        return dict(space='virtual', offset=hex(cpu['rip']), thread=cpu['thread'])

    def _cpu_delta_admit(self):
        state = self.call('status')
        if state.get('state') != 'stopped':
            raise ValueError('PE CPU deltas require a stopped target')
        self._layer_setup()
        if (self._layers or self._ram_applied or self._execution or self._pending_exec
                or self.breakpoints or self.watchpoints):
            raise ValueError('PE CPU deltas require no active layers, pending instruction, breakpoints or watchpoints')
        cpu = self._cpu_delta_cpu(self.registers())
        if state.get('stop_reason', {}).get('thread') != cpu['thread']:
            raise ValueError('PE CPU delta stop/register thread mismatch')
        checked_runtime_rip(self, cpu['rip'])

    def _cpu_delta_ranges(self, ranges):
        validate_ranges(ranges)
        result = []
        for item in ranges:
            if 'cs' in item:
                raise ValueError('PE CPU delta ranges require flat addresses without cs')
            address = self._address(item['address'], item['length'])
            end = address + item['length']
            if not any(r.start <= address and end <= r.start + len(r.data)
                       and r.writable and not r.executable for r in self.regions):
                raise ValueError('PE CPU delta ranges require writable non-executable main-image RAM')
            if any(address < int(r['address'], 16) + r['length'] and int(r['address'], 16) < end for r in result):
                raise ValueError('CPU delta RAM ranges overlap')
            result.append(dict(address=hex(address), length=item['length']))
        return result

    def _cpu_delta_observe(self, history):
        cpu = self._cpu_delta_cpu(self.registers())
        if 'initial_cpu' in history and cpu['thread'] != history['initial_cpu']['thread']:
            raise ValueError('PE CPU delta selected thread changed')
        checked_runtime_rip(self, cpu['rip'])
        state = self.call('status')
        if state.get('state') != 'stopped' or state.get('stop_reason', {}).get('thread') != cpu['thread']:
            raise ValueError('PE CPU delta selected thread is not stopped')
        ram = []
        for item in history['ranges']:
            data = bytes.fromhex(self.memory(item['address'], length=item['length'])['hex'])
            if len(data) != item['length']:
                raise ValueError('PE CPU delta RAM observation length mismatch')
            ram.append(data)
        return cpu, ram

    def _cpu_delta_anchor_size(self, anchor):
        size, native = anchor.get('size'), anchor.get('native_size')
        if type(size) is not int or type(native) is not int or size <= 0 or native <= 0:
            raise ValueError('PE CPU delta anchor requires manifest and native sidecar sizes')
        return size + native

    def _cpu_delta_anchor_manifest(self, anchor):
        return anchor.get('metadata', {}).get('files')

    def _cpu_delta_check_anchor(self, history, row):
        _, document, _ = get_state(self.project, history['anchor']['artifact'], self.version['id'])
        if (document['machine_size'] != history['anchor']['native_size']
                or document['metadata']['files'] != history['disk_manifest']
                or self._cpu_delta_cpu(document['metadata']['registers']) != history['initial_cpu']):
            raise ValueError('PE CPU delta recovery anchor metadata mismatch')

    def _cpu_delta_trace_step(self, before_cpu, timeout_ms):
        trace = self.trace('cpu-delta-instruction.json', count=1, timeout_ms=timeout_ms)
        row = self.project.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (trace['artifact'],)).fetchone()
        if (row is None or row['kind'] != 'trace' or row['run'] != self.run_id
                or row['sha256'] != trace['sha256'] or _sha(bytes(row['data'])) != trace['sha256']):
            raise ValueError('PE CPU delta trace hash/identity mismatch')
        document = json.loads(bytes(row['data']))
        events = document.get('events')
        state = document.get('session', {})
        if (document.get('run') != self.run_id or document.get('version') != self.version['id']
                or document.get('complete') is not True or document.get('requested_count') != 1
                or not isinstance(events, list) or len(events) != 1 or state.get('state') != 'stopped'
                or state.get('stop_reason', {}).get('kind') != 'step'
                or state.get('stop_reason', {}).get('thread') != before_cpu['thread']
                or self._cpu_delta_cpu(events[0].get('registers')) != before_cpu
                or integer(events[0].get('address')) != before_cpu['rip']):
            raise ValueError('PE CPU delta trace must certify one completed selected-thread instruction')
        return trace, self._cpu_delta_pc(self._cpu_delta_cpu(self.registers()))

    def _cpu_delta_prepare_restore(self, current, target):
        if current['thread'] != target['thread']:
            raise ValueError('PE CPU delta selected thread changed')
        edits = {name: dict(expected=current[name], value=target[name])
                 for name in REGISTERS if current[name] != target[name]}
        validate_edits([], edits)
        checked_runtime_rip(self, target['rip'])

    def _cpu_delta_write_memory(self, history, change):
        address = int(history['ranges'][change['range']]['address'], 16) + change['offset']
        return self.write_memory(address, change['after_hex'], expected_hex=change['before_hex'])

    def _cpu_delta_write_register(self, name, value):
        snapshot = self._cpu_delta_cpu(self.registers())
        return self.write_registers({name: dict(expected=snapshot[name], value=value)})

    @pe_delta_locked
    def cpu_delta_start(self, ranges, *, max_steps=16, max_bytes=2 * 1024**3):
        return super().cpu_delta_start(ranges, max_steps=max_steps, max_bytes=max_bytes)

    cpu_delta_record = pe_delta_locked(CpuDeltaSessionMixin.cpu_delta_record)
    cpu_delta_rewind = pe_delta_locked(CpuDeltaSessionMixin.cpu_delta_rewind)
    cpu_delta_recover = pe_delta_locked(CpuDeltaSessionMixin.cpu_delta_recover)
    cpu_delta_status = pe_delta_locked(CpuDeltaSessionMixin.cpu_delta_status)
