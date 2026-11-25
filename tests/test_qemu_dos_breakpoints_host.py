"""Host-only compatibility checks for QEMU DOS breakpoint alias readback."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.execution_trace import _native_controls
from fdisbull.qemu_dos_process import QemuDOSProcessSession


class _QMP:
    def __init__(self, *, running=False):
        self.running = running
        self.commands = []

    def call(self, method, params=None):
        self.commands.append((method, params))
        assert method == 'query-status'
        return {'running': self.running}


class _Remote:
    def __init__(self):
        self.commands = []

    def request(self, command):
        self.commands.append(command)
        return b'OK'


class _VM:
    def __init__(self, *, running=False, exited=False):
        self.lock = threading.RLock()
        self.qmp = _QMP(running=running)
        self.process = SimpleNamespace(poll=lambda: 1 if exited else None)
        self.remote = _Remote()
        self.machine_stopped = False
        self.context = None

    def debugger(self):
        return self.remote


def _session(vm=None):
    debug = object.__new__(QemuDOSProcessSession)
    debug.vm = vm or _VM()
    debug.vm.context = debug
    debug.closed = False
    debug.breakpoints = {}
    debug.next_bp = 1
    debug._return_breakpoint = None
    debug.run_id = 'host-test-run'
    debug._runtime_epoch = 'host-test-run:process:1'
    debug._epoch_number = 1
    return debug


def test_call_lists_owned_execution_and_watchpoint_aliases_and_delete_preserves_alias():
    debug = _session()
    execution = debug.breakpoint(0x1234)
    watch = debug.breakpoint(0x2345, access='rw', length=4)
    with debug.vm.lock:
        automatic = debug._create_machine_breakpoint(
            0x2345, access='rw', length=4, owner='automatic-runtime-tracking')

    debug.vm.machine_stopped = False
    native_commands_before_list = list(debug.vm.remote.commands)
    revision_before_list = debug.vm.session_revision.snapshot()["state_revision"]
    result = debug.call('breakpoints.list', {})
    assert result['state'] == 'stopped'
    assert debug.vm.machine_stopped is False
    assert result['session_id']
    assert result['state_revision'] == revision_before_list
    assert result['breakpoints'] == [
        dict(breakpoint_id=execution['breakpoint_id'], kind='execution', enabled=True,
             once=False, address=dict(space='linear', offset='0x1234'), access='x', length=1,
             address_space='selected-vCPU virtual address', owner='user'),
        dict(breakpoint_id=watch['breakpoint_id'], kind='watchpoint', enabled=True,
             once=False, address=dict(space='linear', offset='0x2345'), access='rw', length=4,
             address_space='selected-vCPU virtual address', owner='user'),
        dict(breakpoint_id=automatic['breakpoint_id'], kind='watchpoint', enabled=True,
             once=False, address=dict(space='linear', offset='0x2345'), access='rw', length=4,
             address_space='selected-vCPU virtual address',
             owner='automatic-runtime-tracking'),
    ]
    assert debug.vm.remote.commands == native_commands_before_list

    debug.delete_breakpoint(watch['breakpoint_id'])
    after_delete = debug.call('breakpoints.list')
    assert [row['breakpoint_id'] for row in after_delete['breakpoints']] == [
        execution['breakpoint_id'], automatic['breakpoint_id']]
    assert 'z4,2345,4' not in debug.vm.remote.commands
    debug.delete_breakpoint(automatic['breakpoint_id'])
    assert debug.vm.remote.commands[-1] == 'z4,2345,4'


@pytest.mark.parametrize('params', [{'unexpected': True}, [], ''])
def test_list_rejects_nonempty_or_nonobject_parameters(params):
    debug = _session()
    with pytest.raises(ValueError, match='empty parameters'):
        debug.call('breakpoints.list', params)
    assert not debug.vm.qmp.commands


def test_list_refuses_running_and_exited_machine_without_native_enumeration():
    running = _session(_VM(running=True))
    with pytest.raises(ValueError, match='Pause'):
        running.call('breakpoints.list')
    assert running.vm.qmp.commands == [('query-status', None)]
    assert not running.vm.remote.commands

    exited = _session(_VM(exited=True))
    with pytest.raises(DebuggerError, match='exited'):
        exited.call('breakpoints.list')
    assert not exited.vm.qmp.commands
    assert not exited.vm.remote.commands


def test_list_preserves_revision_and_live_histories():
    debug = _session()
    debug.breakpoint(0x1234)
    debug._qemu_history_live = {'valid': True, 'cursor': 0}
    debug._qemu_cpu_delta_history = {'id': 'selected-state', 'valid': True,
                                     'frozen': False}
    debug._history_bind()
    before_revision = debug.vm.session_revision.snapshot()

    listed = debug.call('breakpoints.list')

    assert listed['state_revision'] == before_revision['state_revision']
    assert debug.vm.session_revision.snapshot() == before_revision
    assert debug._qemu_history_live == {'valid': True, 'cursor': 0}
    assert debug._qemu_cpu_delta_history == {'id': 'selected-state', 'valid': True,
                                             'frozen': False}


def test_restore_replacement_clears_old_aliases_and_listing_uses_new_epoch():
    debug = _session()
    old = debug.breakpoint(0x3456)
    previous_vm = debug.vm
    restored_vm = _VM()
    restored_vm.context = debug
    debug.vm = restored_vm
    debug.breakpoints = {}
    debug.next_bp = 1
    debug._epoch_number += 1
    debug._runtime_epoch = 'host-test-run:process:2'

    result = debug.call('breakpoints.list')
    assert result['breakpoints'] == []
    assert result['session_id'] != ''
    assert debug.breakpoints == {}
    assert old['breakpoint_id'] not in [row['breakpoint_id'] for row in result['breakpoints']]
    assert previous_vm.remote.commands == ['Z1,3456,1']
    assert not restored_vm.remote.commands


def test_listing_rejects_owner_epoch_change_during_status_read():
    debug = _session()
    original = debug.vm
    original.qmp.call = lambda method, params=None: (
        setattr(debug, '_epoch_number', 2) or {'running': False})
    with pytest.raises(DebuggerError, match='ownership changed during listing'):
        debug.call('breakpoints.list')


def test_listing_closes_owner_when_qmp_transport_fails():
    debug = _session()
    owner = debug.vm
    owner.closed = False
    owner.close = lambda: setattr(owner, 'closed', True)
    owner.qmp.socket = None

    def failed_status(method, params=None):
        raise DebuggerError('QMP status transport closed')

    owner.qmp.call = failed_status
    with pytest.raises(DebuggerError, match='transport closed'):
        debug.call('breakpoints.list')
    assert owner.closed


def test_native_controls_accepts_execution_alias_and_rejects_watchpoint():
    debug = _session()
    execution = debug.breakpoint(0x4567)
    assert _native_controls(debug) == [dict(
        id=execution['breakpoint_id'], space='linear', offset=0x4567,
        segment=None, once=False)]

    debug.breakpoint(0x5678, access='r', length=2)
    with pytest.raises(ValueError, match='data/watchpoints'):
        _native_controls(debug)


@pytest.mark.parametrize('deadline_source', [
    'rpc', 'session', 'machine', 'qmp',
])
@pytest.mark.parametrize('deadline_age', ['expired', 'near'])
def test_listing_lock_wait_obeys_shortest_inherited_deadline(deadline_source, deadline_age):
    debug = _session()
    lock_held = threading.Event()
    release_lock = threading.Event()

    def hold_machine_lock():
        debug.vm.lock.acquire()
        lock_held.set()
        release_lock.wait(1)
        debug.vm.lock.release()

    holder = threading.Thread(target=hold_machine_lock)
    holder.start()
    assert lock_held.wait(1)
    deadline = time.monotonic() - 0.01 if deadline_age == 'expired' else time.monotonic() + 0.04
    if deadline_source == 'rpc':
        debug._rpc_deadline = deadline
    elif deadline_source == 'session':
        debug._deadline = deadline
    elif deadline_source == 'machine':
        debug.vm.operation_deadline = deadline
    else:
        debug.vm.qmp.operation_deadline = deadline

    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='deadline'):
            debug.call('breakpoints.list')
        assert time.monotonic() - started < 0.5
        assert not debug.vm.qmp.commands
    finally:
        release_lock.set()
        holder.join(timeout=1)
    assert not holder.is_alive()
