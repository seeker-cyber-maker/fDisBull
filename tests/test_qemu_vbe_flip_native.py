"""VBE 101h BIOS display-start calls, native raster latches, and pending replay."""

import json
import os
import struct
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_flip import (
    COM_SHA,
    FLIP_ORIGIN,
    FLIP_Y,
    RESULT,
    WIDTH,
    event,
    expected_rgb,
    source_with_flip_probe,
    symbols,
)
from support.paired_video_frame_oracle import PIT_HZ
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE
from test_qemu_vbe_guest_retrace_native import (
    HEIGHT,
    LINE,
    PERIOD,
    expected_status,
    register,
)
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach

from fdisbull.project import Project

PROFILE = 'vga-640x480-flip'
MODEL = 'qemu-vga-640x480-flip-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-10'
LAYOUT = 'vbe-banked-101'
PITCH = WIDTH
A, B = 0, FLIP_ORIGIN
EDGE = 490 * LINE
EDGE_END = 492 * LINE
IMAGE = 'vbe-flip.fdb'
DOSBOX_REFERENCE = 'b1fc8efdc69fc2477655a6c599143cdbe32092b7dc0147e2d2c9ff2aebbd76c9'
DOSBOX_PIXELS = {
    A: '5a5656922ff09ce0d4292da990de6ea5cd13fd2f17f883be9cf863c574cbef27',
    B: 'b89e78a0a768dc04ca593cbc1a6c113d4ae1ebd7b8bd7faa6d5225db5a55a2ff',
}

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_FLIP') != '1',
    reason='Select the exact native QEMU VBE 101h BIOS page-flip witness',
)


def read_memory(debug, address, length, *, space='virtual'):
    return bytes.fromhex(debug.memory(address, length=length, space=space)['hex'])


def expected_pixels(origin):
    return expected_rgb(origin, _RGB)


def display(debug, programmed, active, deadline=None):
    native = debug.retrace_observe()['native']
    assert native['phase-supported'] and native['vbe101-timing']['line-period-ns'] == LINE
    timestamp = native['virtual-ns']
    assert native['phase']['phase-ns'] == timestamp % PERIOD
    assert native['phase']['status1-timing-bits'] == expected_status(timestamp)
    expected = {'programmed-origin-bytes': programmed, 'active-origin-bytes': active}
    if deadline is not None:
        expected['pending-deadline-ns'] = deadline
    assert native['vbe101-display-start'] == expected, native['vbe101-display-start']
    census = debug.vga_configuration_observe()['current']['raw']
    assert census['vbe-start-address'] * 4 == programmed
    assert census['vbe-line-offset'] == PITCH
    assert census['vbe'][8:10] == [0, programmed // PITCH]
    return {'virtual_ns': timestamp, 'phase': native['phase'], 'display_start': expected, 'raw': census}


def frame(debug, origin, *, start=None):
    advanced = debug.video_frame_advance(timeout_ms=8000)
    assert advanced['advance_completed'], advanced
    state = source(debug)
    actual = state['frame']
    assert state['model'] == MODEL and state['state'] == 'observing'
    assert state['scanout-layout'] == actual['scanout-layout'] == LAYOUT
    assert actual['vbe101-origin-bytes'] == origin
    assert (actual['width'], actual['height'], actual['stride'], actual['pixel-format']) == (
        640,
        HEIGHT,
        PITCH * 3,
        'RGB888',
    )
    assert (actual['line-period-ns'], actual['period-ns']) == (LINE, PERIOD)
    actual_start = actual['frame-start-ns']
    assert actual_start % PERIOD == 0
    if start is not None:
        assert start == actual_start
    assert len(actual['rows']) == HEIGHT
    for number, row in enumerate(actual['rows']):
        time = actual_start + LINE // 4 + number * LINE
        assert row['row'] == number and row['intended-ns'] == time
        assert time <= row['actual-ns'] < min(time + LINE, actual_start + HEIGHT * LINE)
    assert actual['first-sample-ns'] == actual['rows'][0]['actual-ns']
    assert actual['last-sample-ns'] == actual['completed-ns'] == actual['rows'][-1]['actual-ns']
    pixels = expected_pixels(origin)
    assert actual['pixel-sha256'] == sha256(pixels).hexdigest() == DOSBOX_PIXELS[origin]
    verify_export(debug, state, pixels)
    return logical(state)['frame']


def at_bios(debug, site, *, subfunction, y):
    park(debug, site)
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == site
    assert read_memory(debug, site, 2) == b'\xcd\x10'
    assert register(cpu, 'ax') & 0xFFFF == 0x4F07
    assert register(cpu, 'bx') & 0xFF == subfunction
    if y is not None:
        assert register(cpu, 'cx') & 0xFFFF == 0 and register(cpu, 'dx') & 0xFFFF == y
    return cpu


def request(debug, labels, *, subfunction, y, old, start, phase):
    _reach(debug, start + phase)
    for label, value in (
        ('flip_subfunction', bytes([subfunction])),
        ('flip_sync', b'\0'),
        ('flip_y', struct.pack('<H', y)),
        ('flip_go', b'\x01'),
    ):
        address = labels[label]
        previous = read_memory(debug, address, len(value))
        if label == 'flip_go':
            assert previous == b'\0'
        if value != previous:
            debug.write_memory(address, value.hex(), expected_hex=previous.hex())
    at_bios(debug, labels['bios_set'], subfunction=subfunction, y=y)
    entry = display(debug, old, old)
    timestamp = entry['virtual_ns']
    assert start + phase <= timestamp < start + phase + LINE // 2, entry
    return entry


def waiting(debug, labels, programmed, active, deadline):
    report = display(debug, programmed, active, deadline)
    cpu = debug.registers()
    segment = int(cpu['registers']['cs'], 0)
    ivt_offset, ivt_segment = struct.unpack('<HH', read_memory(debug, 0x40, 4, space='physical'))
    pc = int(cpu['linear_pc'], 0)
    assert segment == ivt_segment and segment >= 0xC000, (cpu, ivt_segment)
    assert segment * 16 <= pc < (segment + 0x1000) * 16
    assert pc != labels['post_bios']
    opcode = read_memory(debug, pc, 8, space='physical').hex()
    return {'hardware': report, 'cpu': cpu, 'rom_opcode': opcode, 'int10_vector': [ivt_segment, ivt_offset]}


def returned(debug, labels, *, entry, new, active, edge=None, pending=None):
    park(debug, labels['post_bios'])
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == labels['bios_set'] + 2
    assert register(cpu, 'ax') & 0xFFFF == 0x004F
    at_return = display(debug, new, active, pending)
    if edge is not None:
        assert edge <= at_return['virtual_ns'] <= edge + EDGE_END - EDGE
        assert at_return['phase']['status1-timing-bits'] & 8
    else:
        assert entry['virtual_ns'] < at_return['virtual_ns'] < entry['virtual_ns'] + 4 * LINE
        assert not at_return['phase']['status1-timing-bits'] & 8
    at_bios(debug, labels['bios_get'], subfunction=1, y=None)
    park(debug, labels['bios_get'] + 2)
    observed = debug.registers()
    assert tuple(register(observed, field) & 0xFFFF for field in ('ax', 'cx', 'dx')) == (
        0x004F,
        0,
        new // PITCH,
    )
    park(debug, labels['flip_done'])
    raw = read_memory(debug, labels['flip_result'], RESULT.size)
    guest = event(raw)
    assert (guest['x'], guest['y']) == (0, new // PITCH)
    assert guest['status_before'] & 8 == entry['phase']['status1-timing-bits'] & 8
    assert guest['status_after'] & 8 == at_return['phase']['status1-timing-bits'] & 8
    elapsed_ticks = guest['elapsed_pit_ticks']
    expected_ticks = (at_return['virtual_ns'] - entry['virtual_ns']) * PIT_HZ / 10**9
    assert abs(elapsed_ticks - expected_ticks) <= 24, (elapsed_ticks, expected_ticks)
    return {'hardware': at_return, 'result_hex': raw.hex(), 'guest': guest}


def replay(debug, labels, start, entry):
    old = frame(debug, A, start=start)
    untouched = waiting(debug, labels, B, A, start + EDGE)
    completed_call = returned(debug, labels, entry=entry, new=B, active=B, edge=start + EDGE)
    assert logical(source(debug))['frame'] == old
    new = frame(debug, B, start=start + PERIOD)
    assert new['frame-id'] == old['frame-id'] + 1
    return {'old': old, 'still_waiting': untouched, 'completed_call': completed_call, 'new': new}


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


def load_pending(debug, spec):
    old = debug.vm.process
    loaded = debug.load_state(spec['checkpoint'], timeout_ms=60_000)
    assert loaded['instrumentation']['format'] == FORMAT
    new = debug.vm.process
    assert new is not old and old.poll() == 0
    actual = source(debug)
    saved = spec['source']
    assert actual['epoch'] != saved['epoch'] and actual['token'] != saved['token']
    assert logical(actual) == logical(saved)
    assert waiting(debug, spec['labels'], B, A, spec['start'] + EDGE) == spec['pending']
    verify_export(debug, actual, expected_pixels(A))
    return new


def cold_replay(spec_path):
    spec = json.loads(spec_path.read_text())
    directory = spec_path.parent
    runtime = spec['runtime']
    assert digest(runtime['executable']) == spec['qemu_sha256']
    assert digest(spec['tool']) == spec['qemu_img_sha256']
    assert flip_rom_hash(runtime) == spec['flip_rom_sha256']
    with Project(directory / IMAGE) as project:
        with launch(project, directory, runtime, spec['disk'], spec['tool']) as debug:
            initial = debug.vm.process
            restored = load_pending(debug, spec)
            result = replay(debug, spec['labels'], spec['start'], spec['entry'])
    assert initial is not restored and initial.poll() == restored.poll() == 0
    return {
        'host_pid': os.getpid(),
        'result': result,
        'owners': {
            'cold_entry': {'pid': initial.pid, 'returncode': initial.poll()},
            'cold_restored': {'pid': restored.pid, 'returncode': restored.poll()},
        },
    }


def controls(debug, labels, next_start):
    high = request(debug, labels, subfunction=0x80, y=0, old=B, start=next_start, phase=EDGE + LINE // 4)
    assert high['phase']['status1-timing-bits'] & 8
    _reach(debug, next_start + EDGE_END + LINE // 2)
    missed_deadline = next_start + PERIOD + EDGE
    late = waiting(debug, labels, A, B, missed_deadline)
    assert not late['hardware']['phase']['status1-timing-bits'] & 8
    intervening = frame(debug, B, start=next_start + PERIOD)
    late_return = returned(debug, labels, entry=high, new=A, active=A, edge=missed_deadline)
    late_frame = frame(debug, A, start=next_start + 2 * PERIOD)

    immediate_start = next_start + 3 * PERIOD
    immediate = request(
        debug, labels, subfunction=0, y=FLIP_Y, old=A, start=immediate_start, phase=120 * LINE + LINE // 2
    )
    immediate_return = returned(
        debug, labels, entry=immediate, new=B, active=A, pending=immediate_start + EDGE
    )
    unchanged = frame(debug, A, start=immediate_start)
    changed = frame(debug, B, start=immediate_start + PERIOD)
    return {
        'late': {
            'entry': high,
            'pending': late,
            'old': intervening,
            'returned': late_return,
            'new': late_frame,
        },
        'immediate': {'entry': immediate, 'old': unchanged, 'returned': immediate_return, 'new': changed},
    }


def flip_rom_hash(runtime):
    from fdisbull.qemu_video_checkpoint import VBE101_FLIP_ROM

    return digest(Path(runtime['firmware']) / VBE101_FLIP_ROM)


def test_native_vbe_page_flip_pending_origin_and_replay(tmp_path, clock_runtime, clock_disk):
    executable = clock_runtime['executable']
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    actual_hash, helper_hash = digest(executable), digest(tool)
    rom_hash = flip_rom_hash(clock_runtime)
    assert actual_hash == os.environ['FDISBULL_QEMU_VBE_FLIP_SHA256']
    assert helper_hash == os.environ['FDISBULL_QEMU_VBE_FLIP_IMG_SHA256']
    assert rom_hash == os.environ['FDISBULL_QEMU_VBE_FLIP_ROM_SHA256']
    code = assemble(
        tmp_path,
        'vbe-flip',
        source_with_flip_probe(_SOURCE)
        + '\ncolors: db '
        + ','.join(str(value) for color in _DAC for value in color),
        clock_runtime['nasm'],
    )
    authored_hash = sha256(code).hexdigest()
    assert authored_hash == COM_SHA
    page_labels, flip_labels = symbols(code)
    binary = tmp_path / 'FLIP.COM'
    binary.write_bytes(code)
    receipt = {
        'com_sha256': authored_hash,
        'qemu_sha256': actual_hash,
        'qemu_img_sha256': helper_hash,
        'flip_rom_sha256': rom_hash,
        'dosbox_reference_sha256': DOSBOX_REFERENCE,
        'profile': PROFILE,
        'completed': False,
    }
    owners, cold_owners = {}, {}

    def write():
        (tmp_path / 'vbe-flip-replay.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    try:
        with Project.create(tmp_path / IMAGE, binary, image='com') as project:
            with launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['start'] = debug.vm.process
                process = process_record(debug)
                first, planar, held, _, advance = (com_address(process, at) for at in page_labels)
                labels = {name: com_address(process, at) for name, at in flip_labels.items()}
                park(debug, first)
                debug.write_memory(advance, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(advance, '02', expected_hex='01')
                park(debug, held)
                receipt['held'] = display(debug, A, A)
                armed = debug.video_frame_start()['native']
                assert armed['model'] == MODEL and armed['scanout-layout'] == LAYOUT
                retained = receipt['retained'] = frame(debug, A)
                start = retained['frame-start-ns'] + PERIOD
                entry = receipt['entry'] = request(
                    debug,
                    labels,
                    subfunction=0x80,
                    y=FLIP_Y,
                    old=A,
                    start=start,
                    phase=120 * LINE + LINE // 2,
                )
                assert not entry['phase']['status1-timing-bits'] & 8
                _reach(debug, start + 145 * LINE + LINE // 2)
                partial = source(debug)
                assert partial['rows-sampled'] == 146 and logical(partial)['frame'] == retained
                assert partial['next-deadline-ns'] == start + 146 * LINE + LINE // 4
                verify_export(debug, partial, expected_pixels(A))
                pending = receipt['pending'] = waiting(debug, labels, B, A, start + EDGE)
                receipt['partial_rows'] = partial['rows-sampled']
                saved = debug.save_state('vbe-flip-pending')
                receipt['checkpoint_sha256'] = saved['sha256']
                spec = {
                    **receipt,
                    'entry': entry,
                    'pending': pending,
                    'source': partial,
                    'labels': labels,
                    'start': start,
                    'checkpoint': saved['artifact'],
                    'tool': tool,
                    'disk': {'image': str(clock_disk['image'])},
                    'runtime': {
                        key: str(value) if isinstance(value, Path) else value
                        for key, value in clock_runtime.items()
                    },
                }
                write()
                receipt['forward'] = replay(debug, labels, start, entry)
                write()
                owners['hot'] = load_pending(debug, spec)
                receipt['hot'] = replay(debug, labels, start, entry)
                assert receipt['hot'] == receipt['forward']
                write()
                receipt['controls'] = controls(debug, labels, start + PERIOD)
            assert all(proc.poll() == 0 for proc in owners.values())
        spec_path = tmp_path / 'cold-spec.json'
        spec_path.write_text(json.dumps(spec))
        cold_run = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(spec_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        (tmp_path / 'cold.log').write_text(cold_run.stdout + cold_run.stderr)
        assert cold_run.returncode == 0, cold_run.stderr
        cold = json.loads(cold_run.stdout)
        assert cold['host_pid'] != os.getpid()
        receipt['cold_host_pid'] = cold['host_pid']
        cold_owners = cold['owners']
        assert not {proc.pid for proc in owners.values()} & {item['pid'] for item in cold_owners.values()}
        receipt['cold'] = cold['result']
        assert receipt['cold'] == receipt['forward']
        receipt['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        receipt['owners'] = {
            **{stage: {'pid': proc.pid, 'returncode': proc.poll()} for stage, proc in owners.items()},
            **cold_owners,
        }
        write()


if __name__ == '__main__':
    print(json.dumps(cold_replay(Path(sys.argv[1]))))
