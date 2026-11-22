"""Captured resource ownership across the two public frame-input entries."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_frame_key_batch import PLAN_COMMAND, APPLY_COMMAND, BATCH_COMMANDS
from test_qemu_dos_history import project, session
from test_qemu_dos_frames import frames, start
from test_qemu_frame_keys import keys
from test_qemu_frame_key_batch import batch_keys, _invoke


class Sentinel:
    def __init__(self, **fields):
        self.__dict__.update(fields)
        self.__dict__['writes'] = []
        self.__dict__['closes'] = 0
    def __setattr__(self, name, value):
        self.writes.append(name)
        self.__dict__[name] = value
    def close(self): self.__dict__['closes'] += 1


def _replacement():
    return Sentinel(operation_deadline='replacement-deadline',
        qmp=Sentinel(operation_deadline='replacement-qmp'),
        gdb=Sentinel(operation_deadline='replacement-gdb'))


def _assert_untouched(replacement):
    for resource in (replacement, replacement.qmp, replacement.gdb):
        assert resource.writes == [] and resource.closes == 0


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('capability', ['batch', 'legacy'])
@pytest.mark.parametrize('boundary', ['operation-guard', 'history-guard', 'query',
                                    'intent', 'apply', 'accepted', 'persistence'])
def test_replacement_never_receives_cleanup_or_deadline_writes(batch_keys, entry, capability, boundary):
    start(batch_keys)
    if capability == 'legacy': batch_keys.vm.qmp_commands -= BATCH_COMMANDS
    original = batch_keys.vm
    original.process = SimpleNamespace(poll=lambda: 0)
    qmp = original.qmp
    original.operation_deadline = qmp.operation_deadline = None
    replacement = _replacement()
    def replace(): batch_keys.vm = replacement
    if boundary in ('operation-guard', 'history-guard'):
        name = 'operation_guard' if boundary == 'operation-guard' else 'history_operation_guard'
        setattr(original, name, lambda *args: replace())
    elif boundary in ('query', 'apply'):
        previous = original.qmp.call
        target = ('x-fdisbull-query-frame-keys' if boundary == 'query' else
                  APPLY_COMMAND if capability == 'batch' else 'x-fdisbull-apply-frame-key-edges')
        def changed(name, arguments=None, **kwargs):
            result = previous(name, arguments, **kwargs)
            if name == target: replace()
            return result
        original.qmp.call = changed
    elif boundary in ('intent', 'accepted'):
        previous = batch_keys._event
        target = 'frame-inputs-intent' if boundary == 'intent' else 'frame-inputs'
        def event(name, receipt):
            previous(name, receipt)
            if name == target: replace()
        batch_keys._event = event
    else:
        previous = batch_keys._history_new_revision
        def persist(manifest, **kwargs):
            result = previous(manifest, **kwargs)
            if batch_keys.key_state['active'] and kwargs.get('pending') is None: replace()
            return result
        batch_keys._history_new_revision = persist
    with pytest.raises(DebuggerError, match='owner|channels') as caught:
        _invoke(batch_keys, entry, [dict(key='a', pressed=True)])
    _assert_untouched(replacement)
    assert batch_keys.vm is replacement and not batch_keys.closed
    assert qmp.operation_deadline is None and original.operation_deadline is None
    assert caught.value.frame_input_owner['owner_changed']
    assert original._fdisbull_control_quarantine == 'failed frame input original owner'
    assert original.lock.acquire(blocking=False)
    original.lock.release()
    if boundary in ('apply', 'accepted', 'persistence'):
        assert caught.value.frame_input_owner['accepted_evidence'] is not None


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
def test_plan_callback_replacement_is_caught_before_intent(batch_keys, entry):
    start(batch_keys)
    replacement = _replacement()
    def changed(raw):
        batch_keys.vm = replacement
        return raw
    batch_keys.batch_peer.transform_plan = changed
    with pytest.raises(DebuggerError): _invoke(batch_keys, entry)
    _assert_untouched(replacement)
    assert not batch_keys.events and not batch_keys.key_state['active']
    assert all(name != APPLY_COMMAND for name, _ in batch_keys.batch_peer.calls)


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('capability', ['batch', 'legacy'])
def test_late_acceptance_preserves_evidence_and_original_deadlines(batch_keys, entry, capability, monkeypatch):
    start(batch_keys)
    if capability == 'legacy': batch_keys.vm.qmp_commands -= BATCH_COMMANDS
    now = [100.0]
    monkeypatch.setattr('fdisbull.qemu_frame_key_batch.time.monotonic', lambda: now[0])
    original = batch_keys.vm; qmp = original.qmp
    original.process = SimpleNamespace(poll=lambda: 0)
    original.operation_deadline = 500.0
    qmp.operation_deadline = 600.0
    serial = SimpleNamespace(operation_deadline=700.0)
    batch_keys._channel = serial
    previous = batch_keys._event
    def late(name, receipt):
        previous(name, receipt)
        if name == 'frame-inputs': now[0] += 1000
    batch_keys._event = late
    with pytest.raises(TimeoutError, match='outer deadline') as caught:
        _invoke(batch_keys, entry, [dict(key='a', pressed=True)])
    assert caught.value.frame_input_owner['accepted_evidence']['held'] == ['a']
    assert batch_keys.closed and batch_keys.key_state['held'] == ['a']
    assert (original.operation_deadline, qmp.operation_deadline, serial.operation_deadline) == (500.0,600.0,700.0)
    assert original.lock.acquire(blocking=False)
    original.lock.release()


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
def test_callback_primary_error_and_result_survive_failing_cleanup(batch_keys, entry):
    start(batch_keys)
    batch_keys.vm.process = SimpleNamespace(poll=lambda: 0)
    failure = RuntimeError('accepted receipt persistence failed')
    failure.result = {'original': 'callback evidence'}
    def event(name, receipt):
        if name == 'frame-inputs': raise failure
    batch_keys._event = event
    def close_error(): raise OSError('captured channel close failed')
    batch_keys.vm.qmp.close = close_error
    with pytest.raises(RuntimeError) as caught: _invoke(batch_keys, entry)
    assert caught.value is failure and caught.value.result == {'original': 'callback evidence'}
    assert caught.value.frame_input_owner['accepted_evidence']['held'] == ['a','alt','ctrl','up']
    assert 'OSError' in caught.value.frame_input_owner['cleanup_errors']
    assert batch_keys.closed


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('stage', ['plan', 'apply'])
def test_refusal_does_not_hide_original_lock_release_failure(batch_keys, entry, stage):
    start(batch_keys)
    setattr(batch_keys.batch_peer, stage + '_refusal', 'device-busy')
    original_lock = batch_keys.vm.lock
    released = []
    def release():
        original_lock.release(); released.append(True)
        raise OSError('original lock release failed')
    batch_keys.vm.lock = SimpleNamespace(acquire=original_lock.acquire, release=release)
    with pytest.raises((ValueError, OSError)) as caught: _invoke(batch_keys, entry)
    assert released == [True]
    assert batch_keys.closed
    assert 'OSError' in caught.value.frame_input_owner['cleanup_errors']
