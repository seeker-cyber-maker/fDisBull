"""Strict mutable SB16 producer continuation from explicit and history roots.

Opt-in native inputs are the existing FDISBULL_QEMU_SB16 / FreeDOS / mcopy /
firmware / qemu-img / NASM selectors from test_qemu_sb16_native. Root owns VM
execution. This is one hot-session regression; separate-host original-Doom
qualification remains a distinct gate. There is no future CPU waiver.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_sb16_ring_fixture import (
    BLOCK_BYTES, BLOCKS, CHANNELS, RATE, RING_BYTES, block_pcm, ring_pcm, sb16_ring,
)
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_process_native import assert_completion, com_address, read_bytes
from test_qemu_sb16_native import _device, _launch, _pcm, _runtime


def _symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    return {name: com_address(info, offset) for name, offset in offsets.items()
            if name != 'report_size'}


def _sample(project, debug, offsets, name):
    symbols = _symbols(debug, offsets)
    raw = read_bytes(debug, symbols['report'], offsets['report_size'])
    assert raw[:4] == b'SBR1'
    def number(field, width):
        start = offsets[field] - offsets['report']
        return int.from_bytes(raw[start:start + width], 'little')
    generation_at = offsets['generations'] - offsets['report']
    generations = list(struct.unpack_from('<16H', raw, generation_at))
    physical = number('buffer_physical', 4)
    ring = read_bytes(debug, physical, RING_BYTES)
    assert physical % RING_BYTES == 0 and physical & 0xffff <= 0xf000
    active = number('refill_active', 2)
    assert 0 <= active <= BLOCKS
    # A clock stop may interrupt the producer's current refill. Every other
    # block must satisfy the independent guest formula; complete selected
    # stops below additionally require active==0 and the full ring oracle.
    for block, generation in enumerate(generations):
        if active != block + 1:
            assert ring[block * BLOCK_BYTES:(block + 1) * BLOCK_BYTES] == block_pcm(block, generation)
    pcm, artifact, chunks = _pcm(project, debug, name + '.wav')
    return dict(cpu=debug.registers(), report_hex=raw.hex(), ring_hex=ring.hex(),
        ring_sha256=hashlib.sha256(ring).hexdigest(), buffer_physical=physical,
        generations=generations, irq_count=number('irq_count', 4),
        busy_count=number('busy_count', 4), produced_bytes=number('produced_bytes', 4),
        stage=number('stage', 2), refill_active=active, device=_device(debug),
        pcm_hex=pcm.hex(), pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        audio_artifact=artifact, chunks=chunks, clock=debug.clock_observe())


def _assert_exact(actual, expected):
    # Entire CPU dictionary is deliberate: matching a later NOP, rendered
    # output or guest counter cannot substitute for the exact endpoint.
    for key in ('cpu', 'device', 'report_hex', 'ring_hex', 'buffer_physical',
                'generations', 'irq_count', 'busy_count', 'produced_bytes',
                'stage', 'refill_active', 'pcm_hex', 'pcm_sha256', 'chunks'):
        assert actual[key] == expected[key], key
    assert actual['clock']['virtual_ns'] == expected['clock']['virtual_ns']
    assert actual['clock']['counter']['value'] == expected['clock']['counter']['value']


def _assert_selected(state):
    assert state['stage'] == 1 and state['refill_active'] == 0
    assert state['irq_count'] > 0 and sum(state['generations']) == state['irq_count']
    assert state['produced_bytes'] == state['irq_count'] * BLOCK_BYTES
    assert bytes.fromhex(state['ring_hex']) == ring_pcm(state['generations'])
    device = state['device']
    assert device['dma-active'] is True and device['voice-active'] is True
    assert (device['voice-frequency'], device['voice-channels'], device['voice-bits'],
            device['voice-signed']) == (RATE, CHANNELS, 8, False)
    assert device['dma-length'] == RING_BYTES and 0 < device['dma-position'] < RING_BYTES
    assert 0 < device['left-till-irq'] <= BLOCK_BYTES


def _advance(project, debug, offsets, captured, label):
    before = debug.clock_observe()
    budget_receipt(debug.clock_advance(600_000_000, timeout_ms=15000), 600_000_000, before=before)
    state = _sample(project, debug, offsets, label)
    assert state['irq_count'] > captured['irq_count']
    assert sum(state['generations']) > sum(captured['generations'])
    assert state['ring_hex'] != captured['ring_hex'], 'The guest producer did not mutate its DMA ring'
    assert len(state['pcm_hex']) > len(captured['pcm_hex'])
    assert state['pcm_hex'].startswith(captured['pcm_hex']), 'Retained PCM prefix changed'
    assert len(set(bytes.fromhex(state['pcm_hex']))) > 1
    return state


def test_native_sb16_mutable_stereo_ring_explicit_and_history_root_full_cpu_continuation(tmp_path):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'ring-boot.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = sb16_ring(tmp_path, runtime['NASM'])
    source = tmp_path / 'SBRING.COM'
    source.write_bytes(code)
    report = dict(format='fdisbull-authored-sb16-mutable-ring-native-1', success=False,
        rate=RATE, channels=CHANNELS, dma_bytes=RING_BYTES, irq_block_bytes=BLOCK_BYTES,
        future_ns=600_000_000, repeats=2, cases=[], future_cpu_required_exact=True,
        no_guest_memory_or_register_writes=True)
    try:
        with Project.create(tmp_path / 'ring.fdb', source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['ready'])
                assert read_bytes(debug, symbols['reset_byte'], 3) == b'\xaa\x04\x05'
                debug.audio_start(max_frames=80000)
                park(debug, symbols['started'])
                budget_receipt(debug.clock_advance(80_000_000, timeout_ms=10000), 80_000_000)
                park(debug, symbols['busy'])
                captured = _sample(project, debug, offsets, 'captured-a')
                report['captured'] = captured
                _assert_selected(captured)
                origin_epoch = debug.dos_process_info()['capture_epoch']
                explicit = debug.save_state('ring-explicit-a.state')
                root = debug.rewind_start(max_steps=1, max_bytes=128 * 1024 * 1024, timeout_ms=60000)
                report.update(explicit=explicit, history_root=root)
                assert root['cursor'] and root['retained_nodes'] == 1
                after_captures = _sample(project, debug, offsets, 'after-both-captures')
                report['after_captures'] = after_captures
                _assert_exact(after_captures, captured)
                original = _advance(project, debug, offsets, captured, 'original-future')
                report['original_future'] = original
                history = root['history']
                epochs = {origin_epoch}
                owners = {debug.vm.process.pid}
                windows = {captured['audio_artifact']['metadata']['window']}
                for repeat in (1, 2):
                    for route in ('explicit', 'history-root'):
                        label = route + '-' + str(repeat)
                        entry = dict(route=route, repeat=repeat)
                        report['cases'].append(entry)
                        old = debug.vm.process
                        if route == 'explicit':
                            loaded = debug.load_state(explicit['artifact'], timeout_ms=60000)
                        else:
                            response = debug.rewind(history=history, node=root['cursor'], timeout_ms=60000)
                            entry['history'] = response
                            assert response['valid'] and response['cursor'] == root['cursor']
                            history = response['history']
                            loaded = response['restore']
                        entry['restore'] = loaded
                        info = debug.dos_process_info()
                        assert old.poll() is not None and debug.vm.process is not old
                        assert debug.vm.process.poll() is None and debug.vm.process.pid not in owners
                        owners.add(debug.vm.process.pid)
                        assert loaded['source_binding_restored'] is True and info['state'] == 'active'
                        assert info['capture_epoch'] not in epochs
                        epochs.add(info['capture_epoch'])
                        restored = _sample(project, debug, offsets, label + '-selected')
                        entry['selected'] = restored
                        _assert_selected(restored)
                        _assert_exact(restored, captured)
                        window = restored['audio_artifact']['metadata']['window']
                        assert window not in windows
                        windows.add(window)
                        future = _advance(project, debug, offsets, captured, label + '-future')
                        entry['future'] = future
                        _assert_exact(future, original)
                        assert future['audio_artifact']['metadata']['window'] == window
                        entry['full_continuation_exact'] = True
                lease = debug.keyboard_key_down('q')['lease']
                debug.keyboard_key_up(lease)
                assert_completion(debug, debug.run(timeout_ms=5000), exit_code=42)
                owner = debug.vm.process
            assert owner.poll() is not None
        report['success'] = True
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash
        assert digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-sb16-ring.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
