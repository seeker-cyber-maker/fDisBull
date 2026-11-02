import hashlib
import json
from pathlib import Path

import pytest

from fdisbull.game_il import author_program, canonical
from fdisbull import shadowrun_replay as replay


def record(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def make_inputs(root, rom, program=None):
    session = root / 'capture-a'
    native = session / 'native'
    scene = native / 'scene-001000'
    scene.mkdir(parents=True)
    arrays = {
        'vram': bytes(65536), 'cram': bytes(128), 'vsram': bytes(128),
        'reg': bytes(32), 'ram': bytes(65536),
    }
    capture_files = {}
    for name, raw in arrays.items():
        (scene / f'{name}.bin').write_bytes(raw)
        capture_files[f'native/scene-001000/{name}.bin'] = record(raw)
    capture_files['native/frame-001000.png'] = record(b'png identity only')
    capture = {
        'format': 'fdisbull-private-genesis-scenes-1',
        'inputs': {'rom': record(rom), 'core': {'sha256': replay.CORE_SHA256, 'size': 1}},
        'captures': [1000], 'files': capture_files,
    }
    (session / 'capture.json').write_text(json.dumps(capture))
    receipt = {'rom_sha256': hashlib.sha256(rom).hexdigest(), 'core_sha256': replay.CORE_SHA256}
    (native / 'receipt.json').write_text(json.dumps(receipt))

    atlas_dir = root / 'atlas'
    atlas_dir.mkdir()
    vdp = {
        'atlas/vdp-rgb.bin': bytes(512 * 480 * 3),
        'atlas/vdp-coverage.bin': bytes([1]) * (512 * 480),
        'atlas/vdp-conflicts.bin': bytes(512 * 480),
        'atlas/raster-rgb.bin': bytes(512 * 480 * 3),
        'atlas/raster-coverage.bin': bytes([1]) * (512 * 480),
        'atlas/raster-conflicts.bin': bytes(512 * 480),
    }
    asset_names = {
        'atlas/vdp-rgb.bin': 'vdp-reconstructed-world-rgb.bin',
        'atlas/vdp-coverage.bin': 'vdp-reconstructed-world-coverage.bin',
        'atlas/vdp-conflicts.bin': 'vdp-reconstructed-world-conflicts.bin',
        'atlas/raster-rgb.bin': 'absolute-world-rgb.bin',
        'atlas/raster-coverage.bin': 'absolute-world-coverage.bin',
        'atlas/raster-conflicts.bin': 'absolute-world-conflicts.bin',
    }
    for bundle_name, raw in vdp.items():
        (atlas_dir / asset_names[bundle_name]).write_bytes(raw)
    audit = {'format': 'fdisbull-shadowrun-atlas-camera-coverage-v1'}
    audit_raw = json.dumps(audit).encode() + b'\n'
    (atlas_dir / 'camera-viewport-coverage.json').write_bytes(audit_raw)
    mosaic = {'width': 512, 'height': 480, 'origin_absolute_world': [768, 512],
              'screen_crop_width': 256, 'conflict_pixels': 0,
              'rgb_sha256': record(vdp['atlas/raster-rgb.bin'])['sha256'],
              'coverage_sha256': record(vdp['atlas/raster-coverage.bin'])['sha256'],
              'conflict_sha256': record(vdp['atlas/raster-conflicts.bin'])['sha256']}
    vdp_meta = {'includes_pixels_under_sat': True, 'unmasked_conflict_pixels': 0,
                'unknown_pixels_are_not_filled': True,
                'rgb_sha256': record(vdp['atlas/vdp-rgb.bin'])['sha256'],
                'coverage_sha256': record(vdp['atlas/vdp-coverage.bin'])['sha256'],
                'conflict_sha256': record(vdp['atlas/vdp-conflicts.bin'])['sha256']}
    index = {'format': 'fdisbull-shadowrun-opening-world-assets-v2',
        'status': 'bounded observed field mosaic plus separate interaction UI snapshots',
        'rom_sha256': hashlib.sha256(rom).hexdigest(), 'core_sha256': replay.CORE_SHA256,
        'mosaic': mosaic, 'vdp_background_reconstruction': vdp_meta,
        'field_frames': [{'capture': 'capture-a', 'frame': 1000}],
        'capture_receipts_sha256': {'capture-a': record((native / 'receipt.json').read_bytes())['sha256']},
        'camera_viewport_coverage_reference': {
            'path': 'camera-viewport-coverage.json', 'sha256': record(audit_raw)['sha256'],
            'all_sampled_viewports_vdp_complete_conflict_free': True}}
    index_path = atlas_dir / 'index.json'
    index_path.write_text(json.dumps(index))
    return root / 'source.bin', scene, index_path, arrays, vdp


def patch_lifter(monkeypatch, rom, program):
    monkeypatch.setattr(replay, 'ROM_SHA256', hashlib.sha256(rom).hexdigest())
    monkeypatch.setattr(replay, '_read_rom', lambda path: rom)
    import fdisbull.udl_shadowrun as lifter
    monkeypatch.setattr(lifter, 'lift_opening_stoker', lambda raw: program)


def test_export_inspect_and_reject_tampered_payload(tmp_path, monkeypatch):
    rom = bytes([3]) * replay.ROM_SIZE
    program = author_program('void opening(void) { return; }',
        [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    patch_lifter(monkeypatch, rom, program)
    rom_path, snapshot, atlas, arrays, atlas_arrays = make_inputs(tmp_path, rom, program)
    rom_path.write_bytes(rom)
    bundle = tmp_path / 'bundle'
    receipt = replay.export_opening(rom_path, snapshot=snapshot, atlas=atlas, output=bundle)
    assert receipt['executed'] is False
    assert (bundle / 'manifest.json').is_file()
    assert not (bundle / 'source.rom').exists()
    assert replay.inspect_opening(bundle / 'manifest.json')['status'] == 'payload-integrity-verified'
    tampered = bundle / 'capture/ram.bin'
    tampered.chmod(0o600)
    changed = bytearray(tampered.read_bytes())
    changed[0] ^= 1
    tampered.write_bytes(changed)
    with pytest.raises(ValueError, match='hash mismatch'):
        replay.inspect_opening(bundle / 'manifest.json')


def test_export_requires_capture_and_atlas_to_bind_same_native_receipt(tmp_path, monkeypatch):
    rom = bytes([5]) * replay.ROM_SIZE
    program = author_program('void opening(void) { return; }',
        [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    patch_lifter(monkeypatch, rom, program)
    rom_path, snapshot, atlas, _, _ = make_inputs(tmp_path, rom, program)
    rom_path.write_bytes(rom)
    index = json.loads(atlas.read_text())
    index['capture_receipts_sha256']['capture-a'] = '0' * 64
    atlas.write_text(json.dumps(index))
    with pytest.raises(ValueError, match='capture receipt'):
        replay.export_opening(rom_path, snapshot=snapshot, atlas=atlas, output=tmp_path / 'reject')


def test_build_requires_fresh_canonical_lift_and_passes_locked_vdp_layer(tmp_path, monkeypatch):
    rom = bytes([7]) * replay.ROM_SIZE
    program = author_program('void opening(void) { return; }',
        [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    patch_lifter(monkeypatch, rom, program)
    rom_path, snapshot, atlas, arrays, atlas_arrays = make_inputs(tmp_path, rom, program)
    rom_path.write_bytes(rom)
    bundle = tmp_path / 'bundle'
    replay.export_opening(rom_path, snapshot=snapshot, atlas=atlas, output=bundle)
    import fdisbull.shadowrun_scene_assets as scene_assets
    monkeypatch.setattr(scene_assets, 'decode_vdp_snapshot', lambda *args: 'decoded-scene')
    calls = {}
    def backend(raw_rom, scene, raw_ram, output, **kwargs):
        calls.update({'rom': raw_rom, 'scene': scene, 'ram': raw_ram, 'kwargs': kwargs})
        Path(output).mkdir(parents=True)
        probe = b'NES output'
        Path(output, 'probe.nes').write_bytes(probe)
        Path(output, 'manifest.json').write_text(json.dumps({'rom_sha256': 'generated', 'program_sha256': 'uil'}))
        return {'output_sha256': hashlib.sha256(probe).hexdigest(),
                'program_sha256': hashlib.sha256(canonical(program)).hexdigest(),
                'dialogue_projection': {'reentry': 'target-only transition suppresses controls and fails after 240 ticks'},
                'publication': {'reentry_active_byte':24,'reentry_tick_byte':25}}
    import fdisbull.udc_nes_shadowrun as backend_module
    monkeypatch.setattr(backend_module, 'build_opening_atlas_probe', backend)
    out = tmp_path / 'build'
    result = replay.build_opening(bundle / 'manifest.json', rom_path=rom_path,
                                  cc65_root=tmp_path / 'toolchain', output=out)
    assert result['source_relift_checked'] is True
    assert calls['scene'] == 'decoded-scene'
    assert calls['ram'] == arrays['ram']
    assert calls['kwargs']['enable_stoker'] is True
    assert calls['kwargs']['atlas_origin_x'] == 768
    assert calls['kwargs']['atlas_rgb'] == atlas_arrays['atlas/vdp-rgb.bin']
    assert (out / 'replay-receipt.json').is_file()
    lowering = json.loads((out / 'replay-receipt.json').read_text())['lowering_receipt']
    assert lowering['renderer_transition_state_publication'] == {
        'active_byte':24,'tick_byte':25,'bound_ticks':240,'controls_suppressed_while_active':True}
    assert lowering['scope'].startswith('renderer-side NES transition')
    import fdisbull.udl_shadowrun as lifter
    changed_program = author_program('void opening(void) { unsigned char x; x = 1; }',
        [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    monkeypatch.setattr(lifter, 'lift_opening_stoker', lambda raw: changed_program)
    with pytest.raises(ValueError, match='Fresh source lift differs'):
        replay.build_opening(bundle / 'manifest.json', rom_path=rom_path,
            cc65_root=tmp_path / 'toolchain', output=tmp_path / 'changed-build')
    assert not (tmp_path / 'changed-build').exists()


def test_console_udc_routes_only_registered_nes_profile(tmp_path, monkeypatch):
    from fdisbull.console_udc import compile_console_path
    import fdisbull.shadowrun_replay as subject
    source = tmp_path / 'manifest.json'
    source.write_text(json.dumps({'format': replay.FORMAT}))
    seen = {}
    def build(path, **kwargs):
        seen.update(path=path, **kwargs)
        return {'format': 'routed'}
    monkeypatch.setattr(subject, 'build_opening', build)
    result = compile_console_path(source, region_path='rom.bin', cc65_root='cc65',
        output='output', target='nes')
    assert result == {'format': 'routed'}
    assert seen == {'path': source, 'rom_path': 'rom.bin', 'cc65_root': 'cc65', 'output': 'output'}
    with pytest.raises(ValueError, match='NES-only'):
        compile_console_path(source, region_path='rom.bin', cc65_root='cc65',
            output='output', target='genesis')
