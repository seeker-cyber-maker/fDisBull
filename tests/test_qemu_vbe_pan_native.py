"""Native VBE horizontal panning, independent latches, and partial-frame restore."""

import json
import os
import struct
import subprocess
import sys
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import pytest
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_flip import RESULT, event
from support.paired_vbe_pan import (
    COM_SHA,
    SETUP_RESULT,
    expected_rgb,
    source_with_pan_probe,
    symbols,
)
from support.paired_video_frame_oracle import PIT_HZ
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE
from test_qemu_vbe_flip_native import at_bios, flip_rom_hash, read_memory, register
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD, expected_status
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach

from fdisbull.project import Project

PROFILE = 'vga-640x480-pan'
MODEL = 'qemu-vga-640x480-pan-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-11'
LAYOUT = 'vbe-banked-101'
VISIBLE_WIDTH, PITCH = 640, 648
LEADING, TRAILING = 490 * LINE, 492 * LINE
IMAGE = 'vbe-pan.fdb'
DOSBOX_REFERENCE = '58fb52b4478d7f4197512ce3a23da97409b40a531e67aff74d6f4d7bc09c0a7a'
DOSBOX_PIXELS = {
    0: 'db7725a73989da6087d5510aa840ddb8791f7c94370952daa1b3904f9006f65c',
    1: '26304bcf512d7f14435c3ac84149fbeac6e3578d732541970623d1a9d4cd465f',
    4: 'a014f6b6d77c0eedec67726b2955bdd348c35f08951f4adada1c712be49e2561',
    5: 'd28b67caf546dd2963651779f0f350f121811d8ea2d3079ad1b84cb9ff8002d9',
}

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_PAN') != '1',
    reason='Select the exact native QEMU VBE 101h horizontal panning witness',
)


def display(debug, programmed, coarse, fine, *, next_coarse=None, next_fine=None):
    current = debug.retrace_observe()['native']
    now = current['virtual-ns']
    assert current['phase-supported'] and current['vbe101-timing']['line-period-ns'] == LINE
    assert current['phase']['phase-ns'] == now % PERIOD
    assert current['phase']['status1-timing-bits'] == expected_status(now)
    origin = {'programmed-origin-bytes': programmed & ~3, 'active-origin-bytes': coarse}
    pel = {'pitch-bytes': PITCH, 'programmed-pel': programmed & 3, 'active-pel': fine}
    if next_coarse is not None:
        origin['pending-deadline-ns'] = next_coarse
    if next_fine is not None:
        pel['pending-deadline-ns'] = next_fine
    assert current['vbe101-display-start'] == origin, current
    assert current['vbe101-panning'] == pel, current
    raw = debug.vga_configuration_observe()['current']['raw']
    assert raw['vbe-start-address'] * 4 == programmed & ~3
    assert raw['vbe-line-offset'] == PITCH and raw['vbe'][8:10] == [programmed, 0]
    return {'virtual_ns': now, 'phase': current['phase'], 'origin': origin, 'pel': pel, 'raw': raw}


@lru_cache(maxsize=4)
def pixels(x):
    return expected_rgb(x, _RGB)


def complete_frame(debug, x, *, start=None):
    result = debug.video_frame_advance(timeout_ms=8000)
    assert result['advance_completed'], result
    current = source(debug)
    frame = current['frame']
    assert current['state'] == 'observing' and current['model'] == MODEL
    assert current['scanout-layout'] == frame['scanout-layout'] == LAYOUT
    assert (frame['vbe101-origin-bytes'], frame['vbe101-pel'], frame['vbe101-pitch-bytes']) == (
        x & ~3,
        x & 3,
        PITCH,
    )
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (
        VISIBLE_WIDTH,
        HEIGHT,
        VISIBLE_WIDTH * 3,
        'RGB888',
    )
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    frame_start = frame['frame-start-ns']
    assert frame_start % PERIOD == 0
    if start is not None:
        assert start == frame_start
    assert len(frame['rows']) == HEIGHT
    for row, recorded in enumerate(frame['rows']):
        deadline = frame_start + LINE // 4 + row * LINE
        assert recorded['row'] == row and recorded['intended-ns'] == deadline
        assert deadline <= recorded['actual-ns'] < min(deadline + LINE, frame_start + HEIGHT * LINE)
    assert frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
    assert frame['last-sample-ns'] == frame['completed-ns'] == frame['rows'][-1]['actual-ns']
    expected = pixels(x)
    assert frame['pixel-sha256'] == sha256(expected).hexdigest() == DOSBOX_PIXELS[x]
    verify_export(debug, current, expected)
    return logical(current)['frame']


def issue(debug, labels, *, x, current, kind, start, phase):
    _reach(debug, start + phase)
    for name, value in (
        ('flip_subfunction', bytes([kind])),
        ('flip_sync', b'\0'),
        ('flip_x', struct.pack('<H', x)),
        ('flip_y', b'\0\0'),
        ('flip_go', b'\x01'),
    ):
        at = labels[name]
        previous = read_memory(debug, at, len(value))
        if name == 'flip_go':
            assert previous == b'\0'
        if previous != value:
            debug.write_memory(at, value.hex(), expected_hex=previous.hex())
    cpu = at_bios(debug, labels['bios_set'], subfunction=kind, y=None)
    assert register(cpu, 'cx') & 0xFFFF == x and register(cpu, 'dx') & 0xFFFF == 0
    entry = display(debug, current, current & ~3, current & 3)
    assert start + phase <= entry['virtual_ns'] < start + phase + LINE // 2
    return entry


def pending_rom(debug, labels, start):
    before = display(debug, 5, 0, 0, next_coarse=start + LEADING, next_fine=start + TRAILING)
    cpu = debug.registers()
    offset, segment = struct.unpack('<HH', read_memory(debug, 0x40, 4, space='physical'))
    current_segment = int(cpu['registers']['cs'], 0)
    pc = int(cpu['linear_pc'], 0)
    assert current_segment == segment >= 0xC000 and segment * 16 <= pc < (segment + 0x1000) * 16
    assert pc != labels['post_bios']
    return {
        'hardware': before,
        'cpu': cpu,
        'int10_vector': [segment, offset],
        'opcode': read_memory(debug, pc, 8, space='physical').hex(),
    }


def return_site(debug, labels):
    park(debug, labels['post_bios'])
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == labels['bios_set'] + 2
    assert register(cpu, 'ax') & 0xFFFF == 0x004F


def getter(debug, labels, requested, entry, response):
    at_bios(debug, labels['bios_get'], subfunction=1, y=None)
    park(debug, labels['bios_get'] + 2)
    cpu = debug.registers()
    assert tuple(register(cpu, key) & 0xFFFF for key in ('ax', 'cx', 'dx')) == (0x004F, requested, 0)
    park(debug, labels['flip_done'])
    raw = read_memory(debug, labels['flip_result'], RESULT.size)
    guest = event(raw)
    assert (guest['x'], guest['y']) == (requested, 0)
    assert guest['status_before'] & 8 == entry['phase']['status1-timing-bits'] & 8
    assert guest['status_after'] & 8 == response['phase']['status1-timing-bits'] & 8
    pit_ticks = (response['virtual_ns'] - entry['virtual_ns']) * PIT_HZ / 10**9
    assert abs(guest['elapsed_pit_ticks'] - pit_ticks) <= 24, (guest, pit_ticks)
    return {'raw': raw.hex(), 'guest': guest}


def finish_early(debug, labels, entry, response, start, old):
    guest = getter(debug, labels, 5, entry, response)
    assert logical(source(debug))['frame'] == old
    _reach(debug, start + TRAILING + LINE // 2)
    settled = display(debug, 5, 4, 1)
    new = complete_frame(debug, 5, start=start + PERIOD)
    assert new['frame-id'] == old['frame-id'] + 1
    return {'returned': response, 'guest_get': guest, 'settled': settled, 'new': new}


def replay(debug, labels, start, entry, *, at_leading=None):
    old = complete_frame(debug, 0, start=start)
    waiting = pending_rom(debug, labels, start)
    return_site(debug, labels)
    response = display(debug, 5, 4, 0, next_fine=start + TRAILING)
    assert start + LEADING <= response['virtual_ns'] < start + TRAILING
    if at_leading is not None:
        at_leading(old, response)
    return {'old': old, 'waiting': waiting, **finish_early(debug, labels, entry, response, start, old)}


def controls(debug, labels, middle):
    # The exact paired DOSBox sequence starts with X=5. A direct reset
    # between the two latches turns the fine component off one frame early.
    late = issue(debug, labels, x=0, current=5, kind=0, start=middle, phase=LEADING + 512)
    assert late['phase']['status1-timing-bits'] == 9
    return_site(debug, labels)
    next_coarse = middle + PERIOD + LEADING
    response = display(debug, 0, 4, 1, next_coarse=next_coarse, next_fine=middle + TRAILING)
    assert late['virtual_ns'] < response['virtual_ns'] < middle + TRAILING
    direct_get = getter(debug, labels, 0, late, response)
    _reach(debug, middle + TRAILING + 4 * LINE)
    fine_only = display(debug, 0, 4, 0, next_coarse=next_coarse)
    coarse = complete_frame(debug, 4, start=middle + PERIOD)
    zero = complete_frame(debug, 0, start=middle + 2 * PERIOD)

    # A genuine BL=80h call issued while high waits for the next leading
    # edge. Its fine component already took effect at the first trailing edge.
    middle += 2 * PERIOD
    high = issue(debug, labels, x=5, current=0, kind=0x80, start=middle, phase=LEADING + 512)
    assert high['phase']['status1-timing-bits'] == 9
    _reach(debug, middle + TRAILING + 4 * LINE)
    queued = display(debug, 5, 0, 1, next_coarse=middle + PERIOD + LEADING)
    mixed = complete_frame(debug, 1, start=middle + PERIOD)
    return_site(debug, labels)
    high_return = display(debug, 5, 4, 1)
    assert middle + PERIOD + LEADING <= high_return['virtual_ns'] < middle + PERIOD + TRAILING
    high_get = getter(debug, labels, 5, high, high_return)
    assert logical(source(debug))['frame'] == mixed
    five = complete_frame(debug, 5, start=middle + 2 * PERIOD)

    middle += 2 * PERIOD
    low = issue(debug, labels, x=0, current=5, kind=0x80, start=middle, phase=480 * LINE + LINE // 2)
    assert low['phase']['status1-timing-bits'] == 1
    return_site(debug, labels)
    low_return = display(debug, 0, 0, 1, next_fine=middle + TRAILING)
    assert middle + LEADING <= low_return['virtual_ns'] < middle + TRAILING
    low_get = getter(debug, labels, 0, low, low_return)
    final = complete_frame(debug, 0, start=middle + PERIOD)
    return {
        'direct': {
            'entry': late,
            'returned': response,
            'guest_get': direct_get,
            'fine_only': fine_only,
            'mixed': coarse,
            'settled': zero,
        },
        'wait_high': {
            'entry': high,
            'queued': queued,
            'mixed': mixed,
            'returned': high_return,
            'guest_get': high_get,
            'settled': five,
        },
        'wait_low': {'entry': low, 'returned': low_return, 'guest_get': low_get, 'settled': final},
    }


def launch(project, directory, runtime, disk, tool):
    return project.debugger(
        runtime['executable'],
        directory,
        **launch_options(
            runtime,
            disk,
            qemu_clock='virtual',
            qemu_retrace='precise',
            qemu_video_source_profile=PROFILE,
            qemu_checkpoint_tool=tool,
        ),
    )


def load(debug, checkpoint, saved):
    previous = debug.vm.process
    loaded = debug.load_state(checkpoint, timeout_ms=60_000)
    assert loaded['instrumentation']['format'] == FORMAT
    owner = debug.vm.process
    current = source(debug)
    assert owner is not previous and previous.poll() == 0
    assert current['epoch'] != saved['epoch'] and current['token'] != saved['token']
    assert logical(current) == logical(saved)
    return owner


def restore_pending(debug, spec):
    owner = load(debug, spec['checkpoint'], spec['source'])
    assert pending_rom(debug, spec['labels'], spec['start']) == spec['pending']
    verify_export(debug, source(debug), pixels(0))
    return owner


def cold_replay(path):
    spec = json.loads(path.read_text())
    runtime = spec['runtime']
    assert digest(runtime['executable']) == spec['qemu_sha256']
    assert digest(spec['tool']) == spec['qemu_img_sha256']
    assert flip_rom_hash(runtime) == spec['rom_sha256']
    with Project(path.parent / IMAGE) as project:
        with launch(project, path.parent, runtime, spec['disk'], spec['tool']) as debug:
            entry = debug.vm.process
            restored = restore_pending(debug, spec)
            result = replay(debug, spec['labels'], spec['start'], spec['entry'])
    assert entry is not restored and entry.poll() == restored.poll() == 0
    return {
        'host_pid': os.getpid(),
        'result': result,
        'owners': {
            'cold_entry': {'pid': entry.pid, 'returncode': entry.poll()},
            'cold_restored': {'pid': restored.pid, 'returncode': restored.poll()},
        },
    }


def test_native_vbe_horizontal_pan_checkpoint_replay(tmp_path, clock_runtime, clock_disk):
    executable = clock_runtime['executable']
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    qemu_hash, tool_hash = digest(executable), digest(tool)
    rom_hash = flip_rom_hash(clock_runtime)
    assert (qemu_hash, tool_hash, rom_hash) == tuple(
        os.environ[name]
        for name in (
            'FDISBULL_QEMU_VBE_PAN_SHA256',
            'FDISBULL_QEMU_VBE_PAN_IMG_SHA256',
            'FDISBULL_QEMU_VBE_PAN_ROM_SHA256',
        )
    )
    code = assemble(
        tmp_path,
        'vbe-pan',
        source_with_pan_probe(_SOURCE)
        + '\ncolors: db '
        + ','.join(str(value) for color in _DAC for value in color),
        clock_runtime['nasm'],
    )
    authored_hash = sha256(code).hexdigest()
    assert authored_hash == COM_SHA
    page_labels, pan_labels = symbols(code)
    binary = tmp_path / 'PAN.COM'
    binary.write_bytes(code)
    receipt = {
        'profile': PROFILE,
        'com_sha256': authored_hash,
        'qemu_sha256': qemu_hash,
        'qemu_img_sha256': tool_hash,
        'rom_sha256': rom_hash,
        'dosbox_reference_sha256': DOSBOX_REFERENCE,
        'completed': False,
    }
    owners, cold_owners = {}, {}

    def write():
        (tmp_path / 'vbe-pan-replay.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    try:
        with Project.create(tmp_path / IMAGE, binary, image='com') as project:
            with launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['start'] = debug.vm.process
                process = process_record(debug)
                first, planar, held, _, advance = (com_address(process, at) for at in page_labels)
                labels = {name: com_address(process, at) for name, at in pan_labels.items()}
                park(debug, first)
                debug.write_memory(advance, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(advance, '02', expected_hex='01')
                park(debug, held)
                debug.write_memory(labels['pan_setup_go'], '01', expected_hex='00')
                park(debug, labels['pan_ready'])
                assert read_memory(debug, labels['pan_setup_go'], 1) == b'\x02'
                ax, bx, cx, lines = SETUP_RESULT.unpack(
                    read_memory(debug, labels['pan_setup_result'], SETUP_RESULT.size)
                )
                assert (ax, bx, cx) == (0x004F, PITCH, PITCH) and lines >= HEIGHT
                receipt['bios_pitch'] = {'status': ax, 'pitch': bx, 'pixels': cx, 'lines': lines}
                assert display(debug, 0, 0, 0)['raw']['vbe'][6] == PITCH
                debug.video_frame_start()
                retained = receipt['retained'] = complete_frame(debug, 0)
                start = retained['frame-start-ns'] + PERIOD
                entry = receipt['entry'] = issue(
                    debug,
                    labels,
                    x=5,
                    current=0,
                    kind=0x80,
                    start=start,
                    phase=120 * LINE + LINE // 2,
                )
                assert not entry['phase']['status1-timing-bits'] & 8
                _reach(debug, start + 145 * LINE + LINE // 2)
                partial = source(debug)
                assert partial['rows-sampled'] == 146 and logical(partial)['frame'] == retained
                assert partial['next-deadline-ns'] == start + 146 * LINE + LINE // 4
                pending = receipt['pending'] = pending_rom(debug, labels, start)
                verify_export(debug, partial, pixels(0))
                saved = debug.save_state('pan-both-pending')
                receipt['checkpoint_sha256'] = saved['sha256']
                receipt['partial_rows'] = partial['rows-sampled']
                spec = {
                    **receipt,
                    'source': partial,
                    'checkpoint': saved['artifact'],
                    'start': start,
                    'labels': labels,
                    'tool': tool,
                    'disk': {'image': str(clock_disk['image'])},
                    'runtime': {
                        key: str(val) if isinstance(val, Path) else val for key, val in clock_runtime.items()
                    },
                }
                write()

                leading = {}

                def save_fine_only(old, response):
                    leading.update(old=old, response=response, source=source(debug))
                    artifact = debug.save_state('pan-fine-pending')
                    leading['artifact'] = artifact['artifact']
                    receipt['fine_checkpoint_sha256'] = artifact['sha256']
                    assert display(debug, 5, 4, 0, next_fine=start + TRAILING) == response

                receipt['forward'] = replay(debug, labels, start, entry, at_leading=save_fine_only)
                write()
                owners['hot'] = restore_pending(debug, spec)
                receipt['hot'] = replay(debug, labels, start, entry)
                assert receipt['hot'] == receipt['forward']
                owners['hot_fine'] = load(debug, leading['artifact'], leading['source'])
                response = display(debug, 5, 4, 0, next_fine=start + TRAILING)
                assert response == leading['response']
                receipt['hot_fine'] = finish_early(debug, labels, entry, response, start, leading['old'])
                assert receipt['hot_fine'] == {
                    key: receipt['forward'][key] for key in ('returned', 'guest_get', 'settled', 'new')
                }
                write()
                receipt['controls'] = controls(debug, labels, start + PERIOD)
            assert all(owner.poll() == 0 for owner in owners.values())

        spec_path = tmp_path / 'cold-spec.json'
        spec_path.write_text(json.dumps(spec))
        cold = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(spec_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        (tmp_path / 'cold.log').write_text(cold.stdout + cold.stderr)
        assert cold.returncode == 0, cold.stderr
        report = json.loads(cold.stdout)
        assert report['host_pid'] != os.getpid()
        cold_owners = report['owners']
        assert not {owner.pid for owner in owners.values()} & {info['pid'] for info in cold_owners.values()}
        receipt['cold'] = report['result']
        assert receipt['cold'] == receipt['forward']
        receipt['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        receipt['owners'] = {
            **{phase: {'pid': owner.pid, 'returncode': owner.poll()} for phase, owner in owners.items()},
            **cold_owners,
        }
        write()


if __name__ == '__main__':
    print(json.dumps(cold_replay(Path(sys.argv[1]))))
