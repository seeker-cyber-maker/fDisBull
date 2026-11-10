"""Host-side snapshot-job protocol checks; not native QEMU evidence."""
import threading
import struct

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_checkpoint import snapshot_job, validate_qcow_header
from fdisbull.qemu_machine import MachineDebugSession


class Peer:
    def __init__(self, outcome='ok'):
        self.outcome = outcome
        self.calls = []
        self.job = None

    def call(self, method, args=None, *, timeout_ms):
        self.calls.append((method, args))
        if method == 'query-status':
            return {'running': self.outcome == 'running',
                    'status': 'running' if self.outcome == 'running' else 'paused'}
        if method in ('snapshot-save', 'snapshot-load'):
            self.job = {'id': args['job-id'], 'type': method, 'status': 'concluded'}
            if self.outcome == 'error':
                self.job['error'] = 'snapshot failed'
            return {}
        if method == 'query-jobs':
            return [] if self.outcome == 'missing' else [self.job]
        if method == 'job-dismiss':
            return {}
        raise AssertionError(method)


class Machine:
    def __init__(self, outcome='ok'):
        self.lock = threading.RLock()
        self.qmp = Peer(outcome)
        self.closed = False

    def close(self):
        self.closed = True


def test_snapshot_job_waits_for_conclusion_and_dismisses():
    vm = Machine()
    result = snapshot_job(vm, 'save', tag='one', vmstate='disk0', devices=['disk0'])
    assert result['status'] == 'concluded'
    assert [call[0] for call in vm.qmp.calls] == [
        'query-status', 'snapshot-save', 'query-jobs', 'job-dismiss', 'query-status']
    assert not vm.closed


@pytest.mark.parametrize('outcome', ['error', 'missing'])
def test_uncertain_dispatched_job_closes_owner(outcome):
    vm = Machine(outcome)
    with pytest.raises(DebuggerError):
        snapshot_job(vm, 'load', tag='one', vmstate='disk0', devices=['disk0'])
    assert vm.closed
    assert not any(method == 'job-dismiss' for method, _ in vm.qmp.calls)


def test_running_machine_refuses_before_job_dispatch():
    vm = Machine('running')
    with pytest.raises(ValueError, match='stopped'):
        snapshot_job(vm, 'save', tag='one', vmstate='disk0', devices=['disk0'])
    assert [call[0] for call in vm.qmp.calls] == ['query-status']
    assert not vm.closed


def test_pending_owned_input_refuses_before_qmp():
    vm = Machine()
    vm._physical_input = {'pending': [1], 'leases': {}, 'valid': True}
    with pytest.raises(ValueError, match='released machine input'):
        snapshot_job(vm, 'save', tag='one', vmstate='disk0', devices=['disk0'])
    assert vm.qmp.calls == []


@pytest.mark.parametrize('devices', [[], ['disk0', 'disk0'], ['other']])
def test_bad_nodes_refuse_before_qmp(devices):
    vm = Machine()
    with pytest.raises(ValueError, match='block-node'):
        snapshot_job(vm, 'save', tag='one', vmstate='disk0', devices=devices)
    assert vm.qmp.calls == []


def _qcow_header():
    data = bytearray(104)
    struct.pack_into('>IIQIIQI', data, 0, 0x514649fb, 3, 0, 0, 16, 1474560, 0)
    struct.pack_into('>I', data, 100, 104)
    return data


def test_qcow_header_accepts_only_expected_standalone_size():
    validate_qcow_header(bytes(_qcow_header()), 1474560)
    with pytest.raises(ValueError):
        validate_qcow_header(bytes(_qcow_header()), 1474561)


@pytest.mark.parametrize('offset,fmt,value', [
    (8, '>Q', 4096),       # backing path offset
    (16, '>I', 1),         # backing path length
    (32, '>I', 1),         # encryption
    (72, '>Q', 4),         # external data-file feature
    (72, '>Q', 1),         # dirty image
    (80, '>Q', 1),         # lazy refcounts
])
def test_qcow_header_rejects_dependencies_before_image_parser(offset, fmt, value):
    data = _qcow_header()
    struct.pack_into(fmt, data, offset, value)
    with pytest.raises(ValueError, match='qcow2'):
        validate_qcow_header(bytes(data), 1474560)


def test_restore_deadline_refuses_contended_machine_before_dispatch():
    session = MachineDebugSession.__new__(MachineDebugSession)
    session.vm = Machine()
    session.vm.lock = threading.Lock()
    session.vm.lock.acquire()
    try:
        with pytest.raises(TimeoutError, match='deadline'):
            session.load_state('not-dispatched', timeout_ms=5)
        assert session.vm.qmp.calls == []
        assert not session.vm.closed
    finally:
        session.vm.lock.release()
