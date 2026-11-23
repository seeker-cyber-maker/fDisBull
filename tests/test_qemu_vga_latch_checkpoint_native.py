"""Mode X page choices across native latch boundaries and instrumented restore."""
from copy import deepcopy
from hashlib import sha256
import json
import os
import struct

import pytest

from fdisbull.project import Project
from fdisbull.qemu_instrumented_checkpoint import VIDEO_LATCH_FORMAT
from fdisbull.qemu_video_checkpoint import LATCH_MODEL, LATCH_PROFILE
from support.dos_process_fixture import assemble, digest
from test_dosbox_frame_source_probe_native import _held_pages, _pixels
from test_dosbox_unchained_timed_latch_native import _delta, _guest as _paired_guest
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vga_phase_checkpoint_native import _reach


pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_LATCH') != '1',
    reason='Select the exact native QEMU timed VGA latch witness',
)


def _guest():
    code = _held_pages()
    anchor = 'page_b:\n    nop\n    jmp page_b\n'
    assert code.count(anchor) == 1
    return code.replace(anchor, '''page_b:
    nop
    cmp byte [go],2
    jne page_b
    mov ax,400ch
    call crtc
returned_a:
    nop
    jmp returned_a
''').replace('dw page_a,page_b,go', 'dw page_a,page_b,returned_a,go')


def _native(debug):
    return debug.video_frame_observe()['native']


def _logical(state):
    state = deepcopy(state)
    state.pop('token')
    state.pop('epoch')
    if 'frame' in state:
        state['frame'].pop('epoch')
    return state


def _page(debug):
    crtc = debug.vga_configuration_observe()['current']['raw']['crtc']
    return (crtc[12] << 8) | crtc[13]


def _finish(debug, origin, first):
    done = debug.video_frame_advance(timeout_ms=5000)
    assert done['advance_completed'], done
    state = _native(debug)
    frame = state['frame']
    assert state['model'] == LATCH_MODEL
    assert frame['page-latch']['origin-bytes'] == origin * 4
    assert len(frame['rows']) == 200
    palette = [bytes((v << 2) | (v >> 4) for v in (color, color * 2, color * 3))
               for color in range(17)]
    rgb = b''.join(palette[index] for index in _pixels(first))
    assert frame['pixel-sha256'] == sha256(rgb).hexdigest()
    return _logical(state)


def _restore(debug, artifact, saved):
    previous = debug.vm.process
    selected = debug.load_state(artifact, timeout_ms=60000)
    assert selected['instrumentation']['format'] == VIDEO_LATCH_FORMAT
    assert debug.vm.process is not previous and previous.poll() == 0
    observed = _native(debug)
    assert observed['token'] != saved['token'] and observed['epoch'] != saved['epoch']
    assert _logical(observed) == _logical(saved)


def test_unchained_page_latch_replays_early_and_late_writes(
        tmp_path, clock_runtime, clock_disk, record_property):
    assert digest(clock_runtime['executable']) == os.environ['FDISBULL_QEMU_VGA_LATCH_SHA256']
    tool = os.environ['FDISBULL_QEMU_IMG']
    assert digest(tool) == os.environ['FDISBULL_QEMU_VGA_LATCH_IMG_SHA256']
    code = assemble(tmp_path, 'latch-pages', _guest(), clock_runtime['nasm'])
    assert code[-12:-8] == b'SVGA'
    a, b, returned_a, flag = struct.unpack('<4H', code[-8:])
    binary = tmp_path / 'PAGES.COM'
    binary.write_bytes(code)
    record_property('authored_com_sha256', digest(binary))
    database = tmp_path / 'latch.fdb'

    def launch(project):
        return project.debugger(clock_runtime['executable'], tmp_path,
            **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                qemu_retrace='precise', qemu_checkpoint_tool=tool,
                qemu_video_source_profile=LATCH_PROFILE))

    with Project.create(database, binary, image='com') as project:
        with launch(project) as debug:
            process = process_record(debug)
            a, b, returned_a, flag = (com_address(process, n) for n in (a, b, returned_a, flag))
            park(debug, a)
            debug.video_frame_start()
            first_a = _finish(debug, 0x4000, 1)
            latch = first_a['next-deadline-ns']
            assert first_a['awaiting-page-latch'] and _page(debug) == 0x4000

            debug.write_memory(flag, '01', expected_hex='00')
            park(debug, b)
            early = _native(debug)
            assert early['awaiting-page-latch'] and early['virtual-ns'] < latch
            assert early['frame']['page-latch']['origin-bytes'] == 0x10000
            assert _page(debug) == 0x8000
            early_saved = debug.save_state('early-page')
            first_b = _finish(debug, 0x8000, 5)
            _restore(debug, early_saved['artifact'], early)
            assert _page(debug) == 0x8000 and _finish(debug, 0x8000, 5) == first_b

            late_target = first_b['next-deadline-ns']
            line = first_b['frame']['line-period-ns']
            _reach(debug, late_target + line // 4)
            selected = _native(debug)
            assert not selected['awaiting-page-latch'] and selected['rows-sampled'] == 0
            assert selected['pending-page-latch']['origin-bytes'] == 0x20000
            debug.write_memory(flag, '02', expected_hex='01')
            park(debug, returned_a)
            after_write = _native(debug)
            assert after_write['virtual-ns'] > selected['pending-page-latch']['actual-ns']
            assert after_write['pending-page-latch'] == selected['pending-page-latch']
            assert _page(debug) == 0x4000

            first_row = selected['next-deadline-ns']
            _reach(debug, first_row + 2 * 64 * line + line // 2)
            partial = _native(debug)
            assert partial['rows-sampled'] == 65
            assert partial['pending-page-latch']['origin-bytes'] == 0x20000
            partial_saved = debug.save_state('partial-page')
            expected_b = _finish(debug, 0x8000, 5)
            expected_a = _finish(debug, 0x4000, 1)
            last_hot_process = debug.vm.process
        assert last_hot_process.poll() == 0

    with Project(database) as project:
        with launch(project) as debug:
            _restore(debug, partial_saved['artifact'], partial)
            assert _page(debug) == 0x4000
            assert _finish(debug, 0x8000, 5) == expected_b
            assert _finish(debug, 0x4000, 1) == expected_a
            last_cold_process = debug.vm.process
        assert last_cold_process.poll() == 0
    assert binary.read_bytes() == code
    assert digest(clock_disk['image']) == clock_disk['prepared_sha256']


def test_unchained_page_latch_replays_the_paired_guest_pit_witness(
        tmp_path, clock_runtime, clock_disk, record_property):
    """Use the exact DOSBox reference program and guest-measured write phases."""
    native_sha = digest(clock_runtime['executable'])
    assert native_sha == os.environ['FDISBULL_QEMU_VGA_LATCH_SHA256']
    code = assemble(tmp_path, 'paired-latch', _paired_guest(), clock_runtime['nasm'])
    assert code[-12:-8] == b'LVGA'
    assert sha256(code).hexdigest() == '8bfc1d46e3f3c4c8b83df416d4b814c38cc340946f7f1fef66117a8ee9e54434'
    hold, out, report, command = struct.unpack('<4H', code[-8:])
    assert code[out - 0x100:out - 0x100 + 1] == b'\xef'
    binary = tmp_path / 'LATCH.COM'
    binary.write_bytes(code)
    receipt = dict(backend_sha256=native_sha, authored_com_sha256=digest(binary), trials=[])
    record_property('authored_com_sha256', digest(binary))

    try:
        with Project.create(tmp_path / 'pair.fdb', binary, image='com') as project:
            with project.debugger(clock_runtime['executable'], tmp_path,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                        qemu_retrace='precise', qemu_video_source_profile=LATCH_PROFILE)) as debug:
                owner = debug.vm.process
                process = process_record(debug)
                hold, out, report, command = (com_address(process, n) for n in (hold, out, report, command))
                park(debug, hold)
                debug.video_frame_start()
                _finish(debug, 0x4000, 1)

                for number, old, new, sequence in (
                        (1, 0x4000, 0x8000, [0x8000]),
                        (2, 0x8000, 0x4000, [0x8000, 0x4000])):
                    trial = dict(phase=number, requested_crtc_start=new, frames=[])
                    receipt['trials'].append(trial)
                    debug.write_memory(command, f'{number:02x}', expected_hex='00')
                    park(debug, out)
                    regs = debug.registers()['registers']
                    assert int(regs.get('rax', regs.get('eax')), 0) & 65535 == new | 0x0c
                    assert int(regs.get('rdx', regs.get('edx')), 0) & 65535 == 0x03d4
                    pre = _native(debug)
                    trial['pre'] = {k:pre[k] for k in ('virtual-ns', 'awaiting-page-latch', 'next-deadline-ns')}
                    assert pre['frame']['page-latch']['origin-bytes'] == old * 4
                    assert _page(debug) == old
                    debug.step(count=1, timeout_ms=5000)
                    assert int(debug.registers()['linear_pc'], 0) == out + 1
                    assert _page(debug) == new
                    after = _native(debug)
                    assert after['frame'] == pre['frame']
                    if number == 1:
                        assert after['awaiting-page-latch']
                        assert after['virtual-ns'] < after['next-deadline-ns']
                    else:
                        assert after['pending-page-latch'] == pre['pending-page-latch']
                        assert after['pending-page-latch']['origin-bytes'] == old * 4
                    for origin in sequence:
                        frame = _finish(debug, origin, 1 if origin == 0x4000 else 5)['frame']
                        trial['frames'].append(dict(
                            frame=frame['frame-id'], latch=frame['page-latch'], rgb_sha256=frame['pixel-sha256']))
                    raw = bytes.fromhex(debug.memory(report, length=13, space='virtual')['hex'])
                    edge, period, started, ended, following, before, after, completed = struct.unpack('<5H3B', raw)
                    trial['guest'] = dict(before_status=before, after_status=after, completed=completed,
                                          bracket=_delta(started, ended), since_rise=_delta(edge, started))
                    assert completed == number and _delta(started, ended) < 96, trial
                    if number == 1:
                        trial['guest']['after_out_until_rise'] = _delta(ended, following)
                        assert not ((before | after) & 8) and 15 <= _delta(ended, following) <= 400, trial
                        assert 16000 <= period <= 18000 and 16000 <= _delta(edge, following) <= 18000, trial
                    else:
                        assert before & after & 8 and _delta(edge, started) < 100, trial
            assert owner.poll() == 0
    finally:
        if 'owner' in locals():
            receipt['owner_returncode'] = owner.poll()
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'qemu-paired-latch.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
