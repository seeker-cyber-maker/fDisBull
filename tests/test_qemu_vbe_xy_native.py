"""Paired combined VBE coordinates with independent retrace latches and restore."""

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
from support.paired_vbe_pan import PITCH, SETUP_RESULT, WIDTH
from support.paired_vbe_xy import (
    COM_SHA,
    bank_seams,
    expected_rgb,
    source_with_xy_probe,
    symbols,
)
from support.paired_video_frame_oracle import PIT_HZ
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE
from test_qemu_vbe_flip_native import at_bios, read_memory, register
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD, expected_status
from test_qemu_vbe_pan_native import LEADING, TRAILING, return_site
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach

from fdisbull.project import Project

PROFILE = 'vga-640x480-xy'
MODEL = 'qemu-vga-640x480-xy-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-12'
LAYOUT = 'vbe-banked-101'
IMAGE = 'vbe-xy.fdb'
ROM = 'fdisbull-vgabios-vbe101-xy.bin'
A, B = (0, 0), (5, 64)
DOSBOX_REFERENCE = '20741a0a568217dab132ed71a0fc859997a4339d1ec2fac8bc34914acd0451b9'
DOSBOX_PIXELS = {
    0: '8d7275fa5c91f7a71a97c0b9f83dfb4ee1c0115813e335b0454c792650138198',
    1: '0b6cc886b49d8c3c6bacd0ced71ddfe30982ad282db26b2ae8f7d366aff9b45d',
    0xA204: 'c560546bde6bfc2e2f81404cd4f472e9acbabe8d35df73fc545effe649e6cf44',
    0xA205: '77b66bdb9507cc88e664f0ca837ec454e12c105f6a23544907e9ff3a5f32714c',
}

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_XY') != '1',
    reason='Select the exact native QEMU banked VBE X/Y witness',
)


def origin(point):
    x, y = point
    return y * PITCH + x


def display(debug, point, active, *, next_coarse=None, next_fine=None):
    current = debug.retrace_observe()['native']
    now = current['virtual-ns']
    target, shown = origin(point), origin(active)
    assert current['phase-supported'] and current['vbe101-timing']['line-period-ns'] == LINE
    assert current['phase']['phase-ns'] == now % PERIOD
    assert current['phase']['status1-timing-bits'] == expected_status(now)
    coarse = {'programmed-origin-bytes': target & ~3, 'active-origin-bytes': shown & ~3}
    fine = {'pitch-bytes': PITCH, 'programmed-pel': target & 3, 'active-pel': shown & 3}
    if next_coarse is not None:
        coarse['pending-deadline-ns'] = next_coarse
    if next_fine is not None:
        fine['pending-deadline-ns'] = next_fine
    assert current['vbe101-display-start'] == coarse, current
    assert current['vbe101-panning'] == fine, current
    configuration = debug.vga_configuration_observe()['current']
    raw = configuration['raw']
    assert raw['vbe-start-address'] * 4 == target & ~3
    assert raw['vbe-line-offset'] == PITCH and raw['vbe'][8:10] == list(point)
    return {
        'virtual_ns': now,
        'phase': current['phase'],
        'coarse': coarse,
        'fine': fine,
        'raw': raw,
        'configuration_generation': configuration['configuration_generation'],
    }


@lru_cache(maxsize=4)
def pixels(point):
    return expected_rgb(origin(point), _RGB)


def cross_bank_rows(base, rgb):
    crossings = []
    for row, split_at in bank_seams(base):
        begin = base + row * PITCH
        last = begin + WIDTH - 1
        rgb_start = row * WIDTH * 3
        rgb_boundary = rgb_start + split_at * 3
        rgb_end = rgb_start + WIDTH * 3
        crossings.append(
            {
                'row': row,
                'derived_first_byte': begin,
                'derived_last_byte': last,
                'bank_boundary': begin + split_at,
                'left_rgb_sha256': sha256(rgb[rgb_start:rgb_boundary]).hexdigest(),
                'right_rgb_sha256': sha256(rgb[rgb_boundary:rgb_end]).hexdigest(),
            }
        )
    assert len(crossings) in (4, 5)
    return crossings


def complete(debug, point, *, start=None):
    advanced = debug.video_frame_advance(timeout_ms=8000)
    assert advanced['advance_completed'], advanced
    state = source(debug)
    actual = state['frame']
    assert state['model'] == MODEL and state['state'] == 'observing'
    assert state['scanout-layout'] == actual['scanout-layout'] == LAYOUT
    address = origin(point)
    assert (actual['vbe101-origin-bytes'], actual['vbe101-pel'], actual['vbe101-pitch-bytes']) == (
        address & ~3,
        address & 3,
        PITCH,
    )
    assert (actual['width'], actual['height'], actual['stride'], actual['pixel-format']) == (
        WIDTH,
        HEIGHT,
        WIDTH * 3,
        'RGB888',
    )
    assert (actual['line-period-ns'], actual['period-ns']) == (LINE, PERIOD)
    frame_start = actual['frame-start-ns']
    assert frame_start % PERIOD == 0 and (start is None or start == frame_start)
    assert len(actual['rows']) == HEIGHT
    for row, observed in enumerate(actual['rows']):
        deadline = frame_start + LINE // 4 + row * LINE
        assert observed['row'] == row and observed['intended-ns'] == deadline
        assert deadline <= observed['actual-ns'] < min(deadline + LINE, frame_start + HEIGHT * LINE)
    assert actual['first-sample-ns'] == actual['rows'][0]['actual-ns']
    assert actual['last-sample-ns'] == actual['completed-ns'] == actual['rows'][-1]['actual-ns']
    packed = pixels(point)
    assert actual['pixel-sha256'] == sha256(packed).hexdigest() == DOSBOX_PIXELS[address]
    verify_export(debug, state, packed)
    return {'frame': logical(state)['frame'], 'cross_bank_rows': cross_bank_rows(address, packed)}


def enter_bios(debug, labels, point, kind, start, phase):
    _reach(debug, start + phase)
    # The command is the exact shared DOS guest's six data bytes plus go.
    data = struct.pack('<BBBHH', 1, kind, 0, point[1], point[0])
    at = labels['flip_go']
    observed = read_memory(debug, at, len(data))
    assert observed[0] == 0
    debug.write_memory(at, data.hex(), expected_hex=observed.hex())
    cpu = at_bios(debug, labels['bios_set'], subfunction=kind, y=None)
    assert tuple(register(cpu, key) & 0xFFFF for key in ('cx', 'dx')) == point


def issue(debug, labels, *, point, current, kind, start, phase):
    enter_bios(debug, labels, point, kind, start, phase)
    entry = display(debug, current, current)
    assert start + phase <= entry['virtual_ns'] < start + phase + LINE // 2
    return entry


def waiting(debug, labels, start):
    report = display(debug, B, A, next_coarse=start + LEADING, next_fine=start + TRAILING)
    cpu = debug.registers()
    offset, segment = struct.unpack('<HH', read_memory(debug, 0x40, 4, space='physical'))
    pc = int(cpu['linear_pc'], 0)
    assert int(cpu['registers']['cs'], 0) == segment >= 0xC000
    assert segment * 16 <= pc < (segment + 0x1000) * 16 and pc != labels['post_bios']
    return {'display': report, 'cpu': cpu, 'vector': [segment, offset]}


def getter(debug, labels, requested, entry, response, *, set_ax=0x004F):
    at_bios(debug, labels['bios_get'], subfunction=1, y=None)
    park(debug, labels['bios_get'] + 2)
    cpu = debug.registers()
    assert tuple(register(cpu, key) & 0xFFFF for key in ('ax', 'cx', 'dx')) == (0x004F, *requested)
    park(debug, labels['flip_done'])
    raw = read_memory(debug, labels['flip_result'], RESULT.size)
    if set_ax == 0x004F:
        guest = event(raw)
    else:
        set_status, get_status, x, y, before, after, before_bits, after_bits = RESULT.unpack(raw)
        assert (set_status, get_status) == (set_ax, 0x004F)
        guest = {
            'set_ax': set_status,
            'get_ax': get_status,
            'x': x,
            'y': y,
            'status_before': before_bits,
            'status_after': after_bits,
            'elapsed_pit_ticks': (before - after) & 0xFFFF,
        }
    assert (guest['x'], guest['y']) == requested and read_memory(debug, labels['flip_go'], 1) == b'\0'
    assert guest['status_before'] & 8 == entry['phase']['status1-timing-bits'] & 8
    assert guest['status_after'] & 8 == response['phase']['status1-timing-bits'] & 8
    elapsed_ticks = (response['virtual_ns'] - entry['virtual_ns']) * PIT_HZ / 10**9
    assert abs(guest['elapsed_pit_ticks'] - elapsed_ticks) <= 24
    return {'raw': raw.hex(), 'guest': guest}


def finish_split(debug, labels, entry, start, old):
    response = display(debug, B, (4, B[1]), next_fine=start + TRAILING)
    assert start + LEADING <= response['virtual_ns'] < start + TRAILING
    get = getter(debug, labels, B, entry, response)
    assert logical(source(debug))['frame'] == old['frame']
    _reach(debug, start + TRAILING + LINE // 2)
    settled = display(debug, B, B)
    next_frame = complete(debug, B, start=start + PERIOD)
    assert next_frame['frame']['frame-id'] == old['frame']['frame-id'] + 1
    return {'returned': response, 'guest_get': get, 'settled': settled, 'new': next_frame}


def replay_both(debug, labels, entry, start, *, save_split=None):
    old = complete(debug, A, start=start)
    before = waiting(debug, labels, start)
    return_site(debug, labels)
    if save_split is not None:
        save_split(old, display(debug, B, (4, B[1]), next_fine=start + TRAILING))
    return {'old': old, 'waiting': before, 'after': finish_split(debug, labels, entry, start, old)}


def paired_controls(debug, labels, middle):
    # Restore X/Y between the two latches. The first complete frame uses
    # the retained coarse/vertical address with the new fine component.
    backward = issue(debug, labels, point=A, current=B, kind=0, start=middle, phase=LEADING + 512)
    assert backward['phase']['status1-timing-bits'] == 9
    return_site(debug, labels)
    pending = middle + PERIOD + LEADING
    return_back = display(debug, A, B, next_coarse=pending, next_fine=middle + TRAILING)
    assert backward['virtual_ns'] < return_back['virtual_ns'] < middle + TRAILING
    back_get = getter(debug, labels, A, backward, return_back)
    _reach(debug, middle + TRAILING + 4 * LINE)
    coarse_only = display(debug, A, (4, B[1]), next_coarse=pending)
    coarse = complete(debug, (4, B[1]), start=middle + PERIOD)
    zero = complete(debug, A, start=middle + 2 * PERIOD)

    # Request the combined offset during Vsync. BL80 waits through the
    # current trailing fine latch and returns at the next coarse latch.
    middle += 2 * PERIOD
    forward = issue(debug, labels, point=B, current=A, kind=0x80, start=middle, phase=LEADING + 512)
    assert forward['phase']['status1-timing-bits'] == 9
    _reach(debug, middle + TRAILING + 4 * LINE)
    fine_only = display(debug, B, (1, 0), next_coarse=middle + PERIOD + LEADING)
    fine = complete(debug, (1, 0), start=middle + PERIOD)
    return_site(debug, labels)
    forward_return = display(debug, B, B)
    assert middle + PERIOD + LEADING <= forward_return['virtual_ns'] < middle + PERIOD + TRAILING
    forward_get = getter(debug, labels, B, forward, forward_return)
    assert logical(source(debug))['frame'] == fine['frame']
    combined = complete(debug, B, start=middle + 2 * PERIOD)

    middle += 2 * PERIOD
    low = issue(debug, labels, point=A, current=B, kind=0x80, start=middle, phase=480 * LINE + LINE // 2)
    assert low['phase']['status1-timing-bits'] == 1
    return_site(debug, labels)
    low_return = display(debug, A, (1, 0), next_fine=middle + TRAILING)
    assert middle + LEADING <= low_return['virtual_ns'] < middle + TRAILING
    low_get = getter(debug, labels, A, low, low_return)
    final = complete(debug, A, start=middle + PERIOD)
    return {
        'backward': {'guest_get': back_get, 'coarse_only': coarse_only, 'mixed': coarse, 'final': zero},
        'forward': {'guest_get': forward_get, 'fine_only': fine_only, 'mixed': fine, 'final': combined},
        'low': {'guest_get': low_get, 'final': final},
    }


def reject_and_cancel(debug, labels, start, retained):
    entry = issue(debug, labels, point=B, current=A, kind=0, start=start, phase=120 * LINE + LINE // 2)
    return_site(debug, labels)
    deadlines = {'next_coarse': start + LEADING, 'next_fine': start + TRAILING}
    armed = display(debug, B, A, **deadlines)
    assert armed['configuration_generation'] == entry['configuration_generation'] + 1
    getter(debug, labels, B, entry, armed)

    enter_bios(debug, labels, (9, B[1]), 0, start, 132 * LINE + LINE // 2)
    before = display(debug, B, A, **deadlines)
    old_source = source(debug)
    park(debug, labels['post_bios'])
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == labels['bios_set'] + 2
    assert register(cpu, 'ax') & 0xFFFF == 0x014F
    after = display(debug, B, A, **deadlines)
    for key in ('configuration_generation', 'raw', 'coarse', 'fine'):
        assert after[key] == before[key], key
    rejected = getter(debug, labels, B, before, after, set_ax=0x014F)
    after_source = source(debug)
    for field in ('state', 'token', 'epoch', 'stream-generation', 'frame'):
        assert after_source[field] == old_source[field], field
    assert after_source['state'] == 'observing' and logical(after_source)['frame'] == retained['frame']
    rows = after_source['rows-sampled']
    assert old_source['rows-sampled'] <= rows < HEIGHT
    assert after_source['next-deadline-ns'] == start + rows * LINE + LINE // 4

    enter_bios(debug, labels, A, 0, start, 152 * LINE + LINE // 2)
    retarget = display(debug, B, A, **deadlines)
    return_site(debug, labels)
    settled = display(debug, A, A)
    assert settled['virtual_ns'] < start + LEADING
    assert settled['configuration_generation'] == armed['configuration_generation'] + 1
    replaced = getter(debug, labels, A, retarget, settled)
    current = complete(debug, A, start=start)
    following = complete(debug, A, start=start + PERIOD)
    return {
        'armed': armed,
        'before_reject': before,
        'after_reject': after,
        'guest_reject': rejected,
        'retarget': settled,
        'guest_retarget': replaced,
        'current': current,
        'following': following,
    }


def rom_hash(runtime):
    return digest(Path(runtime['firmware']) / ROM)


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


def load(debug, cut):
    previous = debug.vm.process
    loaded = debug.load_state(cut['artifact'], timeout_ms=60_000)
    assert loaded['instrumentation']['format'] == FORMAT
    owner = debug.vm.process
    assert owner is not previous and previous.poll() == 0
    current = source(debug)
    expected = cut['source']
    assert current['epoch'] != expected['epoch'] and current['token'] != expected['token']
    assert logical(current) == logical(expected)
    verify_export(debug, current, pixels(A))
    return owner


def restore_both(debug, spec):
    point = spec['both']
    owner = load(debug, point)
    assert waiting(debug, spec['labels'], spec['start']) == point['pending']
    return owner


def restore_split(debug, spec):
    point = spec['split']
    owner = load(debug, point)
    assert display(debug, B, (4, B[1]), next_fine=spec['start'] + TRAILING) == point['response']
    cpu = debug.registers()
    assert cpu == point['cpu']
    assert int(cpu['linear_pc'], 0) == spec['labels']['post_bios']
    return owner


def cold_replay(path):
    spec = json.loads(path.read_text())
    runtime = spec['runtime']
    assert digest(runtime['executable']) == spec['qemu_sha256']
    assert digest(spec['tool']) == spec['qemu_img_sha256'] and rom_hash(runtime) == spec['rom_sha256']
    labels, entry, start = (spec[key] for key in ('labels', 'entry', 'start'))
    with Project(path.parent / IMAGE) as project:
        with launch(project, path.parent, runtime, spec['disk'], spec['tool']) as debug:
            initial = debug.vm.process
            both = restore_both(debug, spec)
            first = replay_both(debug, labels, entry, start)
            split = restore_split(debug, spec)
            second = finish_split(debug, labels, entry, start, spec['split']['old'])
    owners = {'cold_entry': initial, 'cold_both': both, 'cold_split': split}
    assert len({p.pid for p in owners.values()}) == 3 and all(p.poll() == 0 for p in owners.values())
    return {
        'host_pid': os.getpid(),
        'both': first,
        'split': second,
        'owners': {key: {'pid': p.pid, 'returncode': p.poll()} for key, p in owners.items()},
    }


def test_native_vbe_combined_xy_both_and_split_checkpoints(tmp_path, clock_runtime, clock_disk):
    executable = clock_runtime['executable']
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    qemu, helper, rom = digest(executable), digest(tool), rom_hash(clock_runtime)
    assert (qemu, helper, rom) == tuple(
        os.environ[name]
        for name in (
            'FDISBULL_QEMU_VBE_XY_SHA256',
            'FDISBULL_QEMU_VBE_XY_IMG_SHA256',
            'FDISBULL_QEMU_VBE_XY_ROM_SHA256',
        )
    )
    code = assemble(
        tmp_path,
        'vbe-xy',
        source_with_xy_probe(_SOURCE)
        + '\ncolors: db '
        + ','.join(str(value) for color in _DAC for value in color),
        clock_runtime['nasm'],
    )
    assert sha256(code).hexdigest() == COM_SHA
    page_offsets, offsets = symbols(code)
    binary = tmp_path / 'PANXY.COM'
    binary.write_bytes(code)
    receipt = {
        'profile': PROFILE,
        'qemu_sha256': qemu,
        'qemu_img_sha256': helper,
        'rom_sha256': rom,
        'com_sha256': COM_SHA,
        'dosbox_reference_sha256': DOSBOX_REFERENCE,
        'completed': False,
    }
    owners, cold_owners = {}, {}

    def write():
        (tmp_path / 'vbe-xy-replay.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    try:
        with Project.create(tmp_path / IMAGE, binary, image='com') as project:
            with launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['source'] = debug.vm.process
                identity = process_record(debug)
                first, planar, held, _, advance = (com_address(identity, at) for at in page_offsets)
                labels = {name: com_address(identity, at) for name, at in offsets.items()}
                park(debug, first)
                debug.write_memory(advance, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(advance, '02', expected_hex='01')
                park(debug, held)
                debug.write_memory(labels['pan_setup_go'], '01', expected_hex='00')
                park(debug, labels['pan_ready'])
                assert read_memory(debug, labels['pan_setup_go'], 1) == b'\x02'
                setup = SETUP_RESULT.unpack(read_memory(debug, labels['pan_setup_result'], SETUP_RESULT.size))
                assert setup[:3] == (0x004F, PITCH, PITCH) and setup[3] >= HEIGHT + B[1]
                receipt['bios_pitch'] = list(setup)
                assert display(debug, A, A)['raw']['vbe'][6] == PITCH
                debug.video_frame_start()
                retained = receipt['retained'] = complete(debug, A)
                start = retained['frame']['frame-start-ns'] + PERIOD
                entry = receipt['entry'] = issue(
                    debug,
                    labels,
                    point=B,
                    current=A,
                    kind=0x80,
                    start=start,
                    phase=120 * LINE + LINE // 2,
                )
                assert not entry['phase']['status1-timing-bits'] & 8
                _reach(debug, start + 145 * LINE + LINE // 2)
                partial = source(debug)
                assert partial['rows-sampled'] == 146 and logical(partial)['frame'] == retained['frame']
                assert partial['next-deadline-ns'] == start + 146 * LINE + LINE // 4
                pending = receipt['pending'] = waiting(debug, labels, start)
                assert pending['display']['configuration_generation'] == entry['configuration_generation'] + 1
                verify_export(debug, partial, pixels(A))
                saved = debug.save_state('xy-both-pending')
                receipt['partial_rows'] = partial['rows-sampled']
                receipt['both_checkpoint_sha256'] = saved['sha256']
                spec = {
                    **receipt,
                    'start': start,
                    'labels': labels,
                    'tool': tool,
                    'both': {'source': partial, 'artifact': saved['artifact'], 'pending': pending},
                    'disk': {'image': str(clock_disk['image'])},
                    'runtime': {k: str(v) if isinstance(v, Path) else v for k, v in clock_runtime.items()},
                }
                write()

                def save_split(old, response):
                    cut = {
                        'old': old,
                        'response': response,
                        'source': source(debug),
                        'cpu': debug.registers(),
                    }
                    artifact = debug.save_state('xy-fine-pending')
                    spec['split'] = {**cut, 'artifact': artifact['artifact']}
                    receipt['split_checkpoint_sha256'] = artifact['sha256']
                    assert display(debug, B, (4, B[1]), next_fine=start + TRAILING) == response

                receipt['forward'] = replay_both(debug, labels, entry, start, save_split=save_split)
                write()
                owners['hot_both'] = restore_both(debug, spec)
                receipt['hot_both'] = replay_both(debug, labels, entry, start)
                assert receipt['hot_both'] == receipt['forward']
                owners['hot_split'] = restore_split(debug, spec)
                receipt['hot_split'] = finish_split(debug, labels, entry, start, spec['split']['old'])
                assert receipt['hot_split'] == receipt['forward']['after']
                write()
                receipt['controls'] = paired_controls(debug, labels, start + PERIOD)
                last = receipt['controls']['low']['final']
                receipt['reject_and_cancel'] = reject_and_cancel(
                    debug,
                    labels,
                    last['frame']['frame-start-ns'] + PERIOD,
                    last,
                )
            assert all(owner.poll() == 0 for owner in owners.values())

        path = tmp_path / 'cold-spec.json'
        path.write_text(json.dumps(spec))
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        (tmp_path / 'cold.log').write_text(child.stdout + child.stderr)
        assert child.returncode == 0, child.stderr
        report = json.loads(child.stdout)
        assert report['host_pid'] != os.getpid()
        cold_owners = report['owners']
        assert not {owner.pid for owner in owners.values()} & {info['pid'] for info in cold_owners.values()}
        receipt['cold_both'] = report['both']
        receipt['cold_split'] = report['split']
        assert (
            receipt['cold_both'] == receipt['forward']
            and receipt['cold_split'] == receipt['forward']['after']
        )
        receipt['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        receipt['owners'] = {
            **{stage: {'pid': owner.pid, 'returncode': owner.poll()} for stage, owner in owners.items()},
            **cold_owners,
        }
        write()


if __name__ == '__main__':
    print(json.dumps(cold_replay(Path(sys.argv[1]))))
