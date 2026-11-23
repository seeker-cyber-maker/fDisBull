"""VBE 101h guest LFB writes and two checkpoint cuts against DOSBox-X."""

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
from support import paired_vbe_lfb as witness
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vbe_flip_native import read_memory, register
from test_qemu_vbe_guest_retrace_native import HEIGHT, LINE, PERIOD
from test_qemu_vga_640_checkpoint_native import logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach


PROFILE = 'vga-640x480-lfb'
MODEL = 'qemu-vga-640x480-lfb-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-14'
ROM = 'fdisbull-vgabios-vbe101-lfb.bin'
DATABASE = 'vbe-lfb.fdb'
LINEAR = 'vbe-linear-101'
BANKED = 'vbe-banked-101'
CUT_ROWS = 146
FRAME_BYTES = 640 * 3

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_LFB') != '1',
    reason='Select the QEMU VBE linear framebuffer producer and DOSBox-X reference',
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


def _mode(debug, labels):
    info = witness.mode_info(read_memory(debug, labels['mode_info'], witness.MODE_INFO_BYTES))
    calls = witness.mode_results(read_memory(debug, labels['mode_results'], witness.MODE_RESULTS.size))
    assert info['attributes'] & 0x91 == 0x91
    assert (info['width'], info['height'], info['bits_per_pixel'], info['default_pitch']) == (640, 480, 8, 640)
    base, = unpack('<I', read_memory(debug, labels['lfb_base'], 4))
    assert info['physical_base'] == base and 0x100000 <= base < 2**32 and base % 65536 == 0
    assert calls['info_ax'] == calls['linear_set_ax'] == calls['linear_get_ax'] == 0x004f
    assert calls['linear_mode'] == 0x4101
    assert calls['stride_ax'] == 0x004f
    assert calls['pitch_bytes'] == calls['pitch_pixels'] == witness.PITCH
    assert (calls['linear_window_ax'], calls['linear_window_dx']) == (0x034f, 0xbeef)
    return info, calls


def _raw(debug):
    return debug.vga_configuration_observe()['current']['raw']


def _assert_layout(raw, layout):
    assert raw['vbe'][1:4] == [640, 480, 8]
    assert raw['vbe'][4] & 0x41 == (0x41 if layout == LINEAR else 0x01)
    assert raw['vbe-line-offset'] == witness.PITCH


def _clock(debug):
    return debug.clock_observe()['virtual_ns']


def _latch(debug):
    info = debug.retrace_observe()['native']
    assert info['phase-supported']
    assert info['vbe101-timing']['line-period-ns'] == LINE
    return info['vbe101-display-start'], info['vbe101-panning']


def _protected_pc(debug, location):
    cpu = debug.registers()
    context = cpu['address_state']
    assert cpu['cpu_mode'] == 'protected'
    assert (context['code_bits'], context['stack_bits'], context['paging']) == (32, 32, False)
    assert context['register_context_match'] is True
    assert int(cpu['linear_pc'], 0) == location
    return cpu


def _window_bytes(debug, base, variant):
    expected = witness.expected_vram(variant)
    observed = {}
    for offset in witness.PROBE_OFFSETS:
        actual = read_memory(debug, base + offset, 1, space='physical')
        assert actual == expected[offset:offset + 1], (hex(base), offset, actual, variant)
        observed[str(offset)] = actual.hex()
    return observed


def _complete(debug, variant, *, start=None, origin=0, layout=LINEAR):
    advance = debug.video_frame_advance(timeout_ms=8000)
    assert advance['advance_completed'], advance
    state = source(debug)
    frame = state['frame']
    assert state['model'] == MODEL and state['state'] == 'observing'
    assert state['scanout-layout'] == frame['scanout-layout'] == layout
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (
        640, HEIGHT, FRAME_BYTES, 'RGB888')
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    assert (frame['vbe101-origin-bytes'], frame['vbe101-pitch-bytes'], frame['vbe101-pel']) == (
        origin & ~3, witness.PITCH, origin & 3)
    stamp = frame['frame-start-ns']
    if start is not None:
        assert stamp == start
    assert stamp % PERIOD == 0 and len(frame['rows']) == HEIGHT
    for index, row in enumerate(frame['rows']):
        intended = stamp + LINE // 4 + index * LINE
        assert row['row'] == index and row['intended-ns'] == intended
        assert intended <= row['actual-ns'] < intended + LINE
    pixels = witness.expected_rgb(variant=variant, origin=origin)
    assert frame['pixel-sha256'] == sha256(pixels).hexdigest()
    verify_export(debug, state, pixels)
    return logical(state)['frame']


def _arm(debug, labels, command):
    debug.write_memory(labels['pm_go'], f'{command:02x}', expected_hex=f'{command - 1:02x}')


def _capture_cut(debug, labels, base, kind, start):
    state = source(debug)
    raw = _raw(debug)
    _assert_layout(raw, LINEAR)
    assert state['state'] == 'observing' and state['scanout-layout'] == LINEAR
    assert state['rows-sampled'] == CUT_ROWS
    assert state['next-deadline-ns'] == start + CUT_ROWS * LINE + LINE // 4
    clock = _clock(debug)
    display, panning = _latch(debug)
    if kind == 'update':
        cpu = _protected_pc(debug, labels['pm_update_cut'])
        variant = 'half'
        assert display == {'programmed-origin-bytes': 0, 'active-origin-bytes': 0}
        assert panning == {'pitch-bytes': witness.PITCH, 'programmed-pel': 0, 'active-pel': 0}
    else:
        cpu = debug.registers()
        assert cpu['cpu_mode'] == 'real'
        _, vector_segment = unpack('<HH', read_memory(debug, 0x40, 4, space='physical'))
        assert int(cpu['registers']['cs'], 0) == vector_segment >= 0xc000
        assert register(cpu, 'dx') & 0xffff == 0x03da
        variant = 'updated'
        assert display == {
            'programmed-origin-bytes': witness.ORIGIN & ~3,
            'active-origin-bytes': 0,
            'pending-deadline-ns': start + 490 * LINE,
        }
        assert panning == {
            'pitch-bytes': witness.PITCH,
            'programmed-pel': witness.ORIGIN & 3,
            'active-pel': 0,
            'pending-deadline-ns': start + 492 * LINE,
        }
    return {
        'clock': clock, 'cpu': cpu, 'vga': raw, 'source': state, 'display': display,
        'panning': panning, 'lfb': _window_bytes(debug, base, variant),
    }


def _save_cut(debug, labels, base, kind, start, previous):
    capture = _capture_cut(debug, labels, base, kind, start)
    assert logical(capture['source'])['frame'] == previous
    saved = debug.save_state(f'vbe-lfb-{kind}.qcow2')
    assert _capture_cut(debug, labels, base, kind, start) == capture
    return {'artifact': saved['artifact'], 'sha256': saved['sha256'],
            'kind': kind, 'start': start, 'capture': capture}


def _restore(debug, labels, base, cut):
    old = debug.vm.process
    load = debug.load_state(cut['artifact'], timeout_ms=60_000)
    assert load['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not old and old.poll() == 0
    current = _capture_cut(debug, labels, base, cut['kind'], cut['start'])
    restored = current.pop('source')
    expected = cut['capture']
    retained = expected['source']
    assert restored['token'] != retained['token'] and restored['epoch'] != retained['epoch']
    assert logical(restored) == logical(retained)
    assert current == {key: expected[key] for key in current}
    return debug.vm.process


def _after_update(debug, labels, base, start):
    half = _complete(debug, 'half', start=start)
    _arm(debug, labels, 2)
    park(debug, labels['pm_updated'])
    _protected_pc(debug, labels['pm_updated'])
    assert logical(source(debug))['frame'] == half
    aperture = _window_bytes(debug, base, 'updated')
    updated = _complete(debug, 'updated', start=start + PERIOD)
    return {'half': half, 'updated': updated, 'aperture': aperture}


def _after_pan(debug, labels, start):
    retained = _complete(debug, 'updated', start=start)
    assert read_memory(debug, labels['rm_pan_call'], 2) == b'\xcd\x10'
    park(debug, labels['rm_pan_call'] + 2)
    assert debug.registers()['cpu_mode'] == 'real'
    now = _clock(debug)
    assert start + 490 * LINE <= now < start + 491 * LINE
    assert logical(source(debug))['frame'] == retained
    park(debug, labels['rm_panned'])
    panned = _complete(debug, 'updated', start=start + PERIOD, origin=witness.ORIGIN)

    _arm(debug, labels, 4)
    park(debug, labels['rm_banked'])
    old = source(debug)
    assert old['state'] == 'invalidated'
    raw = _raw(debug)
    _assert_layout(raw, BANKED)
    assert raw['vbe-start-address'] == 0
    info, mode = _mode(debug, labels)
    assert mode['pan_set_ax'] == mode['pan_get_ax'] == 0x004f
    assert (mode['pan_x'], mode['pan_y']) == (witness.ORIGIN % witness.PITCH, witness.ORIGIN // witness.PITCH)
    assert mode['banked_set_ax'] == mode['banked_get_ax'] == 0x004f
    assert mode['banked_mode'] & 0x7fff == 0x0101
    observed = witness.results(read_memory(debug, labels['results'], witness.RESULT_BYTES))
    for variant in ('baseline', 'half', 'updated'):
        expected = witness.expected_vram(variant)
        assert bytes(observed[variant]) == bytes(expected[index] for index in witness.PROBE_OFFSETS)
    assert bytes(observed['banked']) == b'\x08\x08\x09\x09'
    debug.video_frame_start()
    banked = _complete(debug, 'updated', layout=BANKED)
    return {'retained': retained, 'panned': panned, 'banked': banked,
            'video': raw, 'mode_info': info, 'mode_results': mode,
            'results': {key: value.hex() for key, value in observed.items()}}


def _owners(owners):
    values = {key: {'pid': proc.pid, 'returncode': proc.poll()} for key, proc in owners.items()}
    assert len({item['pid'] for item in values.values()}) == len(values)
    assert all(item['returncode'] == 0 for item in values.values())
    return values


def _replay(debug, labels, base, update, pan):
    owners = {'update': _restore(debug, labels, base, update)}
    continued_update = _after_update(debug, labels, base, update['start'])
    owners['pan'] = _restore(debug, labels, base, pan)
    continued_pan = _after_pan(debug, labels, pan['start'])
    return continued_update | continued_pan, owners


def _cold_replay(path):
    spec = json.loads(path.read_text())
    runtime, tool = spec['runtime'], spec['tool']
    assert _producer(runtime, tool) == spec['producer']
    with Project(path.parent / DATABASE) as project:
        with _launch(project, path.parent, runtime, spec['disk'], tool) as debug:
            initial = debug.vm.process
            replay, owners = _replay(
                debug, spec['labels'], spec['base'], spec['update'], spec['pan'])
    return {'host_pid': os.getpid(), 'result': replay, 'owners': _owners({'initial': initial} | owners)}


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
    local = record['forward']
    assert reference['owner_rc'] == 0
    for field in ('width', 'height', 'bits_per_pixel', 'default_pitch'):
        assert local['mode_info'][field] == reference['mode_info'][field]
    assert reference['mode_info']['attributes'] & 0x91 == 0x91 and reference['mode_info']['physical_base']
    mode_fields = set(witness.MODE_FIELDS) - {'linear_window_ax', 'linear_window_dx', 'banked_mode'}
    assert {field: local['mode_results'][field] for field in mode_fields} == {
        field: reference['mode_results'][field] for field in mode_fields}
    # SeaVGABIOS retains the no-clear bit in the returned mode word.
    assert local['mode_results']['banked_mode'] & 0x7fff == reference['mode_results']['banked_mode']
    assert local['results'] == reference['results']
    for name in ('baseline', 'half', 'updated', 'panned', 'banked'):
        frame = record['baseline'] if name == 'baseline' else local[name]
        assert frame['vbe101-origin-bytes'] + frame['vbe101-pel'] == reference['frames'][name]['origin']
        assert frame['pixel-sha256'] == reference['frames'][name]['pixel_sha256']


def test_vbe_lfb_guest_mmio_restore_and_banked_roundtrip(tmp_path, clock_runtime, clock_disk):
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    producer = _producer(clock_runtime, tool)
    for key, suffix in (('qemu', 'SHA256'), ('qemu-img', 'IMG_SHA256'), ('rom', 'ROM_SHA256')):
        assert producer[key] == os.environ[f'FDISBULL_QEMU_VBE_LFB_{suffix}']
    reference_path = Path(os.environ['FDISBULL_DOSBOX_VBE_LFB_REFERENCE']).resolve(strict=True)
    reference_sha = digest(reference_path)
    assert reference_sha == os.environ['FDISBULL_DOSBOX_VBE_LFB_REFERENCE_SHA256']
    reference = json.loads(reference_path.read_text())
    code = assemble(tmp_path, 'vbe-lfb', witness.SOURCE, clock_runtime['nasm'])
    assert sha256(code).hexdigest() == reference['authored_com_sha256']
    binary = tmp_path / 'LFB.COM'
    binary.write_bytes(code)
    record = {
        'producer': producer, 'profile': PROFILE, 'format': FORMAT,
        'reference_sha256': reference_sha, 'authored_com_sha256': sha256(code).hexdigest(),
        'completed': False,
    }

    try:
        with Project.create(tmp_path / DATABASE, binary, image='com') as project:
            with _launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                original = debug.vm.process
                identity = process_record(debug)
                labels = {name: com_address(identity, offset)
                          for name, offset in witness.labels(code).items()}
                park(debug, labels['pm_ready'])
                _protected_pc(debug, labels['pm_ready'])
                info, _ = _mode(debug, labels)
                base = info['physical_base']
                _assert_layout(_raw(debug), LINEAR)
                _window_bytes(debug, base, 'baseline')
                debug.video_frame_start()
                baseline = record['baseline'] = _complete(debug, 'baseline')

                update_start = baseline['frame-start-ns'] + PERIOD
                _reach(debug, update_start + 64 * LINE + LINE // 2)
                _arm(debug, labels, 1)
                park(debug, labels['pm_update_cut'])
                _reach(debug, update_start + (CUT_ROWS - 1) * LINE + LINE // 2)
                park(debug, labels['pm_update_cut'])
                update = _save_cut(debug, labels, base, 'update', update_start, baseline)
                forward_update = _after_update(debug, labels, base, update_start)

                pan_start = update_start + 2 * PERIOD
                _reach(debug, pan_start + 64 * LINE + LINE // 2)
                _arm(debug, labels, 3)
                park(debug, labels['rm_pan_call'])
                _reach(debug, pan_start + (CUT_ROWS - 1) * LINE + LINE // 2)
                pan = _save_cut(debug, labels, base, 'pan', pan_start, forward_update['updated'])
                record['checkpoints'] = {
                    cut['kind']: {'sha256': cut['sha256'], 'cpu': cut['capture']['cpu'],
                                  'rows': cut['capture']['source']['rows-sampled'],
                                  'display': cut['capture']['display'],
                                  'lfb': cut['capture']['lfb']}
                    for cut in (update, pan)
                }
                record['forward'] = forward_update | _after_pan(debug, labels, pan_start)
                record['hot'], hot = _replay(debug, labels, base, update, pan)
                assert record['hot'] == record['forward']

        record['owners'] = _owners({'original': original, 'hot_update': hot['update'], 'hot_pan': hot['pan']})
        cold = _run_cold(tmp_path / 'cold-spec.json', {
            'runtime': {key: str(value) if isinstance(value, Path) else value
                        for key, value in clock_runtime.items()},
            'disk': {'image': str(clock_disk['image'])}, 'tool': tool,
            'producer': producer, 'labels': labels, 'base': base, 'update': update, 'pan': pan,
        })
        record['cold'] = cold['result']
        assert record['cold'] == record['forward']
        assert not {item['pid'] for item in record['owners'].values()} & {
            item['pid'] for item in cold['owners'].values()}
        record['owners'].update({f'cold_{key}': value for key, value in cold['owners'].items()})
        _check_pair(record, reference)
        record['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vbe-lfb-replay.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    print(json.dumps(_cold_replay(Path(sys.argv[1]))))
