"""Same-byte BIOS same-mode reapply, using native timing and no pixel reads."""
from fractions import Fraction
import hashlib
import os
import struct

import pytest

from support.dos_process_fixture import assemble, digest
from support.paired_video_frame_oracle import vga_geometry
from test_dosbox_vga_chain4_timing_native import _first_phase_probe, _ns, _timing_producer
from test_paired_video_frame_native import _owner, _write_json
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, live_word, process_record, read_bytes
from test_qemu_mode13_paired_phase_native import (
    MODEL, _advance_exact_window, _mode13_owner, _read_geometry, _verify_rows,
)


REAPPLY_DELAY_TICKS = 2300
RAW_BYTES = 17
BODY = f'''
bits 16
org 100h
    nop
    push cs
    pop ds
    mov ax,0013h
    int 10h
    mov di,raw_before
    call census
    in al,61h
    and al,0fch
    out 61h,al
    mov al,0b4h
    out 43h,al
    xor al,al
    out 42h,al
    out 42h,al
    in al,61h
    or al,1
    out 61h,al
warm:
    cmp byte [go],0
    jz warm
    mov dx,3dah
    mov ecx,1000000
.low:
    in al,dx
    test al,8
    jz .wait_rise
    dec ecx
    jnz .low
    jmp fault_stop
.wait_rise:
    mov ecx,1000000
.rise:
    in al,dx
    test al,8
    jnz .rising
    dec ecx
    jnz .rise
    jmp fault_stop
.rising:
    call pit
    mov [rise_count],ax
    mov ecx,1000000
.anchor:
    call pit
    mov bx,[rise_count]
    sub bx,ax
    cmp bx,{REAPPLY_DELAY_TICKS}
    jae .pre
    dec ecx
    jnz .anchor
    jmp fault_stop
.pre:
    mov [before_count],ax
    mov ax,0013h
bios13:
    int 10h
    call pit
    mov [after_count],ax
    mov di,raw_after
    call census
    mov byte [returned],1
held:
    jmp held
fault_stop:
    ud2

pit:
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
    ret

census:
    cld
    mov dx,3cch
    in al,dx
    mov [di],al
    inc di
    mov si,ports
    mov cx,{RAW_BYTES - 1}
.next:
    lodsw
    mov dx,ax
    lodsb
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    loop .next
    ret

ports:
    dw 3c4h
    db 1
%macro register 1
    dw 3d4h
    db %1
%endmacro
    register 0h
    register 6h
    register 7h
    register 9h
    register 10h
    register 11h
    register 12h
    register 15h
    register 16h
    register 17h
    dw 3c4h
    db 4
    dw 3ceh
    db 5
    dw 3ceh
    db 6
    register 0ch
    register 0dh

go: db 0
returned: db 0
rise_count: dw 0
before_count: dw 0
after_count: dw 0
raw_before: times {RAW_BYTES} db 0
raw_after: times {RAW_BYTES} db 0
    db 'REAP'
    dw warm,bios13,held,fault_stop,go,returned,rise_count,raw_before,raw_after
'''


def _program(tmp_path, nasm):
    code = assemble(tmp_path, 'mode13-reapply', BODY, nasm)
    assert code[-22:-18] == b'REAP'
    symbols = dict(zip(('warm', 'bios13', 'held', 'fault_stop', 'go', 'returned', 'rise', 'before', 'after'),
                       struct.unpack('<9H', code[-18:]), strict=True))
    assert code[symbols['bios13'] - 0x100:symbols['bios13'] - 0xfe] == b'\xcd\x10'
    return code, symbols


def _pre_post(read, addr, evidence):
    before = read(addr['before'], RAW_BYTES)
    after = read(addr['after'], RAW_BYTES)
    evidence.update(raw_before=before.hex(), raw_after=after.hex())
    assert before == after and before[12] & 8 and before[13] & 0x60 == 0x40
    assert before[14] & 1 and before[15:17] == bytes(2)
    vga_geometry(before[:12])
    rise, entry, returned = struct.unpack('<3H', read(addr['rise'], 6))
    delay = (rise - entry) & 0xffff
    bios = (entry - returned) & 0xffff
    evidence['pit'] = {'rise_count': rise, 'before_count': entry, 'after_count': returned,
                       'entry_after_vsync_ticks': delay, 'bios_duration_ticks': bios}
    assert REAPPLY_DELAY_TICKS <= delay <= REAPPLY_DELAY_TICKS + 4
    assert bios < 32768


def _observed_dosbox_lattice(timing):
    assert timing['model'] == 'dosbox-vga-chain4-row-timing-v1'
    phase, line = timing['physical_phase'], timing['line_period_ns']
    assert phase in (0, 1) and line > 0
    rows = timing['rows']
    assert [row['physical_line'] for row in rows] == list(range(phase, 400, 2))
    first = timing['first_callback_scheduled_ns']
    scheduled = [row['scheduled_ns'] for row in rows]
    gaps = [right - left for left, right in zip(scheduled, scheduled[1:])]
    assert min(gaps) > 0
    lateness = [_ns(row['actual']) - intended for row, intended in zip(rows, scheduled, strict=True)]
    assert min(lateness) >= -Fraction(1, 2) and 8 * max(lateness) < line
    drift = [due - first - row['physical_line'] * line for due, row in zip(scheduled, rows, strict=True)]
    follows_initial_lattice = all(abs(value) <= Fraction(row['physical_line'] + 2, 2)
                                  for value, row in zip(drift, rows, strict=True))
    return dict(physical_phase=phase, follows_initial_lattice=follows_initial_lattice,
                row_zero_lattice_drift_ns=drift[0], final_lattice_drift_ns=drift[-1],
                minimum_row_gap_ns=min(gaps), maximum_row_gap_ns=max(gaps))


def test_native_dosbox_same_mode13_reapply_reports_physical_phase(tmp_path):
    executable, executable_sha, wrapper = _timing_producer(tmp_path)
    code, addr = _program(tmp_path, os.environ['NASM'])
    work = tmp_path / 'dosbox'
    work.mkdir()
    evidence = {'producer_sha256': executable_sha, 'fixture_sha256': hashlib.sha256(code).hexdigest(),
                'after_rasters': []}
    try:
        with _owner('dosbox', work, code, addr, {'wrapper': wrapper}, evidence) as adapter:
            def step(previous=None):
                frame = adapter.call('frame.step')
                assert frame['completed'] and frame['stop_reason']['kind'] == 'frame'
                identity = {field: frame[field] for field in ('frame_id', 'mode_id')}
                if previous:
                    assert identity['frame_id'] == previous['frame_id'] + 1
                return identity

            adapter.park('warm')
            current = step()
            current = step(current)
            ordinary = adapter.call('video.probe', {'points': [], **current})
            assert (ordinary['width'], ordinary['height']) == (320, 200)
            arm = adapter.call('video.probe', {'points': [], 'source_timing_palette_index': 1, **current})
            assert arm['source_timing_available'] is False
            current = step(current)
            _first_phase_probe(adapter, current, 1, evidence, 'before_warm')
            adapter.write('go', b'\x01')
            adapter.park('bios13')
            assert int(adapter.call('state.get_registers')['general']['eax'], 16) & 0xffff == 0x13
            assert adapter.read(addr['bios13'], 2) == b'\xcd\x10'
            assert adapter.read(addr['returned'], 1) == bytes(1)
            assert adapter.call('video.probe', {'points': [], **current})['frame_id'] == current['frame_id']
            try:
                for index in range(7):
                    current = step(current)
                    probe = adapter.call('video.probe', {'points': [], 'source_timing_palette_index': 1, **current})
                    state = dict(identity=current, receipt=probe)
                    evidence['after_rasters'].append(state)
                    if index == 0:
                        assert adapter.read(addr['returned'], 1) == b'\x01'
                        _pre_post(adapter.read, addr, evidence)
                    if probe['source_timing_available']:
                        state['lattice'] = _observed_dosbox_lattice(probe['source_timing'])
            finally:
                evidence['post_phases'] = [item.get('lattice', {}).get('physical_phase')
                                           for item in evidence['after_rasters']]
            assert all(type(phase) is int and phase in (0, 1) for phase in evidence['post_phases'])
    finally:
        assert digest(executable) == executable_sha
        _write_json(tmp_path / 'dosbox-mode13-reapply.json', evidence)
    assert evidence['reaped'] and evidence['returncode'] == 0


@pytest.mark.skipif(os.environ.get('FDISBULL_REQUIRE_QEMU_MODE13_PHASE') != '1',
                    reason='Select the exact native QEMU mode-13 phase producer')
def test_native_qemu_same_mode13_reapply_reports_physical_phase(tmp_path, clock_runtime, clock_disk):
    code, offsets = _program(tmp_path, clock_runtime['nasm'])
    evidence = {'after_rasters': []}
    try:
        with _mode13_owner(tmp_path, clock_runtime, clock_disk, code, evidence) as (_, debug):
            info = process_record(debug)
            addr = {name: com_address(info, value) for name, value in offsets.items()}
            park(debug, addr['warm'])
            prior, geometry = _read_geometry(debug)
            period, line = geometry['period_ns'], geometry['line_ns']
            old_setup = debug.video_frame_observe()['native']['mode-setup']
            now = debug.clock_observe()['virtual_ns']
            _advance_exact_window(debug, now + 2 * period)
            warm = debug.video_frame_start()['native']
            initial = (warm['virtual-ns'] // period + 1) * period
            _advance_exact_window(debug, initial + line // 4 + 399 * line + line // 2)
            frame = debug.video_frame_observe()['native']['frame']
            _verify_rows(frame, initial, 1, geometry)
            evidence['before_warm'] = frame

            debug.write_memory(addr['go'], '01', expected_hex='00', space='physical')
            park(debug, addr['bios13'])
            before = debug.clock_observe()['virtual_ns']
            evidence['before_bios_ns'] = before
            assert live_word(debug.registers(), 'rax', 'eax', 'ax') == 0x13
            assert read_bytes(debug, addr['bios13'], 2) == b'\xcd\x10'
            assert read_bytes(debug, addr['returned'], 1) == bytes(1)
            park(debug, addr['held'])
            after = debug.clock_observe()['virtual_ns']
            evidence['returned_bios_ns'] = after
            assert read_bytes(debug, addr['returned'], 1) == b'\x01'
            _pre_post(lambda address, length: read_bytes(debug, address, length), addr, evidence)
            post, new_geometry = _read_geometry(debug)
            assert post['raw'] == prior['raw'] and new_geometry == geometry
            invalidated = debug.video_frame_observe()['native']
            assert invalidated['state'] == 'invalidated'
            setup = invalidated['mode-setup']
            evidence['mode_setup'] = {'before': old_setup, 'after': setup}
            assert old_setup['committed-ns'] < before <= setup['committed-ns'] <= after
            first = (setup['committed-ns'] // period + 1) * period
            assert after < first
            started = debug.video_frame_start()['native']
            assert started['model'] == MODEL and started['mode-setup'] == setup
            assert started['next-deadline-ns'] == first + line // 4
            for index in (0, 1):
                start = first + index * period
                _advance_exact_window(debug, start + line // 4 + (398 + index) * line + line // 2)
                frame = debug.video_frame_observe()['native']['frame']
                evidence['after_rasters'].append(frame)
                _verify_rows(frame, start, index, geometry)
                assert frame['frame-id'] == started['frame-sequence'] + index + 1
    finally:
        _write_json(tmp_path / 'qemu-mode13-reapply.json', evidence)
    assert evidence['reaped'] and evidence['returncode'] == 0
