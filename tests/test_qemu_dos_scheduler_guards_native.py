"""Native scheduler guard witness using an authored DOS/V86 fixture."""
import hashlib
from contextlib import contextmanager
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import prepare_dos_baseline
from support.qemu_dos_scheduler_fixture import ANCHOR, MONITOR_UUID, scheduler_fixture
from test_qemu_dos_checkpoint_sessions_native import _number
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


@contextmanager
def _one_task_scheduler(tmp_path, **fixture_options):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = scheduler_fixture(tmp_path, runtime['NASM'], **fixture_options)
    source = tmp_path / 'SCHED.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'guard.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            addresses = [base + marker[key] for key in ('ready', 'fetch', 'scratch', 'shared', 'gp', 'yield_site')]
            for key in ('vm_stack', 'ring0_stack'):
                addresses.extend((base + marker[key] - 64, base + marker[key] - 1))
            pages = sorted({value & ~4095 for value in addresses})
            task = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            assert task == binding['task_id']
            debug.dos_task_scheduler()
            yield debug, base, marker, binding
    assert source.read_bytes() == data


def _native_context(qmp, binding):
    return qmp.call('x-fdisbull-task-context-read', {
        'uuid': binding['monitor_uuid'], 'cookie': binding['cookie'],
        'incarnation': binding['incarnation']})


def test_native_iret_width_mismatch_refuses_before_frame_pop(tmp_path, monkeypatch):
    evidence = {}
    with _one_task_scheduler(tmp_path, iret16=True) as (debug, base, marker, binding):
        point = debug.breakpoint(base + marker['yield_site'] + 2)
        assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
        debug.delete_breakpoint(point['breakpoint_id'])
        context = _native_context(debug.vm.qmp, binding)
        assert context['interrupt-depth'] == 1 and len(context['frames']) == 1
        frame = context['frames'][0]
        assert frame['vector'] == 0x61 and frame['width'] == 32
        address = frame['frame-ss-base'] + frame['frame-sp']
        size = frame['frame-size']
        original = debug.dos_task_memory(address, length=size, task=binding['task_id'])['hex']
        sp_before = _number(debug.registers()['registers']['rsp'])
        qmp, remote, old_close = debug.vm.qmp, debug.vm.debugger(), debug.close
        def capture_before_close(*args, **kwargs):
            if not evidence:
                try:
                    evidence['machine'] = qmp.call('query-status')
                    evidence['status'] = qmp.call('x-fdisbull-task-scheduler-observe')
                    evidence['context'] = _native_context(qmp, binding)
                    evidence['registers'] = remote.registers()
                    evidence['frame'] = qmp.call('x-fdisbull-task-layer-read', {
                        'uuid': binding['monitor_uuid'], 'cookie': binding['cookie'],
                        'incarnation': binding['incarnation'], 'address': address,
                        'length': size, 'view': 'ram'})['data-hex']
                except BaseException as error:
                    evidence['capture_error'] = repr(error)
            return old_close(*args, **kwargs)
        monkeypatch.setattr(debug, 'close', capture_before_close)
        with pytest.raises(DebuggerError): debug.run(timeout_ms=15000)
        assert debug.closed and 'capture_error' not in evidence, evidence
        assert evidence['machine']['running'] is False
        assert 'iret' in evidence['status'].get('fault', '').lower()
        assert evidence['context']['interrupt-depth'] == 1
        assert _number(evidence['registers']['rsp']) == sp_before
        assert evidence['frame'] == original


def test_native_v86_gp_records_error_code_frame_before_handler(tmp_path):
    with _one_task_scheduler(tmp_path, gp_fault=True) as (debug, base, marker, binding):
        point = debug.breakpoint(base + marker['gp'])
        assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
        debug.delete_breakpoint(point['breakpoint_id'])
        context = _native_context(debug.vm.qmp, binding)
        assert context['interrupt-depth'] == 1 and len(context['frames']) == 1
        frame = context['frames'][0]
        assert frame['vector'] == 13 and frame['width'] == 32 and frame['frame-size'] == 40
        assert frame['error-code-present'] is True and frame['error-code'] == 0


def test_native_interrupt_frame_refuses_unowned_ring0_before_any_write(tmp_path, monkeypatch):
    runtime = _inputs()
    nasm = runtime['NASM']
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = hashlib.sha256(boot.read_bytes()).hexdigest()
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = scheduler_fixture(tmp_path, nasm, isolate_ring0=True)
    assert data[marker['after_a'] - 2:marker['after_a']] == b'\xcd\x61'
    source = tmp_path / 'SCHED.COM'; source.write_bytes(data)
    evidence = {}
    with Project.create(tmp_path / 'guard.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            # The fixture reserves 8192 bytes and chooses an aligned 4096-byte
            # ring-zero stack wholly inside it, regardless of COM load segment.
            stack_buffer = base + marker['ring0_stack'] - 8192
            ring0_page = (stack_buffer + 4095) & ~4095
            ring0_top = ring0_page + 4096
            points = [base + marker[name] for name in ('ready', 'fetch', 'scratch', 'shared')]
            points.extend((base + marker['vm_stack'] - 64, base + marker['vm_stack'] - 1))
            pages = sorted({value & ~4095 for value in points})
            assert ring0_page not in pages
            task = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            assert task == binding['task_id']
            debug.dos_task_scheduler()
            point = debug.breakpoint(base + marker['after_a'] - 2)
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            original = bytes.fromhex(debug.memory(ring0_top - 64, length=64, space='physical')['hex'])
            qmp = debug.vm.qmp
            remote = debug.vm.debugger()
            old_close = debug.close

            def capture_before_close(*args, **kwargs):
                if not evidence:
                    try:
                        evidence['machine'] = qmp.call('query-status')
                        evidence['status'] = qmp.call('x-fdisbull-task-scheduler-observe')
                        evidence['context'] = qmp.call('x-fdisbull-task-context-read', {
                            'uuid': binding['monitor_uuid'], 'cookie': binding['cookie'],
                            'incarnation': binding['incarnation']})
                        evidence['stack'] = remote.memory(ring0_top - 64, 64, space='physical')
                    except BaseException as error:
                        evidence['capture_error'] = repr(error)
                return old_close(*args, **kwargs)

            monkeypatch.setattr(debug, 'close', capture_before_close)
            with pytest.raises(DebuggerError):
                debug.run(timeout_ms=15000)
            assert debug.closed
            assert 'capture_error' not in evidence, evidence
            assert evidence['machine']['running'] is False
            fault = evidence['status'].get('fault', '').lower()
            assert 'frame' in fault and ('private' in fault or 'stack' in fault), evidence['status']
            assert evidence['context']['interrupt-depth'] == 0
            assert evidence['context']['frames'] == []
            assert evidence['stack'] == original
    assert source.read_bytes() == data and hashlib.sha256(boot.read_bytes()).hexdigest() == boot_hash
