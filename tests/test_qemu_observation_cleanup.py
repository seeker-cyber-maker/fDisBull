"""Captured-owner cleanup never follows resources swapped into the VM object."""
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_machine import QemuMachine
from fdisbull.qemu_observation_authority import ObservationAuthority


class Resource:
    def __init__(self, name):
        self.name, self.closes, self.cleanups = name, 0, 0
        self.closed = False
        self.on_close = None

    def close(self):
        self.closes += 1
        self.closed = True
        if self.on_close is not None:
            self.on_close()

    def cleanup(self):
        self.cleanups += 1


class Process:
    def __init__(self):
        self.stdin, self.stdout = Resource('stdin'), Resource('stdout')
        self.terminates, self.kills, self.waits = 0, 0, 0
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminates += 1

    def kill(self):
        self.kills += 1

    def wait(self, timeout):
        assert timeout == 3
        self.waits += 1
        self.returncode = 0
        return 0


def client(kind, name):
    value = kind.__new__(kind)
    value.socket = Resource(name)
    value.operation_deadline = None
    return value


def owner():
    vm = QemuMachine.__new__(QemuMachine)
    vm.lock, vm.process = threading.RLock(), Process()
    vm.qmp, vm.gdb = client(QemuControl, 'qmp'), client(GDBRemote, 'gdb')
    vm._channels = [Resource('extra-channel')]
    vm.temporary = Resource('/owned-observation')
    vm._qemu_image_proof = Resource('image-proof')
    vm._admission_guest_pidfd = None
    vm.operation_deadline = None
    vm.machine_configuration = dict(memory_mib=16, cpus=1)
    closed = []
    vm.close_observer = lambda: closed.append('original')
    context = SimpleNamespace(vm=vm, run_id='original-run', project=object())
    vm.context = context
    vm.observation_authority = ObservationAuthority(vm)
    vm.observation_authority.bind(qmp=vm.qmp, gdb=vm.gdb)
    return vm, context, closed


@pytest.mark.parametrize('replacement', [
    'process', 'qmp', 'gdb', 'qmp_socket', 'gdb_socket', 'channels',
    'temporary', 'proof', 'close_observer', 'context_vm',
])
def test_failed_scope_closes_original_resources_and_leaves_every_replacement_untouched(replacement):
    vm, context, callbacks = owner()
    process, qmp, gdb = vm.process, vm.qmp, vm.gdb
    qmp_socket, gdb_socket = qmp.socket, gdb.socket
    extra, temporary, proof = vm._channels[0], vm.temporary, vm._qemu_image_proof
    foreign_process = Process()
    foreign = Resource('/foreign')
    foreign_client = client(QemuControl if replacement == 'qmp' else GDBRemote, 'foreign-client')
    foreign_callback = []
    foreign_vm = SimpleNamespace(closed=False)
    with pytest.raises(DebuggerError, match='authored failure'):
        with vm.observation_authority.observe(context, deadline=time.monotonic() + 2,
                ram_ranges=[dict(address=0x5000, length=4)]):
            if replacement == 'process':
                vm.process = foreign_process
            elif replacement in ('qmp', 'gdb'):
                setattr(vm, replacement, foreign_client)
            elif replacement in ('qmp_socket', 'gdb_socket'):
                getattr(vm, replacement.split('_')[0]).socket = foreign
            elif replacement == 'channels':
                vm._channels = [foreign]
            elif replacement == 'temporary':
                vm.temporary = foreign
            elif replacement == 'proof':
                vm._qemu_image_proof = foreign
            elif replacement == 'close_observer':
                vm.close_observer = lambda: foreign_callback.append('foreign')
            else:
                context.vm = foreign_vm
            raise DebuggerError('authored failure after the captured owner changed')
    vm.close()
    vm.close()  # A second error handler must not close the replacements either.
    assert process.terminates == process.waits == 1 and process.kills == 0
    assert process.stdin.closes == process.stdout.closes == 1
    assert qmp_socket.closes == gdb_socket.closes == extra.closes == 1
    assert temporary.cleanups == proof.closes == 1
    assert foreign_process.terminates == foreign_process.kills == foreign_process.waits == 0
    assert foreign_process.stdin.closes == foreign_process.stdout.closes == 0
    assert foreign.closes == foreign.cleanups == 0
    assert foreign_client.socket.closes == 0 and not foreign_callback
    assert foreign_vm.closed is False
    assert vm.observation_authority._cleanup_owner['closed'] is True
    if replacement == 'process':
        assert vm.process is foreign_process
    elif replacement in ('qmp', 'gdb'):
        assert getattr(vm, replacement) is foreign_client
    elif replacement in ('qmp_socket', 'gdb_socket'):
        assert getattr(vm, replacement.split('_')[0]).socket is foreign
    elif replacement == 'channels':
        assert vm._channels == [foreign]
    elif replacement == 'temporary':
        assert vm.temporary is foreign
    elif replacement == 'proof':
        assert vm._qemu_image_proof is foreign
    elif replacement == 'context_vm':
        assert callbacks == [] and context.vm is foreign_vm


def test_cleanup_inside_active_scope_does_not_reenter_or_change_a_replacement_owner():
    vm, context, callbacks = owner()
    process = vm.process
    foreign = Process()
    with pytest.raises(DebuggerError, match='invalidated'):
        with vm.observation_authority.observe(context, deadline=time.monotonic() + 2,
                ram_ranges=[dict(address=0x5000, length=4)]):
            vm.process = foreign
            vm.close()  # Source metadata/export failures close inside the lease.
    vm.close()
    assert process.terminates == process.waits == 1
    assert foreign.terminates == foreign.waits == 0
    assert vm.process is foreign and callbacks == []


@pytest.mark.parametrize('change', ['client', 'context'])
def test_cleanup_callback_replacement_is_rechecked_before_clear_and_close_observer(change):
    vm, context, callbacks = owner()
    original_qmp, original_socket = vm.qmp, vm.qmp.socket
    foreign = client(QemuControl, 'replacement-during-close')
    foreign_vm = SimpleNamespace(closed=False)
    def replace():
        if change == 'client':
            vm.qmp = foreign
        else:
            context.vm = foreign_vm
    vm.gdb.socket.on_close = replace
    with pytest.raises(DebuggerError, match='authored failure'):
        with vm.observation_authority.observe(context, deadline=time.monotonic() + 2,
                ram_ranges=[dict(address=0x5000, length=4)]):
            raise DebuggerError('authored failure before cleanup callback')
    vm.close()
    assert original_socket.closes == 1 and original_qmp.socket is None
    assert foreign.socket.closes == 0 and callbacks == []
    if change == 'client':
        assert vm.qmp is foreign
    else:
        assert context.vm is foreign_vm and not foreign_vm.closed
