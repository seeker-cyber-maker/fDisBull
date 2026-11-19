"""OS image proofs use real owned processes; QMP is an explicit boundary double."""
from copy import deepcopy
import ctypes
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from fdisbull import qemu_image as image
from fdisbull.dosbox_rpc import DebuggerError


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def owned(tmp_path):
    if sys.platform != 'linux':
        pytest.skip('Linux executing inode witness; Darwin is separately exercised')
    owners = []
    def launch(name='one', suffix=b''):
        directory = tmp_path / name
        directory.mkdir()
        binary = directory / 'native'
        shutil.copyfile('/bin/sleep', binary)
        with binary.open('ab') as stream:
            stream.write(suffix)
        binary.chmod(0o700)
        launcher = directory / 'launch'
        launcher.write_bytes(b'#!/bin/sh\nexec "$(dirname "$0")/native" 60\n')
        launcher.chmod(0o700)
        process = subprocess.Popen([str(launcher)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        end = time.monotonic() + 2
        while os.readlink(f'/proc/{process.pid}/exe') != str(binary):
            if process.poll() is not None or time.monotonic() >= end:
                pytest.fail('Authored native owner failed to exec')
            time.sleep(.005)
        calls = []
        def call(method, **kwargs):
            calls.append(method)
            assert method == 'query-cpus-fast'
            return [{'cpu-index': 0, 'thread-id': process.pid}]
        vm = SimpleNamespace(process=process, operation_deadline=None,
            inputs={'qemu': dict(path=str(launcher), sha256=digest(launcher),
                                 version='QEMU emulator version 10.0.13')},
            machine_configuration={'cpus': 1},
            qmp=SimpleNamespace(call=call, greeting={'QMP': {'version': {'qemu':
                {'major': 10, 'minor': 0, 'micro': 13}}}}), calls=calls,
            binary=binary, closed=False)
        def close():
            proof = getattr(vm, '_qemu_image_proof', None)
            if proof is not None:
                proof.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2)
            handle = getattr(vm, '_admission_guest_pidfd', None)
            if handle is not None:
                os.close(handle); vm._admission_guest_pidfd = None
            vm.closed = True
        vm.close = close
        owners.append(vm)
        return vm
    yield launch
    for vm in owners:
        vm.close()


def admit(vm):
    proof = image.admit(vm, time.monotonic() + 2)
    vm._qemu_image_proof = proof
    vm.inputs['qemu_image'] = deepcopy(proof.identity)
    return proof


def test_same_launcher_same_version_different_executed_bytes_are_distinct(owned):
    one, two = owned('one'), owned('two', b'authored producer distinction')
    admit(one); admit(two)
    assert one.inputs['qemu']['sha256'] == two.inputs['qemu']['sha256']
    assert one.inputs['qemu']['version'] == two.inputs['qemu']['version']
    assert one.inputs['qemu_image']['sha256'] == digest(one.binary)
    assert two.inputs['qemu_image']['sha256'] == digest(two.binary)
    assert one.inputs['qemu_image']['sha256'] != two.inputs['qemu_image']['sha256']
    with pytest.raises(ValueError, match='producer identity differs'):
        image.compatible(one.inputs, two.inputs)
    assert not one.closed and not two.closed


def test_same_image_relocated_has_no_pid_inode_or_path_in_compatibility(owned):
    one, two = owned('one'), owned('two')
    admit(one); admit(two)
    image.compatible(one.inputs, two.inputs)
    assert one.process.pid != two.process.pid
    assert one.inputs['qemu_image']['path'] != two.inputs['qemu_image']['path']
    assert set(one.inputs['qemu_image']) == {'format', 'path', 'size', 'sha256', 'version'}
    image.verify(one)
    image.verify(two)


def test_linux_hashes_executing_inode_after_name_is_replaced(owned):
    vm = owned()
    expected = digest(vm.binary)
    vm.binary.unlink()
    vm.binary.write_bytes(b'replacement path is not the executing image')
    admit(vm)
    assert vm.inputs['qemu_image']['sha256'] == expected
    assert vm.inputs['qemu_image']['path'].endswith(' (deleted)')
    image.verify(vm)


@pytest.mark.parametrize('change', ['record', 'owner', 'dead'])
def test_changed_live_authority_closes_and_quarantines_without_re_admission(owned, change):
    vm = owned()
    admit(vm)
    if change == 'record':
        vm.inputs['qemu_image']['sha256'] = '0' * 64
    elif change == 'owner':
        vm.process = SimpleNamespace(pid=vm.process.pid, poll=lambda: None)
    else:
        vm.process.terminate(); vm.process.wait(timeout=2)
    with pytest.raises(DebuggerError, match='changed'):
        image.verify(vm)
    assert vm.closed and vm._fdisbull_control_quarantine
    assert vm.calls == ['query-cpus-fast']


def test_qmp_version_mismatch_refuses_before_image_hash(owned, monkeypatch):
    vm = owned()
    vm.qmp.greeting['QMP']['version']['qemu']['micro'] += 1
    monkeypatch.setattr(image, '_hash', lambda *a, **kw: pytest.fail('hashed after version refusal'))
    with pytest.raises(DebuggerError, match='version differs'):
        admit(vm)


def test_launcher_mutation_during_admission_is_refused(owned):
    vm = owned()
    Path(vm.inputs['qemu']['path']).write_bytes(b'changed launcher')
    with pytest.raises(DebuggerError, match='launcher changed'):
        admit(vm)


def test_shared_deadline_expires_without_second_chunk(owned, monkeypatch):
    vm = owned()
    proof = admit(vm)
    with pytest.raises(TimeoutError, match='identity deadline'):
        proof.verify(vm, time.monotonic() - 1)
    assert not vm.closed  # Direct proof is read-only; public verify owns cleanup.


def test_descendant_qmp_owner_is_not_the_native_launcher(owned, monkeypatch):
    vm = owned()
    child = subprocess.Popen(['/bin/sleep', '60'])
    try:
        vm.qmp.call = lambda *a, **kw: [{'cpu-index': 0, 'thread-id': child.pid}]
        monkeypatch.setattr(image, '_descendant', lambda pid, parent, deadline: True)
        with pytest.raises(DebuggerError, match='must exec'):
            admit(vm)
        assert vm._admission_guest == (child.pid, image._process(child.pid)[1])
    finally:
        child.terminate(); child.wait(timeout=2)


def test_legacy_state_is_refused_without_retrospective_wrapper_inference():
    with pytest.raises(ValueError, match='legacy producer is unqualified'):
        image.require_record({'qemu': {'sha256': '1' * 64, 'version': '10.0.13'}})


def test_native_format_is_required_for_observed_image(tmp_path):
    path = tmp_path / 'script'; path.write_bytes(b'#!/bin/sh\nexit 0\n')
    fd = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(DebuggerError, match='native executable'):
            image._hash(fd, time.monotonic() + 1)
    finally:
        os.close(fd)


@pytest.mark.parametrize('different', [False, True])
def test_darwin_mapping_compares_vnode_to_open_file_not_path_alone(tmp_path, monkeypatch, different):
    path = tmp_path / 'native'; path.write_bytes(b'authored map')
    opened = path.stat()
    record = image._RegionPath()
    record.path = os.fsencode(path)
    value = record.vnode.stat
    value.dev = opened.st_dev & 0xffffffff
    value.ino = opened.st_ino + int(different)
    value.size = opened.st_size
    value.mode = opened.st_mode
    value.mtime, value.mtime_ns = divmod(opened.st_mtime_ns, 10**9)
    value.ctime, value.ctime_ns = divmod(opened.st_ctime_ns, 10**9)
    def info(pid, flavor, address, target, size):
        assert flavor == 8
        ctypes.memmove(target, ctypes.byref(record), size)
        return size
    monkeypatch.setattr(image, '_libproc', lambda: SimpleNamespace(proc_pidinfo=info))
    if different:
        with pytest.raises(DebuggerError, match='vnode differs'):
            image._mac_mapping(123, str(path), opened, time.monotonic() + 1)
    else:
        image._mac_mapping(123, str(path), opened, time.monotonic() + 1)


def test_darwin_unavailable_mapping_has_no_path_only_fallback(tmp_path, monkeypatch):
    path = tmp_path / 'native'; path.write_bytes(b'authored map')
    monkeypatch.setattr(image, '_libproc', lambda: SimpleNamespace(proc_pidinfo=lambda *a: 0))
    with pytest.raises(DebuggerError, match='Cannot bind macOS'):
        image._mac_mapping(123, str(path), path.stat(), time.monotonic() + 1)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux exact process-handle cleanup')
def test_nonexec_descendant_refusal_reaps_guest_when_qmp_quit_fails():
    wrapper = subprocess.Popen(['/bin/sh', '-c', '/bin/sleep 60 & echo $!; wait $!'],
                               stdout=subprocess.PIPE, text=True)
    child = int(wrapper.stdout.readline())
    calls = []
    def call(method, **kwargs):
        calls.append(method)
        if method == 'query-cpus-fast':
            return [{'cpu-index': 0, 'thread-id': child}]
        raise DebuggerError('authored lost QMP quit')
    vm = SimpleNamespace(process=wrapper, machine_configuration={'cpus': 1},
                         qmp=SimpleNamespace(call=call), _admission_guest_pidfd=None)
    try:
        with pytest.raises(DebuggerError, match='must exec'):
            image._peer(vm, time.monotonic() + 2)
        image.admission_quit(vm)
        assert wrapper.wait(timeout=2) != 0
        assert calls == ['query-cpus-fast', 'quit']
        assert not Path(f'/proc/{child}').exists()
    finally:
        handle = vm._admission_guest_pidfd
        if handle is not None:
            try:
                import signal
                signal.pidfd_send_signal(handle, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(handle)
        if wrapper.poll() is None:
            wrapper.terminate()
        wrapper.wait(timeout=2); wrapper.stdout.close()


def test_changed_captured_birth_never_signals_a_reused_pid(monkeypatch):
    vm = SimpleNamespace(_admission_guest=(123, 'original'), qmp=SimpleNamespace(
        call=lambda *a, **kw: pytest.fail('quit sent after changed birth')))
    monkeypatch.setattr(image, '_process', lambda _: (1, 'replacement'))
    monkeypatch.setattr(image.os, 'kill', lambda *a: pytest.fail('signal sent to reused PID'))
    with pytest.raises(DebuggerError, match='PID was reused'):
        image.admission_quit(vm)


def test_admission_cleanup_failure_preserves_primary_and_still_reaps(tmp_path, monkeypatch):
    from fdisbull import qemu_machine
    from test_qemu_machine import authored_qemu_identity
    executable, disk = authored_qemu_identity(tmp_path)
    monkeypatch.setattr(qemu_machine, 'QemuControl', lambda *a: SimpleNamespace(close=lambda: None))
    primary = DebuggerError('authored executing image refused')
    def fail(*args):
        raise primary
    def cleanup(*args):
        raise DebuggerError('authored unobservable Darwin guest')
    monkeypatch.setattr(image, 'admit', fail)
    monkeypatch.setattr(image, 'admission_quit', cleanup)
    spawned = []
    vm = qemu_machine.QemuMachine.__new__(qemu_machine.QemuMachine)
    with pytest.raises(DebuggerError, match='authored executing image refused') as caught:
        vm.__init__(executable, boot_image=disk, on_spawn=spawned.append)
    assert caught.value.__cause__ is primary
    assert primary.guest_cleanup_error == 'DebuggerError'
    assert vm.temporary is None and len(spawned) == 1 and spawned[0].poll() is not None


@pytest.mark.parametrize('stage',['qmp','gdb','input'])
def test_transport_or_input_cleanup_failure_cannot_skip_known_owner_reap(tmp_path,monkeypatch,stage):
    from fdisbull import qemu_machine
    from test_qemu_machine import authored_qemu_identity
    executable,disk=authored_qemu_identity(tmp_path)
    def broken():
        raise OSError('authored cleanup failure')
    monkeypatch.setattr(qemu_machine,'QemuControl',lambda *a:SimpleNamespace(
        close=broken if stage=='qmp' else lambda:None))
    primary=DebuggerError('authored admission refused')
    def refused(vm,deadline):
        if stage=='gdb':vm.gdb=SimpleNamespace(close=broken)
        if stage=='input':vm.context=SimpleNamespace(_input_on_close=broken)
        raise primary
    monkeypatch.setattr(image,'admit',refused)
    spawned=[]
    vm=qemu_machine.QemuMachine.__new__(qemu_machine.QemuMachine)
    with pytest.raises(DebuggerError,match='authored admission refused') as caught:
        vm.__init__(executable,boot_image=disk,on_spawn=spawned.append)
    assert caught.value.__cause__ is primary and primary.machine_cleanup_error=='OSError'
    assert len(spawned)==1 and spawned[0].poll() is not None
    assert vm.temporary is None and vm.qmp is None and vm.gdb is None


@pytest.mark.parametrize('saved_kind', ['matching', 'different', 'legacy'])
def test_wine_expected_producer_is_checked_before_restore(tmp_path, monkeypatch, saved_kind):
    from fdisbull import qemu_machine
    from fdisbull.wine_rpc import WineQemuRPC
    from support.qemu_image_fixture import attach_image
    calls, machines = [], []
    inputs = {key: dict(path=str(tmp_path/key), sha256=str(i)*64)
              for i, key in enumerate(('qemu', 'kernel', 'initramfs'), 1)}
    sample = SimpleNamespace(inputs=deepcopy(inputs), process=object())
    attach_image(sample)
    saved = deepcopy(sample.inputs)
    if saved_kind == 'different':
        saved['qemu_image']['sha256'] = '0' * 64
    elif saved_kind == 'legacy':
        del saved['qemu_image']
    def machine(*args, **kwargs):
        vm = SimpleNamespace(inputs=deepcopy(sample.inputs), process=object(),
            command=[], log_path=tmp_path/'boot.log', temporary=None,
            lock=__import__('threading').RLock(), closed=False)
        vm.qmp = SimpleNamespace(restore=lambda *a, **kw: calls.append('restore'))
        vm.serial = lambda deadline: SimpleNamespace(close=lambda: calls.append('serial-close'))
        vm.close = lambda: setattr(vm, 'closed', True)
        attach_image(vm)
        machines.append(vm)
        return vm
    class RPC(WineQemuRPC):
        agent_resource = None
        @staticmethod
        def runtime_resources():
            return {}
        def call(self, *args, **kwargs):
            return {'protocol': self.protocol, 'resources': {}}
    monkeypatch.setattr(qemu_machine, 'QemuMachine', machine)
    if saved_kind == 'matching':
        rpc = RPC('launch', 'kernel', 'initramfs', restore=tmp_path/'state',
                  expected_runtime_inputs=saved, _on_restore_admitted=lambda:calls.append('retire'))
        assert calls == ['retire', 'restore']
        rpc.close()
    else:
        with pytest.raises(DebuggerError, match='producer'):
            RPC('launch', 'kernel', 'initramfs', restore=tmp_path/'state',
                expected_runtime_inputs=saved, _on_restore_admitted=lambda:calls.append('retire'))
        assert calls == []
        assert machines == [] if saved_kind == 'legacy' else machines[0].closed


def test_linux_missing_process_handle_never_falls_back_to_pid_signal(monkeypatch):
    vm = SimpleNamespace(process=SimpleNamespace(pid=456,poll=lambda:None),
        _admission_guest=(123,'original'), qmp=SimpleNamespace(call=lambda *a,**kw:None))
    tick=[100.0]
    def clock():
        tick[0]+=.3
        return tick[0]
    monkeypatch.setattr(image.sys,'platform','linux')
    monkeypatch.setattr(image,'_process',lambda pid:(1,'original'))
    monkeypatch.setattr(image.os,'kill',lambda *a:pytest.fail('unbound PID signal'))
    monkeypatch.setattr(image.time,'monotonic',clock)
    monkeypatch.setattr(image.time,'sleep',lambda _:None)
    with pytest.raises(DebuggerError,match='no process handle'):
        image.admission_quit(vm)
