"""Zero-voice/capture-only and inactive extant SB16 voice recovery."""
from copy import deepcopy
import json

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline, digest
from support.qemu_sb16_fixture import sb16_pcm
from test_qemu_clock_budget_native import park, budget_receipt
from test_qemu_sb16_native import _runtime, _launch, _device, _symbols, _pcm


@pytest.mark.parametrize('capture', [False, True], ids=['no-window', 'capture-only'])
def test_native_sb16_zero_and_inactive_voice_graph_restore(tmp_path, capture):
    runtime = _runtime()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
        tmp_path / 'initial.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = sb16_pcm(tmp_path, runtime['NASM'], rate=8000)
    binary = tmp_path / 'SB16.COM'
    binary.write_bytes(code)
    report = {'format': 'fdisbull-sb16-initial-native-1', 'capture': capture, 'restores': []}
    with Project.create(tmp_path / 'initial.fdb', binary, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            assert not _device(debug)['voice-present']
            if capture:
                debug.audio_start(max_frames=16000)

            def recover(label):
                before = dict(cpu=debug.registers(), device=_device(debug),
                              clock=debug.clock_observe(), audio=debug.audio_observe())
                saved = debug.save_state(label + '.state')
                old = debug.vm.process
                loaded = debug.load_state(saved['artifact'])
                assert old.poll() is not None and debug.vm.process is not old
                assert loaded['source_binding_restored'] is True
                assert debug.registers() == before['cpu'] and _device(debug) == before['device']
                assert debug.clock_observe()['virtual_ns'] == before['clock']['virtual_ns']
                audio = debug.audio_observe()
                assert audio['frames'] == before['audio']['frames'] == 0
                assert audio['state'] == before['audio']['state']
                if capture:
                    assert audio['window'] != before['audio']['window']
                    samples, _, _ = _pcm(project, debug, label + '.wav')
                    assert samples == b''
                report['restores'].append(dict(label=label, saved=saved, loaded=loaded,
                                               device=deepcopy(before['device'])))

            recover('zero-voice')
            symbols = _symbols(debug, offsets)
            park(debug, symbols['ready'])
            device = _device(debug)
            # Reset creates 11025-Hz voice; the guest then programs the next
            # transfer at 8000 Hz. Save the extant geometry, not next settings.
            assert device['voice-present'] and not device['voice-active'] and not device['dma-active']
            assert device['voice-frequency'] == 11025
            recover('inactive-voice')
            if not capture:
                debug.audio_start(max_frames=16000)
            park(debug, symbols['started'])
            budget_receipt(debug.clock_advance(60_000_000, timeout_ms=10000), 60_000_000)
            assert debug.audio_observe()['frames'] > 0
            assert _device(debug)['voice-frequency'] == 8000
            owner = debug.vm.process
        assert owner.poll() is not None
    assert binary.read_bytes() == code and digest(disk['image']) == disk['prepared_sha256']
    report['passed'] = True
    (tmp_path / 'native-initial-sb16.json').write_text(json.dumps(report, indent=2) + '\n')
