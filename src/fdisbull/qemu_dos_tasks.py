"""Observed architectural contexts and cooperating DOS monitor task lifetimes.

Architectural registers alone cannot identify a software-scheduled task. The
optional FDBTASK1 anchor is an explicit cooperating-monitor protocol, not a
decoder for undocumented QEMM or DESQview scheduler structures.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import struct

from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked

COMMAND = 'x-fdisbull-query-task-context'
MODEL = 'qemu-i386-architectural-task-context-v1'
FORMAT = 'fdisbull-dos-monitor-task-1'
_CONTEXT_FIELDS = ('mode', 'cpl', 'eip', 'esp', 'cs-selector', 'ss-selector',
    'cr0', 'cr3', 'cr4', 'efer', 'gdt-base', 'gdt-limit', 'idt-base', 'idt-limit',
    'tr-selector', 'tr-base', 'tr-limit', 'tr-flags',
    'ldtr-selector', 'ldtr-base', 'ldtr-limit', 'ldtr-flags')


def _number(value):
    if isinstance(value, str):
        try:
            value = int(value, 0)
        except ValueError:
            raise ValueError('Invalid physical task anchor address') from None
    if type(value) is not int or not 0 <= value <= 0xffffffff - 55:
        raise ValueError('Physical task anchor must fit a 32-bit RAM address')
    return value


def task_key(binding):
    if not isinstance(binding, dict) or binding.get('format') != FORMAT:
        raise ValueError('Invalid DOS monitor task binding')
    try:
        key = (binding['anchor_address'], binding['monitor_uuid'], binding['cookie'],
               binding['incarnation'], binding['process_nonce'])
    except KeyError as error:
        raise ValueError('Incomplete DOS monitor task binding') from error
    if (type(key[0]) is not int or _number(key[0]) != key[0]
            or not isinstance(key[1], str) or not re.fullmatch('[0-9a-f]{32}', key[1])
            or any(type(x) is not int or not 0 < x < 1 << 64 for x in key[2:4])
            or not isinstance(key[4], str) or not re.fullmatch('[0-9a-f]{32}', key[4])):
        raise ValueError('Invalid DOS monitor task lifetime')
    expected_id = 'dos-task-' + hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).hexdigest()
    if 'task_id' in binding and binding['task_id'] != expected_id:
        raise ValueError('DOS monitor task identifier differs from its lifetime key')
    return key


def _identifier(binding):
    return 'dos-task-' + hashlib.sha256(json.dumps(task_key(binding), separators=(',', ':')).encode()).hexdigest()


def read_task_context(vm, binding=None):
    if COMMAND not in vm.qmp_commands:
        if binding is not None:
            raise ValueError('DOS monitor tasks require the native task-context extension')
        return None
    arguments = None
    if binding is not None:
        task_key(binding)
        address = binding['anchor_address']
        ram_end = min(vm.machine_configuration['memory_mib'] << 20, 0xc0000000)
        if not (0 <= address < address + 56 <= 0xa0000
                or 0x100000 <= address < address + 56 <= ram_end):
            raise ValueError('Task anchor must reside in conventional or extended PC RAM')
        arguments = {'anchor-address': binding['anchor_address']}
    raw = vm.qmp.call(COMMAND, arguments)
    if (not isinstance(raw, dict) or raw.get('api-version') != 1 or type(raw.get('api-version')) is not int
            or raw.get('model') != MODEL or raw.get('cpu-index') != 0
            or raw.get('mode') not in ('real', 'protected', 'v86')
            or any(type(raw.get(k)) is not int or not 0 < raw[k] < 1 << 64
                   for k in ('epoch', 'context-generation'))
            or any(type(raw.get(k)) is not int or not 0 <= raw[k] < 1 << 64
                   for k in _CONTEXT_FIELDS if k != 'mode')):
        raise DebuggerError('Invalid native architectural task-context receipt')
    if binding is not None:
        if raw.get('anchor-address') != binding['anchor_address'] or not isinstance(raw.get('anchor-hex'), str):
            raise DebuggerError('Native task anchor differs from its physical binding')
        try:
            anchor = bytes.fromhex(raw['anchor-hex'])
        except ValueError:
            raise DebuggerError('Invalid native task-anchor encoding') from None
        if len(anchor) != 56 or anchor[:8] != b'FDBTASK1':
            raise ValueError('Unsupported cooperating DOS monitor task anchor')
        sequence, cookie, incarnation, state, reserved = struct.unpack_from('<QQQII', anchor, 24)
        if sequence & 1 or not cookie or not incarnation or state != 1 or reserved:
            raise ValueError('DOS monitor task transition or lifetime is not active and stable')
        if anchor[8:24].hex() != binding['monitor_uuid']:
            raise ValueError('DOS monitor instance changed')
    return deepcopy(raw)


def stable_context(raw):
    return {key: raw[key] for key in _CONTEXT_FIELDS}


def validate_register_context(raw, registers):
    if raw is None:
        return
    state = registers['address_state']
    if raw['mode'] != registers['cpu_mode'] or state.get('machine_vcpus') != 1:
        raise ValueError('Native task observation differs from selected CPU mode')
    for native, observed in (('cr0', 'CR0'), ('cr3', 'CR3'), ('cr4', 'CR4'), ('efer', 'EFER')):
        value = state.get('control', {}).get(observed)
        if value is None or (int(value, 16) if isinstance(value, str) else value) != raw[native]:
            raise ValueError('Native task control register differs: ' + observed)


def observe_task(session, binding=None, vm=None):
    vm = session.vm if vm is None else vm
    binding = getattr(session, '_dos_task_binding', None) if binding is None else binding
    first = read_task_context(vm, binding)
    if first is None:
        raise ValueError('Native DOS task-context observation is unavailable')
    if read_task_context(vm, binding) != first:
        raise DebuggerError('Native task context changed during stopped observation')
    result = dict(format=FORMAT, run=session.run_id,
        capture_epoch=session._layer_epoch(), native_epoch=first['epoch'],
        context_generation=first['context-generation'], context=stable_context(first),
        task_id=None, matches_binding=None, task_identity=None,
        scope='architectural context only; software task identity unknown')
    if binding is not None:
        anchor = bytes.fromhex(first['anchor-hex'])
        sequence, cookie, incarnation, _, _ = struct.unpack_from('<QQQII', anchor, 24)
        current = dict(format=FORMAT, anchor_address=binding['anchor_address'],
            monitor_uuid=anchor[8:24].hex(), cookie=cookie, incarnation=incarnation,
            process_nonce=binding['process_nonce'])
        current['task_id'] = _identifier(current)
        result.update(current, scheduler_generation=sequence,
            matches_binding=task_key(current) == task_key(binding),
            task_identity=deepcopy(current), scope='cooperating monitor task lifetime')
        previous = getattr(vm, '_dos_task_frontier', None)
        if previous is not None:
            if (previous['native_epoch'] != result['native_epoch']
                    or result['context_generation'] < previous['context_generation']
                    or sequence < previous['scheduler_generation']):
                raise DebuggerError('Native task epoch changed or task observation regressed')
            if sequence == previous['scheduler_generation'] and task_key(current) != task_key(previous):
                raise DebuggerError('Task lifetime changed without a scheduler generation transition')
        vm._dos_task_frontier = deepcopy(result)
    return result


def require_task(session, binding=None):
    binding = getattr(session, '_dos_task_binding', None) if binding is None else binding
    if binding is None:
        return None
    observed = observe_task(session, binding)
    if observed['matches_binding'] is not True:
        raise ValueError('Selected native DOS task differs from the bound task lifetime')
    if getattr(session, '_dos_task_monitor', None):
        from .qemu_dos_task_views import _observe, _row
        _observe(session, _row(session, binding['task_id']))
    return observed


def capture_task_checkpoint(session):
    binding = getattr(session, '_dos_task_binding', None)
    first = read_task_context(session.vm, binding)
    if first is not None:
        validate_register_context(first, session.registers())
        if read_task_context(session.vm, binding) != first:
            raise DebuggerError('Native task changed during checkpoint capture')
    return first


def restore_task_checkpoint(vm, saved, binding):
    if saved is None:
        if binding is not None:
            raise ValueError('Task-bound checkpoint lacks native context state')
        return None
    current = read_task_context(vm, binding)
    if (current is None or stable_context(current) != stable_context(saved)
            or current.get('anchor-address') != saved.get('anchor-address')
            or current.get('anchor-hex') != saved.get('anchor-hex')
            or current['epoch'] <= saved['epoch']
            or current['context-generation'] <= saved['context-generation']):
        raise DebuggerError('Restored native task context, anchor or epoch differs from checkpoint')
    return dict(source_epoch=saved['epoch'], native_epoch=current['epoch'],
                source_generation=saved['context-generation'],
                context_generation=current['context-generation'])


class QemuDOSTaskMixin:
    @_locked
    def dos_task_observe(self):
        if self.project.db.in_transaction:
            raise ValueError('DOS task observation requires a project outside a transaction')
        self._stopped()
        try:
            result = observe_task(self)
            self._event('dos-task-observe', result)
            return result
        except DebuggerError:
            self.close()
            raise

    @_locked
    def dos_task_bind(self, *, anchor_address, expected_monitor):
        from .qemu_dos_checkpoint import _origin, _verify_process
        if self.project.db.in_transaction:
            raise ValueError('DOS task binding requires a project outside a transaction')
        if not isinstance(expected_monitor, str) or not re.fullmatch('[0-9a-fA-F]{32}', expected_monitor):
            raise ValueError('expected_monitor must be the 32-hex cooperating monitor UUID')
        self._stopped()
        candidate = dict(format=FORMAT, anchor_address=_number(anchor_address),
            monitor_uuid=expected_monitor.lower(), cookie=1, incarnation=1,
            process_nonce=self._nonce.hex())
        observed = observe_task(self, candidate)
        candidate = observed['task_identity']
        previous = getattr(self, '_dos_task_binding', None)
        if previous is None and (getattr(self, '_layer_active', []) or getattr(self, '_qemu_hooks', {})):
            raise ValueError('Bind the native task before activating task-owned layers or hooks')
        if previous is not None and task_key(previous) != task_key(candidate):
            if getattr(self, '_layer_active', []) or getattr(self, '_qemu_hooks', {}):
                row = getattr(self, '_dos_task_views', {}).get(candidate['task_id'])
                if (getattr(self, '_layer_active', []) or row is None or row['retired']
                        or task_key(row['binding']) != task_key(candidate)):
                    raise ValueError('Clear task-owned layers and hooks before rebinding a different task')
        _verify_process(self, self._process, _origin(self), task_binding=candidate)
        self._dos_task_binding = deepcopy(candidate)
        self.metadata['dos_task_binding'] = deepcopy(candidate)
        self._persist_process()
        self._event('dos-task-bind', dict(binding=deepcopy(candidate), observation=observed))
        return deepcopy(candidate)
