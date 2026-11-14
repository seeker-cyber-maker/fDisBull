"""Existing Wine snapshots cannot silently lose machine input ownership."""
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.qemu_input import QemuPhysicalInputMixin, require_released_machine_input
from fdisbull.wine_rpc import WineQemuRPC
from fdisbull.wine_state import PEStateSessionMixin


class InputPeer:
    def __init__(self):
        self.running = False
        self.input_batches, self.captures = [], []

    def call(self, method, arguments=None, **options):
        if method == 'query-status':
            return dict(running=self.running, status='running' if self.running else 'paused')
        assert method == 'input-send-event'
        self.input_batches.append(arguments)
        return {}

    def save(self, path):
        self.captures.append(path)
        return dict(format='test-native-capture-boundary')


class InputOwner(QemuPhysicalInputMixin):
    def __init__(self):
        self.project = None
        self.run_id = 'machine-input-owner'
        self.vm = SimpleNamespace(qmp=InputPeer(), qmp_commands={'input-send-event'},
                                  lock=threading.RLock(), closed=False)

    def dispatch(self):
        self.vm.qmp.running = True
        result = self._input_after_continue(time.monotonic() + 1)
        self.vm.qmp.running = False
        assert result['delivery'] == 'qmp_accepted'


def prepared_input(kind):
    owner = InputOwner()
    if kind == 'pending_motion':
        owner.mouse_move_relative(1, 0)
        return owner
    token = (owner.mouse_button_down('left') if kind == 'accepted_mouse'
             else owner.keyboard_key_down('shift'))['lease']
    if kind != 'pending_keyboard':
        owner.dispatch()
    if kind in ('pending_release', 'released'):
        owner.keyboard_key_up(token)
    if kind == 'released':
        owner.dispatch()
    return owner


def native_rpc(owner):
    rpc = WineQemuRPC.__new__(WineQemuRPC)
    rpc.vm, rpc.qmp, rpc.lock = owner.vm, owner.vm.qmp, owner.vm.lock
    rpc.capabilities = {'keyboard': True}
    rpc.closed_by_failure = False
    def close():
        rpc.closed_by_failure = True
    rpc.close = close
    return rpc


class Snapshot(PEStateSessionMixin):
    def __init__(self, rpc):
        self.rpc, self._pending_exec, self._keyboard_leases = rpc, None, {}
        self.calls = []

    def _layer_setup(self):
        pass

    def call(self, method):
        self.calls.append(method)
        return dict(pending=False, held=[])

    def registers(self):
        pytest.fail('Native checkpoint passed physical-input preflight')


@pytest.mark.parametrize('kind', [
    'pending_keyboard', 'pending_motion', 'accepted_keyboard', 'accepted_mouse', 'pending_release',
])
def test_wine_native_snapshot_rejects_machine_input_before_guest_calls_or_migration(kind):
    owner = prepared_input(kind)
    rpc = native_rpc(owner)
    snapshot = Snapshot(rpc)
    before = owner.input_state()
    with pytest.raises(ValueError, match='released machine input'):
        snapshot.save_state('checkpoint.sav')
    assert snapshot.calls == [] and rpc.qmp.captures == []
    assert not rpc.closed_by_failure and owner.input_state() == before


@pytest.mark.parametrize('kind', [
    'pending_keyboard', 'pending_motion', 'accepted_keyboard', 'accepted_mouse', 'pending_release',
])
def test_direct_wine_capture_refusal_preserves_vm_for_explicit_release(kind):
    owner = prepared_input(kind)
    rpc = native_rpc(owner)
    before = owner.input_state()
    with pytest.raises(ValueError, match='released machine input'):
        rpc.capture(Path('/unused-checkpoint.mig.gz'))
    assert rpc.qmp.captures == [] and not rpc.closed_by_failure
    assert owner.input_state() == before and not owner.vm.closed


def test_accepted_release_allows_existing_native_capture_without_restoring_a_lease():
    owner = prepared_input('released')
    state = owner.input_state()
    assert state['pending_edges'] == 0 and state['leases'] == {} and state['valid']
    require_released_machine_input(owner.vm)
    rpc = native_rpc(owner)
    result = rpc.capture(Path('/unused-checkpoint.mig.gz'))
    assert result['format'] == 'test-native-capture-boundary'
    assert len(rpc.qmp.captures) == 1 and not rpc.closed_by_failure


def test_untouched_existing_wine_vm_does_not_gain_a_new_input_requirement():
    owner = InputOwner()
    assert not hasattr(owner.vm, '_physical_input')
    require_released_machine_input(owner.vm)
    rpc = native_rpc(owner)
    rpc.capture(Path('/unused-checkpoint.mig.gz'))
    assert len(rpc.qmp.captures) == 1 and not rpc.closed_by_failure
