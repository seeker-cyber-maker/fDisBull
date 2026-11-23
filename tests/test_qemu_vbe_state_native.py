"""Restore a guest's saved VBE 101h display state after a machine checkpoint."""

from hashlib import sha256
import json
import os
from pathlib import Path
from struct import unpack
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support import paired_vbe_state as witness
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vbe_flip_native import read_memory
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach


PROFILE = 'vga-640x480-vbe-state'
MODEL = 'qemu-vga-640x480-lfb-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-14'
ROM = 'fdisbull-vgabios-vbe101-state.bin'
DATABASE = 'vbe-state.fdb'
CUT_ROWS = 146

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_STATE') != '1',
    reason='Select the QEMU VBE display-state producer and DOSBox-X reference',
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


def _go(debug, labels, command):
    debug.write_memory(labels['rm_go'], f'{command:02x}', expected_hex=f'{command - 1:02x}')


def _raw(debug):
    return debug.vga_configuration_observe()['current']['raw']


def _complete(debug, scene, *, start=None):
    advance = debug.video_frame_advance(timeout_ms=8000)
    assert advance['advance_completed'], advance
    observed = source(debug)
    assert observed['state'] == 'observing' and observed['model'] == MODEL
    frame = observed['frame']
    assert observed['scanout-layout'] == frame['scanout-layout'] == 'vbe-banked-101'
    assert (frame['width'], frame['height'], frame['pixel-format']) == (640, HEIGHT, 'RGB888')
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    pitch, origin = (witness.MUTATED_PITCH, 0) if scene == 'mutated' else (witness.PITCH, witness.ORIGIN)
    assert (frame['vbe101-origin-bytes'], frame['vbe101-pitch-bytes'], frame['vbe101-pel']) == (
        origin & ~3, pitch, origin & 3)
    stamp = frame['frame-start-ns']
    if start is not None:
        assert stamp == start
    assert stamp % PERIOD == 0 and len(frame['rows']) == HEIGHT
    for index, row in enumerate(frame['rows']):
        intended = stamp + LINE // 4 + index * LINE
        assert row['row'] == index and row['intended-ns'] == intended
        assert intended <= row['actual-ns'] < intended + LINE
    pixels = witness.expected_rgb(scene)
    assert frame['pixel-sha256'] == sha256(pixels).hexdigest()
    verify_export(debug, observed, pixels)
    return logical(observed)['frame']


def _buffer(debug, labels, size):
    return read_memory(debug, labels['state_buffer'], size)


def _save_block(debug, labels, size):
    guard = witness.STATE_FILL
    address = labels['state_buffer']
    assert labels['state_guard'] == address - 16
    data = read_memory(debug, address - 16, witness.STATE_BYTES + 32)
    assert data[:16] == bytes([guard]) * 16
    assert data[16 + size:] == bytes([guard]) * (witness.STATE_BYTES + 16 - size)
    payload = data[16:16 + size]
    assert payload != bytes([guard]) * size
    return payload


def _phase(debug, labels, scene):
    data = read_memory(debug, labels['phase_results'], witness.PHASE_RESULT.size * len(witness.PHASES))
    state = witness.phases(data)[scene]
    pitch, origin, bank, color = (
        (witness.MUTATED_PITCH, 0, 3, witness.MUTATED_COLOR) if scene == 'mutated' else
        (witness.PITCH, witness.ORIGIN, 2, witness.PALETTE[0]))
    x, y = origin % pitch, origin // pitch
    assert all(value == 0x004f for key, value in state.items() if key.endswith('_ax'))
    assert state['mode'] == 0x0101
    assert (state['pitch'], state['pixels'], state['lines']) == (pitch, pitch, (16 << 20) // pitch)
    assert (state['x'], state['y'], state['bank'], state['dac_width']) == (x, y, bank, 6)
    assert state['color'] == bytes((*reversed(color), 0xcc)).hex()
    expected_probe = 7 if scene == 'initial' else witness.VRAM_MUTATION
    assert state['probe'] == expected_probe
    raw = _raw(debug)
    assert raw['vbe'][1:6] == [640, HEIGHT, 8, 1, bank]
    assert raw['vbe'][6] == pitch and raw['vbe'][8:10] == [x, y]
    assert raw['vbe-line-offset'] == pitch and raw['bank-offset'] == bank * witness.BANK_BYTES
    return state


def _capture_cut(debug, labels, buffer_size, start):
    cpu = debug.registers()
    assert cpu['cpu_mode'] == 'real'
    address = int(cpu['linear_pc'], 0)
    assert address == labels['rm_mutated']
    clock = debug.clock_observe()['virtual_ns']
    state = source(debug)
    assert state['state'] == 'observing' and state['scanout-layout'] == 'vbe-banked-101'
    assert state['rows-sampled'] == CUT_ROWS
    assert state['next-deadline-ns'] == start + CUT_ROWS * LINE + LINE // 4
    assert read_memory(debug, labels['rm_go'], 1) == b'\x02'
    return {
        'clock': clock, 'cpu': cpu, 'raw': _raw(debug), 'source': state,
        'buffer-sha256': sha256(_save_block(debug, labels, buffer_size)).hexdigest(),
    }


def _restore(debug, labels, cut):
    old = debug.vm.process
    loaded = debug.load_state(cut['artifact'], timeout_ms=60_000)
    assert loaded['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not old and old.poll() == 0
    current = _capture_cut(debug, labels, cut['buffer_size'], cut['start'])
    actual_source = current.pop('source')
    expected = cut['capture']
    previous_source = expected['source']
    assert actual_source['token'] != previous_source['token']
    assert actual_source['epoch'] != previous_source['epoch']
    assert logical(actual_source) == logical(previous_source)
    assert current == {key: expected[key] for key in current}
    return debug.vm.process


def _settle_restored_viewport(debug):
    retrace = debug.retrace_observe()['native']
    display = retrace['vbe101-display-start']
    panning = retrace['vbe101-panning']
    assert display['programmed-origin-bytes'] == witness.ORIGIN & ~3
    assert panning['programmed-pel'] == witness.ORIGIN & 3
    deadlines = [state['pending-deadline-ns'] for state in (display, panning)
                 if 'pending-deadline-ns' in state]
    if deadlines:
        _reach(debug, max(deadlines) + LINE // 4)
    settled = debug.retrace_observe()['native']
    assert settled['vbe101-display-start']['active-origin-bytes'] == witness.ORIGIN & ~3
    assert settled['vbe101-panning']['active-pel'] == witness.ORIGIN & 3
    return {'display': display, 'panning': panning}


def _continue(debug, labels, cut):
    disturbed = _complete(debug, 'mutated', start=cut['start'])
    _go(debug, labels, 3)
    park(debug, labels['rm_restored'])
    assert source(debug)['state'] == 'invalidated'
    assert unpack('<2H', read_memory(debug, labels['statuses'], 4)) == (0x004f, 0x004f)
    assert sha256(_save_block(debug, labels, cut['buffer_size'])).hexdigest() == cut['capture']['buffer-sha256']
    phase = _phase(debug, labels, 'restored')
    viewport = _settle_restored_viewport(debug)
    debug.video_frame_start()
    restored = _complete(debug, 'restored')
    _go(debug, labels, 4)
    park(debug, labels['rm_dac_done'])
    dac = witness.dac_probe(read_memory(debug, labels['dac_results'], witness.DAC_RESULT.size))
    assert all(value == 0x004f for key, value in dac.items() if key.endswith('_ax'))
    assert dac['width'] == 8 and dac['color'] == bytes((*reversed(witness.DAC8_COLOR), 0xcc)).hex()
    assert _raw(debug)['dac-8bit'] is True
    return {'disturbed': disturbed, 'restored': restored, 'phase': phase, 'dac': dac,
            'viewport': viewport}


def _owners(**processes):
    owners = {name: {'pid': process.pid, 'returncode': process.poll()}
              for name, process in processes.items()}
    assert len({item['pid'] for item in owners.values()}) == len(owners)
    assert all(item['returncode'] == 0 for item in owners.values())
    return owners


def _cold_replay(path):
    spec = json.loads(path.read_text())
    runtime, tool = spec['runtime'], spec['tool']
    assert _producer(runtime, tool) == spec['producer']
    with Project(path.parent / DATABASE) as project:
        with _launch(project, path.parent, runtime, spec['disk'], tool) as debug:
            initial = debug.vm.process
            restored = _restore(debug, spec['labels'], spec['cut'])
            continued = _continue(debug, spec['labels'], spec['cut'])
    return {
        'host_pid': os.getpid(), 'result': continued,
        'owners': _owners(cold_initial=initial, cold_restored=restored),
    }


def _run_cold(path, spec):
    path.write_text(json.dumps(spec))
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(path)],
        text=True, capture_output=True, timeout=120, check=False,
    )
    path.with_name('cold.log').write_text(process.stdout + process.stderr)
    assert process.returncode == 0, process.stderr
    cold = json.loads(process.stdout)
    assert cold.pop('host_pid') != os.getpid()
    return cold


def _check_pair(record, reference):
    assert reference['owner_rc'] == 0
    assert record['initial'] == reference['phases']['initial']
    assert record['mutated'] == reference['phases']['mutated']
    restored = record['forward']['phase']
    reference_restored = reference['phases']['restored']
    for field in ('mode', 'dac_width', 'color', 'probe'):
        assert restored[field] == reference_restored[field]
    # The pinned S3 implementation resets these fields during 4F04h restore.
    assert tuple(reference_restored[key] for key in ('pitch', 'x', 'y', 'bank')) == (640, 1, 0, 0)
    assert (reference['dac8']['width'], reference['dac8']['color']) == (6, '073615cc')
    for name, frame in (
        ('initial', record['baseline']),
        ('mutated', record['forward']['disturbed']),
    ):
        assert frame['pixel-sha256'] == reference['frames'][name]['pixel_sha256']


def test_vbe_guest_display_state_block_survives_hot_and_fresh_checkpoint_restore(
        tmp_path, clock_runtime, clock_disk):
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    producer = _producer(clock_runtime, tool)
    for key, suffix in (('qemu', 'SHA256'), ('qemu-img', 'IMG_SHA256'), ('rom', 'ROM_SHA256')):
        assert producer[key] == os.environ[f'FDISBULL_QEMU_VBE_STATE_{suffix}']
    reference_path = Path(os.environ['FDISBULL_DOSBOX_VBE_STATE_REFERENCE']).resolve(strict=True)
    reference_sha = digest(reference_path)
    assert reference_sha == os.environ['FDISBULL_DOSBOX_VBE_STATE_REFERENCE_SHA256']
    reference = json.loads(reference_path.read_text())
    code = assemble(tmp_path, 'vbe-state', witness.SOURCE, clock_runtime['nasm'])
    code_sha = sha256(code).hexdigest()
    assert code_sha == reference['authored_com_sha256']
    binary = tmp_path / 'STATE.COM'
    binary.write_bytes(code)
    record = {
        'producer': producer, 'profile': PROFILE, 'format': FORMAT,
        'reference_sha256': reference_sha, 'authored_com_sha256': code_sha,
        'completed': False,
    }

    try:
        with Project.create(tmp_path / DATABASE, binary, image='com') as project:
            with _launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                original = debug.vm.process
                identity = process_record(debug)
                labels = {name: com_address(identity, offset)
                          for name, offset in witness.labels(code).items()}
                park(debug, labels['rm_ready'])
                size_data = read_memory(debug, labels['size_results'],
                                        witness.SIZE_RESULT.size * len(witness.SIZE_MASKS))
                sizes = record['sizes'] = witness.sizes(size_data)
                size_ax, blocks = sizes[0x0f]
                assert size_ax == 0x004f and 0 < blocks * 64 <= witness.STATE_BYTES
                buffer_size = blocks * 64
                assert _buffer(debug, labels, witness.STATE_BYTES) == bytes([witness.STATE_FILL]) * witness.STATE_BYTES
                record['initial'] = _phase(debug, labels, 'initial')
                debug.video_frame_start()
                record['baseline'] = _complete(debug, 'initial')

                _go(debug, labels, 1)
                park(debug, labels['rm_saved'])
                assert unpack('<H', read_memory(debug, labels['statuses'], 2)) == (0x004f,)
                saved_hash = sha256(_save_block(debug, labels, buffer_size)).hexdigest()
                _go(debug, labels, 2)
                park(debug, labels['rm_mutated'])
                record['mutated'] = _phase(debug, labels, 'mutated')
                assert source(debug)['state'] == 'invalidated'
                debug.video_frame_start()
                last = _complete(debug, 'mutated')
                start = last['frame-start-ns'] + PERIOD
                _reach(debug, start + (CUT_ROWS - 1) * LINE + LINE // 2)
                park(debug, labels['rm_mutated'])
                capture = _capture_cut(debug, labels, buffer_size, start)
                assert capture['buffer-sha256'] == saved_hash
                assert logical(capture['source'])['frame'] == last
                saved = debug.save_state('vbe-display-state.qcow2')
                assert _capture_cut(debug, labels, buffer_size, start) == capture
                cut = {'artifact': saved['artifact'], 'start': start,
                       'buffer_size': buffer_size, 'capture': capture}
                record['checkpoint'] = {
                    'sha256': saved['sha256'], 'rows': capture['source']['rows-sampled'],
                    'cpu': capture['cpu'], 'guest-buffer-sha256': saved_hash,
                }
                record['forward'] = _continue(debug, labels, cut)
                hot = _restore(debug, labels, cut)
                record['hot'] = _continue(debug, labels, cut)
                assert record['hot'] == record['forward']

        record['owners'] = _owners(original=original, hot=hot)
        cold = _run_cold(tmp_path / 'cold-spec.json', {
            'runtime': {key: str(value) if isinstance(value, Path) else value
                        for key, value in clock_runtime.items()},
            'disk': {'image': str(clock_disk['image'])}, 'tool': tool,
            'producer': producer, 'labels': labels, 'cut': cut,
        })
        record['cold'] = cold['result']
        assert record['cold'] == record['forward']
        assert not {item['pid'] for item in record['owners'].values()} & {
            item['pid'] for item in cold['owners'].values()}
        record['owners'].update(cold['owners'])
        _check_pair(record, reference)
        record['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vbe-state-replay.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    print(json.dumps(_cold_replay(Path(sys.argv[1]))))
