"""Real PS/2 → pinned DOS driver → authored INT33 consumption and recovery.

Root owns native execution. Supply FDISBULL_CTMOUSE_EXE (exact GPLv2 driver
identified below), FDISBULL_QEMU_CLOCK, FDISBULL_QEMU_DOS_BOOT_IMAGE,
FDISBULL_QEMU_DOS_MCOPY, FDISBULL_QEMU_DOS_FIRMWARE, FDISBULL_QEMU_IMG and NASM.
FDISBULL_REQUIRE_QEMU_MOUSE=1 and FDISBULL_REQUIRE_QEMU_CLOCK=1 forbid missing
input skips. Driver/media bytes and generated native states remain private.

This gate uses neutral-input process checkpoints. Pending motion and held mouse
leases are explicitly refused; it does not claim they can be restored.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_dos_mouse_fixture import CTMOUSE_SHA256, int33_mouse, prepare_mouse_disk
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import assert_completion, com_address, launch_options, read_bytes


@pytest.fixture
def mouse_inputs():
    required = ('FDISBULL_CTMOUSE_EXE', 'FDISBULL_QEMU_IMG', 'FDISBULL_QEMU_DOS_FIRMWARE')
    values = {name: os.environ.get(name) for name in required}
    missing = [name for name, value in values.items() if not value]
    if missing:
        message = 'Native INT33 mouse inputs missing: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_QEMU_MOUSE') == '1':
            pytest.fail(message)
        pytest.skip(message)
    driver = Path(values['FDISBULL_CTMOUSE_EXE']).expanduser().resolve(strict=True)
    assert digest(driver) == CTMOUSE_SHA256, 'Wrong CTMOUSE.EXE; retain the pinned package/source notices'
    return dict(driver=driver, checkpoint=values['FDISBULL_QEMU_IMG'])


def _symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    return {name: com_address(info, offset) for name, offset in offsets.items() if name != 'report_size'}


def _word(debug, symbols, name):
    return int.from_bytes(read_bytes(debug, symbols[name], 2), 'little')


def _neutral(debug):
    state = debug.input_state()
    assert state['valid'] and state['pending_edges'] == 0 and state['leases'] == {}
    return state


def _continue_mouse(debug, symbols, report, label):
    """Consume one unaccelerated +2 packet/right pair after the saved +3."""
    debug.mouse_move_relative(2, 0)
    lease = debug.mouse_button_down('right')['lease']
    pressed = park(debug, symbols['second_pressed'])
    assert _word(debug, symbols, 'stage') == 3
    assert _word(debug, symbols, 'total_x') == 5 and _word(debug, symbols, 'total_y') == 0
    assert _word(debug, symbols, 'buttons') == 2
    debug.mouse_button_up(lease)
    released = park(debug, symbols['done'])
    assert _word(debug, symbols, 'stage') == 4 and _word(debug, symbols, 'buttons') == 0
    assert _word(debug, symbols, 'total_x') == 5
    neutral = _neutral(debug)
    report.setdefault('continuations', []).append(dict(label=label, press=pressed, release=released,
        neutral=neutral, total_x=5, total_y=0, buttons=0,
        scope='guest INT33 samples; native dispatch receipts alone do not establish consumption'))


def _restored(debug, saved, old_process, old_epoch, cpu, raw_report, offsets, report, label):
    result = debug.load_state(saved['artifact'])
    assert old_process.poll() is not None and debug.vm.process is not old_process
    assert debug.vm.process.poll() is None
    info = debug.dos_process_info()
    assert result['source_binding_restored'] is True and info['state'] == 'active'
    assert info['capture_epoch'] != old_epoch
    assert debug.registers() == cpu
    symbols = _symbols(debug, offsets)
    assert read_bytes(debug, symbols['report'], offsets['report_size']) == raw_report
    assert _word(debug, symbols, 'stage') == 2 and _word(debug, symbols, 'buttons') == 0
    assert _word(debug, symbols, 'total_x') == 3
    _neutral(debug)
    report.setdefault('restores', []).append(dict(label=label, result=result,
        old_pid=old_process.pid, old_returncode=old_process.poll(), new_pid=debug.vm.process.pid,
        cpu_exact=True, report_sha256=hashlib.sha256(raw_report).hexdigest(), neutral_input=True))
    return symbols


def test_native_int33_driver_motion_buttons_and_neutral_hot_cold_checkpoint(
        tmp_path, clock_runtime, clock_disk, mouse_inputs):
    disk = prepare_mouse_disk(clock_disk['image'], tmp_path / 'mouse-boot.img',
                              mouse_inputs['driver'], clock_runtime['mcopy'])
    code, offsets = int33_mouse(tmp_path, clock_runtime['nasm'])
    binary = tmp_path / 'MOUSE.COM'
    binary.write_bytes(code)
    db = tmp_path / 'mouse.fdb'
    report = dict(format='fdisbull-authored-int33-mouse-native-1',
        driver_sha256=CTMOUSE_SHA256, disk={k: str(v) if isinstance(v, Path) else v.hex()
            if isinstance(v, bytes) else v for k, v in disk.items()}, success=False,
        held_or_pending_restore_qualified=False)
    options = launch_options(clock_runtime, disk, qemu_clock='virtual',
        qemu_checkpoint_tool=mouse_inputs['checkpoint'], boot_timeout_ms=30000)
    try:
        with Project.create(db, binary, image='com') as project:
            with project.debugger(clock_runtime['executable'], tmp_path, **options) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['ready'])
                assert _word(debug, symbols, 'installed') == 0xffff
                assert _word(debug, symbols, 'driver_buttons') in (2, 3, 0xffff)
                assert _word(debug, symbols, 'vector_segment') != 0
                assert _word(debug, symbols, 'total_x') == _word(debug, symbols, 'total_y') == 0
                # CuteMouse updateposition bypasses adaptive gain for packet
                # magnitudes <=4 at its default senscoeff=256. Use that
                # externally specified branch, rather than fit observed gain.
                debug.mouse_move_relative(3, 0)
                left = debug.mouse_button_down('left')['lease']
                pending, paused_cpu = deepcopy(debug.input_state()), debug.registers()
                with pytest.raises(ValueError, match='released machine input'):
                    debug.save_state()
                assert debug.input_state() == pending and debug.registers() == paused_cpu
                pressed = park(debug, symbols['first_pressed'])
                assert _word(debug, symbols, 'stage') == 1
                assert _word(debug, symbols, 'total_x') == 3 and _word(debug, symbols, 'total_y') == 0
                assert _word(debug, symbols, 'buttons') == 1
                held = deepcopy(debug.input_state())
                with pytest.raises(ValueError, match='released machine input'):
                    debug.save_state()
                assert debug.input_state() == held and debug.vm.process.poll() is None
                debug.mouse_button_up(left)
                released = park(debug, symbols['checkpoint'])
                _neutral(debug)
                assert _word(debug, symbols, 'stage') == 2 and _word(debug, symbols, 'buttons') == 0
                cpu = debug.registers()
                raw_report = read_bytes(debug, symbols['report'], offsets['report_size'])
                captured_epoch = debug.dos_process_info()['capture_epoch']
                captured_run = debug.run_id
                saved = debug.save_state('mouse-neutral.state')
                assert saved['metadata']['format'] == 'fdisbull-qemu-dos-process-qcow2-v2'
                report.update(saved=saved, first_press=pressed, first_release=released,
                    captured_cpu=cpu, captured_report_sha256=hashlib.sha256(raw_report).hexdigest(),
                    pending_capture_refused=True, held_capture_refused=True)
                _continue_mouse(debug, symbols, report, 'before-hot-restore')
                old_process = debug.vm.process
                symbols = _restored(debug, saved, old_process, captured_epoch, cpu,
                                    raw_report, offsets, report, 'hot')
                with pytest.raises(ValueError, match='owned unused physical input lease'):
                    debug.mouse_button_up(left)
                _continue_mouse(debug, symbols, report, 'after-hot-restore')
                hot_owner = debug.vm.process
            assert hot_owner.poll() is not None

        # New Project and launcher: saved history does not reconnect an owner.
        with Project(db) as project:
            assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
            export = tmp_path / 'cold-mouse.state'
            project.debug_export(saved['artifact'], export)
            assert digest(export) == saved['sha256'] and export.stat().st_size == saved['size']
            with project.debugger(clock_runtime['executable'], tmp_path, **options) as debug:
                assert debug.run_id != captured_run
                launch_epoch = debug.dos_process_info()['capture_epoch']
                old_process = debug.vm.process
                symbols = _restored(debug, saved, old_process, launch_epoch, cpu,
                                    raw_report, offsets, report, 'cold')
                assert debug.dos_process_info()['capture_epoch'] != captured_epoch
                _continue_mouse(debug, symbols, report, 'after-cold-restore')
                completed = debug.run(timeout_ms=5000)
                assert_completion(debug, completed, exit_code=42)
                report['completion'] = completed
                cold_owner = debug.vm.process
            assert cold_owner.poll() is not None
        report['success'] = True
    finally:
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == disk['source_sha256']
        assert digest(disk['image']) == disk['prepared_sha256']
        assert digest(mouse_inputs['driver']) == CTMOUSE_SHA256
        (tmp_path / 'native-mouse.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
