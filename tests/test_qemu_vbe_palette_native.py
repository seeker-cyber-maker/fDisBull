"""Paired banked VBE scanline/DAC behavior and timed palette replay."""

import json
import os
from hashlib import sha256
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_palette import (
    ACTIVE_RASTER, COM_SHA, DAC6, DAC8, DIRECT, FIRST_COLOR, PITCH, REQUEST, RESULT, TIMED,
    WIDTH, event, expected_rgb, source_with_palette_probe, symbols, updated_palette,
)
from support.paired_video_frame_oracle import PIT_HZ
from support.paired_vbe_status import LINE_TICKS
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE
from test_qemu_vbe_flip_native import read_memory, register
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD, expected_status
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach


PROFILE = 'vga-640x480-palette'
MODEL = 'qemu-vga-640x480-palette-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-13'
ROM = 'fdisbull-vgabios-vbe101-palette.bin'
LAYOUT = 'vbe-banked-101'
DATABASE = 'vbe-palette.fdb'
SCANLINE, WIDTH_DAC, PALETTE = 0x4F06, 0x4F08, 0x4F09
SET, GET, SYNC = 0, 1, 0x80
SUCCESS, FAILED, UNSUPPORTED = 0x004F, 0x014F, 0x024F
LEADING = 490 * LINE
SEED = bytes.fromhex('f1e2d3c4b5a69788')
REGISTER_NAMES = ('ax', 'bx', 'cx', 'dx')
PIXELS = {}
for name, colors, bits in (('dac6', DAC6, 6), ('dac8', DAC8, 8)):
    PIXELS[name] = expected_rgb(PITCH, updated_palette(_RGB, FIRST_COLOR, colors, bits))
TIMED_PALETTE = updated_palette(updated_palette(_RGB, FIRST_COLOR, DAC8, 8), FIRST_COLOR, TIMED, 8)
PIXELS['timed_low'] = expected_rgb(PITCH, TIMED_PALETTE)
PIXELS['timed_high'] = PIXELS['dac8']

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_PALETTE') != '1',
    reason='Select the exact paired VBE palette reference and QEMU producer',
)


def _configuration(debug):
    configuration = debug.vga_configuration_observe()['current']
    return {
        'raw': configuration['raw'],
        'generation': configuration['configuration_generation'],
    }


def _clock(debug):
    return debug.clock_observe()['virtual_ns']


def _write(debug, address, data):
    old = read_memory(debug, address, len(data))
    if old != data:
        debug.write_memory(address, data.hex(), expected_hex=old.hex())


def _call(debug, labels, ax, bx, cx=0, dx=0, *, data=None, gate=DIRECT):
    if data is not None:
        _write(debug, labels['palette_buffer'], data)
    address = labels['palette_go']
    assert read_memory(debug, address, 1) == b'\0'
    _write(debug, address, REQUEST.pack(1, gate, ax, bx, cx, dx))
    site = labels['palette_bios']
    park(debug, site)
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == site
    assert read_memory(debug, site, 2) == b'\xcd\x10'
    assert [register(cpu, key) & 0xFFFF for key in REGISTER_NAMES] == [ax, bx, cx, dx]
    assert (int(cpu['registers']['es'], 0) * 16 + (register(cpu, 'di') & 0xFFFF)
            == labels['palette_buffer'])
    return _clock(debug)


def _return(debug, labels, entered, *, status=SUCCESS, buffer_bytes=None, deadline=None):
    park(debug, labels['palette_return'])
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == labels['palette_return']
    returned = _clock(debug)
    assert returned >= entered
    if deadline is not None:
        assert deadline <= returned < deadline + LINE // 2
    park(debug, labels['palette_done'])
    guest = event(read_memory(debug, labels['palette_result'], RESULT.size))
    assert guest['ax'] == status, guest
    assert [guest[key] for key in REGISTER_NAMES] == [register(cpu, key) & 0xFFFF for key in REGISTER_NAMES]
    assert read_memory(debug, labels['palette_go'], 1) == b'\0'
    assert guest['status_before'] & 8 in (expected_status(entered - 512) & 8, expected_status(entered) & 8)
    assert guest['status_after'] & 8 in (expected_status(returned) & 8, expected_status(returned + 512) & 8)
    assert abs(guest['elapsed_pit_ticks'] - (returned - entered) * PIT_HZ / 10**9) <= 24
    if buffer_bytes is not None:
        guest['buffer'] = read_memory(debug, labels['palette_buffer'], buffer_bytes).hex()
    return {
        'guest': guest,
        'entry_ns': entered,
        'returned_ns': returned,
        'cpu': cpu,
    }


def _transact(debug, labels, ax, bx, cx=0, dx=0, *, data=None,
              status=SUCCESS, buffer_bytes=None):
    entered = _call(debug, labels, ax, bx, cx, dx, data=data)
    return _return(debug, labels, entered, status=status, buffer_bytes=buffer_bytes)['guest']


def _stride_controls(debug, labels):
    configuration = _configuration(debug)
    vram = configuration['raw']['vbe-size']
    maximum = min(8184, vram // HEIGHT // 8 * 8)
    assert maximum >= PITCH

    trials = {}

    def issue(name, subfunction, argument, pitch, *, status=SUCCESS):
        result = _transact(debug, labels, SCANLINE, subfunction, argument, status=status)
        if status == SUCCESS:
            assert (result['bx'], result['cx'], result['dx']) == (pitch, pitch, min(vram // pitch, 0xFFFF))
        if name is not None:
            trials[name] = result
        return _configuration(debug)

    assert issue('current_stride', 1, 0, WIDTH) == configuration
    assert issue('max_stride', 3, 0, maximum) == configuration
    pixels = issue('pixel_stride', 0, 641, PITCH)
    assert pixels['raw']['vbe-line-offset'] == PITCH and pixels['raw']['vbe'][6] == PITCH
    assert pixels['generation'] == configuration['generation'] + 1
    assert issue(None, GET, 0, PITCH) == pixels
    short = issue('small_positive_stride', 2, 1, 8)
    assert short['raw']['vbe-line-offset'] == 8
    assert short['generation'] == pixels['generation'] + 1
    clamped = issue('huge_stride', 2, 0xFFFF, maximum)
    assert clamped['raw']['vbe-line-offset'] == maximum
    assert clamped['generation'] == short['generation'] + 1
    assert issue('zero_stride', 2, 0, maximum, status=UNSUPPORTED) == clamped
    assert issue(None, GET, 0, maximum) == clamped
    # Bytes and pixels are the same only for this 8-bit mode. Exercise the
    # byte setter from a different previous stride so a no-op cannot pass.
    final = issue('byte_stride', 2, 647, PITCH)
    assert final['raw']['vbe-line-offset'] == PITCH
    assert final['generation'] == clamped['generation'] + 1
    assert issue(None, GET, 0, PITCH) == final
    return trials


def _width(debug, labels, expected, *, write=False):
    result = _transact(debug, labels, WIDTH_DAC, expected << 8 if write else GET)
    assert result['bx'] >> 8 == expected
    raw = _configuration(debug)['raw']
    assert raw['dac-8bit'] is (expected == 8)
    assert raw['vbe-line-offset'] == PITCH
    return result


def _palette_read(debug, labels, data):
    sentinel = (SEED * ((len(data) + len(SEED) - 1) // len(SEED)))[:len(data)]
    expected = bytes(sentinel[i] if i % 4 == 3 else bgrx for i, bgrx in enumerate(data))
    guest = _transact(debug, labels, PALETTE, GET, len(data) // 4, FIRST_COLOR,
                      data=sentinel, buffer_bytes=len(data))
    assert bytes.fromhex(guest['buffer']) == expected
    return guest


def _palette_write(debug, labels, data):
    return _transact(debug, labels, PALETTE, SET, len(data) // 4, FIRST_COLOR, data=data)


def _reject_range(debug, labels):
    before = _configuration(debug)
    # Two entries starting at 255 overflow the inclusive palette index bound.
    # A timed rejection must also leave the clock in the same scanline window.
    original = TIMED
    started = _call(debug, labels, PALETTE, SYNC, 2, 255, data=original)
    result = _return(debug, labels, started, status=FAILED, buffer_bytes=len(original))
    assert result['returned_ns'] - started < LINE
    assert bytes.fromhex(result['guest']['buffer']) == original
    assert _configuration(debug) == before
    return result['guest']


def _complete(debug, name, *, start=None):
    result = debug.video_frame_advance(timeout_ms=8000)
    assert result['advance_completed'], result
    state = source(debug)
    frame = state['frame']
    assert state['model'] == MODEL and state['state'] == 'observing'
    assert state['scanout-layout'] == frame['scanout-layout'] == LAYOUT
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (
        WIDTH, HEIGHT, WIDTH * 3, 'RGB888',
    )
    assert (frame['vbe101-origin-bytes'], frame['vbe101-pel'], frame['vbe101-pitch-bytes']) == (0, 0, PITCH)
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    assert frame['dac-8bit'] is (name != 'dac6')
    stamp = frame['frame-start-ns']
    assert stamp % PERIOD == 0 and (start is None or stamp == start)
    assert len(frame['rows']) == HEIGHT
    for row, observed in enumerate(frame['rows']):
        planned = stamp + LINE // 4 + row * LINE
        assert observed['row'] == row and observed['intended-ns'] == planned
        assert planned <= observed['actual-ns'] < planned + LINE
    assert frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
    assert frame['last-sample-ns'] == frame['completed-ns'] == frame['rows'][-1]['actual-ns']
    packed = PIXELS[name]
    assert frame['pixel-sha256'] == sha256(packed).hexdigest()
    verify_export(debug, state, packed)
    return logical(state)['frame']


def _observe_cut(debug, labels, *, rows, frame_start, waiting):
    state = source(debug)
    config = _configuration(debug)
    assert state['state'] == 'observing' and state['frame']['dac-8bit'] and config['raw']['dac-8bit']
    assert state['rows-sampled'] == rows
    assert state['next-deadline-ns'] == frame_start + rows * LINE + LINE // 4
    cpu = debug.registers()
    vector = struct.unpack('<HH', read_memory(debug, 0x40, 4, space='physical'))
    if waiting:
        pc = int(cpu['linear_pc'], 0)
        assert int(cpu['registers']['cs'], 0) == vector[1] >= 0xC000
        assert vector[1] * 16 <= pc < (vector[1] + 0x1000) * 16
        assert pc != labels['palette_return']
        assert register(cpu, 'dx') & 0xFFFF == 0x03DA
    assert read_memory(debug, labels['palette_go'], 1) == bytes([waiting])
    assert read_memory(debug, labels['palette_buffer'], len(TIMED)) == TIMED
    return {
        'source': state,
        'cpu': cpu,
        'config': config,
        'clock_ns': _clock(debug),
        'int10_vector': list(vector),
    }


def _save(debug, labels, *, name, rows, start, waiting, previous):
    cut = _observe_cut(debug, labels, rows=rows, frame_start=start, waiting=waiting)
    assert logical(cut['source'])['frame'] == previous
    verify_export(debug, cut['source'], PIXELS['dac8'])
    artifact = debug.save_state(name)
    after = _observe_cut(debug, labels, rows=rows, frame_start=start, waiting=waiting)
    assert after == cut
    return dict(cut, artifact=artifact['artifact'], sha256=artifact['sha256'],
                rows=rows, frame_start=start, waiting=waiting)


def _load(debug, labels, cut):
    owner = debug.vm.process
    receipt = debug.load_state(cut['artifact'], timeout_ms=60_000)
    assert receipt['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not owner and owner.poll() == 0
    current = _observe_cut(debug, labels, rows=cut['rows'],
                           frame_start=cut['frame_start'], waiting=cut['waiting'])
    old = cut['source']
    assert current['source']['epoch'] != old['epoch'] and current['source']['token'] != old['token']
    assert logical(current.pop('source')) == logical(old)
    assert current == {key: cut[key] for key in current}
    verify_export(debug, source(debug), PIXELS['dac8'])
    return debug.vm.process


def _finish_pending(debug, labels, entered, start):
    before = _complete(debug, 'dac8', start=start)
    result = _return(debug, labels, entered, deadline=start + LEADING)
    assert (result['guest']['status_before'] & 8, result['guest']['status_after'] & 8) == (0, 8)
    assert logical(source(debug))['frame'] == before
    return {'old': before, 'timed': result}


def _finish_transferred(debug, labels, start):
    changed = _complete(debug, 'timed_low', start=start)
    following = _complete(debug, 'timed_low', start=start + PERIOD)
    assert following['frame-id'] == changed['frame-id'] + 1
    readback = _palette_read(debug, labels, TIMED + DAC8[len(TIMED):])
    return {'first': changed, 'following': following, 'palette': readback}


def _reach_transferred(debug, start):
    _reach(debug, start + PERIOD + 95 * LINE + LINE // 2)


def _high_control(debug, labels, start):
    when = start + LEADING + 512
    _reach(debug, when)
    entered = _call(debug, labels, PALETTE, SYNC, 2, FIRST_COLOR, data=DAC8[:len(TIMED)])
    assert when <= entered < when + LINE // 2 and expected_status(entered) == 9
    intact = _complete(debug, 'timed_low', start=start + PERIOD)
    result = _return(debug, labels, entered, deadline=start + PERIOD + LEADING)
    assert result['guest']['status_before'] == result['guest']['status_after'] == 9
    assert logical(source(debug))['frame'] == intact
    restored = _complete(debug, 'timed_high', start=start + 2 * PERIOD)
    assert restored['frame-id'] == intact['frame-id'] + 1
    assert _palette_read(debug, labels, DAC8)['ax'] == SUCCESS
    return {'intact': intact, 'timed': result, 'following': restored}


def _launch(project, directory, runtime, disk, tool):
    return project.debugger(
        runtime['executable'], directory,
        **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise',
                         qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=tool),
    )


def _producer_identity(runtime, tool):
    return {
        'qemu_sha256': digest(runtime['executable']),
        'qemu_img_sha256': digest(tool),
        'rom_sha256': digest(Path(runtime['firmware']) / ROM),
    }


def _owners(processes):
    assert len({p.pid for p in processes.values()}) == len(processes)
    values = {name: {'pid': p.pid, 'returncode': p.poll()} for name, p in processes.items()}
    assert all(p['returncode'] == 0 for p in values.values())
    return values


def _cold_replay(path):
    spec = json.loads(path.read_text())
    runtime, tool, labels, entered, start = (
        spec[key] for key in ('runtime', 'tool', 'labels', 'entry_ns', 'start_ns')
    )
    assert _producer_identity(runtime, tool) == spec['producer']
    with Project(path.parent / DATABASE) as project:
        with _launch(project, path.parent, runtime, spec['disk'], tool) as debug:
            initial = debug.vm.process
            pending = _load(debug, labels, spec['pending'])
            replayed = _finish_pending(debug, labels, entered, start)
            _reach_transferred(debug, start)
            replayed['changed'] = _finish_transferred(debug, labels, start + PERIOD)
            transferred = _load(debug, labels, spec['transferred'])
            changed = _finish_transferred(debug, labels, start + PERIOD)
    return {
        'host_pid': os.getpid(),
        'pending': replayed,
        'transferred': changed,
        'owners': _owners({'cold_initial': initial, 'cold_pending': pending, 'cold_transferred': transferred}),
    }


def _check_pairing(receipt, reference):
    assert reference['authored_com_sha256'] == receipt['authored_com_sha256']
    for name in ('current_stride', 'pixel_stride', 'byte_stride', 'max_stride', 'small_positive_stride',
                 'huge_stride', 'zero_stride', 'width_6', 'set_width_8', 'width_8',
                 'reset_width_6', 'restored_width_6', 'get_dac6', 'get_dac8', 'invalid_range',
                 'timed_low', 'timed_high'):
        assert {key: receipt['trials'][name][key] for key in REGISTER_NAMES} == {
            key: reference['trials'][name][key] for key in REGISTER_NAMES
        }
    for name in ('get_dac6', 'get_dac8', 'invalid_range'):
        assert receipt['trials'][name]['buffer'] == reference['trials'][name]['buffer']
    for name, status in (('timed_low', (0, 8)), ('timed_high', (8, 8))):
        for engine in (receipt, reference):
            trial = engine['trials'][name]
            assert trial['ax'] == SUCCESS
            assert (trial['status_before'] & 8, trial['status_after'] & 8) == status
        elapsed = receipt['trials'][name]['elapsed_pit_ticks']
        assert abs(elapsed - reference['trials'][name]['elapsed_pit_ticks']) < 2 * LINE_TICKS
    for name in ('dac6', 'dac8', 'timed_low', 'timed_low_retained', 'timed_high', 'timed_high_retained'):
        assert receipt['frames'][name]['pixel-sha256'] == reference['frames'][name]['pixel_sha256']


def test_native_vbe_stride_dac_palette_with_pending_and_transferred_restore(tmp_path, clock_runtime, clock_disk):
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    producer = _producer_identity(clock_runtime, tool)
    assert list(producer.values()) == [os.environ[name] for name in (
        'FDISBULL_QEMU_VBE_PALETTE_SHA256',
        'FDISBULL_QEMU_VBE_PALETTE_IMG_SHA256',
        'FDISBULL_QEMU_VBE_PALETTE_ROM_SHA256',
    )]
    reference_path = Path(os.environ['FDISBULL_DOSBOX_VBE_PALETTE_REFERENCE']).resolve(strict=True)
    reference_sha = digest(reference_path)
    assert reference_sha == os.environ['FDISBULL_DOSBOX_VBE_PALETTE_REFERENCE_SHA256']
    reference = json.loads(reference_path.read_text())
    code = assemble(tmp_path, 'vbe-palette', source_with_palette_probe(_SOURCE)
                    + '\ncolors: db ' + ','.join(str(v) for c in _DAC for v in c), clock_runtime['nasm'])
    assert sha256(code).hexdigest() == COM_SHA
    pages, symbols_in_com = symbols(code)
    binary = tmp_path / 'PALETTE.COM'
    binary.write_bytes(code)
    receipt = {
        'profile': PROFILE, 'format': FORMAT, 'producer': producer,
        'authored_com_sha256': COM_SHA, 'dosbox_reference_sha256': reference_sha,
        'frames': {}, 'trials': {}, 'checkpoints': {}, 'completed': False,
    }
    trials, frames, cuts = (receipt[name] for name in ('trials', 'frames', 'checkpoints'))
    owners = {}

    def write():
        (tmp_path / 'vbe-palette-replay.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    try:
        with Project.create(tmp_path / DATABASE, binary, image='com') as project:
            with _launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['source'] = debug.vm.process
                identity = process_record(debug)
                first, planar, banked, _, advance = (com_address(identity, offset) for offset in pages)
                labels = {name: com_address(identity, offset) for name, offset in symbols_in_com.items()}
                park(debug, first)
                debug.write_memory(advance, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(advance, '02', expected_hex='01')
                park(debug, banked)

                trials.update(_stride_controls(debug, labels))
                trials['width_6'] = _width(debug, labels, 6)
                _palette_write(debug, labels, DAC6)
                trials['get_dac6'] = _palette_read(debug, labels, DAC6)
                debug.video_frame_start()
                frames['dac6'] = _complete(debug, 'dac6')
                debug.video_frame_stop()

                trials['set_width_8'] = _width(debug, labels, 8, write=True)
                trials['width_8'] = _width(debug, labels, 8)
                _palette_write(debug, labels, DAC8)
                trials['get_dac8'] = _palette_read(debug, labels, DAC8[:len(TIMED)])
                debug.video_frame_start()
                frames['dac8'] = _complete(debug, 'dac8')
                start = frames['dac8']['frame-start-ns'] + PERIOD
                trials['invalid_range'] = _reject_range(debug, labels)
                entered = _call(debug, labels, PALETTE, SYNC, 2, FIRST_COLOR,
                                data=TIMED, gate=ACTIVE_RASTER)
                assert start - 3 * LINE <= entered < start and expected_status(entered) == 1
                _reach(debug, start + 145 * LINE + LINE // 2)
                pending = _save(debug, labels, name='palette-pending', rows=146,
                                start=start, waiting=True, previous=frames['dac8'])
                cuts['pending'] = pending['sha256']
                write()

                forward = receipt['forward'] = _finish_pending(debug, labels, entered, start)
                trials['timed_low'] = forward['timed']['guest']
                frames['timed_low_retained'] = forward['old']
                _reach_transferred(debug, start)
                transferred = _save(debug, labels, name='palette-transferred', rows=96,
                                    start=start + PERIOD, waiting=False, previous=forward['old'])
                cuts['transferred'] = transferred['sha256']
                forward['changed'] = _finish_transferred(debug, labels, start + PERIOD)
                frames['timed_low'] = forward['changed']['first']
                write()

                owners['hot_pending'] = _load(debug, labels, pending)
                hot = receipt['hot_pending'] = _finish_pending(debug, labels, entered, start)
                _reach_transferred(debug, start)
                hot['changed'] = _finish_transferred(debug, labels, start + PERIOD)
                assert hot == forward
                owners['hot_transferred'] = _load(debug, labels, transferred)
                receipt['hot_transferred'] = _finish_transferred(debug, labels, start + PERIOD)
                assert receipt['hot_transferred'] == forward['changed']
                high = receipt['high_control'] = _high_control(debug, labels, start + 2 * PERIOD)
                frames['timed_high'] = high['following']
                frames['timed_high_retained'] = high['intact']
                trials['timed_high'] = high['timed']['guest']
                debug.video_frame_stop()
                trials['reset_width_6'] = _width(debug, labels, 6, write=True)
                trials['restored_width_6'] = _width(debug, labels, 6)

        receipt['owners'] = _owners(owners)
        path = tmp_path / 'cold-spec.json'
        path.write_text(json.dumps({
            'runtime': {key: str(value) if isinstance(value, Path) else value
                        for key, value in clock_runtime.items()},
            'tool': tool, 'producer': producer, 'labels': labels, 'entry_ns': entered, 'start_ns': start,
            'disk': {'image': str(clock_disk['image'])}, 'pending': pending, 'transferred': transferred,
        }))
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(path)],
            text=True, capture_output=True, timeout=120, check=False,
        )
        (tmp_path / 'cold.log').write_text(child.stdout + child.stderr)
        assert child.returncode == 0, child.stderr
        cold = json.loads(child.stdout)
        assert cold.pop('host_pid') != os.getpid()
        assert not {p.pid for p in owners.values()} & {p['pid'] for p in cold['owners'].values()}
        receipt['owners'].update(cold.pop('owners'))
        receipt['cold'] = cold
        assert cold['pending'] == receipt['forward']
        assert cold['transferred'] == receipt['forward']['changed']
        _check_pairing(receipt, reference)
        receipt['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        write()


if __name__ == '__main__':
    print(json.dumps(_cold_replay(Path(sys.argv[1]))))
