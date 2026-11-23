"""Pinned QEMU counterparts for the authored DOSBox-X Mode 13h witnesses."""
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import struct
import time

import pytest

from support.dos_process_fixture import assemble, digest
from support.paired_video_frame_fixture import TRIAL_BYTES
from support.paired_video_frame_oracle import (
    HEIGHT, PIT_HZ, parse_trial, phase_predictions, rgb_for_rows,
)
from support.qemu_video_frame_fixture import guest_video_timing
from test_dosbox_vga_chain4_timing_native import COM_SHA256, MODE_SWITCH
from test_paired_video_frame_native import (
    WORK_SECONDS, _QemuOwner, _calibration, _write_json, paired_video_program,
)
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, live_word, process_record, read_bytes,
)


pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_MODE13_PHASE') != '1',
    reason='Select exact native QEMU and firmware for the paired Mode 13h witnesses',
)
MODEL = 'qemu-vga-chain4-dosbox-mode13-v1'
SWITCH_SHA256 = '360506d4851aaae7f9bdc328c4b4c66f067789a3704ba3791608ea03ea9577b6'
FIRMWARE = {
    'bios-256k.bin': 'f1d4f396011197eb989029659cde250751cc711c336b8fbbe6f77cfe0dc5dcd8',
    'vgabios-stdvga.bin': '651513519f9e0d5b99d3b051a8f5c68db69e987339b59a441d371068c34c146b',
}
BOOT_SHA256 = '552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc'
WINDOWS = {3: (8991, 40), 4: (8991, 36)}


@contextmanager
def _mode13_owner(tmp_path, runtime, disk, code, evidence):
    assert not any((directory / '.git').exists() for directory in
                   (tmp_path.resolve(), *tmp_path.resolve().parents))
    assert digest(runtime['boot_image']) == disk['source_sha256'] == BOOT_SHA256
    executable_sha = os.environ['FDISBULL_QEMU_MODE13_PHASE_SHA256']
    tool = Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True)
    img_sha = os.environ['FDISBULL_QEMU_MODE13_PHASE_IMG_SHA256']
    firmware = Path(runtime['firmware']).resolve(strict=True)
    assert digest(runtime['executable']) == executable_sha and digest(tool) == img_sha
    assert all(digest(firmware / name) == sha for name, sha in FIRMWARE.items())
    evidence.update(producer_sha256=executable_sha, qemu_img_sha256=img_sha,
                    firmware=FIRMWARE, fixture_sha256=hashlib.sha256(code).hexdigest())
    binary, project = create_project(tmp_path, code, filename='PAIRVID.COM')
    owner = None
    try:
        with project:
            with project.debugger(runtime['executable'], tmp_path,
                    **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise',
                                     qemu_video_source_profile='dosbox-mode13', qemu_checkpoint_tool=str(tool))) as debug:
                owner = debug.vm.process
                evidence['owner_pid'] = owner.pid
                yield project, debug
    finally:
        if owner is not None:
            evidence.update(reaped=owner.poll() is not None, returncode=owner.poll())
        assert binary.read_bytes() == code and digest(disk['image']) == disk['prepared_sha256']
        assert digest(runtime['boot_image']) == BOOT_SHA256
        assert digest(runtime['executable']) == executable_sha and digest(tool) == img_sha
        assert all(digest(firmware / name) == sha for name, sha in FIRMWARE.items())


def _read_geometry(debug):
    current = debug.vga_configuration_observe()['current']
    raw = current['raw']
    crtc = raw['crtc']
    assert raw['display-enabled'] and raw['graphics'][5] & 0x60 == 0x40
    assert raw['sequencer'][4] & 8 and raw['graphics'][6] & 1
    bytes_from_registers = struct.pack('<9BH', raw['misc-output'], raw['sequencer'][1],
                                       *[crtc[index] for index in (0, 4, 5, 6, 7, 0x10, 0x11)],
                                       raw['vbe'][4])
    return current, guest_video_timing(bytes_from_registers)


def _verify_rows(frame, start, phase, geometry):
    line = geometry['line_ns']
    assert frame['source-phase'] == phase and frame['frame-start-ns'] == start
    assert frame['period-ns'] == geometry['period_ns'] and frame['line-period-ns'] == line
    assert (frame['width'], frame['height']) == (320, HEIGHT)
    rows = frame['rows']
    expected = [start + line // 4 + (2 * number + phase) * line for number in range(HEIGHT)]
    assert [row['row'] for row in rows] == list(range(HEIGHT))
    assert [row['intended-ns'] for row in rows] == expected
    lag = [row['actual-ns'] - due for row, due in zip(rows, expected, strict=True)]
    assert min(lag) >= 0 and 8 * max(lag) < line
    return max(lag)


def test_native_current_qemu_mode13_strict_warm_pulses(tmp_path, clock_runtime, clock_disk):
    code, symbols = paired_video_program(tmp_path, clock_runtime['nasm'])
    assert hashlib.sha256(code).hexdigest() == COM_SHA256
    evidence = {'windows': WINDOWS, 'frames': []}
    try:
        with _mode13_owner(tmp_path, clock_runtime, clock_disk, code, evidence) as (project, debug):
            adapter = _QemuOwner(project, debug, tmp_path, symbols, time.monotonic() + WORK_SECONDS)
            geometry, horizontal, nominal = _calibration(adapter, evidence)
            assert WINDOWS == {
                3: (nominal['delay_ticks'] - 1, nominal['width_ticks'] + 3),
                4: (nominal['delay_ticks'] - 1, nominal['width_ticks'] - 1),
            }
            _, programmed = _read_geometry(debug)
            assert horizontal.lo <= Fraction(programmed['line_ns'] * PIT_HZ, 1000000000) <= horizontal.hi
            started = adapter.start()
            assert started['native']['model'] == MODEL
            for number in range(1, 5):
                pulse = number in WINDOWS
                if pulse:
                    delay, width = WINDOWS[number]
                    adapter.write('delay_ticks', struct.pack('<H', delay))
                    adapter.write('width_ticks', struct.pack('<H', width))
                adapter.write('pulse_mode', bytes([pulse]))
                adapter.write('command', b'\x01')
                adapter.park('trial_ready')
                ready_raw = adapter.read(adapter.offsets['trial'], TRIAL_BYTES)
                ready = parse_trial(ready_raw)
                assert (ready['number'], ready['mode']) == (number, pulse)
                before = adapter.before_frame()
                frame_start = (before['native']['virtual-ns'] // programmed['period_ns'] + 1) * programmed['period_ns']
                advance = adapter.advance(before)
                frame = advance['frame']
                record = {'number': number, 'ready_raw': ready_raw.hex(), 'frame': frame}
                evidence['frames'].append(record)
                record['max_callback_lateness_ns'] = _verify_rows(frame, frame_start, 1, programmed)
                mid = parse_trial(adapter.read(adapter.offsets['trial'], TRIAL_BYTES))
                assert mid['post_generation'] == 0
                adapter.park('trial_done')
                trial_raw = adapter.read(adapter.offsets['trial'], TRIAL_BYTES)
                trial = parse_trial(trial_raw)
                record['post_raw'] = trial_raw.hex()
                assert trial['post_generation'] == ready['ready_generation'] + 1
                if pulse:
                    predictions, windows = phase_predictions(horizontal, geometry, trial)
                    expected = predictions[1]['rgb']
                    alternative = predictions[0]['rgb']
                    record.update(timing_windows=windows, expected_sha256=hashlib.sha256(expected).hexdigest(),
                                  alternative_sha256=hashlib.sha256(alternative).hexdigest())
                else:
                    expected = rgb_for_rows(['A'] * HEIGHT)
                record['prediction_preceded_rgb_export'] = True
                _write_json(tmp_path / f'frame-{number}-prior-prediction.json', record)
                rgb, _ = adapter.capture(number, advance)
                record['rgb_sha256'] = hashlib.sha256(rgb).hexdigest()
                assert rgb == expected
                if pulse:
                    assert rgb != alternative and rgb != rgb_for_rows(['C'] * HEIGHT)
    finally:
        _write_json(tmp_path / 'qemu-mode13-warm-receipt.json', evidence)
    assert evidence['reaped'] and evidence['returncode'] == 0


def _advance_exact_window(debug, target):
    before = debug.clock_observe()
    delta = target - before['virtual_ns']
    assert delta > 0
    return budget_receipt(debug.clock_advance(delta, timeout_ms=5000), delta, before=before)


def test_native_current_qemu_first_and_steady_after_same_text_mode13_edge(tmp_path, clock_runtime, clock_disk):
    code = assemble(tmp_path, 'mode13-first-raster', MODE_SWITCH, clock_runtime['nasm'])
    assert code[-14:-10] == b'FDBF' and hashlib.sha256(code).hexdigest() == SWITCH_SHA256
    warm, bios, _fault, go, entered = struct.unpack('<5H', code[-10:])
    text_poll = b'\x80\x3e' + struct.pack('<H', go) + b'\x02'
    assert code.count(text_poll) == 1
    post_bios = b'\xcd\x10\xc6\x06' + struct.pack('<H', entered) + b'\x01'
    assert code[bios - 0x100:].startswith(post_bios)
    offsets = {'warm': warm, 'text': 0x100 + code.index(text_poll), 'bios': bios,
               'returned': bios + len(post_bios), 'go': go, 'entered': entered}
    evidence = {'anchor_rule': 'first whole VGA period plus period//16 while held in text'}
    try:
        with _mode13_owner(tmp_path, clock_runtime, clock_disk, code, evidence) as (_, debug):
            info = process_record(debug)
            address = {key: com_address(info, offset) for key, offset in offsets.items()}
            park(debug, address['warm'])
            old, geometry = _read_geometry(debug)
            evidence['warm_programming'] = old
            period, line = geometry['period_ns'], geometry['line_ns']
            assert period == line * 449
            debug.write_memory(address['go'], '01', expected_hex='00', space='physical')
            park(debug, address['text'])
            text = debug.vga_configuration_observe()['current']
            assert text['raw']['graphics'][6] & 1 == 0
            assert debug.video_frame_observe()['native'].get('mode-setup') is None
            now = debug.clock_observe()['virtual_ns']
            anchor = (now // period + 1) * period + period // 16
            evidence['held_text_window'] = _advance_exact_window(debug, anchor)
            assert read_bytes(debug, address['go'], 1) == b'\x01'
            assert read_bytes(debug, address['entered'], 1) == b'\0'
            debug.write_memory(address['go'], '02', expected_hex='01', space='physical')
            park(debug, address['bios'])
            before = debug.clock_observe()['virtual_ns']
            evidence['before_bios_ns'] = before
            assert anchor <= before < anchor + line
            assert live_word(debug.registers(), 'rax', 'eax', 'ax') == 0x13
            assert read_bytes(debug, address['bios'], 2) == b'\xcd\x10'
            park(debug, address['returned'])
            after = debug.clock_observe()['virtual_ns']
            evidence['returned_bios_ns'] = after
            assert read_bytes(debug, address['entered'], 1) == b'\x01'
            new, entered_geometry = _read_geometry(debug)
            evidence['returned_programming'] = new
            assert new['configuration_generation'] > text['configuration_generation']
            assert entered_geometry == geometry
            observed = debug.video_frame_observe()['native']
            setup = observed.get('mode-setup')
            evidence['mode_setup'] = setup
            first = (anchor // period + 1) * period
            evidence['first_frame_start_ns'] = first
            assert setup and before <= setup['committed-ns'] <= after < first, evidence
            started = debug.video_frame_start()['native']
            assert started['model'] == MODEL and started['mode-setup'] == setup
            assert started['next-deadline-ns'] == first + line // 4
            for index in (0, 1):
                start = first + index * period
                _advance_exact_window(debug, start + line // 4 + (398 + index) * line + line // 2)
                native = debug.video_frame_observe()['native']
                frame = native['frame']
                evidence[f'phase_{index}'] = frame
                evidence[f'phase_{index}_max_callback_lateness_ns'] = _verify_rows(frame, start, index, geometry)
                assert frame['frame-id'] == started['frame-sequence'] + index + 1
    finally:
        _write_json(tmp_path / 'qemu-mode13-first-receipt.json', evidence)
    assert evidence['reaped'] and evidence['returncode'] == 0
