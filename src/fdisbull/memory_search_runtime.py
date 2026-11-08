"""Persistent memory searches and explicitly guarded live edits.

Searches consume immutable private debugger artifacts.  A numeric address is
never an allocation identity: each capture retains its run, byte version,
address domain, declared task and the observed translations of its whole range.
No guest code runs while the host scans a snapshot.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from functools import wraps
import hashlib
import json
import time
import uuid


MAX_BYTES = 16 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _integer(value, label, low=0, high=0xffffffff):
    if isinstance(value, str):
        try:
            value = int(value, 0)
        except ValueError:
            raise ValueError('Invalid ' + label) from None
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def _artifact(project, identifier, kind):
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('A stored artifact identifier is required')
    row = project.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    if row is None or row['kind'] != kind:
        raise ValueError('Unknown ' + kind + ' artifact')
    data = bytes(row['data'])
    if len(data) > (MAX_BYTES if kind == 'memory-snapshot' else MAX_JSON) or _sha(data) != row['sha256']:
        raise ValueError('Stored memory artifact failed its size or hash check')
    return dict(row), data, json.loads(row['metadata'])


def _snapshot(project, identifier):
    from .memory_search import validate_snapshot
    row, data, metadata = _artifact(project, identifier, 'memory-snapshot')
    snapshot = metadata['snapshot']
    validate_snapshot(data, snapshot)
    if snapshot['context']['run_id'] != row['run']:
        raise ValueError('Snapshot run differs from its owning artifact')
    return row, data, metadata


def _search(project, identifier):
    from .memory_search import validate_search
    row, data, _ = _artifact(project, identifier, 'memory-search')
    envelope = json.loads(data)
    if not isinstance(envelope, dict) or envelope.get('format') != 'fdisbull-memory-search-artifact-1':
        raise ValueError('Unknown stored search format')
    snap_row, memory, metadata = _snapshot(project, envelope['snapshot_artifact'])
    if row['run'] != snap_row['run']:
        raise ValueError('Search and snapshot have different owning runs')
    validate_search(envelope['state'], memory, metadata['snapshot'])
    return row, envelope, memory, metadata


def _brief(artifact, **extra):
    # Never return snapshot bytes or an unbounded candidate list by default.
    return {key: value for key, value in artifact.items() if key != 'metadata'} | extra


class MemorySearchProjectMixin:
    """Queries remain usable after closing the live debugger and reopening FDB."""

    def memory_snapshot_info(self, snapshot):
        row, _, metadata = _snapshot(self, snapshot)
        return dict(artifact=snapshot, run=row['run'], sha256=row['sha256'], **metadata)

    def _save_memory_search(self, run, envelope):
        raw = _json(envelope)
        if len(raw) > MAX_JSON:
            raise ValueError('Stored search exceeds its JSON budget')
        artifact = self._debug_artifact(run, 'memory-search.json', 'memory-search', raw,
                                       dict(format=envelope['format'], snapshot_artifact=envelope['snapshot_artifact']))
        from .memory_search import search_results
        _, memory, metadata = _snapshot(self, envelope['snapshot_artifact'])
        preview = search_results(envelope['state'], memory, metadata['snapshot'], limit=16)
        return _brief(artifact, snapshot_artifact=envelope['snapshot_artifact'], results=preview)

    def memory_search_start(self, snapshot, **options):
        from .memory_search import start_search
        row, data, metadata = _snapshot(self, snapshot)
        state = start_search(data, metadata['snapshot'], **options)
        envelope = dict(format='fdisbull-memory-search-artifact-1', snapshot_artifact=snapshot,
                        previous_snapshot_artifact=None, parent_search_artifact=None, state=state)
        return self._save_memory_search(row['run'], envelope)

    def memory_search_refine(self, search, snapshot, **options):
        from .memory_search import refine_search
        row, old, before, before_metadata = _search(self, search)
        after_row, after, after_metadata = _snapshot(self, snapshot)
        if after_row['run'] != row['run']:
            raise ValueError('Cannot refine across different capture runs')
        state = refine_search(old['state'], before, before_metadata['snapshot'], after,
                              after_metadata['snapshot'], **options)
        envelope = dict(format=old['format'], snapshot_artifact=snapshot,
                        previous_snapshot_artifact=old['snapshot_artifact'], parent_search_artifact=search, state=state)
        return self._save_memory_search(row['run'], envelope)

    def memory_search_results(self, search, *, offset=0, limit=64):
        from .memory_search import search_results
        _, envelope, data, metadata = _search(self, search)
        previous = envelope['previous_snapshot_artifact']
        options = {}
        if previous is not None:
            _, before, before_metadata = _snapshot(self, previous)
            options = dict(before_data=before, before_snapshot=before_metadata['snapshot'])
        return dict(search_artifact=search, snapshot_artifact=envelope['snapshot_artifact'],
                    **search_results(envelope['state'], data, metadata['snapshot'], offset=offset, limit=limit, **options))

    def memory_edit_plan(self, search, *, offset, value, condition='equal', compare_value=None):
        from .memory_search import plan_edit
        row, envelope, data, metadata = _search(self, search)
        plan = plan_edit(envelope['state'], data, metadata['snapshot'], offset=offset, value=value,
                         condition=condition, compare_value=compare_value)
        stored = dict(format='fdisbull-memory-edit-artifact-1', search_artifact=search,
                      snapshot_artifact=envelope['snapshot_artifact'], plan=plan)
        artifact = self._debug_artifact(row['run'], 'memory-edit.json', 'memory-edit', _json(stored),
                                       dict(format=stored['format']))
        return _brief(artifact, plan=plan, applied=False)


def _locked(function):
    @wraps(function)
    def operation(self, *args, **kwargs):
        if hasattr(self, 'vm'):
            # These mixins also call QMP/GDB directly while holding the machine
            # lock. Use the same transport-failure cleanup as ordinary machine
            # controls, including the owning process's close observer. Import
            # lazily because MachineContext itself inherits these mixins.
            from .qemu_machine import machine_operation
            return machine_operation(function)(self, *args, **kwargs)
        from .debug_timeline import FrameTimelineSessionMixin
        gate = FrameTimelineSessionMixin._timeline_gate(self)
        with gate:
            return function(self, *args, **kwargs)
    return operation


def _paused(session):
    """Return observed address state while requiring one owned stopped CPU."""
    if hasattr(session, 'vm'):
        session._stopped()
        registers = session.registers()
        state = deepcopy(registers['address_state'])
        if state.get('machine_vcpus') != 1:
            raise ValueError('Memory search requires an observed single-vCPU machine')
        return dict(registers=registers, address_state=state, stop=session.vm.qmp.call('query-status'))
    from .runtime_observations import _paused as dos_paused
    backend = getattr(session, 'backend_name', None) or getattr(session, 'metadata', {}).get('backend')
    if backend not in (None, 'dosbox', 'dosbox-x', 'dosbox-qemu'):
        raise ValueError('Live memory search currently requires DOSBox or the full-machine DOS backend')
    stop = dos_paused(session)
    context = stop.get('observation_address_context')
    mode = stop['observation_cpu_mode']
    if not isinstance(context, dict):
        raise ValueError('Memory snapshots require observed CPU/address context; rebuild the backend')
    state = dict(cpu_mode=mode, a20=context.get('a20_enabled'), machine_vcpus=1,
                 register_context_match=True, control={name.upper(): context.get(name) for name in ('cr0','cr3','cr4')})
    return dict(address_state=state, stop=stop)


def _read(session, address, length, space):
    chunks = []
    for offset in range(0, length, 65536):
        count = min(65536, length - offset)
        if hasattr(session, 'vm'):
            value = session._stopped().memory(address + offset, count, space='virtual' if space == 'linear' else space)
        else:
            result = session.call('memory.read', dict(address=dict(space=space, offset=f'0x{address + offset:08X}'), length=count))
            value = base64.b64decode(result['data_base64'], validate=True)
        if not isinstance(value, bytes) or len(value) != count:
            raise ValueError('Incomplete memory snapshot read')
        chunks.append(value)
    return b''.join(chunks)


def _mapping(session, address, length, space, observed):
    if space == 'physical':
        return dict(kind='physical-addresses', allocation_identity='unqualified'), []
    from .dos_memory import translate_386_page
    state = observed['address_state']
    pages = []
    cache = {}

    def physical(location, count):
        # Cache each page-table page only within this one paused observation.
        # The after-capture observation gets a new cache, detecting even a
        # remap that reuses CR3 and changes only an individual PTE.
        base = location & ~4095
        if base not in cache:
            cache[base] = _read(session, base, 4096, 'physical')
        return cache[base][location - base:location - base + count]

    start = address & ~4095
    for location in range(start, address + length, 4096):
        result = translate_386_page(location, state, physical)
        if result['status'] != 'mapped':
            raise ValueError('Memory snapshot has an unqualified mapping: ' + result.get('reason', result['status']))
        entries = []
        for item in result['entries']:
            raw = int(item['value'], 16)
            # Accessed/dirty bits are activity, not a different physical map.
            raw &= ~(0x60 if item['kind'] == 'table' else 0x20)
            entries.append(dict(kind=item['kind'], address=item['physical_address'], value=hex(raw)))
        pages.append(dict(linear=hex(location), physical=result['physical_address'], entries=entries))
    controls = {name: value for name, value in state['control'].items() if name in ('CR0', 'CR3', 'CR4', 'EFER')}
    identity = dict(kind='observed-386-pages', cpu_mode=state['cpu_mode'], a20=state.get('a20'),
                    control=controls, pages_sha256=_sha(_json(pages)), page_count=len(pages),
                    allocation_identity='unqualified')
    return identity, pages


def _context(session, address, length, space, task_id, observed, mapping):
    if space not in ('linear', 'physical'):
        raise ValueError('Memory snapshot space must be linear or physical')
    if task_id is None and space == 'physical':
        task_id = 'physical-machine'
        task_evidence = 'physical address identity; not an application allocation'
    else:
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 128 or any(ord(ch) < 32 for ch in task_id):
            raise ValueError('Linear snapshots require an explicit task_id (caller-declared task lifetime)')
        task_evidence = 'caller-declared task lifetime; not inferred from an address or CR3'
    if hasattr(session, '_runtime_state'):
        session._runtime_state()
    epoch = getattr(session, '_runtime_epoch', session.run_id)
    return dict(source_sha256=session.metadata['source_sha256'], version_id=session.version['id'],
                version_sha256=session.metadata['version_sha256'], run_id=session.run_id,
                address_space=space, region=dict(start=address, length=length), task_id=task_id,
                task_evidence=task_evidence, mapping_id=_sha(_json(mapping)), capture_epoch=epoch)


def _capture(session, address, length, space, task_id):
    address = _integer(address, 'snapshot address')
    length = _integer(length, 'snapshot length', 1, MAX_BYTES)
    if address + length > 0x100000000 or space not in ('linear','physical'):
        raise ValueError('Snapshot exceeds its 32-bit address domain')
    before = _paused(session)
    mapping, pages = _mapping(session, address, length, space, before)
    context = _context(session, address, length, space, task_id, before, mapping)
    data = _read(session, address, length, space)
    after = _paused(session)
    after_mapping, _ = _mapping(session, address, length, space, after)
    if context != _context(session, address, length, space, task_id, after, after_mapping):
        raise ValueError('Memory task, epoch or mapping changed during capture')
    # A physical range remains the same domain across modes, but the actual
    # capture must still be made at one stop, not across guest execution.
    if before != after:
        raise ValueError('Stopped CPU context changed during memory capture')
    return data, context, dict(before=before, mapping=mapping, pages=pages,
                               atomicity='owned paused CPU; no guest execution during capture',
                               task_lifetime='caller-declared; allocation/free events are not inferred')


class MemorySearchSessionMixin:
    @_locked
    def memory_snapshot(self, address, *, length, space='linear', task_id=None, name='memory-snapshot.bin'):
        from .memory_search import snapshot_metadata
        from .debugger import stamp
        data, context, evidence = _capture(self, address, length, space, task_id)
        snapshot = snapshot_metadata(data, context=context, capture_id=uuid.uuid4().hex, captured_at=stamp())
        artifact = self._artifact(name, 'memory-snapshot', data, dict(snapshot=snapshot, capture=evidence))
        return _brief(artifact, snapshot=snapshot, capture=evidence)

    @_locked
    def memory_apply(self, plan):
        """Apply one owned plan once, with fresh whole-region mapping and bytes."""
        row, data, _ = _artifact(self.project, plan, 'memory-edit')
        envelope = json.loads(data)
        if envelope.get('format') != 'fdisbull-memory-edit-artifact-1' or row['run'] != self.run_id:
            raise ValueError('Memory edit belongs to a different capture run')
        planned = envelope['plan']
        if planned.get('eligible') is not True:
            return dict(plan_artifact=plan, applied=False, reason='condition_not_satisfied')
        if not hasattr(self, '_applied_memory_plans'):
            self._applied_memory_plans = set()
        if plan in self._applied_memory_plans:
            raise ValueError('This memory plan was already dispatched; create a fresh plan')
        _, search, saved, metadata = _search(self.project, envelope['search_artifact'])
        if search['snapshot_artifact'] != envelope['snapshot_artifact']:
            raise ValueError('Edit and search snapshot references differ')
        from .memory_search import plan_edit
        reproduced = plan_edit(search['state'], saved, metadata['snapshot'], offset=planned['offset'],
                               value=planned['requested_displayed_value'], condition=planned['condition']['mode'],
                               compare_value=planned['condition']['compare_value'])
        if reproduced != planned:
            raise ValueError('Stored edit plan differs from its owning search and snapshot')
        expected_context = metadata['snapshot']['context']
        region = expected_context['region']
        current, context, _ = _capture(self, region['start'], region['length'], expected_context['address_space'],
                                       None if expected_context['task_evidence'].startswith('physical address') else expected_context['task_id'])
        if context != expected_context or planned['context'] != context:
            raise ValueError('Memory edit context changed; write refused')
        offset = _integer(planned['offset'], 'edit offset', 0, len(current) - 1)
        replacement = bytes.fromhex(planned['replacement_hex'])
        expected = bytes.fromhex(planned['expected_hex'])
        if not replacement or len(replacement) != len(expected) or offset + len(expected) > len(current):
            raise ValueError('Invalid stored memory edit extent')
        if saved[offset:offset + len(expected)] != expected or current[offset:offset + len(expected)] != expected:
            raise ValueError('Memory edit expected bytes changed; write refused')
        layers = getattr(self, '_layer_state', None)
        if callable(layers) and layers().get('active'):
            raise ValueError('Disable code layers before a live memory search edit')
        receipt = dict(plan_artifact=plan, run=self.run_id, address=hex(region['start'] + offset),
                       space=context['address_space'], expected_hex=expected.hex(), replacement_hex=replacement.hex(),
                       applied=False, verified=False, dispatch_outcome='unknown', assisted=True)
        self._event('memory-search-write-attempt', receipt)
        self._applied_memory_plans.add(plan)
        phase = 'dispatch'
        try:
            address = region['start'] + offset
            if hasattr(self, 'vm'):
                self.write_memory(address, replacement.hex(), expected_hex=expected.hex(),
                                  space='virtual' if context['address_space'] == 'linear' else 'physical')
            else:
                self.call('memory.write', dict(address=dict(space=context['address_space'], offset=f'0x{address:08X}'),
                    expected_sha256=_sha(expected), data_base64=base64.b64encode(replacement).decode()))
            phase = 'readback'
            observed = _read(self, address, len(replacement), context['address_space'])
            stopped = _paused(self)
            mapping, _ = _mapping(self, region['start'], region['length'], context['address_space'], stopped)
            after_context = _context(self, region['start'], region['length'], context['address_space'],
                                    None if context['task_evidence'].startswith('physical address') else context['task_id'], stopped, mapping)
            if observed != replacement or after_context != context:
                raise ValueError('Memory edit readback or mapping changed after dispatch')
            receipt.update(applied=True, verified=True, dispatch_outcome='readback-verified', after_hex=observed.hex())
            phase = 'completion-journal'
            self._event('memory-search-write', receipt)
        except BaseException as error:
            receipt.update(failure_phase=phase, error_type=type(error).__name__, error=str(error))
            try:
                self._event('memory-search-write-failed', receipt)
            except BaseException as event_error:
                receipt['failure_event_error'] = str(event_error)
            finally:
                try:
                    self.close()
                except BaseException as close_error:
                    receipt['close_error'] = str(close_error)
            from .runtime_observations import RuntimeMemoryWriteError
            raise RuntimeMemoryWriteError(receipt, error) from error
        return receipt
