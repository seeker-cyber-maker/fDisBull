"""Finite, receipt-bound extraction of observed Shadowrun player poses.

This does not infer the original animation state machine. Source imagery and
returned target patterns are private, and must not be committed or packaged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .shadowrun_scene_assets import _sprites, _cram_words, decode_vdp_snapshot
from .udl_shadowrun import checked_rom, project_vdp_scene

CORE_SHA256 = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observed_poses(rom: bytes, capture_dir: str | Path, frames: list[int], *,
                   actor_sat_index: int = 1) -> dict:
    """Project a finite contiguous run of captured SAT poses to NES patterns.

    The capture receipt must bind each raw VDP input and the exact cartridge
    and core. OAM coordinates remain source screen positions: callers must
    independently establish the relationship to a target actor anchor. The
    returned frame sequence is an observation, not a general playback rule.
    """
    checked_rom(rom)
    if (not frames or len(frames) > 64 or any(type(n) is not int or n < 0 for n in frames)
            or frames != list(range(frames[0], frames[0] + len(frames)))):
        raise ValueError('expected 1..64 consecutive nonnegative capture frames')
    if type(actor_sat_index) is not int or not 0 <= actor_sat_index < 80:
        raise ValueError('invalid SAT index')
    root = Path(capture_dir)
    receipt = json.loads((root / 'capture.json').read_text())
    if (receipt.get('format') != 'fdisbull-private-genesis-scenes-1'
            or receipt.get('inputs', {}).get('rom', {}).get('sha256') != _hash(rom)
            or receipt.get('inputs', {}).get('core', {}).get('sha256') != CORE_SHA256
            or any(n not in receipt.get('captures', []) for n in frames)):
        raise ValueError('capture receipt does not bind the requested source and frames')
    files = receipt.get('files', {})
    poses, observations, cache = [], [], {}
    for frame in frames:
        arrays = {}
        for name in ('vram', 'cram', 'vsram', 'reg'):
            rel = f'native/scene-{frame:06d}/{name}.bin'
            data = (root / rel).read_bytes()
            entry = files.get(rel, {})
            if entry.get('size') != len(data) or entry.get('sha256') != _hash(data):
                raise ValueError(f'capture payload mismatch: {rel}')
            arrays[name] = data
        reg, vram = arrays['reg'], arrays['vram']
        if len(reg) != 32 or len(vram) != 65536 or len(arrays['cram']) != 128 or len(arrays['vsram']) != 128:
            raise ValueError('invalid VDP array length')
        if not (reg[12] & 0x80 and reg[12] & 1 and reg[1] & 4) or reg[12] & 6:
            raise ValueError('unsupported VDP mode')
        sprites = _sprites(vram, (reg[5] & 0x7e) << 9, True,
                           shadow_highlight_enabled=bool(reg[12] & 8))
        matches = [s for s in sprites if s.sat_index == actor_sat_index]
        if len(matches) != 1:
            raise ValueError('actor SAT entry is missing')
        actor = matches[0]
        if (any(actor.effects) or not (0 <= actor.x < 256 and 1 <= actor.y < 224)
                or actor.x + actor.width > 256 or actor.y + actor.height > 224):
            raise ValueError('actor is not projectable in this observed frame')
        # A changed palette or actor dimensions changes the target projection.
        key = (actor.pixels, actor.effects, actor.width, actor.height, actor.palette,
               _cram_words(arrays['cram']))
        if key not in cache:
            scene = decode_vdp_snapshot(vram, arrays['cram'], arrays['vsram'], reg)
            projection = project_vdp_scene(rom, scene, actor_sat_index=actor_sat_index)
            raw_oam = projection['sprite_oam']
            # Keep per-tile offsets independent of source screen position.
            relative_oam = bytearray(raw_oam)
            for pos in range(0, len(relative_oam), 4):
                relative_oam[pos] = (relative_oam[pos] - actor.y) & 255
                relative_oam[pos + 3] = (relative_oam[pos + 3] - actor.x) & 255
            cache[key] = len(poses)
            poses.append({'chr': projection['sprite_chr'], 'oam_offsets': bytes(relative_oam),
                          'palette': projection['sprite_palette'],
                          'width': actor.width, 'height': actor.height})
        observations.append({'frame': frame, 'pose': cache[key],
                             'screen_x': actor.x, 'screen_y': actor.y})
    return {'format': 'fdisbull-shadowrun-observed-poses-1',
            'capture_receipt_sha256': _hash((root / 'capture.json').read_bytes()),
            'rom_sha256': _hash(rom), 'core_sha256': CORE_SHA256,
            'actor_sat_index': actor_sat_index, 'poses': poses,
            'observations': observations,
            'scope': 'finite source capture, target color reduction; no animation rules inferred'}

# Reviewed source spans are separate from the capture-derived pose extraction.
ANIMATION_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_animation.c'
ANIMATION_SPANS = (
    (0x5fee, 0x600e, '2aac9eeaef2424e7d5014144f7c6d2535f0499082e115f9ae88d89fdcaff073d'),
    (0x6060, 0x6070, 'ec098ce3fe5eecbfd288aa2bfbad2d7c0d68458d3f0acc0efe3633026a8d326f'),
)


def lift_animation_counter(rom: bytes) -> dict:
    """Lift reviewed counter and positive-table index-wrap slices to GameIL.

    Caller is responsible for authenticating the mode, prior inputs and ROM
    table count. This is not the complete source animation state machine.
    """
    from .game_il import author_program
    checked_rom(rom)
    for start, end, digest in ANIMATION_SPANS:
        if _hash(rom[start:end]) != digest:
            raise ValueError('reviewed animation interval changed')
    raw = ANIMATION_SOURCE.read_bytes()
    evidence = {'kind': 'reviewed-source-bound-animation-counter-slice',
                'source_sha256': _hash(rom),
                'spans': [{'start': a, 'end': b, 'sha256': h} for a, b, h in ANIMATION_SPANS],
                'authoring_sha256': _hash(raw),
                'scope': 'actor phase counter and positive-count selector index wrap',
                'excluded': ['selector table lookup', 'negative-count selector', 'actor mode changes',
                             'graphics upload', 'frame visibility timing', 'whole-game animation']}
    program = author_program(raw.decode(), [{'id': 0, 'length': len(rom), 'sha256': _hash(rom)}],
                             evidence=evidence)
    if ANIMATION_SOURCE.read_bytes() != raw:
        raise ValueError('animation source changed while lifting')
    return program

# Only mappings actually observed in the dense original right-walk capture.
# These IDs index the first-occurrence pose order returned for frames 5999..6060.
RIGHT_WALK_POSES = {
    (0x10, 0): (0, 0x9e8e),
    (0x2c, 0): (1, 0x9e46),
    (0x2c, 1): (2, 0x9e58),
    (0x28, 0): (6, 0x9dfe),
    (0x28, 1): (3, 0x9e10),
    (0x28, 2): (4, 0x9e22),
    (0x28, 3): (5, 0x9dec),
}


def observed_right_walk_pose(rom: bytes, kind: int, selector: int, index: int) -> dict:
    """Resolve a qualified observed source-table entry to the captured pose ID.

    Table selection precedes the corresponding captured raster by one frame in
    the measured right-walk sequence; callers must model that latency. The
    actor mode and counter inputs remain the caller's responsibility. An
    unobserved key fails closed; this is not a general actor renderer.
    """
    checked_rom(rom)
    if type(kind) is not int or kind != 3 or type(selector) is not int or type(index) is not int:
        raise ValueError('unobserved actor kind or invalid selector/index')
    try:
        pose, expected_pointer = RIGHT_WALK_POSES[(selector, index)]
    except KeyError:
        raise ValueError('unobserved actor selector/index') from None
    read32 = lambda pos: int.from_bytes(rom[pos:pos + 4], 'big')
    table = read32(0x62ac + kind * 4)
    record = read32(table + selector)
    count = int.from_bytes(rom[record:record + 2], 'big')
    pointer = read32(record + 4 + index * 4)
    if (table != 0x6378 or count != (1 if selector == 0x10 else 4)
            or pointer != expected_pointer):
        raise ValueError('reviewed selector table changed')
    return {'pose': pose, 'source_table': table, 'source_record': record,
            'source_frame_pointer': pointer, 'capture_delay_frames': 1}
