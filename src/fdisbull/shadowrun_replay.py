"""Private, bounded Shadowrun Genesis opening -> NES replay bundles.

This profile combines authored opening/interaction GameIL, one provenance-
bound Genesis capture and one bounded observed atlas.  It is not a whole-game
lift and does not copy a ROM into the exported bundle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from .game_il import canonical, validate_program

FORMAT = 'fdisbull-shadowrun-opening-replay-1'
PROFILE = 'shadowrun-genesis-opening-stoker-assisted-v1'
ROM_SIZE = 2 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
MAX_SMALL = 1 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
CORE_SHA256 = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
ATLAS_ORIGIN = (768, 512)
ATLAS_SIZE = (512, 480)
# The separate animated experiment admits this reviewed atlas only. A bundle's
# self-declared payload hashes alone are not independent observation evidence.
ANIMATED_ATLAS_SHA256 = {
    'atlas/vdp-rgb.bin': 'edce6bcd35ee612fd04210bf5bb864568982c83f91e65b893e3b46895f399a0f',
    'atlas/vdp-coverage.bin': '8b88873e4c48de164e1c3ee2410a4c1c180d8e01d668307ba8d08d4f717b6e18',
    'atlas/vdp-conflicts.bin': '9eb8fa54d87a9b9775dd55c07b3d164453884695bd1ed83fe2f63259ee9e6afc',
}
SNAPSHOT_FILES = {
    'capture/vram.bin': ('vram', 65536),
    'capture/cram.bin': ('cram', 128),
    'capture/vsram.bin': ('vsram', 128),
    'capture/reg.bin': ('reg', 32),
    'capture/ram.bin': ('ram', 65536),
}
ATLAS_FILES = {
    'atlas/vdp-rgb.bin': ('vdp-reconstructed-world-rgb.bin', 512 * 480 * 3),
    'atlas/vdp-coverage.bin': ('vdp-reconstructed-world-coverage.bin', 512 * 480),
    'atlas/vdp-conflicts.bin': ('vdp-reconstructed-world-conflicts.bin', 512 * 480),
    'atlas/raster-rgb.bin': ('absolute-world-rgb.bin', 512 * 480 * 3),
    'atlas/raster-coverage.bin': ('absolute-world-coverage.bin', 512 * 480),
    'atlas/raster-conflicts.bin': ('absolute-world-conflicts.bin', 512 * 480),
}
PAYLOADS = {'program.uil.json': MAX_JSON,
            **{name: size for name, (_, size) in SNAPSHOT_FILES.items()},
            **{name: size for name, (_, size) in ATLAS_FILES.items()}}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _record(raw: bytes) -> dict:
    return {'size': len(raw), 'sha256': _sha(raw)}


def _read(path: Path, limit: int, *, exact: int | None = None) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular non-symlink input file')
    before = path.stat()
    if before.st_size > limit or (exact is not None and before.st_size != exact):
        raise ValueError('Input file exceeds its declared size')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or len(raw) != before.st_size or path.stat().st_size != before.st_size:
        raise ValueError('Input file changed or exceeded its read bound')
    if exact is not None and len(raw) != exact:
        raise ValueError('Input file has the wrong exact size')
    return raw


def _json(path: Path) -> tuple[dict, bytes]:
    raw = _read(path, MAX_JSON)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value, raw


def _is_git_path(path: Path) -> bool:
    return any((parent / '.git').exists() for parent in (path, *path.parents))


def _new_private_directory(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    if _is_git_path(target):
        raise ValueError('Output must be outside Git worktrees')
    if target.exists():
        raise ValueError('Output directory must be new')
    if not target.parent.is_dir():
        raise ValueError('Output parent directory must already exist')
    return target


def profiles() -> dict:
    return {'format': 'fdisbull-shadowrun-opening-profiles-1', 'profiles': [{
        'id': PROFILE, 'format': FORMAT, 'source_platform': 'genesis',
        'source_size': ROM_SIZE, 'source_sha256': ROM_SHA256,
        'target': 'nes', 'presentation': 'captured absolute-world atlas',
        'interaction': 'bounded assisted Stoker opening adapter',
        'whole_game_automatic_lifting': False,
        'limits': ['one reviewed Shadowrun Genesis ROM identity only',
                   'one source-associated captured opening state and bounded atlas',
                   'screen movement and Stoker interaction are an assisted target projection',
                   'not whole-game recovery, original NES parity, or arbitrary-ROM support']
    }], 'unsupported_rom_policy': 'refuse semantic export for any other source identity'}


def _read_rom(path: str | Path) -> bytes:
    raw = _read(Path(path).expanduser(), ROM_SIZE, exact=ROM_SIZE)
    if _sha(raw) != ROM_SHA256:
        raise ValueError('Expected the exact reviewed Shadowrun Genesis cartridge')
    from .udl_shadowrun import checked_rom
    checked_rom(raw)
    return raw


def _source_capture(snapshot_path: str | Path, rom_hash: str) -> tuple[dict, dict[str, bytes], dict]:
    snapshot = Path(snapshot_path).expanduser().resolve()
    if snapshot.is_symlink() or not snapshot.is_dir() or not re.fullmatch(r'scene-[0-9]{6}', snapshot.name):
        raise ValueError('Expected one native/scene-NNNNNN capture directory')
    frame = int(snapshot.name[-6:])
    capture_root = snapshot.parents[1]
    capture_path = capture_root / 'capture.json'
    native_receipt_path = capture_root / 'native' / 'receipt.json'
    capture, capture_raw = _json(capture_path)
    receipt, receipt_raw = _json(native_receipt_path)
    if capture.get('format') != 'fdisbull-private-genesis-scenes-1':
        raise ValueError('Missing recognized capture association')
    if frame not in capture.get('captures', []):
        raise ValueError('Capture receipt does not include this requested frame')
    inputs = capture.get('inputs', {})
    if (inputs.get('rom', {}).get('sha256') != rom_hash or
            inputs.get('rom', {}).get('size') != ROM_SIZE or
            inputs.get('core', {}).get('sha256') != CORE_SHA256):
        raise ValueError('Capture receipt is not bound to the requested ROM/core identity')
    if (receipt.get('rom_sha256') != rom_hash or receipt.get('core_sha256') != CORE_SHA256):
        raise ValueError('Native receipt is not bound to the requested ROM/core identity')
    frame_files = capture.get('files')
    if not isinstance(frame_files, dict):
        raise ValueError('Capture receipt has no file identity table')
    arrays: dict[str, bytes] = {}
    source_names = {}
    for name, (field, exact_size) in SNAPSHOT_FILES.items():
        source_name = f'native/{snapshot.name}/{field}.bin'
        expected = frame_files.get(source_name)
        if not isinstance(expected, dict):
            raise ValueError('Capture receipt does not bind ' + source_name)
        raw = _read(snapshot / f'{field}.bin', exact_size, exact=exact_size)
        if expected != _record(raw):
            raise ValueError('Captured state differs from its source receipt: ' + field)
        arrays[field] = raw
        source_names[field] = expected
    capture_identity = {'capture_id': capture_root.name, 'frame': frame,
        'capture_json_sha256': _sha(capture_raw), 'native_receipt_sha256': _sha(receipt_raw),
        'source_rom_sha256': rom_hash, 'source_core_sha256': CORE_SHA256,
        'snapshot_arrays': source_names,
        'frame_screenshot': frame_files.get(f'native/frame-{frame:06d}.png')}
    return capture_identity, arrays, capture


def _atlas_inputs(index_path: str | Path, capture_id: dict) -> tuple[dict, dict[str, bytes]]:
    index_file = Path(index_path).expanduser().resolve()
    index, index_raw = _json(index_file)
    if index.get('format') != 'fdisbull-shadowrun-opening-world-assets-v2':
        raise ValueError('Expected the reviewed Shadowrun opening-world atlas index')
    if index.get('status') != 'bounded observed field mosaic plus separate interaction UI snapshots':
        raise ValueError('Atlas index has an unsupported status')
    if index.get('rom_sha256') != capture_id['source_rom_sha256'] or index.get('core_sha256') != capture_id['source_core_sha256']:
        raise ValueError('Atlas and captured state use different source identities')
    mosaic = index.get('mosaic', {})
    if (mosaic.get('width'), mosaic.get('height'), mosaic.get('origin_absolute_world'),
            mosaic.get('screen_crop_width')) != (512, 480, [768, 512], 256):
        raise ValueError('Atlas does not match the registered absolute-world geometry')
    if mosaic.get('conflict_pixels') != 0:
        raise ValueError('Atlas contains conflicting RGB observations')
    # The index must bind this exact capture snapshot as a field view.
    matching = [item for item in index.get('field_frames', [])
                if item.get('capture') == capture_id['capture_id'] and item.get('frame') == capture_id['frame']]
    if not matching:
        raise ValueError('Atlas does not bind the selected native capture state')
    if index.get('capture_receipts_sha256', {}).get(capture_id['capture_id']) != capture_id['native_receipt_sha256']:
        raise ValueError('Atlas does not bind the selected native capture receipt')
    vd = index.get('vdp_background_reconstruction', {})
    if (vd.get('includes_pixels_under_sat') is not True or
            vd.get('unmasked_conflict_pixels') != 0 or vd.get('unknown_pixels_are_not_filled') is not True):
        raise ValueError('Atlas VDP-reconstruction evidence is missing or unsupported')
    arrays = {}
    for bundle_name, (atlas_name, size) in ATLAS_FILES.items():
        raw = _read(index_file.parent / atlas_name, size, exact=size)
        expected_hash = (vd if bundle_name.startswith('atlas/vdp-') else mosaic).get(
            {'atlas/vdp-rgb.bin':'rgb_sha256','atlas/vdp-coverage.bin':'coverage_sha256',
             'atlas/vdp-conflicts.bin':'conflict_sha256','atlas/raster-rgb.bin':'rgb_sha256',
             'atlas/raster-coverage.bin':'coverage_sha256','atlas/raster-conflicts.bin':'conflict_sha256'}[bundle_name])
        if _sha(raw) != expected_hash:
            raise ValueError('Atlas asset hash differs from index: ' + atlas_name)
        arrays[bundle_name] = raw
    if any(arrays['atlas/vdp-conflicts.bin']) or any(arrays['atlas/raster-conflicts.bin']):
        raise ValueError('Atlas conflict masks must be empty for this profile')
    camera_audit = index.get('camera_viewport_coverage_reference', {})
    if camera_audit.get('all_sampled_viewports_vdp_complete_conflict_free') is not True:
        raise ValueError('Atlas does not prove complete VDP coverage for its sampled viewports')
    audit_raw = _read(index_file.parent / 'camera-viewport-coverage.json', MAX_JSON)
    if _sha(audit_raw) != camera_audit.get('sha256'):
        raise ValueError('Atlas camera viewport audit hash mismatch')
    audit = json.loads(audit_raw)
    if audit.get('format') != 'fdisbull-shadowrun-atlas-camera-coverage-v1':
        raise ValueError('Unsupported atlas camera audit')
    info = {'index_sha256': _sha(index_raw), 'index_format': index['format'],
        'origin_absolute_world': [768, 512], 'size': [512, 480],
        'selected_layer_for_build': 'vdp-reconstructed-world; separate from SAT-masked raster-observed layer',
        'camera_viewport_audit_sha256': _sha(audit_raw),
        'camera_viewport_audit_claim': 'all sampled viewpoints only; unsampled intermediate camera states not claimed',
        'selected_capture': capture_id['capture_id'], 'selected_frame': capture_id['frame'],
        'arrays': {name: _record(raw) for name, raw in arrays.items()}}
    return info, arrays


def _write_payloads(root: Path, payloads: dict[str, bytes]) -> dict:
    files = {}
    for name, raw in payloads.items():
        if name not in PAYLOADS or len(raw) > PAYLOADS[name]:
            raise ValueError('Unexpected or oversized Shadowrun bundle payload: ' + name)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o400)
        files[name] = _record(raw)
    if set(files) != set(PAYLOADS):
        raise ValueError('Shadowrun bundle payload set is incomplete')
    if sum(item['size'] for item in files.values()) > MAX_TOTAL:
        raise ValueError('Shadowrun bundle exceeds its total size limit')
    return files


def export_opening(rom_path: str | Path, *, snapshot: str | Path,
                   atlas: str | Path, output: str | Path) -> dict:
    rom = _read_rom(rom_path)
    capture_id, arrays, _ = _source_capture(snapshot, _sha(rom))
    atlas_info, atlas_arrays = _atlas_inputs(atlas, capture_id)
    from .udl_shadowrun import lift_opening_stoker
    program = lift_opening_stoker(rom)
    validate_program(program)
    program_raw = canonical(program)
    payloads = {'program.uil.json': program_raw}
    payloads.update({name: arrays[field] for name, (field, _) in SNAPSHOT_FILES.items()})
    payloads.update(atlas_arrays)
    destination = _new_private_directory(output)
    temporary = Path(tempfile.mkdtemp(prefix='.shadowrun-opening-', dir=destination.parent))
    try:
        files = _write_payloads(temporary, payloads)
        manifest = {'format': FORMAT, 'profile': PROFILE, 'target': 'nes',
            'source': {'platform': 'genesis', 'size': len(rom), 'sha256': _sha(rom)},
            'source_core': {'sha256': CORE_SHA256, 'captured_core_only': True},
            'program': {'path': 'program.uil.json', 'canonical_sha256': _sha(program_raw),
                        'format': program['format'], 'scope': 'bounded opening movement and guarded Stoker request/UI projection'},
            'capture': capture_id, 'atlas': atlas_info,
            'recipe': {'id': PROFILE, 'target': 'nes', 'actor_sat_index': 1,
                'atlas_origin_x': ATLAS_ORIGIN[0], 'atlas_origin_y': ATLAS_ORIGIN[1],
                'atlas_row_offset': 0, 'max_pattern_merges': 0, 'enable_stoker': True,
                'selected_atlas_rgb': 'atlas/vdp-rgb.bin', 'selected_atlas_coverage': 'atlas/vdp-coverage.bin',
                'selected_atlas_conflicts': 'atlas/vdp-conflicts.bin'},
            'files': files,
            'scope': {'executed': False, 'assisted_opening_profile': True,
                'whole_game_recovery': False, 'source_game_coverage': 'opening movement and bounded Stoker interaction only',
                'projection_limits': ['captured source camera/atlas is bounded', 'world art is quantized for NES output',
                    'Stoker UI is an authored target adapter; original dialogue engine is not implemented',
                    'captured RAM dispatch and activity context are supplied assumptions']}}
        raw_manifest = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'
        if len(raw_manifest) > MAX_JSON:
            raise ValueError('Shadowrun bundle manifest exceeds its size limit')
        with (temporary / 'manifest.json').open('xb') as stream:
            stream.write(raw_manifest)
        (temporary / 'manifest.json').chmod(0o400)
        if destination.exists():
            raise ValueError('Output directory appeared during export')
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'format': FORMAT, 'output_directory': str(destination), 'manifest': str(destination / 'manifest.json'),
            'manifest_sha256': _sha(raw_manifest), 'program_sha256': _sha(program_raw),
            'source_rom_sha256': _sha(rom), 'executed': False}


def _bundle(manifest_path: str | Path) -> tuple[Path, dict, dict[str, bytes]]:
    selected_manifest = Path(manifest_path).expanduser()
    if selected_manifest.is_symlink() or selected_manifest.name != 'manifest.json':
        raise ValueError('Expected the bundle manifest.json path')
    manifest_file = selected_manifest.resolve()
    bundle = manifest_file.parent
    manifest, _ = _json(manifest_file)
    if manifest.get('format') != FORMAT or manifest.get('profile') != PROFILE or manifest.get('target') != 'nes':
        raise ValueError('Unsupported Shadowrun opening bundle profile')
    if (manifest.get('source') != {'platform':'genesis','size':ROM_SIZE,'sha256':ROM_SHA256} or
            manifest.get('source_core', {}).get('sha256') != CORE_SHA256):
        raise ValueError('Bundle source identity is not the registered Shadowrun cartridge/core')
    if manifest.get('recipe') != {'id':PROFILE,'target':'nes','actor_sat_index':1,
            'atlas_origin_x':768,'atlas_origin_y':512,'atlas_row_offset':0,'max_pattern_merges':0,
            'enable_stoker':True,'selected_atlas_rgb':'atlas/vdp-rgb.bin',
            'selected_atlas_coverage':'atlas/vdp-coverage.bin','selected_atlas_conflicts':'atlas/vdp-conflicts.bin'}:
        raise ValueError('Bundle recipe differs from the registered bounded projection')
    file_table = manifest.get('files')
    if not isinstance(file_table, dict) or set(file_table) != set(PAYLOADS):
        raise ValueError('Bundle payload table differs from the registered fixed file set')
    payloads = {}
    total = 0
    for name, limit in PAYLOADS.items():
        if not isinstance(name, str) or name not in file_table:
            raise ValueError('Missing fixed bundle payload')
        path = bundle / name
        if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Bundle payload path is unsafe')
        raw = _read(path, limit)
        if file_table[name] != _record(raw):
            raise ValueError('Bundle payload hash mismatch: ' + name)
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError('Bundle payload total exceeds the profile size limit')
        payloads[name] = raw
    program = json.loads(payloads['program.uil.json'])
    validate_program(program)
    if (manifest.get('program', {}).get('canonical_sha256') != _sha(canonical(program)) or
            manifest.get('program', {}).get('format') != 'fdisbull-game-il-2'):
        raise ValueError('Bundled GameIL canonical hash mismatch')
    if program.get('regions') != [{'id': 0, 'length': ROM_SIZE, 'sha256': ROM_SHA256}]:
        raise ValueError('Bundled GameIL does not bind the exact registered source region')
    capture = manifest.get('capture', {})
    if (capture.get('source_rom_sha256') != ROM_SHA256 or
            capture.get('source_core_sha256') != CORE_SHA256 or
            capture.get('frame') not in range(0, 1000000) or
            not isinstance(capture.get('capture_id'), str) or
            not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', capture.get('capture_id', '')) or
            not all(isinstance(capture.get(field), str) and re.fullmatch(r'[0-9a-f]{64}', capture[field])
                    for field in ('capture_json_sha256', 'native_receipt_sha256')) or
            not isinstance(capture.get('snapshot_arrays'), dict) or
            set(capture['snapshot_arrays']) != {field for field, _ in SNAPSHOT_FILES.values()}):
        raise ValueError('Bundle capture provenance is invalid')
    for name, (field, _) in SNAPSHOT_FILES.items():
        if capture['snapshot_arrays'].get(field) != _record(payloads[name]):
            raise ValueError('Bundle capture identity does not match ' + field)
    atlas = manifest.get('atlas', {})
    for name, (field, _) in ATLAS_FILES.items():
        if atlas.get('arrays', {}).get(name) != _record(payloads[name]):
            raise ValueError('Bundle atlas identity does not match ' + name)
    return bundle, manifest, payloads


def inspect_opening(manifest_path: str | Path) -> dict:
    bundle, manifest, payloads = _bundle(manifest_path)
    return {'format': FORMAT, 'profile': PROFILE, 'status': 'payload-integrity-verified',
        'bundle_directory': str(bundle), 'source': manifest['source'],
        'program': manifest['program'], 'capture': manifest['capture'],
        'atlas': manifest['atlas'], 'payload_count': len(payloads),
        'executed': False, 'source_relift_checked': False,
        'capture_receipts_reopened': False,
        'limits': manifest['scope']['projection_limits']}


def build_animated_opening(manifest_path: str | Path, *, rom_path: str | Path,
                           capture: str | Path, cc65_root: str | Path,
                           output: str | Path) -> dict:
    """Build the separately qualified, right-only animated experiment.

    This preserves the existing courtyard/Stoker build. The extra source run
    supplies private observed poses, not a recorded input playback program.
    """
    initial_manifest, manifest_raw = _json(Path(manifest_path).expanduser())
    _, manifest, payloads = _bundle(manifest_path)
    if canonical(initial_manifest) != canonical(manifest):
        raise ValueError('Opening manifest changed during validation')
    rom = _read_rom(rom_path)
    from .udl_shadowrun import lift_opening_stoker
    if (_sha(rom) != manifest['source']['sha256'] or
            canonical(lift_opening_stoker(rom)) != canonical(json.loads(payloads['program.uil.json']))):
        raise ValueError('Animated build differs from the registered source lift')
    if any(_sha(payloads[name]) != digest for name, digest in ANIMATED_ATLAS_SHA256.items()):
        raise ValueError('Animated build requires the independently reviewed atlas payloads')
    snapshot = Path(capture).expanduser().resolve() / 'native/scene-005999'
    _, arrays, _ = _source_capture(snapshot, _sha(rom))
    if any(arrays[field] != payloads[name] for name, (field, _) in SNAPSHOT_FILES.items()):
        raise ValueError('Animation initial state differs from the opening bundle')
    from .shadowrun_nes_animation import build_right_walk_animation_probe
    result = build_right_walk_animation_probe(rom, capture, output, cc65_root=cc65_root,
        atlas_rgb=payloads['atlas/vdp-rgb.bin'], atlas_coverage=payloads['atlas/vdp-coverage.bin'],
        atlas_conflicts=payloads['atlas/vdp-conflicts.bin'],
        atlas_origin_x=manifest['recipe']['atlas_origin_x'], atlas_origin_y=manifest['recipe']['atlas_origin_y'],
        atlas_row_offset=manifest['recipe']['atlas_row_offset'],
        max_pattern_merges=manifest['recipe']['max_pattern_merges'])
    if _sha(_read(Path(output).expanduser().resolve() / 'animated.nes', 128 * 1024)) != result['output_sha256']:
        raise ValueError('Animated backend output hash mismatch')
    if _read_rom(rom_path) != rom:
        raise ValueError('Original ROM path changed during animated build')
    if _read(Path(manifest_path).expanduser(), MAX_JSON) != manifest_raw:
        raise ValueError('Opening manifest changed during animated build')
    result = {**result, 'bundle_manifest_sha256': _sha(manifest_raw),
              'atlas_payloads': {name: _record(payloads[name]) for name in ATLAS_FILES},
              'source_path_unchanged': True, 'executed': False}
    (Path(output).expanduser().resolve() / 'animated-replay.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def build_opening(manifest_path: str | Path, *, rom_path: str | Path,
                  cc65_root: str | Path, output: str | Path) -> dict:
    _, manifest, payloads = _bundle(manifest_path)
    rom = _read_rom(rom_path)
    if _sha(rom) != manifest['source']['sha256']:
        raise ValueError('Build ROM differs from the exported source identity')
    from .udl_shadowrun import lift_opening_stoker
    current = lift_opening_stoker(rom)
    validate_program(current)
    if canonical(current) != canonical(json.loads(payloads['program.uil.json'])):
        raise ValueError('Fresh source lift differs from the exported GameIL')
    from .shadowrun_scene_assets import decode_vdp_snapshot
    scene = decode_vdp_snapshot(payloads['capture/vram.bin'], payloads['capture/cram.bin'],
                                 payloads['capture/vsram.bin'], payloads['capture/reg.bin'])
    destination = _new_private_directory(output)
    result = None
    try:
        from .udc_nes_shadowrun import build_opening_atlas_probe
        result = build_opening_atlas_probe(rom, scene, payloads['capture/ram.bin'], destination,
            actor_sat_index=manifest['recipe']['actor_sat_index'], cc65_root=cc65_root,
            atlas_rgb=payloads['atlas/vdp-rgb.bin'], atlas_coverage=payloads['atlas/vdp-coverage.bin'],
            atlas_conflicts=payloads['atlas/vdp-conflicts.bin'],
            atlas_origin_x=manifest['recipe']['atlas_origin_x'], atlas_origin_y=manifest['recipe']['atlas_origin_y'],
            atlas_row_offset=manifest['recipe']['atlas_row_offset'],
            max_pattern_merges=manifest['recipe']['max_pattern_merges'],
            enable_stoker=manifest['recipe']['enable_stoker'])
        outputs = {}
        total = 0
        for path in sorted(destination.rglob('*')):
            if path.is_symlink():
                raise ValueError('Build output contains a symlink')
            if path.is_file():
                raw = _read(path, MAX_JSON if path.suffix == '.json' else 4 * 1024 * 1024)
                total += len(raw)
                if total > 32 * 1024 * 1024:
                    raise ValueError('Build output exceeds the inspection limit')
                outputs[path.relative_to(destination).as_posix()] = _record(raw)
        expected_output = result.get('output_sha256') if isinstance(result, dict) else None
        if (not isinstance(expected_output, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_output) or
                outputs.get('probe.nes', {}).get('sha256') != expected_output):
            raise ValueError('Backend output hash does not match the generated NES cartridge')
        if result.get('program_sha256') != _sha(canonical(current)):
            raise ValueError('Backend reports a different canonical GameIL program hash')
        dialogue = result.get('dialogue_projection', {})
        publication = result.get('publication', {})
        if (not isinstance(dialogue, dict) or not isinstance(dialogue.get('reentry'), str) or
                'suppress' not in dialogue.get('reentry', '').lower() or '240' not in dialogue.get('reentry', '') or
                publication.get('reentry_active_byte') != 24 or publication.get('reentry_tick_byte') != 25):
            raise ValueError('Backend lowering receipt omits the bounded Stoker reentry projection')
        backend_manifest_raw = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        lowering_receipt = {'format': 'fdisbull-shadowrun-opening-lowering-1',
            'source_program_sha256': _sha(canonical(current)),
            'backend_manifest_sha256': _sha(backend_manifest_raw),
            'target_only_renderer_transition': dialogue['reentry'],
            'renderer_transition_state_publication': {'active_byte': 24, 'tick_byte': 25,
                'bound_ticks': 240, 'controls_suppressed_while_active': True},
            'target_output_sha256': expected_output,
            'scope': 'renderer-side NES transition only; does not claim a Genesis reentry implementation'}
        receipt = {'format': 'fdisbull-shadowrun-opening-build-1', 'profile': PROFILE,
            'source_rom_sha256': _sha(rom), 'bundle_manifest_sha256': _sha(_read(Path(manifest_path), MAX_JSON)),
            'bundle_program_sha256': manifest['program']['canonical_sha256'],
            'output_files': outputs, 'backend_manifest': result, 'lowering_receipt': lowering_receipt,
            'executed': False, 'source_relift_checked': True,
            'scope': manifest['scope']}
        receipt_raw = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'
        if len(receipt_raw) > MAX_JSON:
            raise ValueError('Build receipt exceeds its size limit')
        with (destination / 'replay-receipt.json').open('xb') as stream:
            stream.write(receipt_raw)
        return {'format': receipt['format'], 'output_directory': str(destination),
                'receipt_sha256': _sha(receipt_raw), 'output_sha256': expected_output,
                'program_sha256': result.get('program_sha256'), 'executed': False,
                'source_relift_checked': True}
    except BaseException:
        # Preserve backend output if it got far enough to create files; callers
        # can inspect a failed native build without rerunning over it.
        raise
