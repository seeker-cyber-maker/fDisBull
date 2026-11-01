"""Experimental selected-RAM/exposed-register net deltas, not machine rewind.

Intervals use observed next fetches. Devices, unselected RAM, hidden CPU state,
and host files are not restored. A partial undo freezes execution and capture
until an existing full native checkpoint has been successfully loaded.
"""
from contextlib import contextmanager
from copy import deepcopy
import base64
import hashlib
import json
import time
import uuid

from .debug_rewind import READ_ONLY, _bounded, _pc
from .debug_state import REGISTERS, integer
from .operation_budget import rpc_budget


FORMAT = 'fdisbull-cpu-ram-delta-1'
FROZEN_READ_ONLY = frozenset({'agent.capabilities', 'session.status',
                            'state.get_registers', 'memory.read', 'session.close'})
NARROW = frozenset({'eip', 'cs', 'ds', 'es', 'ss', 'fs', 'gs', 'flags'})


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _cpu(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('cpu_mode') != 'real':
        raise ValueError('CPU deltas require real-mode DOS registers')
    values = {}
    for name in sorted(REGISTERS):
        if name == 'eip':
            value = snapshot.get('instruction_pointer')
        elif name == 'flags':
            value = snapshot.get('flags')
        else:
            value = snapshot.get('general', {}).get(name, snapshot.get('segments', {}).get(name))
        value = integer(value)
        if value > (0xffff if name in NARROW else 0xffffffff):
            raise ValueError('CPU delta register exceeds real-mode width: ' + name)
        values[name] = value
    return values


def _pc_of(cpu):
    return _pc(dict(cpu_mode='real', segments={'cs': cpu['cs']}, instruction_pointer=cpu['eip']))


def _fingerprint(cpu, ram):
    return dict(cpu_sha256=_sha(_encoded(cpu)), ram_sha256=[_sha(data) for data in ram])


def _runs(before, after):
    """Coalesce contiguous changed bytes; unchanged selected bytes stay guarded."""
    result = []
    for number, (old, new) in enumerate(zip(before, after)):
        start = 0
        while start < len(old):
            if old[start] == new[start]:
                start += 1
                continue
            end = start + 1
            while end < len(old) and old[end] != new[end]:
                end += 1
            result.append(dict(range=number, offset=start,
                               before_hex=old[start:end].hex(), after_hex=new[start:end].hex()))
            start = end
    return result


class CpuDeltaSessionMixin:
    def _cpu_delta_native(self):
        if self.closed:
            raise ValueError('Debugger session is closed')
        backend = getattr(self, 'backend_name', None) or self.metadata.get('backend', 'dosbox')
        if backend != 'dosbox' or not all(self.rpc.capabilities.get(key)
                                          for key in ('save_states', 'register_edit')):
            raise ValueError('CPU deltas require native DOSBox with save_states and register_edit')

    def _cpu_delta_identity(self):
        return dict(run=self.run_id, version=self.version['id'], **{
            key: self.metadata.get(key) for key in ('source_sha256', 'version_sha256',
            'emulator_sha256', 'runtime_profile', 'runtime_load_segment', 'game_dir')})

    def _cpu_delta_invalidate(self, reason):
        history = getattr(self, '_cpu_delta_history', None)
        if history is not None and history['valid']:
            history['valid'] = False
            history['invalid_reason'] = reason
            self._event('cpu-delta-invalidated', dict(history=history['id'], reason=reason,
                                                     cursor=history['cursor']))

    def _cpu_delta_before_call(self, method, params=None):
        if getattr(self, '_cpu_delta_busy', False) or getattr(self, '_cpu_delta_load_depth', 0):
            return
        history = getattr(self, '_cpu_delta_history', None)
        if history is not None and history['frozen'] and method not in FROZEN_READ_ONLY:
            raise ValueError('CPU delta partial state is frozen; load a full native checkpoint before execution or capture')
        if method not in READ_ONLY:
            self._cpu_delta_invalidate('unrecorded RPC: ' + str(method))

    @contextmanager
    def _cpu_delta_full_load(self):
        """Permit the verified native-load path, including its layer restoration.

        The caller must invoke _cpu_delta_loaded only after successful readback.
        Merely entering/leaving this context never makes a partial state resumable.
        """
        self._cpu_delta_invalidate('full native load attempted')
        self._cpu_delta_load_depth = getattr(self, '_cpu_delta_load_depth', 0) + 1
        try:
            yield
        finally:
            self._cpu_delta_load_depth -= 1

    def _cpu_delta_loaded(self):
        self._cpu_delta_invalidate('full native checkpoint loaded')
        history = getattr(self, '_cpu_delta_history', None)
        if history is not None:
            history['frozen'] = False
            history['partial_restored'] = False

    @contextmanager
    def _cpu_delta_owned(self):
        if getattr(self, '_cpu_delta_busy', False):
            raise ValueError('Nested CPU delta operations are unsupported')
        self._cpu_delta_busy = True
        try:
            yield
        finally:
            self._cpu_delta_busy = False

    def _cpu_delta_require(self, *, valid=True):
        self._cpu_delta_native()
        history = getattr(self, '_cpu_delta_history', None)
        if history is None or (valid and not history['valid']):
            raise ValueError('No valid CPU delta history; explicitly start a new history')
        if history['identity'] != self._cpu_delta_identity():
            self._cpu_delta_invalidate('live session identity changed')
            raise ValueError('CPU delta history belongs to a different live session identity')
        if self._disk_manifest() != history['disk_manifest']:
            self._cpu_delta_invalidate('mounted game files changed')
            raise ValueError('Mounted game files changed during CPU delta history')
        return history

    def _cpu_delta_admit(self):
        if self.call('session.status').get('state') != 'stopped':
            raise ValueError('CPU deltas require a stopped target')
        layers = self._layer_state()
        if layers.get('active') or layers.get('ram_applied') or getattr(self, '_hooks', {}):
            raise ValueError('CPU deltas require no active layers or hooks')
        if getattr(self, '_spatial_guard_active', False) or getattr(self, '_spatial_guard_failed', False):
            raise ValueError('CPU deltas cannot use a temporary or failed spatial guard')
        if self.call('input.mouse.state').get('mouse', {}).get('release_pending'):
            raise ValueError('CPU deltas require no pending mouse input')
        if self.rpc.capabilities.get('input', {}).get('keyboard'):
            keyboard = self.keyboard_state()['keyboard']
            if keyboard.get('pending_events') or keyboard.get('owned_keys'):
                raise ValueError('CPU deltas require no pending or held keyboard input')

    def _cpu_delta_ranges(self, ranges):
        if not isinstance(ranges, list) or not 1 <= len(ranges) <= 64:
            raise ValueError('CPU deltas require 1..64 explicit RAM ranges')
        result = []
        total = 0
        for item in ranges:
            if not isinstance(item, dict) or set(item) not in ({'address', 'length'}, {'address', 'length', 'cs'}):
                raise ValueError('A CPU delta range requires address, length, and optional cs')
            _bounded(item['length'], 'range length', 1, 65536)
            address, _ = self.project._dos_parse_address(item['address'], item.get('cs'))
            end = address + item['length']
            if address < self.static_base or end > self.static_base + self.module_size:
                raise ValueError('CPU delta range is outside the original mapped DOS module')
            # Restrict writes to conventional RAM, excluding video/ROM handlers.
            if address + self.delta < 0 or end + self.delta > 0xa0000:
                raise ValueError('CPU delta range must fit conventional DOS RAM')
            if any(address < int(old['address'], 16) + old['length'] and int(old['address'], 16) < end
                   for old in result):
                raise ValueError('CPU delta RAM ranges overlap')
            result.append(dict(address=hex(address), length=item['length']))
            total += item['length']
        if total > 65536:
            raise ValueError('Combined CPU delta RAM ranges exceed 65536 bytes')
        return result

    def _cpu_delta_observe(self, history):
        cpu = _cpu(self.registers())
        ram = []
        for item in history['ranges']:
            observed = self.memory(item['address'], length=item['length'])
            data = bytes.fromhex(observed['hex'])
            if len(data) != item['length'] or observed.get('sha256') != _sha(data):
                raise ValueError('CPU delta RAM observation failed its length/hash check')
            ram.append(data)
        return cpu, ram

    def cpu_delta_start(self, ranges, *, max_steps=16, max_bytes=67108864):
        _bounded(max_steps, 'max_steps', 1, 128)
        _bounded(max_bytes, 'max_bytes', 1, 256 * 1024 * 1024)
        self._cpu_delta_native()
        old = getattr(self, '_cpu_delta_history', None)
        if old is not None and old['frozen']:
            raise ValueError('CPU delta partial state is frozen; recover before starting a history')
        normalized = self._cpu_delta_ranges(ranges)
        started = time.monotonic()
        with self._cpu_delta_owned():
            self._cpu_delta_admit()
            _cpu(self.registers())
            self._cpu_delta_invalidate('new CPU delta history started')
            self._rewind_invalidate('CPU delta history started')
            manifest = self._disk_manifest()
            anchor = self.save_state('cpu-delta-recovery.sav', max_bytes=max_bytes)
            size = anchor.get('size')
            if type(size) is not int or not 1 <= size <= max_bytes:
                raise ValueError('CPU delta recovery anchor violated its byte budget')
            if anchor.get('metadata', {}).get('disk_manifest') != manifest or self._disk_manifest() != manifest:
                raise ValueError('Mounted game files changed while capturing CPU delta anchor')
            history = dict(id=uuid.uuid4().hex, identity=self._cpu_delta_identity(), valid=True,
                invalid_reason=None, frozen=False, partial_restored=False, cursor=0, entries=[],
                captures_used=0, delta_bytes_used=0, anchor_bytes_used=size,
                anchor={key: anchor[key] for key in ('artifact', 'sha256', 'size')},
                disk_manifest=deepcopy(manifest), ranges=normalized, max_steps=max_steps, max_bytes=max_bytes)
            cpu, ram = self._cpu_delta_observe(history)
            if cpu != _cpu(anchor['metadata']['registers']):
                raise ValueError('CPU changed while capturing CPU delta recovery anchor')
            history['initial_cpu'], history['initial_ram'] = cpu, ram
            # Worst case: isolated changed bytes with JSON keys, two hex bytes,
            # offsets, and a range index each. Include variable identity/range text.
            history['per_step_reservation_bytes'] = (128 * sum(item['length'] for item in normalized)
                + 16384 + len(_encoded(dict(identity=history['identity'], ranges=normalized))))
            history['anchor_elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
            self._cpu_delta_history = history
        result = self.cpu_delta_status()
        self._event('cpu-delta-start', result)
        return result

    def cpu_delta_status(self):
        history = getattr(self, '_cpu_delta_history', None)
        result = dict(format=FORMAT, run=self.run_id, active=history is not None and not self.closed,
            valid=False, unit='next-fetch interval', instruction_completion='unknown',
            scope='selected conventional RAM and exposed real-mode registers',
            full_machine_restored=False, devices_restored=False, unselected_ram='unknown',
            hidden_cpu_state='unknown', disk_restore=False, survives_live_session=False,
            budget_scope='cumulative native anchor plus delta JSON payloads; traces separately retained',
            implementation='net differences; no native write journal or deterministic replay')
        if history is None:
            return dict(result, history=None, cursor=0, available_back=0, retained_steps=0,
                captures_used=0, delta_bytes_used=0, anchor_bytes_used=0, total_bytes_used=0,
                anchor=None, frozen=False, partial_restored=False, resume_safe=not self.closed,
                invalid_reason='not_started')
        result.update(history=history['id'], valid=history['valid'] and not self.closed,
            invalid_reason='session_closed' if self.closed else history['invalid_reason'],
            cursor=history['cursor'], available_back=history['cursor'] if history['valid'] and not self.closed else 0,
            retained_steps=len(history['entries']), captures_used=history['captures_used'],
            frozen=history['frozen'], partial_restored=history['partial_restored'],
            resume_safe=not history['frozen'] and not self.closed)
        for key in ('anchor', 'ranges', 'anchor_bytes_used', 'delta_bytes_used', 'max_steps',
                    'max_bytes', 'per_step_reservation_bytes', 'anchor_elapsed_ms'):
            result[key] = deepcopy(history[key])
        result['total_bytes_used'] = history['anchor_bytes_used'] + history['delta_bytes_used']
        return result

    def _cpu_delta_document(self, history, entry, parent):
        row = self.project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (entry['delta']['artifact'],)).fetchone()
        if row is None or row['kind'] != 'cpu-ram-delta' or row['run'] != self.run_id or row['version'] != self.version['id']:
            raise ValueError('CPU delta artifact must belong to this live run and version')
        data = bytes(row['data'])
        if _sha(data) != row['sha256'] or row['sha256'] != entry['delta']['sha256'] or len(data) != entry['delta']['size']:
            raise ValueError('CPU delta artifact hash/size mismatch')
        document = json.loads(data)
        if (document.get('format') != FORMAT or document.get('identity') != history['identity']
                or document.get('history') != history['id'] or document.get('index') != entry['index']
                or document.get('parent_sha256') != parent or document.get('ranges') != history['ranges']):
            raise ValueError('CPU delta artifact history/parent chain mismatch')
        trace = self.project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (document.get('trace_artifact'),)).fetchone()
        if (trace is None or trace['kind'] != 'trace' or trace['run'] != self.run_id
                or trace['version'] != self.version['id'] or trace['sha256'] != document.get('trace_sha256')
                or _sha(bytes(trace['data'])) != document.get('trace_sha256')):
            raise ValueError('CPU delta trace artifact hash/identity mismatch')
        return document

    def _cpu_delta_states(self, history, target):
        cpu, ram = deepcopy(history['initial_cpu']), list(history['initial_ram'])
        selected = (deepcopy(cpu), list(ram)) if target == 0 else None
        parent = history['anchor']['sha256']
        for entry in history['entries'][:history['cursor']]:
            document = self._cpu_delta_document(history, entry, parent)
            if document['before'] != _fingerprint(cpu, ram) or document['before_pc'] != _pc_of(cpu):
                raise ValueError('CPU delta before-state chain mismatch')
            for name, change in document['registers'].items():
                if name not in REGISTERS or cpu[name] != change['before']:
                    raise ValueError('CPU delta register chain mismatch')
                value = integer(change['after'])
                if value > (0xffff if name in NARROW else 0xffffffff):
                    raise ValueError('CPU delta register width mismatch')
                cpu[name] = value
            for change in document['memory']:
                number, offset = change['range'], change['offset']
                old, new = bytes.fromhex(change['before_hex']), bytes.fromhex(change['after_hex'])
                if (type(number) is not int or not 0 <= number < len(ram) or type(offset) is not int
                        or offset < 0 or not old or len(old) != len(new) or offset + len(old) > len(ram[number])
                        or ram[number][offset:offset + len(old)] != old):
                    raise ValueError('CPU delta RAM chain mismatch')
                ram[number] = ram[number][:offset] + new + ram[number][offset + len(old):]
            if (document['after'] != _fingerprint(cpu, ram) or document['after_pc'] != _pc_of(cpu)):
                raise ValueError('CPU delta after-state chain mismatch')
            if entry['index'] == target:
                selected = deepcopy(cpu), list(ram)
            parent = entry['delta']['sha256']
        return (cpu, ram), selected

    @rpc_budget
    def cpu_delta_record(self, count=1, timeout_ms=10000):
        _bounded(count, 'count', 1, 128)
        history = self._cpu_delta_require()
        if history['frozen']:
            raise ValueError('CPU delta partial state is frozen; recover before recording')
        if history['captures_used'] + count > history['max_steps']:
            raise ValueError('CPU delta capture budget exhausted')
        remaining = history['max_bytes'] - history['anchor_bytes_used'] - history['delta_bytes_used']
        if count * history['per_step_reservation_bytes'] > remaining:
            raise ValueError('CPU delta byte budget cannot reserve requested intervals before execution')
        started = time.monotonic()
        records = []
        with self._cpu_delta_owned():
            try:
                self._cpu_delta_admit()
                expected, _ = self._cpu_delta_states(history, history['cursor'])
                for _ in range(count):
                    before_cpu, before_ram = self._cpu_delta_observe(history)
                    if (before_cpu, before_ram) != expected:
                        raise ValueError('CPU delta selected state changed outside recorded intervals')
                    self._cpu_delta_require()
                    deadline = self._rpc_deadline - time.monotonic()
                    if deadline <= 0:
                        raise TimeoutError('CPU delta recording host-time budget expired before execution')
                    history['captures_used'] += 1
                    trace = self.trace('cpu-delta-fetch.json', count=2,
                        timeout_ms=max(1, int(deadline * 1000)), fast_forward=True)
                    after_pc = self._rewind_trace(trace, _pc_of(before_cpu))
                    after_cpu, after_ram = self._cpu_delta_observe(history)
                    if _pc_of(after_cpu) != after_pc:
                        raise ValueError('CPU delta final PC differs from validated trace')
                    self._cpu_delta_require()
                    parent = history['entries'][history['cursor'] - 1]['delta']['sha256'] if history['cursor'] else history['anchor']['sha256']
                    changes = {name: dict(before=before_cpu[name], after=value) for name, value in after_cpu.items()
                               if value != before_cpu[name]}
                    memory = _runs(before_ram, after_ram)
                    document = dict(format=FORMAT, identity=history['identity'], history=history['id'],
                        index=history['cursor'] + 1, parent_sha256=parent, ranges=history['ranges'],
                        before=_fingerprint(before_cpu, before_ram), after=_fingerprint(after_cpu, after_ram),
                        before_pc=_pc_of(before_cpu), after_pc=after_pc,
                        registers=changes, memory=memory, trace_artifact=trace['artifact'],
                        trace_sha256=trace['sha256'])
                    data = _encoded(document)
                    if len(data) > history['per_step_reservation_bytes']:
                        raise ValueError('CPU delta encoding exceeded its conservative preflight reservation')
                    artifact = self._artifact('cpu-ram-delta.json', 'cpu-ram-delta', data,
                        dict(format=FORMAT, history=history['id'], index=document['index'], parent_sha256=parent,
                             full_machine_restored=False, devices_restored=False))
                    if artifact.get('size') != len(data) or artifact.get('sha256') != _sha(data):
                        raise ValueError('CPU delta artifact receipt mismatch')
                    history['delta_bytes_used'] += len(data)
                    entry = dict(index=document['index'], delta={key: artifact[key] for key in ('artifact', 'sha256', 'size')},
                        trace_artifact=trace['artifact'], before_pc=document['before_pc'], after_pc=after_pc,
                        changed_registers=len(changes), changed_bytes=sum(len(bytes.fromhex(c['after_hex'])) for c in memory))
                    history['entries'] = history['entries'][:history['cursor']] + [entry]
                    history['cursor'] += 1
                    records.append(deepcopy(entry))
                    expected = after_cpu, after_ram
            except BaseException as error:
                self._cpu_delta_invalidate('record failed: ' + type(error).__name__)
                raise
        result = dict(format=FORMAT, run=self.run_id, requested_count=count, recorded_count=len(records),
            cursor=history['cursor'], records=records, history=self.cpu_delta_status(),
            host_elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        self._event('cpu-delta-record', result)
        return result

    def cpu_delta_rewind(self, count=1):
        _bounded(count, 'count', 1, 128)
        history = self._cpu_delta_require()
        if count > history['cursor']:
            raise ValueError('CPU delta rewind count exceeds the available past')
        target = history['cursor'] - count
        started = time.monotonic()
        attempted = False
        with self._cpu_delta_owned():
            try:
                self._cpu_delta_admit()
                expected, selected = self._cpu_delta_states(history, target)
                observed = self._cpu_delta_observe(history)
                if observed != expected:
                    raise ValueError('CPU delta expected-after CPU or selected RAM mismatch')
                self._cpu_delta_require()
                target_cpu, target_ram = selected
                for change in _runs(observed[1], target_ram):
                    attempted = True
                    history['frozen'] = history['partial_restored'] = True
                    address = int(history['ranges'][change['range']]['address'], 16) + self.delta + change['offset']
                    self.call('memory.write', dict(address=dict(space='linear', offset=f'0x{address:08X}'),
                        expected_sha256=_sha(bytes.fromhex(change['before_hex'])),
                        data_base64=base64.b64encode(bytes.fromhex(change['after_hex'])).decode()))
                for name in sorted(REGISTERS):
                    if observed[0][name] != target_cpu[name]:
                        attempted = True
                        history['frozen'] = history['partial_restored'] = True
                        self.call('state.set_register', dict(register=name.upper(), value=target_cpu[name]))
                if self._cpu_delta_observe(history) != selected:
                    raise ValueError('CPU delta complete selected-state readback mismatch')
                self._cpu_delta_require()
                history['cursor'] = target
                history['frozen'] = history['partial_restored'] = True
            except BaseException as error:
                try:
                    self._cpu_delta_invalidate('undo failed: ' + type(error).__name__)
                except BaseException:
                    # Invalidation changes the in-memory safety flags before
                    # logging. A failed receipt must not replace the root error.
                    pass
                finally:
                    if attempted:
                        try:
                            self.close()
                        except BaseException:
                            # Preserve the original uncertain write/readback
                            # failure even if process cleanup also reports one.
                            pass
                raise
        result = dict(format=FORMAT, run=self.run_id, rewound_count=count, cursor=target,
            partial_restored=True, full_machine_restored=False, devices_restored=False, resume_safe=False,
            history=self.cpu_delta_status(), host_elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        self._event('cpu-delta-rewind', result)
        return result

    def cpu_delta_recover(self):
        # Current CPU mode may be unsupported after an unsuccessful forward trace.
        # Recovery validates the trusted anchor, rather than the current CPU mode.
        history = self._cpu_delta_require(valid=False)
        row = self.project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (history['anchor']['artifact'],)).fetchone()
        if (row is None or row['kind'] != 'state' or row['run'] != self.run_id
                or row['version'] != self.version['id'] or row['sha256'] != history['anchor']['sha256']
                or _sha(bytes(row['data'])) != history['anchor']['sha256']):
            self._cpu_delta_invalidate('recovery anchor hash/identity mismatch')
            raise ValueError('CPU delta recovery anchor hash/identity mismatch')
        metadata = json.loads(row['metadata'])
        if metadata.get('disk_manifest') != history['disk_manifest'] or _cpu(metadata.get('registers')) != history['initial_cpu']:
            self._cpu_delta_invalidate('recovery anchor metadata mismatch')
            raise ValueError('CPU delta recovery anchor metadata mismatch')
        with self._cpu_delta_owned():
            restore = self.load_state(history['anchor']['artifact'])
        result = dict(format=FORMAT, run=self.run_id, anchor=deepcopy(history['anchor']), restore=restore,
                      full_native_anchor_loaded=True, history=self.cpu_delta_status())
        self._event('cpu-delta-recover', result)
        return result
