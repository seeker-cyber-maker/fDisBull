"""Admission and typed receipts for native PIC interrupt preemption.

The native engine observes real PIC acknowledgements and matching guest EOIs.
Python configures policy and validates stopped evidence; it never schedules an
IRQ, acknowledges a device, or chooses the next task.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked

MODEL = 'qemu-pc-pic-preemption-v1'
COMMAND = 'x-fdisbull-task-preemption-configure'
FORMAT = 'fdisbull-native-dos-scheduler-2'
CONTROLS_FORMAT = 'fdisbull-qemu-controls-task-5'
COUNTERS = ('ack-count', 'eoi-count', 'preemption-count')


def _uint(value, limit=1 << 64):
    return type(value) is int and 0 <= value < limit


def _task_key(raw, prefix):
    uuid = raw.get(prefix+'uuid')
    if (not isinstance(uuid,str) or not re.fullmatch('[0-9a-f]{32}',uuid)
            or not _uint(raw.get(prefix+'cookie')) or raw[prefix+'cookie'] == 0
            or not _uint(raw.get(prefix+'incarnation')) or raw[prefix+'incarnation'] == 0):
        raise DebuggerError('Invalid native preemption task lifetime')
    return uuid,raw[prefix+'cookie'],raw[prefix+'incarnation']


def validate_preemption(raw):
    if (not isinstance(raw,dict) or raw.get('model') != MODEL
            or any(type(raw.get(key)) is not bool for key in
                   ('enabled','pending','inflight','last-valid'))
            or not _uint(raw.get('irq'),8) or raw['irq'] == 2
            or type(raw.get('quantum')) is not int or not 1 <= raw['quantum'] <= 65535
            or not _uint(raw.get('quantum-progress'),raw['quantum'])
            or any(not _uint(raw.get(key)) for key in COUNTERS)
            or not raw['preemption-count'] <= raw['eoi-count'] <= raw['ack-count']
            or any(not _uint(raw.get(key),256) for key in
                   ('pic-mask','pic-irr','pic-isr','pic-irq-base','last-vector','inflight-vector'))
            or raw['pic-irq-base'] & 7
            or any(not _uint(raw.get(key),8) for key in ('last-irq','inflight-irq'))
            or any(not _uint(raw.get(key)) for key in ('inflight-sequence','inflight-frame-sequence'))
            or any(not isinstance(raw.get(prefix+'uuid'),str)
                   or any(not _uint(raw.get(prefix+name)) for name in ('cookie','incarnation'))
                   for prefix in ('last-from-','last-to-','inflight-'))):
        raise DebuggerError('Invalid native PIC preemption receipt')
    if raw['inflight']:
        _task_key(raw,'inflight-')
        if (not raw['enabled'] or raw['pending'] or not raw['inflight-sequence']
                or not raw['inflight-frame-sequence']
                or raw['inflight-irq'] != raw['irq']
                or raw['inflight-vector'] != raw['pic-irq-base']+raw['irq']
                or not raw['pic-isr'] & (1 << raw['irq'])
                or raw['ack-count'] != raw['eoi-count']+1):
            raise DebuggerError('Native in-flight IRQ differs from its PIC owner')
    elif raw['ack-count'] != raw['eoi-count']:
        raise DebuggerError('Native PIC acknowledgement lacks its in-flight owner')
    if raw['pending'] and not raw['enabled']:
        raise DebuggerError('Disabled native preemption has a pending switch')
    if raw['last-valid']:
        _task_key(raw,'last-from-'); _task_key(raw,'last-to-')
    return raw


def policy(raw):
    return {key:raw[key] for key in ('enabled','irq','quantum')}


def validate_irq_frame(frame, *, required=False):
    if 'pic-irq-valid' not in frame and not required:
        return
    if (type(frame.get('pic-irq-valid')) is not bool
            or not _uint(frame.get('pic-controller'),2)
            or not _uint(frame.get('pic-irq'),8)
            or not _uint(frame.get('pic-vector'),256)
            or not _uint(frame.get('pic-ack-sequence'))
            or type(frame.get('pic-eoi-seen')) is not bool):
        raise DebuggerError('Invalid native PIC interrupt-frame receipt')
    if frame['pic-irq-valid']:
        if (frame['pic-controller'] != 0 or frame['pic-irq'] == 2
                or frame.get('vector') != frame['pic-vector']
                or frame.get('kind') != 'hardware' or not frame['pic-ack-sequence']):
            raise DebuggerError('Native PIC frame differs from its hardware interrupt')
    elif any(frame[key] for key in ('pic-controller','pic-irq','pic-vector',
                                    'pic-ack-sequence','pic-eoi-seen')):
        raise DebuggerError('Native PIC metadata has no owned hardware frame')


def validate_checkpoint_preemption(native, contexts):
    """Bind a global in-service IRQ to its unique saved task hardware frame."""
    if native['api-version'] == 1:
        if any(frame.get('pic-irq-valid') for context in contexts.values()
               for frame in context.get('frames',[])):
            raise ValueError('Legacy checkpoint cannot carry native IRQ preemption frames')
        return
    raw = validate_preemption(native['preemption'])
    outstanding = []
    for context in contexts.values():
        for frame in context.get('frames',[]):
            validate_irq_frame(frame,required=True)
            if not frame.get('pic-irq-valid'):
                continue
            if not frame['pic-eoi-seen']:
                outstanding.append((context,frame))
    if not raw['inflight']:
        if outstanding:
            raise ValueError('Native IRQ frame lacks its in-flight PIC owner')
        return
    if len(outstanding) != 1:
        raise ValueError('Native in-flight PIC ownership has no unique interrupt frame')
    context,frame = outstanding[0]
    owner = _task_key(raw,'inflight-')
    selected = (native.get('selected-uuid'),native.get('selected-cookie'),native.get('selected-incarnation'))
    if ((context.get('uuid'),context.get('cookie'),context.get('incarnation')) != owner
            or selected != owner or frame.get('sequence') != raw['inflight-frame-sequence']
            or frame['pic-ack-sequence'] != raw['inflight-sequence']
            or frame['pic-irq'] != raw['inflight-irq']
            or frame['pic-vector'] != raw['inflight-vector']):
        raise ValueError('Native in-flight IRQ differs from its saved task/frame owner')


class QemuDOSPreemptionMixin:
    @_locked
    def dos_task_preemption(self, *, enabled=True, irq=0, quantum=1):
        from .qemu_dos_scheduler import _mutate, _status, _validate_native_status
        from .qemu_dos_task_views import _preflight
        _preflight(self)
        if (type(enabled) is not bool or type(irq) is not int or not 0 <= irq < 8 or irq == 2
                or type(quantum) is not int or not 1 <= quantum <= 65535):
            raise ValueError('Preemption requires a boolean enable, direct master PIC IRQ and quantum 1..65535')
        if COMMAND not in self.vm.qmp_commands:
            raise ValueError('Native timer/IRQ preemption extension is unavailable')
        before = _status(self,adopt=True)
        if not before['enabled'] or before['api-version'] != 2:
            raise ValueError('Enable the native CPU scheduler before configuring IRQ preemption')
        if before['preemption']['inflight'] or before['preemption']['pending']:
            raise ValueError('Finish the in-flight IRQ or pending preemption before changing policy')
        raw = _mutate(self,COMMAND,dict(enabled=enabled,irq=irq,quantum=quantum))
        try:
            _validate_native_status(raw)
            expected = dict(enabled=enabled,irq=irq,quantum=quantum)
            if raw['api-version'] != 2 or policy(raw['preemption']) != expected:
                raise DebuggerError('Native IRQ preemption differs from requested policy')
            if (raw['epoch'] != before['epoch'] or raw['tasks'] != before['tasks']
                    or any(raw.get('selected-'+key) != before.get('selected-'+key)
                           for key in ('uuid','cookie','incarnation'))
                    or any(raw['preemption'][key] != before['preemption'][key] for key in COUNTERS)):
                raise DebuggerError('Native IRQ configuration changed its CPU owner or event counters')
            progress = (before['preemption']['quantum-progress']
                        if policy(before['preemption']) == expected else 0)
            if raw['preemption']['quantum-progress'] != progress:
                raise DebuggerError('Native IRQ configuration changed its quantum phase unexpectedly')
            self._dos_scheduler['preemption'] = expected
            proof = _status(self,adopt=True)
            self.metadata['native_preemption'] = dict(model=MODEL,**expected)
            self._event('dos-native-preemption-configure',dict(policy=expected,native=proof))
            return dict(preemption=deepcopy(proof['preemption']),native=proof)
        except BaseException:
            self.close()
            raise
