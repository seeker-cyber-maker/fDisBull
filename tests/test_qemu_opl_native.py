"""Real YM3812 pitch/gates and combined OPL/SB16 native checkpoints.

Supply FDISBULL_QEMU_OPL, FDISBULL_QEMU_DOS_BOOT_IMAGE,
FDISBULL_QEMU_DOS_MCOPY, FDISBULL_QEMU_DOS_FIRMWARE, FDISBULL_QEMU_IMG and
NASM. FDISBULL_REQUIRE_QEMU_OPL=1 refuses missing inputs. Root runs VMs.
The independent signal oracle tests pitch/octave/key-off and guest status;
exact PCM continuation is a separate emulator preservation claim, not a
bit-accurate or electrically timed hardware claim.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_opl_fixture import OPL_BLOCK, PENDING_ADDRESS, note_frequency, opl_program
from support.qemu_sb16_ring_fixture import BLOCK_BYTES, BLOCKS, RING_BYTES, block_pcm, ring_pcm
from support.qemu_mixer_assertions import mixer_snapshot
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_process_native import assert_completion, com_address, read_bytes
from test_qemu_sb16_native import _pcm


OUTPUT_RATE = 32000
OPL_FIELDS = {
    'api-version', 'iobase', 'frequency', 'audiodev-id', 'checkpoint-enabled',
    'active', 'enabled', 'address', 'status', 'status-mask', 'mode', 'rhythm',
    'timer1-ticking', 'timer2-ticking', 'timer1-expiry-us', 'timer2-expiry-us',
    'noise-state', 'state-sha256', 'synth-state-sha256', 'register-sha256',
    'keyon-mask', 'active-operators',
}


def _runtime():
    selected = {k: os.environ.get(k) for k in ('FDISBULL_QEMU_OPL',
        'FDISBULL_QEMU_DOS_BOOT_IMAGE', 'FDISBULL_QEMU_DOS_MCOPY',
        'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')}
    selected['NASM'] = os.environ.get('NASM') or shutil.which('nasm')
    missing = [k for k, value in selected.items() if not value]
    if missing:
        message = 'Native OPL inputs missing: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_QEMU_OPL') == '1':
            pytest.fail(message)
        pytest.skip(message)
    for key, value in selected.items():
        p = Path(value).expanduser()
        assert p.is_dir() if key == 'FDISBULL_QEMU_DOS_FIRMWARE' else p.is_file(), key
    return selected


def _launch(project, runtime, directory, disk):
    return project.debugger(runtime['FDISBULL_QEMU_OPL'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'], qemu_transport='pipe',
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], qemu_clock='virtual',
        qemu_audio='sb16-opl', boot_timeout_ms=30000)


def _symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    return {name: com_address(info, offset) for name, offset in offsets.items()
            if name not in ('report_size', 'opl_report_size')}


def _opl(debug):
    value = debug.vm.qmp.call('x-fdisbull-query-opl')
    assert OPL_FIELDS <= value.keys()
    assert (value['api-version'], value['iobase'], value['frequency'], value['audiodev-id']) == (
        1, 0x220, OUTPUT_RATE, 'fdisbull-sb16-opl')
    assert value['checkpoint-enabled'] is True and value['enabled'] is True
    for key in ('state-sha256', 'synth-state-sha256', 'register-sha256'):
        assert re.fullmatch('[0-9a-f]{64}', value[key]), key
    return value


def _sb(debug):
    value = debug.vm.qmp.call('x-fdisbull-query-sb16')
    assert (value['api-version'], value['iobase'], value['irq'], value['dma'],
            value['dma16'], value['version'], value['audiodev-id']) == (
                1, 0x220, 7, 1, 5, 0x0405, 'fdisbull-sb16-opl')
    return value


def _pitch(samples):
    """Independent zero-crossing pitch measurement, without phase fitting."""
    assert len(samples) >= 4096
    values = list(samples[-4096:])
    centre = sum(values) / len(values)
    crossings = [i for i in range(1, len(values))
                 if values[i - 1] <= centre < values[i]]
    assert len(crossings) >= 20 and max(values) - min(values) >= 6
    return OUTPUT_RATE * (len(crossings) - 1) / (crossings[-1] - crossings[0])


def _tap(debug, key):
    lease = debug.keyboard_key_down(key)['lease']
    debug.keyboard_key_up(lease)


def _sample(project, debug, offsets, label):
    symbols = _symbols(debug, offsets)
    report = read_bytes(debug, symbols['report'], offsets['report_size'])
    opl_report = read_bytes(debug, symbols['opl_report'], offsets['opl_report_size'])
    assert report[:4] == b'SBR1' and opl_report[:4] == b'OPL1'
    def number(name, width=2):
        data, origin = (opl_report, offsets['opl_report']) if name.startswith('opl_') else (report, offsets['report'])
        start = offsets[name] - origin
        return int.from_bytes(data[start:start + width], 'little')
    generations = list(struct.unpack_from('<16H', report, offsets['generations'] - offsets['report']))
    physical = number('buffer_physical', 4)
    assert physical % RING_BYTES == 0 and physical & 0xffff <= 0xf000
    ring = read_bytes(debug, physical, RING_BYTES)
    active = number('refill_active')
    assert 0 <= active <= BLOCKS
    for block, generation in enumerate(generations):
        if active != block + 1:
            assert ring[block * BLOCK_BYTES:(block + 1) * BLOCK_BYTES] == block_pcm(block, generation)
    register_at = offsets['opl_registers'] - offsets['opl_report']
    registers = opl_report[register_at:register_at + 256]
    opl = _opl(debug)
    assert opl['register-sha256'] == hashlib.sha256(registers).hexdigest()
    # Querying a stopped armed timer must not emulate a guest port read.
    assert _opl(debug) == opl
    pcm, artifact, chunks = _pcm(project, debug, label + '.wav')
    return dict(cpu=debug.registers(), report_hex=report.hex(), opl_report_hex=opl_report.hex(),
        opl_stage=number('opl_stage'), opl_registers_hex=registers.hex(),
        timer1_status=number('opl_timer1_status', 1), timer2_status=number('opl_timer2_status', 1),
        timer_reset_status=number('opl_timer_reset_status', 1),
        resume_status=number('opl_resume_status', 1), resume_reset_status=number('opl_resume_reset_status', 1),
        ring_hex=ring.hex(), generations=generations, refill_active=active,
        irq_count=number('irq_count', 4), produced_bytes=number('produced_bytes', 4),
        buffer_physical=physical, opl=opl, sb=_sb(debug), clock=debug.clock_observe(),
        pcm_hex=pcm.hex(), pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        audio_artifact=artifact, chunks=chunks, mixer=mixer_snapshot(debug))


def _assert_exact(actual, expected):
    for key in ('cpu', 'report_hex', 'opl_report_hex', 'opl_stage', 'opl_registers_hex',
                'timer1_status', 'timer2_status', 'timer_reset_status', 'resume_status',
                'resume_reset_status', 'ring_hex', 'generations', 'refill_active',
                'irq_count', 'produced_bytes', 'buffer_physical', 'opl', 'sb',
                'pcm_hex', 'pcm_sha256', 'chunks', 'mixer'):
        assert actual[key] == expected[key], key
    assert actual['clock']['virtual_ns'] == expected['clock']['virtual_ns']
    assert actual['clock']['counter']['value'] == expected['clock']['counter']['value']


def _future(project, debug, offsets, captured, label):
    before = debug.clock_observe()
    budget_receipt(debug.clock_advance(600_000_000, timeout_ms=15000), 600_000_000, before=before)
    state = _sample(project, debug, offsets, label)
    assert state['opl_stage'] == 6
    assert state['resume_status'] & 0xe0 == 0xe0
    assert state['resume_reset_status'] & 0xe0 == 0
    assert state['opl']['timer1-ticking'] is False and state['opl']['timer2-ticking'] is False
    assert state['opl']['noise-state'] != captured['opl']['noise-state']
    assert state['opl']['synth-state-sha256'] != captured['opl']['synth-state-sha256']
    assert state['irq_count'] > captured['irq_count'] and state['ring_hex'] != captured['ring_hex']
    assert state['pcm_hex'].startswith(captured['pcm_hex'])
    assert len(state['pcm_hex']) > len(captured['pcm_hex'])
    return state


def _load(project, debug, control, route, label):
    old, epoch = debug.vm.process, debug.dos_process_info()['capture_epoch']
    if route == 'explicit':
        restored = debug.load_state(control['saved']['artifact'], timeout_ms=60000)
    else:
        response = debug.rewind(history=control['history'], node=control['node'], timeout_ms=60000)
        assert response['valid'] and response['cursor'] == control['node']
        control['history'] = response['history']
        restored = response['restore']
    assert old.poll() is not None and debug.vm.process is not old and debug.vm.process.poll() is None
    info = debug.dos_process_info()
    assert restored['source_binding_restored'] is True and info['state'] == 'active'
    assert info['capture_epoch'] not in (epoch, control['origin_epoch'])
    state = _sample(project, debug, control['offsets'], label + '-selected')
    _assert_exact(state, control['captured'])
    assert state['audio_artifact']['metadata']['window'] != control['captured']['audio_artifact']['metadata']['window']
    return restored, state


def _quit(debug):
    _tap(debug, 'q')
    assert_completion(debug, debug.run(timeout_ms=5000), exit_code=42)


def _cold(path):
    control = json.loads(Path(path).read_text())
    directory, runtime = Path(control['directory']), _runtime()
    disk = dict(image=Path(control['disk']))
    assert digest(disk['image']) == control['disk_sha256']
    assert digest(directory / 'OPL.COM') == control['source_sha256']
    result = dict(passed=False, pid=os.getpid(), cases=[])
    try:
        with Project(control['database']) as project:
            for ref in (control['saved'], control['root_checkpoint']):
                assert project.debug_state_info(ref['artifact'])['sha256'] == ref['sha256']
                exported = directory / ('cold-' + ref['artifact'] + '.state')
                project.debug_export(ref['artifact'], exported)
                assert digest(exported) == ref['sha256']
            with _launch(project, runtime, directory, disk) as debug:
                assert debug.run_id != control['origin_run']
                for route in ('explicit', 'history-root'):
                    entry = dict(route=route)
                    result['cases'].append(entry)
                    restored, initial = _load(project, debug, control, route, 'cold-' + route)
                    entry.update(restored=restored, selected=initial)
                    future = _future(project, debug, control['offsets'], control['captured'], 'cold-' + route + '-future')
                    entry['future'] = future
                    _assert_exact(future, control['future'])
                    assert future['audio_artifact']['metadata']['window'] == initial['audio_artifact']['metadata']['window']
                _quit(debug)
                owner = debug.vm.process
            assert owner.poll() is not None
        result['passed'] = True
    finally:
        result['source_unchanged'] = digest(directory / 'OPL.COM') == control['source_sha256']
        result['disk_unchanged'] = digest(disk['image']) == control['disk_sha256']
        (directory / 'cold-opl-result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=result['passed'], pid=os.getpid())))


def test_native_opl_pitch_gates_noise_timers_and_combined_checkpoint_hot_separate_process_cold(tmp_path):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'opl-boot.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = opl_program(tmp_path, runtime['NASM'])
    source = tmp_path / 'OPL.COM'
    source.write_bytes(code)
    database = tmp_path / 'opl.fdb'
    report = dict(format='fdisbull-authored-opl-native-1', success=False, hot=[],
        oracle='Yamaha YM3812 FNUM/BLOCK pitch and guest keyoff/status, not bit-exact hardware PCM',
        hardware_frequency_relative_tolerance=0.015, timer_semantics='stock forced expiry on next port access',
        future_ns=600_000_000, full_future_cpu_required=True)
    control = dict(directory=str(tmp_path), database=str(database), disk=str(disk['image']),
        disk_sha256=disk['prepared_sha256'], source_sha256=digest(source), offsets=offsets)
    try:
        with Project.create(database, source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['opl_tone_loop'])
                debug.audio_start(max_frames=100000)
                budget_receipt(debug.clock_advance(300_000_000, timeout_ms=15000), 300_000_000)
                first = _sample(project, debug, offsets, 'single-tone')
                assert first['opl_stage'] == 1 and first['sb']['dma-active'] is False
                assert first['timer1_status'] & 0xe0 == 0xc0
                assert first['timer2_status'] & 0xe0 == 0xa0
                assert first['timer_reset_status'] & 0xe0 == 0
                fundamental = _pitch(bytes.fromhex(first['pcm_hex']))
                assert abs(fundamental / note_frequency() - 1) < 0.015
                _tap(debug, '2')
                budget_receipt(debug.clock_advance(200_000_000, timeout_ms=15000), 200_000_000)
                octave = _sample(project, debug, offsets, 'octave-tone')
                assert octave['opl_stage'] == 2
                doubled = _pitch(bytes.fromhex(octave['pcm_hex']))
                assert abs(doubled / note_frequency(OPL_BLOCK + 1) - 1) < 0.015
                assert abs(doubled / fundamental - 2) < 0.03
                _tap(debug, 'k')
                budget_receipt(debug.clock_advance(150_000_000, timeout_ms=15000), 150_000_000)
                released = _sample(project, debug, offsets, 'keyoff')
                assert released['opl_stage'] == 3
                assert all(abs(value - 128) <= 1 for value in bytes.fromhex(released['pcm_hex'])[-2048:])
                report.update(tone=first, octave=octave, keyoff=released,
                    observed_pitch_hz=fundamental, observed_octave_hz=doubled,
                    predicted_pitch_hz=note_frequency())
                _tap(debug, 'c')
                budget_receipt(debug.clock_advance(80_000_000, timeout_ms=15000), 80_000_000)
                _tap(debug, 'p')
                park(debug, symbols['opl_pending_data'])
                captured = _sample(project, debug, offsets, 'captured')
                report['captured'] = captured
                assert captured['opl_stage'] == 5 and captured['refill_active'] == 0
                assert captured['irq_count'] > 0 and captured['produced_bytes'] == captured['irq_count'] * BLOCK_BYTES
                assert bytes.fromhex(captured['ring_hex']) == ring_pcm(captured['generations'])
                assert captured['opl']['active'] is True and captured['opl']['active-operators'] > 0
                assert captured['opl']['rhythm'] & 0x3f == 0x3f and captured['opl']['keyon-mask'] & 1
                assert captured['opl']['noise-state'] != first['opl']['noise-state']
                assert captured['opl']['address'] == PENDING_ADDRESS
                assert captured['opl']['timer1-ticking'] is True and captured['opl']['timer2-ticking'] is True
                assert (captured['opl']['timer1-expiry-us'], captured['opl']['timer2-expiry-us']) == (160, 643)
                assert captured['sb']['dma-active'] is True and captured['sb']['voice-channels'] == 2
                assert captured['sb']['voice-frequency'] == 11025 and captured['sb']['dma-length'] == RING_BYTES
                saved = debug.save_state('opl-combined.state')
                root = debug.rewind_start(max_steps=1, max_bytes=128 * 1024 * 1024, timeout_ms=60000)
                root_manifest = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (root['history'],)).fetchone()
                root_node = next(n for n in json.loads(bytes(root_manifest['data']))['nodes'] if n['id'] == root['cursor'])
                control.update(saved=saved, history=root['history'], node=root['cursor'],
                    root_checkpoint=root_node['checkpoint'], captured=captured,
                    origin_run=debug.run_id, origin_epoch=debug.dos_process_info()['capture_epoch'])
                _assert_exact(_sample(project, debug, offsets, 'after-both-captures'), captured)
                future = _future(project, debug, offsets, captured, 'original-future')
                report.update(saved=saved, history_root=root, original_future=future)
                control['future'] = future
                for route in ('explicit', 'history-root'):
                    entry = dict(route=route)
                    report['hot'].append(entry)
                    restored, initial = _load(project, debug, control, route, 'hot-' + route)
                    entry.update(restored=restored, selected=initial)
                    actual = _future(project, debug, offsets, captured, 'hot-' + route + '-future')
                    entry['future'] = actual
                    _assert_exact(actual, future)
                    assert actual['audio_artifact']['metadata']['window'] == initial['audio_artifact']['metadata']['window']
                _quit(debug)
                owner = debug.vm.process
            assert owner.poll() is not None
        control_path = tmp_path / 'cold-opl-control.json'
        control_path.write_text(json.dumps(control, indent=2, sort_keys=True) + '\n')
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--cold', str(control_path)],
            check=False, capture_output=True, text=True, timeout=180,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        (tmp_path / 'cold-opl.log').write_text(child.stdout + child.stderr)
        assert child.returncode == 0, child.stdout + child.stderr
        cold = json.loads((tmp_path / 'cold-opl-result.json').read_text())
        assert cold['passed'] and cold['source_unchanged'] and cold['disk_unchanged'] and cold['pid'] != os.getpid()
        report.update(cold=cold, success=True)
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash and digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-opl.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--cold':
        raise SystemExit('Use pytest or the explicit --cold route')
    _cold(sys.argv[2])
