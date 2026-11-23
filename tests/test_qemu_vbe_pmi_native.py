"""Paired VBE 101h protected-mode calls and a checkpoint in copied BIOS code."""

import json
import os
from hashlib import sha256
from pathlib import Path
from struct import unpack
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_pmi import (
    EXPECTED_BANK, EXPECTED_TIMED_RGB, ORIGIN, PITCH, SOURCE, expected_rgb, labels as pmi_offsets,
)
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vbe_flip_native import read_memory, register
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD, expected_status
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach


PROFILE = 'vga-640x480-pmi'
ROM = 'fdisbull-vgabios-vbe101-pmi.bin'
MODEL = 'qemu-vga-640x480-palette-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-13'
DATABASE = 'vbe-pmi.fdb'
LAYOUT = 'vbe-banked-101'
PALETTE_ROWS = 146

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_PMI') != '1',
    reason='Select the exact VBE protected-mode QEMU producer and DOSBox-X reference',
)


def _launch(project, directory, runtime, disk, tool):
    return project.debugger(
        runtime['executable'], directory,
        **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise',
                         qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=tool),
    )


def _producer(runtime, tool):
    return {
        'qemu': digest(runtime['executable']),
        'qemu-img': digest(tool),
        'rom': digest(Path(runtime['firmware']) / ROM),
    }


def _clock(debug):
    return debug.clock_observe()['virtual_ns']


def _window(debug):
    return debug.vga_configuration_observe()['current']['raw']


def _table(debug, *, rom_address, copy_address, size):
    assert 0xc0000 <= rom_address < rom_address + size <= 0xe0000
    assert 8 < size <= 1024 and 0 < copy_address < 0xa0000
    original = read_memory(debug, rom_address, size, space='physical')
    copy = read_memory(debug, copy_address, size)
    assert copy == original
    window, display, palette, ports = unpack('<4H', copy[:8])
    assert len({window, display, palette}) == 3
    assert all(8 <= entry < size for entry in (window, display, palette))
    assert 8 <= ports < size - 1
    permission_words = []
    for offset in range(ports, size - 1, 2):
        word, = unpack('<H', copy[offset:offset + 2])
        permission_words.append(word)
        if word == 0xffff:
            break
    assert permission_words[-1] == 0xffff
    assert {0x3c8, 0x3c9, 0x3da} <= set(permission_words[:-1])
    return {
        'table': copy_address,
        'table_end': copy_address + size,
        'table_sha256': sha256(copy).hexdigest(),
        'window_entry': copy_address + window,
        'display_entry': copy_address + display,
        'palette_entry': copy_address + palette,
        'ports': permission_words,
    }


def _setup(debug, labels):
    cpu = debug.registers()
    assert cpu['cpu_mode'] == 'protected' and cpu['address_state']['code_bits'] == 32
    query_bytes = read_memory(debug, labels['pmi_queries'], 5 * 8)
    startup = read_memory(debug, labels['pmi_startup'], 8)
    assert startup == query_bytes[:8]
    queries = [unpack('<4H', query_bytes[i:i + 8]) for i in range(0, len(query_bytes), 8)]
    assert [query[0] for query in queries] == [0x004f] * 4 + [0x014f]
    _, size, offset, segment = queries[0]
    rom = segment * 16 + offset
    table = _table(debug, rom_address=rom, copy_address=labels['pmi_copy'], size=size)
    starts = [table[key] - labels['pmi_copy'] for key in ('window_entry', 'display_entry', 'palette_entry')]
    ends = starts[1:] + [size]
    assert [(query[1], query[3] * 16 + query[2]) for query in queries[1:4]] == [
        (end - start, rom + start) for start, end in zip(starts, ends, strict=True)]
    return dict(
        table, queries=[list(query) for query in queries], startup=list(unpack('<4H', startup)),
        cuts={
            'palette': {'entry': table['palette_entry'], 'end': table['table_end'],
                        'return': labels['pm_palette_return'], 'rows': PALETTE_ROWS,
                        'command': 1, 'caller': labels['pm_timed_call'], 'active_origin': 0},
            'display': {'entry': table['display_entry'], 'end': table['palette_entry'],
                        'return': labels['pm_timed_start_return'], 'rows': 96,
                        'command': 3, 'caller': labels['pm_timed_start_call'], 'active_origin': ORIGIN},
        },
    )


def _guest_result(debug, labels):
    bank = read_memory(debug, labels['pm_result'], len(EXPECTED_BANK))
    palette = read_memory(debug, labels['pm_palette_capture'], len(EXPECTED_TIMED_RGB))
    status = list(read_memory(debug, labels['pm_status'], 4))
    readback = list(unpack('<3H', read_memory(debug, labels['rm_readback'], 6)))
    assert (bank, palette) == (EXPECTED_BANK, EXPECTED_TIMED_RGB)
    assert [value & 8 for value in status] == [0, 8, 0, 8]
    assert readback == [0x004f, 0, 0]
    return {'bank': bank.hex(), 'palette': palette.hex(), 'status': status, 'real_readback': readback}


def _frame(debug, pixels, *, model, pitch, origin, start=None):
    state = source(debug)
    frame = state['frame']
    assert state['model'] == model and state['state'] == 'observing'
    assert state['scanout-layout'] == frame['scanout-layout'] == LAYOUT
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (640, 480, 1920, 'RGB888')
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    assert (frame['vbe101-origin-bytes'], frame['vbe101-pitch-bytes'], frame['vbe101-pel']) == (origin, pitch, 0)
    if start is not None:
        assert frame['frame-start-ns'] == start
    start = frame['frame-start-ns']
    assert len(frame['rows']) == HEIGHT
    for index, row in enumerate(frame['rows']):
        intended = start + LINE // 4 + index * LINE
        assert row['row'] == index and row['intended-ns'] == intended
        assert intended <= row['actual-ns'] < intended + LINE
    assert frame['pixel-sha256'] == sha256(pixels).hexdigest()
    verify_export(debug, state, pixels)
    return logical(state)['frame']


def _complete(debug, pixels, **kwargs):
    advance = debug.video_frame_advance(timeout_ms=8000)
    assert advance['advance_completed'], advance
    return _frame(debug, pixels, **kwargs)


def _checkpoint_cut(debug, layout, kind):
    boundary = layout['cuts'][kind]
    cpu = debug.registers()
    context = cpu['address_state']
    assert cpu['cpu_mode'] == 'protected'
    assert (context['code_bits'], context['stack_bits'], context['paging']) == (32, 32, False)
    assert context['register_context_match'] is True
    pc = int(cpu['linear_pc'], 0)
    assert boundary['entry'] <= pc < boundary['end']
    assert read_memory(debug, pc, 1) in (b'\xec', b'\xa8', b'\x74')
    assert register(cpu, 'dx') & 0xffff == 0x03da
    clock = _clock(debug)
    assert expected_status(clock) & 8 == 0
    video = source(debug)
    assert video['rows-sampled'] == boundary['rows']
    displays = debug.retrace_observe()['native']['vbe101-display-start']
    assert displays['programmed-origin-bytes'] == 0
    assert displays['active-origin-bytes'] == boundary['active_origin']
    if kind == 'display':
        assert displays['pending-deadline-ns'] == clock - clock % PERIOD + 490 * LINE
    else:
        assert 'pending-deadline-ns' not in displays
    sp = int(context['segments']['ss']['base'], 0) + register(cpu, 'sp')
    saved_stack = read_memory(debug, sp, 64)
    return_ip = boundary['return'] - int(context['segments']['cs']['base'], 0)
    assert unpack('<I', saved_stack[32:36])[0] == return_ip
    table = read_memory(debug, layout['table'], layout['table_end'] - layout['table'])
    assert sha256(table).hexdigest() == layout['table_sha256']
    return {
        'clock': clock,
        'cpu': cpu,
        'ip-bytes': read_memory(debug, pc, 2).hex(),
        'table_sha256': layout['table_sha256'],
        'stack': saved_stack.hex(),
        'video': video,
        'vga': _window(debug),
        'display': displays,
    }


def _assert_reproduced(fresh, held):
    video = fresh['video']
    assert video['token'] != held['video']['token'] and video['epoch'] != held['video']['epoch']
    assert logical(video) == logical(held['video'])
    assert {key: value for key, value in fresh.items() if key != 'video'} == {
        key: value for key, value in held.items() if key != 'video'}


def _restore(debug, cut, layout):
    owner = debug.vm.process
    restore = debug.load_state(cut['artifact'], timeout_ms=60_000)
    assert restore['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not owner and owner.poll() == 0
    _assert_reproduced(_checkpoint_cut(debug, layout, cut['kind']), cut['evidence'])
    return debug.vm.process


def _owner_receipts(processes):
    receipts = {name: {'pid': process.pid, 'returncode': process.poll()}
                for name, process in processes.items()}
    assert len({value['pid'] for value in receipts.values()}) == len(receipts)
    assert all(value['returncode'] == 0 for value in receipts.values())
    return receipts


def _arm(debug, labels, command):
    address = labels['pm_go']
    debug.write_memory(address, f'{command:02x}', expected_hex=f'{command - 1:02x}')


def _wait_to_cut(debug, labels, layout, start, kind):
    # Enter in active scanout with ample time to stop inside the actual BIOS
    # poll. Both the pre-edge raster prefix and the PM caller are live.
    _reach(debug, start + 64 * LINE + LINE // 2)
    boundary = layout['cuts'][kind]
    _arm(debug, labels, boundary['command'])
    park(debug, boundary['caller'])
    entered = _clock(debug)
    assert start + 64 * LINE <= entered < start + 65 * LINE
    assert expected_status(entered) & 8 == 0
    _reach(debug, start + (boundary['rows'] - 1) * LINE + LINE // 2)
    return _checkpoint_cut(debug, layout, kind)


def _save_cut(debug, layout, kind, evidence, previous):
    assert logical(evidence['video'])['frame'] == previous
    saved = debug.save_state(f'relocated-pmi-{kind}.qcow2')
    assert _checkpoint_cut(debug, layout, kind) == evidence
    return {'artifact': saved['artifact'], 'sha256': saved['sha256'], 'evidence': evidence, 'kind': kind}


def _return_from_wait(debug, site, start):
    park(debug, site)
    cpu = debug.registers()
    assert cpu['cpu_mode'] == 'protected'
    assert int(cpu['linear_pc'], 0) == site
    now = _clock(debug)
    leading = start + 490 * LINE
    assert leading <= now < leading + LINE // 2
    assert expected_status(now) & 8
    return {'clock': now, 'cpu': cpu}


def _after_palette(debug, labels, start):
    previous = _complete(debug, expected_rgb(), model=MODEL, pitch=PITCH, origin=0, start=start)
    returned = _return_from_wait(debug, labels['pm_palette_return'], start)
    assert logical(source(debug))['frame'] == previous
    park(debug, labels['pm_done'])
    changed = _complete(debug, expected_rgb(changed=True), model=MODEL, pitch=PITCH,
                        origin=0, start=start + PERIOD)
    assert changed['frame-id'] == previous['frame-id'] + 1
    _arm(debug, labels, 2)
    park(debug, labels['pm_display_return'])
    assert _window(debug)['vbe'][8:10] == [ORIGIN % PITCH, ORIGIN // PITCH]
    assert logical(source(debug))['frame'] == changed
    assert labels['pm_flipped'] == labels['pm_display_return']
    flipped = _complete(debug, expected_rgb(origin=ORIGIN, changed=True), model=MODEL,
                        pitch=PITCH, origin=ORIGIN, start=start + 2 * PERIOD)
    return {'before': previous, 'return': returned, 'after': changed, 'flipped': flipped}


def _after_display(debug, labels, start):
    intact = _complete(debug, expected_rgb(origin=ORIGIN, changed=True), model=MODEL,
                       pitch=PITCH, origin=ORIGIN, start=start)
    restored_when = _return_from_wait(debug, labels['pm_timed_start_return'], start)
    assert _window(debug)['vbe'][8:10] == [0, 0]
    assert logical(source(debug))['frame'] == intact
    park(debug, labels['pm_restored'])
    restored = _complete(debug, expected_rgb(changed=True), model=MODEL, pitch=PITCH,
                         origin=0, start=start + PERIOD)
    _arm(debug, labels, 4)
    park(debug, labels['rm_done'])
    assert debug.registers()['cpu_mode'] == 'real'
    return {'display-retained': intact, 'return-to-zero': restored, 'display-return': restored_when,
            'vga': _window(debug), 'guest': _guest_result(debug, labels)}


def _replay_palette(debug, labels, start, table, display_cut):
    palette = _after_palette(debug, labels, start)
    display_start = start + 3 * PERIOD
    _assert_reproduced(_wait_to_cut(debug, labels, table, display_start, 'display'),
                       display_cut['evidence'])
    return palette | _after_display(debug, labels, display_start)


def _check_pair(record, reference):
    forward = record['forward']
    guest = forward['guest']
    for field in ('bank', 'palette', 'real_readback'):
        assert guest[field] == reference[field]
    assert [value & 8 for value in guest['status']] == [value & 8 for value in reference['status']]
    assert [query[0] for query in record['table']['queries']] == reference['table']['entries']
    for name, actual in (
        ('baseline', record['baseline']), ('old-retained', forward['before']),
        ('changed', forward['after']), ('panned', forward['flipped']),
        ('zero', forward['return-to-zero']),
    ):
        assert actual['pixel-sha256'] == reference['frames'][name]['pixel_sha256']


def _cold_replay(path):
    spec = json.loads(path.read_text())
    runtime, tool = spec['runtime'], spec['tool']
    assert _producer(runtime, tool) == spec['producer']
    with Project(path.parent / DATABASE) as project:
        with _launch(project, path.parent, runtime, spec['disk'], tool) as debug:
            initial = debug.vm.process
            palette = _restore(debug, spec['palette-cut'], spec['table'])
            continued = _replay_palette(debug, spec['labels'], spec['start'],
                                        spec['table'], spec['display-cut'])
            display = _restore(debug, spec['display-cut'], spec['table'])
            continued_display = _after_display(debug, spec['labels'], spec['start'] + 3 * PERIOD)
    return {
        'host_pid': os.getpid(),
        'continued': continued,
        'continued-display': continued_display,
        'owners': _owner_receipts({'cold_initial': initial, 'cold_palette': palette, 'cold_display': display}),
    }


def _run_cold(path, spec):
    path.write_text(json.dumps(spec))
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(path)],
        text=True, capture_output=True, timeout=120, check=False,
    )
    path.with_name('cold.log').write_text(process.stdout + process.stderr)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result.pop('host_pid') != os.getpid()
    return result


def test_vbe_pmi_restores_timed_calls_inside_relocated_pm_code(tmp_path, clock_runtime, clock_disk):
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    producer = _producer(clock_runtime, tool)
    for key, suffix in (('qemu', 'SHA256'), ('qemu-img', 'IMG_SHA256'), ('rom', 'ROM_SHA256')):
        assert producer[key] == os.environ[f'FDISBULL_QEMU_VBE_PMI_{suffix}']
    reference_path = Path(os.environ['FDISBULL_DOSBOX_VBE_PMI_REFERENCE']).resolve(strict=True)
    reference_sha = digest(reference_path)
    assert reference_sha == os.environ['FDISBULL_DOSBOX_VBE_PMI_REFERENCE_SHA256']
    reference = json.loads(reference_path.read_text())
    code = assemble(tmp_path, 'vbe-pmi', SOURCE, clock_runtime['nasm'])
    offsets = pmi_offsets(code)
    code_sha = sha256(code).hexdigest()
    assert code_sha == reference['authored_com_sha256']
    binary = tmp_path / 'PMI.COM'
    binary.write_bytes(code)
    record = {
        'producer': producer, 'profile': PROFILE, 'format': FORMAT,
        'reference_sha256': reference_sha, 'authored_com_sha256': code_sha,
        'completed': False,
    }
    owners = {}

    try:
        with Project.create(tmp_path / DATABASE, binary, image='com') as project:
            with _launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['original'] = debug.vm.process
                identity = process_record(debug)
                labels = {name: com_address(identity, offset) for name, offset in offsets.items()}
                park(debug, labels['pm_ready'])
                table = record['table'] = _setup(debug, labels)
                debug.video_frame_start()
                baseline = record['baseline'] = _complete(
                    debug, expected_rgb(), model=MODEL, pitch=PITCH, origin=0)
                start = baseline['frame-start-ns'] + PERIOD
                palette_cut = _save_cut(debug, table, 'palette',
                                        _wait_to_cut(debug, labels, table, start, 'palette'), baseline)
                forward_palette = _after_palette(debug, labels, start)
                display_start = start + 3 * PERIOD
                display_cut = _save_cut(debug, table, 'display',
                                        _wait_to_cut(debug, labels, table, display_start, 'display'),
                                        forward_palette['flipped'])
                record['checkpoints'] = {
                    cut['kind']: dict(sha256=cut['sha256'], rows=cut['evidence']['video']['rows-sampled'],
                                      cut_pc=cut['evidence']['cpu']['linear_pc'],
                                      stack=cut['evidence']['stack'], display=cut['evidence']['display'])
                    for cut in (palette_cut, display_cut)
                }
                forward_display = _after_display(debug, labels, display_start)
                record['forward'] = forward_palette | forward_display
                owners['hot_palette'] = _restore(debug, palette_cut, table)
                record['hot'] = _replay_palette(debug, labels, start, table, display_cut)
                assert record['hot'] == record['forward']
                owners['hot_display'] = _restore(debug, display_cut, table)
                record['hot-display'] = _after_display(debug, labels, display_start)
                assert record['hot-display'] == forward_display

        record['owners'] = _owner_receipts(owners)
        cold = _run_cold(tmp_path / 'cold-spec.json', {
            'runtime': {key: str(value) if isinstance(value, Path) else value
                        for key, value in clock_runtime.items()},
            'disk': {'image': str(clock_disk['image'])}, 'tool': tool,
            'producer': producer, 'palette-cut': palette_cut, 'display-cut': display_cut,
            'labels': labels, 'table': table, 'start': start,
        })
        assert not {p.pid for p in owners.values()} & {p['pid'] for p in cold['owners'].values()}
        record['owners'].update(cold['owners'])
        record['cold'] = cold['continued']
        assert record['cold'] == record['forward']
        record['cold-display'] = cold['continued-display']
        assert record['cold-display'] == forward_display
        _check_pair(record, reference)
        record['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vbe-pmi-replay.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    print(json.dumps(_cold_replay(Path(sys.argv[1]))))
