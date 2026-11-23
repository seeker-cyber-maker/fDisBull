"""Exact paired guest native Mode 12h and VBE 101h scanout and restore."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE, _check_pixels
from test_qemu_vga_phase_checkpoint_native import _reach


PROFILE = 'vga-640x480'
MODEL = 'qemu-vga-640x480-scanline-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-8'
COM_SHA256 = 'f3cb52889fb82b2f3fdf44af0c85a4d00b4dde3ba71640981945e79d337d9b8e'
DOSBOX_REFERENCE = 'd4ca5f85c68473b191a5eba9e5b037886e623eb09f6a147ed681f41c226ede15'
DOSBOX_RGB = {
    'vga-mode12': 'e90cbb4dbbf102e25ced01ef9ef7b33bd64d4a5d79135888bfd44194c8f67f18',
    'vbe-banked-101': '5a5656922ff09ce0d4292da990de6ea5cd13fd2f17f883be9cf863c574cbef27',
}
WIDTH, HEIGHT = 640, 480
TIMING = {
    'vga-mode12': (31_700, 16_642_500),
    'vbe-banked-101': (27_208, 14_284_200),
}

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_640') != '1',
    reason='Select the exact native QEMU VGA 640×480 scanout witness',
)


def logical(state):
    value = deepcopy(state)
    value.pop('token')
    value.pop('epoch')
    if 'frame' in value:
        value['frame'].pop('epoch')
    return value


def clock_identity(debug):
    clock = debug.clock_observe()
    return {key: clock[key] for key in ('epoch', 'counter', 'virtual_ns')}


def source(debug):
    return debug.video_frame_observe()['native']


def expected_pixels(page):
    if page == 'planar':
        upper = b''.join(_RGB[index] for index in range(8, 16)) * 80
        lower = b''.join(_RGB[index] for index in range(7, -1, -1)) * 80
        tail = (_RGB[9] + _RGB[10]) * 320
        return upper * 239 + lower * 240 + tail
    return (b''.join(_RGB[index] * 65536 for index in range(1, 5))
            + _RGB[5] * (WIDTH * HEIGHT - 4 * 65536))


def paint_rows(rgb, rows, color):
    packed = bytearray(rgb)
    stride = WIDTH * 3
    for row in rows:
        packed[row * stride:(row + 1) * stride] = _RGB[color] * WIDTH
    return packed


def timing_geometry(debug, layout):
    measured = debug.retrace_observe()
    configuration = debug.vga_configuration_observe()['current']
    native = measured['timing']
    crtc = configuration['raw']['crtc']
    raw = configuration['raw']
    assert not raw['dac-8bit'] and raw['vbe-start-address'] == 0
    if layout == 'vga-mode12':
        htotal = crtc[0] + 5
        lines = (crtc[6] | ((crtc[7] & 1) << 8) | ((crtc[7] & 0x20) << 4)) + 2
        assert native['htotal'] == htotal == 100 and lines == 525
        assert native['total-chars'] == lines * htotal and native['ticks-per-char'] == 317
        assert (htotal * native['ticks-per-char'],
                native['total-chars'] * native['ticks-per-char']) == TIMING[layout]
        assert raw['vbe'][4] == 0 and crtc[0x13] * 2 == 80
        assert raw['sequencer'][2] == 8 and raw['sequencer'][4] == 6
        assert raw['graphics'][5] == 0
    else:
        assert layout == 'vbe-banked-101'
        assert raw['vbe'][1:6] == [640, 480, 8, 1, 4]
        assert raw['vbe-line-offset'] == WIDTH and raw['bank-offset'] == 4 * 65536
    return dict(vga=configuration, legacy_retrace=measured)


def finish(debug, layout, first_deadline, expected):
    line_ns, period_ns = TIMING[layout]
    advance = debug.video_frame_advance(timeout_ms=8000)
    assert advance['advance_completed'], advance
    state = source(debug)
    frame = state['frame']
    assert state['model'] == MODEL and state['state'] == 'observing'
    assert state['scanout-layout'] == frame['scanout-layout'] == layout
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (
        WIDTH, HEIGHT, WIDTH * 3, 'RGB888')
    assert (frame['line-period-ns'], frame['period-ns']) == (line_ns, period_ns)
    assert frame['frame-start-ns'] == first_deadline - line_ns // 4
    assert len(frame['rows']) == HEIGHT
    for ordinal, row in enumerate(frame['rows']):
        predicted = first_deadline + ordinal * line_ns
        assert row['row'] == ordinal and row['intended-ns'] == predicted
        assert predicted <= row['actual-ns'] < predicted + line_ns
    assert frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
    assert frame['last-sample-ns'] == frame['rows'][-1]['actual-ns'] == frame['completed-ns']
    assert frame['pixel-sha256'] == sha256(expected).hexdigest()
    verify_export(debug, state, expected)
    return logical(state)


def verify_export(debug, state, expected):
    before, registers = clock_identity(debug), debug.registers()
    rgba = debug.video_frame_rgba(stream=state['token'], frame_id=state['frame']['frame-id'], timeout_ms=8000)
    assert (rgba.width, rgba.height) == (WIDTH, HEIGHT)
    assert rgba.pixels[3::4] == bytes([255]) * (WIDTH * HEIGHT)
    rgb = bytearray(WIDTH * HEIGHT * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = rgba.pixels[0::4], rgba.pixels[1::4], rgba.pixels[2::4]
    assert rgb == expected
    assert clock_identity(debug) == before and debug.registers() == registers


def restore(debug, artifact, saved, *, retained_rgb=None):
    previous = debug.vm.process
    receipt = debug.load_state(artifact, timeout_ms=60_000)
    assert receipt['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not previous and previous.poll() == 0
    new = source(debug)
    assert new['token'] != saved['token'] and new['epoch'] != saved['epoch']
    assert logical(new) == logical(saved)
    if retained_rgb is not None:
        verify_export(debug, new, retained_rgb)
    return debug.vm.process


def write_retained_bank(debug, rows, color):
    before = clock_identity(debug)
    registers = debug.registers()
    expected = '05' * WIDTH
    replacement = f'{color:02x}' * WIDTH
    results = []
    for row in rows:
        offset = row * WIDTH - 4 * 65536
        assert 0 <= offset < offset + WIDTH <= 65536
        address = 0xA0000 + offset
        assert debug.memory(address, length=WIDTH, space='physical')['hex'] == expected
        result = debug.write_memory(address, replacement, expected_hex=expected, space='physical')
        assert result['after_hex'] == replacement
        results.append(dict(row=row, address=address, sha256=sha256(bytes.fromhex(result['after_hex'])).hexdigest()))
    assert clock_identity(debug) == before and debug.registers() == registers
    return results


def cold_replay_job(spec_path):
    spec = json.loads(spec_path.read_text())
    directory = spec_path.parent
    page, layout = spec['page'], spec['layout']
    _, period = TIMING[layout]
    intact = first = expected_pixels(page)
    following = first
    if spec['mutation'] is not None:
        past, ahead, color = spec['mutation']
        first = paint_rows(first, (ahead,), color)
        following = paint_rows(following, (past, ahead), color)
    exe, helper = Path(spec['runtime']['executable']), Path(spec['checkpoint_tool'])
    assert digest(exe) == spec['qemu_sha256'] and digest(helper) == spec['qemu_img_sha256']
    with Project(directory/'timed-vga.fdb') as project:
        with project.debugger(exe, directory, **launch_options(
                spec['runtime'], spec['disk'], qemu_clock='virtual', qemu_retrace='precise',
                qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=str(helper))) as debug:
            entry = debug.vm.process
            resumed = restore(debug, spec['artifact'], spec['saved'], retained_rgb=intact)
            actual = [finish(debug, layout, spec['deadline'], first),
                      finish(debug, layout, spec['deadline']+period, following)]
    assert entry is not resumed and entry.poll() == resumed.poll() == 0
    return dict(host_pid=os.getpid(), future=actual, owners={
        'cold_entry':dict(pid=entry.pid,returncode=entry.poll()),
        'cold_restored':dict(pid=resumed.pid,returncode=resumed.poll())})


@pytest.mark.parametrize(('page', 'layout', 'sampled'), [
    ('planar', 'vga-mode12', 240), ('banked', 'vbe-banked-101', 445),
])
def test_vga_640_timed_full_rows_and_partial_replay(tmp_path, clock_runtime, clock_disk,
                                                       page, layout, sampled, record_property):
    executable = clock_runtime['executable']
    assert digest(executable) == os.environ['FDISBULL_QEMU_VGA_640_SHA256']
    checkpoint_tool = Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True)
    assert digest(checkpoint_tool) == os.environ['FDISBULL_QEMU_VGA_640_IMG_SHA256']
    code = assemble(tmp_path, 'vga-modes', _SOURCE + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), clock_runtime['nasm'])
    assert sha256(code).hexdigest() == COM_SHA256 and code[-62:-58] == b'VGA3'
    first, planar, banked, _, control = struct.unpack('<5H', code[-58:-48])
    guest = tmp_path / 'VGA.COM'
    guest.write_bytes(code)
    database = tmp_path / 'timed-vga.fdb'
    record_property('authored_com_sha256', digest(guest))
    receipt = dict(qemu_sha256=digest(executable), qemu_img_sha256=digest(checkpoint_tool),
                   authored_com_sha256=COM_SHA256, layout=layout, owners={}, completed=False,
                   dosbox_reference_sha256=DOSBOX_REFERENCE, dosbox_packed_rgb_sha256=DOSBOX_RGB[layout])
    line_ns, period_ns = TIMING[layout]
    receipt['expected_scanout_timing_ns'] = dict(line=line_ns, period=period_ns)
    expected = frame_expected = following_expected = expected_pixels(page)
    owners = {}
    cold_owners = {}
    mutation = None

    def launch(project):
        return project.debugger(executable, tmp_path, **launch_options(
            clock_runtime, clock_disk, qemu_clock='virtual', qemu_retrace='precise',
            qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=str(checkpoint_tool)))

    def future(debug, first_deadline):
        first_frame = finish(debug, layout, first_deadline, frame_expected)
        following = finish(debug, layout, first_deadline + period_ns, following_expected)
        assert following['frame']['frame-id'] == first_frame['frame']['frame-id'] + 1
        return [first_frame, following]

    try:
        with Project.create(database, guest, image='com') as project:
            with launch(project) as debug:
                owners['start'] = debug.vm.process
                info = process_record(debug)
                first, planar, banked, control = (com_address(info, n) for n in (first, planar, banked, control))
                park(debug, first)
                debug.write_memory(control, '01', expected_hex='00')
                park(debug, planar)
                if page == 'banked':
                    debug.write_memory(control, '02', expected_hex='01')
                    park(debug, banked)
                receipt['held_census'] = timing_geometry(debug, layout)
                artifact = debug.screenshot('held-oracle.png')
                png = tmp_path / 'held-oracle.png'
                project.debug_export(artifact['artifact'], png)
                with Image.open(png) as image:
                    receipt['stopped_renderer'] = _check_pixels(image, page)
                assert receipt['stopped_renderer']['sha256'] == sha256(expected).hexdigest()
                armed = debug.video_frame_start()['native']
                assert armed['model'] == MODEL and armed['scanout-layout'] == layout
                assert armed['state'] == 'observing' and armed['rows-sampled'] == 0
                first_deadline = armed['next-deadline-ns']
                assert armed['virtual-ns'] < first_deadline <= armed['virtual-ns'] + period_ns + line_ns // 4
                receipt['armed'] = logical(armed)
                intact = receipt['intact'] = finish(debug, layout, first_deadline, expected)
                assert intact['frame']['pixel-sha256'] == DOSBOX_RGB[layout]
                first_deadline += period_ns
                assert source(debug)['next-deadline-ns'] == first_deadline
                _reach(debug, first_deadline + (sampled - 1) * line_ns + line_ns // 2)
                partial = source(debug)
                assert partial['scanout-layout'] == layout and partial['rows-sampled'] == sampled
                assert partial['next-deadline-ns'] == first_deadline + sampled * line_ns
                assert logical(partial)['frame'] == intact['frame']
                if page == 'banked':
                    mutation = past, ahead, color = (420, 470, 6)
                    assert past < sampled < ahead
                    receipt['held_bank_writes'] = write_retained_bank(debug, (past, ahead), color)
                    assert source(debug) == partial
                    frame_expected = paint_rows(expected, (ahead,), color)
                    following_expected = paint_rows(expected, (past, ahead), color)
                receipt['partial'] = logical(partial)
                saved = debug.save_state('mid-raster')
                receipt['checkpoint'] = saved['sha256']
                receipt['forward'] = expected_future = future(debug, first_deadline)
                owners['hot'] = restore(debug, saved['artifact'], partial, retained_rgb=expected)
                assert owners['hot'] is not owners['start']
                receipt['hot'] = future(debug, first_deadline)
                assert receipt['hot'] == expected_future
            assert owners['hot'].poll() == 0

        spec = tmp_path/'cold-input.json'
        spec.write_text(json.dumps(dict(page=page,layout=layout,mutation=mutation,
            deadline=first_deadline,artifact=saved['artifact'],saved=partial,
            runtime={k:str(v) if isinstance(v,Path) else v for k,v in clock_runtime.items()},
            disk={'image':str(clock_disk['image'])},checkpoint_tool=str(checkpoint_tool),
            qemu_sha256=receipt['qemu_sha256'],qemu_img_sha256=receipt['qemu_img_sha256'])))
        completed = subprocess.run([sys.executable,str(Path(__file__).resolve()),str(spec)],
                                   text=True,capture_output=True,timeout=120)
        (tmp_path/'cold.log').write_text(completed.stdout+completed.stderr)
        assert completed.returncode == 0, completed.stderr
        cold = json.loads(completed.stdout)
        receipt['cold_host_pid'] = cold['host_pid']
        cold_owners = cold['owners']
        assert cold['host_pid'] != os.getpid()
        assert not {proc.pid for proc in owners.values()} & {item['pid'] for item in cold_owners.values()}
        receipt['cold'] = cold['future']
        assert receipt['cold'] == expected_future
        assert all(proc.poll() == 0 for proc in owners.values())
        receipt['completed'] = True
    finally:
        receipt['owners'] = {**{stage: dict(pid=proc.pid, returncode=proc.poll()) for stage, proc in owners.items()},
                             **cold_owners}
        assert guest.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vga640-replay.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    print(json.dumps(cold_replay_job(Path(sys.argv[1]))))
