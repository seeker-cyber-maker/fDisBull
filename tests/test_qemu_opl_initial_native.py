"""Initial OPL graph checkpoints before any guest OPL/SB16 programming.

The initial AdLib software voice exists but is inactive; the SB16 voice does
not yet exist. Exercise both an idle observer and an armed empty capture
window. The existing full OPL fixture separately tests combined-graph cold
recovery. Root alone launches native guests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_opl_fixture import note_frequency, opl_program
from support.qemu_mixer_assertions import mixer_snapshot
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_process_native import com_address
from test_qemu_opl_native import _launch, _opl, _pitch, _quit, _runtime, _sb, _symbols
from test_qemu_sb16_native import _pcm


def _snapshot(project, debug, label):
    audio = debug.audio_observe()
    pcm, artifact, chunks = (None, None, [])
    if audio['state'] != 'idle':
        raw, artifact, chunks = _pcm(project, debug, label + '.wav')
        pcm = raw.hex()
    return dict(cpu=debug.registers(), opl=_opl(debug), sb=_sb(debug),
        audio_state=audio['state'], capture_enabled=audio['native']['enabled'],
        frames=audio['frames'], dropped_frames=audio['dropped_frames'],
        pcm_hex=pcm, audio_artifact=artifact, window=audio.get('window'),
        chunks=chunks, clock=debug.clock_observe(), mixer=mixer_snapshot(debug))


def _assert_exact(actual, expected):
    for key in ('cpu', 'opl', 'sb', 'audio_state', 'capture_enabled', 'frames',
                'dropped_frames', 'pcm_hex', 'chunks', 'mixer'):
        assert actual[key] == expected[key], key
    assert actual['clock']['virtual_ns'] == expected['clock']['virtual_ns']
    assert actual['clock']['counter']['value'] == expected['clock']['counter']['value']


def _tone_future(project, debug, offsets, label):
    if debug.audio_observe()['state'] == 'idle':
        debug.audio_start(max_frames=50000)
    symbols = _symbols(debug, offsets)
    park(debug, symbols['opl_tone_loop'])
    before = debug.clock_observe()
    budget_receipt(debug.clock_advance(300_000_000, timeout_ms=15000), 300_000_000, before=before)
    state = _snapshot(project, debug, label)
    assert state['opl']['active'] is True and state['opl']['active-operators'] > 0
    assert state['opl']['keyon-mask'] & 1
    # The guest's actual DSP reset creates an inactive 11025-Hz U8 voice.
    # The saved entry still has no SB voice; restoration must remove it.
    assert state['sb']['voice-present'] is True and state['sb']['voice-active'] is False
    assert state['sb']['dma-active'] is False
    assert (state['sb']['voice-frequency'], state['sb']['voice-channels'],
            state['sb']['voice-bits'], state['sb']['voice-signed']) == (11025, 1, 8, False)
    assert state['pcm_hex'] and state['dropped_frames'] == 0
    pitch = _pitch(bytes.fromhex(state['pcm_hex']))
    assert abs(pitch / note_frequency() - 1) < 0.015
    state['observed_pitch_hz'] = pitch
    return state


@pytest.mark.parametrize('capture_window', [False, True], ids=['idle-observer', 'capture-only-window'])
def test_native_opl_initial_graph_checkpoint_and_actual_tone_continuation(tmp_path, capture_window):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'opl-initial-boot.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = opl_program(tmp_path, runtime['NASM'])
    source = tmp_path / 'OPLENTRY.COM'
    source.write_bytes(code)
    report = dict(format='fdisbull-authored-opl-initial-native-1', success=False,
        capture_window=capture_window, source_entry_before_guest_device_io=True,
        full_future_cpu_required=True)
    try:
        with Project.create(tmp_path / 'opl-initial.fdb', source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                info = debug.dos_process_info()
                assert int(debug.registers()['linear_pc'], 0) == com_address(info, 0x100)
                if capture_window:
                    debug.audio_start(max_frames=50000)
                initial = _snapshot(project, debug, 'initial')
                report['initial'] = initial
                assert initial['opl']['active'] is False and initial['opl']['keyon-mask'] == 0
                assert initial['opl']['active-operators'] == 0 and initial['opl']['rhythm'] == 0
                assert initial['opl']['address'] == 0
                assert initial['opl']['register-sha256'] == hashlib.sha256(bytes(256)).hexdigest()
                assert initial['opl']['timer1-ticking'] is False and initial['opl']['timer2-ticking'] is False
                assert initial['sb']['voice-present'] is False and initial['sb']['dma-active'] is False
                assert initial['frames'] == initial['dropped_frames'] == 0 and initial['chunks'] == []
                assert initial['audio_state'] == ('capturing' if capture_window else 'idle')
                assert initial['pcm_hex'] == ('' if capture_window else None)
                saved = debug.save_state('opl-entry.state')
                report['saved'] = saved
                _assert_exact(_snapshot(project, debug, 'after-save'), initial)
                future = _tone_future(project, debug, offsets, 'original-tone')
                report['original_future'] = future
                old, epoch = debug.vm.process, debug.dos_process_info()['capture_epoch']
                restored = debug.load_state(saved['artifact'], timeout_ms=60000)
                report['restore'] = restored
                assert old.poll() is not None and debug.vm.process is not old and debug.vm.process.poll() is None
                current = debug.dos_process_info()
                assert restored['source_binding_restored'] is True and current['state'] == 'active'
                assert current['capture_epoch'] != epoch
                recovered = _snapshot(project, debug, 'restored-initial')
                report['restored_initial'] = recovered
                _assert_exact(recovered, initial)
                if capture_window:
                    assert recovered['window'] != initial['window']
                else:
                    assert recovered['window'] is None
                actual = _tone_future(project, debug, offsets, 'restored-tone')
                report['restored_future'] = actual
                _assert_exact(actual, future)
                assert actual['observed_pitch_hz'] == future['observed_pitch_hz']
                assert actual['window'] != future['window']
                _quit(debug)
                owner = debug.vm.process
            assert owner.poll() is not None
        report['success'] = True
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash and digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-opl-initial.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
