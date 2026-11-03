"""Reviewed full-game Miniplanets profile with externally bound original data.

All game rules go through procedural UIL.  Renderer/audio adapters are
qualified separately; this is not an automatic arbitrary-ROM decompiler.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from .game_il import author_program
from .udl_miniplanets import MINIPLANETS_LICENSE, ROM_SHA256
from .udc_nes_level import _FONT

SOURCE_COMMIT = '0ac9c395289cc5d0837c96d45e61a27300e8eebc'
STAGE_HEADERS = 0x655CA
GLOBE_LUT = 0xA537
OBJECT_LUT = 0x1A537
RAFT_LUT = 0x2A537
ENDING_LUT = 0x3A537


def checked_rom(rom):
    if not isinstance(rom, bytes) or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Full-game profile requires the qualified Miniplanets REV04 ROM')
    return rom


def lift_full_game(rom, *, variant='efficient'):
    checked_rom(rom)
    root = Path(__file__).with_name('game_sources')
    units = [root / 'miniplanets_full.c', root / 'miniplanets_actors.c']
    if variant not in ('efficient','baseline'):
        raise ValueError('Game authoring variant must be efficient or baseline')
    # Parsing and provenance must use the same captured bytes, including if a
    # source unit changes on disk while this export is being assembled.
    captured={path:path.read_bytes() for path in units}
    parts=[captured[path].decode('utf-8') for path in units]
    if variant=='baseline':
        # Reconstruct the independently qualified first implementation. This
        # intentional variant changes only storage width within the48-slot
        # domain and redundant empty-slot work, not object scan ordering.
        parts[1],n=re.subn(r'\bu8 p;', 'u16 p;',parts[1])
        parts[1],guards=re.subn(r'\s*if \(object_type == 0\) \{ continue; \}', '',parts[1])
        if n!=17 or guards!=1:raise ValueError('Baseline variant recipe no longer matches its reviewed source')
    source = '\n'.join(parts)
    program = author_program(source, [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
        evidence={'kind': 'reviewed-source-bound-game-specialization',
                  'upstream': 'https://github.com/sikthehedgehog/miniplanets',
                  'upstream_commit': SOURCE_COMMIT, 'license': MINIPLANETS_LICENSE,
                  'authoring_units': {path.name: hashlib.sha256(captured[path]).hexdigest() for path in units},
                  'variant':variant,
                  'entry': 'game_frame', 'boot': 'game_boot',
                  'environment': {'hv16': 'captured original HV samples or declared NES clock adapter',
                                  'sound_busy': 'logical original Sona stream status, independent of NES voice allocation'},
                  'limits': ['reviewed source translation, not an arbitrary 68000 lifter',
                             'presentation fades and publisher logo use a target adapter',
                             'finite native comparisons do not establish whole-game equivalence']})
    stages = []
    for index in range(55):
        h = STAGE_HEADERS + index * 8
        start = int.from_bytes(rom[h:h + 4], 'big')
        if not 0 <= start <= len(rom) - 257:
            raise ValueError('Stage pointer outside qualified image')
        end = start + 256
        population = 0
        while rom[end] != 255:
            if population == 48 or end + 4 > len(rom):
                raise ValueError('Stage object list exceeds its contract')
            population += 1
            end += 4
        stages.append({'index': index, 'name_bcd': rom[h + 4], 'music': rom[h + 5],
                       'map_offset': start, 'map_sha256': hashlib.sha256(rom[start:start + 256]).hexdigest(),
                       'object_count': population,
                       'objects_sha256': hashlib.sha256(rom[start + 256:end]).hexdigest()})
    return {'program': program, 'scene': {'format': 'fdisbull-nes-globe-1',
             'stage_count': len(stages), 'stages': stages,
             'projection': 'original source depth ordering and camera-dependent LUT; nearest 8-pixel background grid',
             'terrain_refresh': 'coherent double-buffered nametable',
             'audio': 'complete original streams with NES hardware arrangement'},
            'provenance': program['evidence']}


def mix_full_game_variants(rom, procedures):
    """Select reviewed baseline/efficient bodies through the same procedure ABI.

    This is a finite tested-domain alternative, not a proof for arbitrary
    source rewrites. Immutable regions, declarations, entry and call ordering
    stay fixed; only a named procedure's qualified body can be selected.
    """
    if not isinstance(procedures,dict) or len(procedures)>512:
        raise ValueError('Expected a bounded procedure-to-variant mapping')
    result=lift_full_game(rom)
    baseline=lift_full_game(rom,variant='baseline')['program']
    alternatives={node['decl']['name']:node for node in baseline['tree']['ext'] if node['node']=='FuncDef'}
    if any(name not in alternatives or choice not in ('baseline','efficient') for name,choice in procedures.items()):
        raise ValueError('Unknown game procedure or unqualified body variant')
    for i,node in enumerate(result['program']['tree']['ext']):
        if node['node']=='FuncDef' and procedures.get(node['decl']['name'])=='baseline':
            result['program']['tree']['ext'][i]=copy.deepcopy(alternatives[node['decl']['name']])
    result['program']['evidence']['variant']='mixed-qualified'
    result['program']['evidence']['procedure_variants']=dict(procedures)
    return result


def lift_game_path(path, *, output, variant='efficient'):
    """Export replayable game/audio UIL into a new private directory."""
    from .console_udc import _private_directory
    from .game_il import canonical
    from .miniplanets_audio import recover_audio
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size != 524288:
        raise ValueError('Expected the qualified 512KiB Miniplanets REV04 cartridge')
    rom = checked_rom(source.read_bytes())
    result = lift_full_game(rom,variant=variant)
    destination = _private_directory(output)
    temporary = Path(tempfile.mkdtemp(prefix='.game-uil-',dir=destination.parent))
    try:
        program = canonical(result['program']) + b'\n'
        audio = canonical(recover_audio(rom)) + b'\n'
        (temporary/'program.uil.json').write_bytes(program)
        (temporary/'audio.uil.json').write_bytes(audio)
        (temporary/'scene.json').write_text(json.dumps(result['scene'],indent=2)+'\n')
        receipt = {'format':'fdisbull-game-lift-1','profile':'miniplanets-full',
                   'source_sha256':ROM_SHA256,'variant':variant,
                   'program_sha256':hashlib.sha256(canonical(result['program'])).hexdigest(),
                   'program_file_sha256':hashlib.sha256(program).hexdigest(),
                   'audio_sha256':hashlib.sha256(audio).hexdigest(),'stages':55,
                   'output_directory':str(destination),'original_region':'external; supply the same ROM to replay/compile',
                   'claim':'reviewed source-bound specialization; finite comparisons are separate evidence'}
        (temporary/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if source.read_bytes()!=rom:raise ValueError('Original cartridge changed during export')
        if destination.exists():raise ValueError('Output appeared during export')
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise
    return receipt


def _slz(raw, offset, *, maximum=65535):
    """Bounded SLZ decoding matching the shipped DecompressSLZ token format."""
    size = int.from_bytes(raw[offset:offset+2], 'big')
    if not 0 < size <= maximum: raise ValueError('Invalid SLZ decoded length')
    pos, output = offset + 2, bytearray()
    while len(output) < size:
        if pos >= len(raw): raise ValueError('Truncated SLZ flags')
        flags, pos = raw[pos], pos + 1
        for bit in range(7, -1, -1):
            if len(output) == size: break
            if flags & (1 << bit):
                if pos + 2 > len(raw): raise ValueError('Truncated SLZ match')
                token = int.from_bytes(raw[pos:pos+2], 'big');pos += 2
                distance, count = (token >> 4) + 3, (token & 15) + 3
                if distance > len(output) or len(output) + count > size:
                    raise ValueError('Invalid SLZ back reference')
                for _ in range(count): output.append(output[-distance])
            else:
                if pos >= len(raw): raise ValueError('Truncated SLZ literal')
                output.append(raw[pos]);pos += 1
    return bytes(output)


def _chr_tile(tile):
    result = bytearray(16)
    for j, value in enumerate(tile):
        for k, pixel in enumerate((value >> 4, value & 15)):
            x, y = (j * 2 + k) % 8, (j * 2 + k) // 8
            color = 0 if pixel == 0 else 1 + (pixel - 1) // 5
            result[y] |= (color & 1) << (7 - x)
            result[y + 8] |= (color >> 1) << (7 - x)
    return bytes(result)


def globe_assets(rom):
    """Build private adapted CHR/projection data; retain no game bytes in Git."""
    checked_rom(rom)
    globe = _slz(rom, 0x5FE8)
    belt = _slz(rom, 0x9D60)
    grass_vram = 0x343
    sources = []
    for animation in range(32):
      for tile_type in range(35):
        for variant in range(9):
            word = int.from_bytes(rom[0xA4CE + tile_type*2:0xA4D0 + tile_type*2], 'big')
            if tile_type == 3 or tile_type >= 23:
                buf, start = rom[0x7960:0x8B60], ((animation >> 3) * 36 + variant * 4) * 32
            elif tile_type == 18:
                buf, start = rom[0x8B60:0x9D60], (((animation >> 2) & 3) * 36 + variant * 4) * 32
            elif 11 <= tile_type <= 14:
                direction_phase = ((-animation if tile_type in (11,13) else animation) & 6) >> 1
                buf, start = belt, (4608 if tile_type in (11,12) else 0) + (direction_phase*36+variant*4)*32
            else:
                buf, start = globe, ((word & 0x7FF) - grass_vram + variant*4) * 32
            if start < 0 or start + 128 > len(buf): raise ValueError('Terrain graphic reference outside decoded atlas')
            # Genesis 2x2 sprite order is column-major; NES plane is row-major.
            sources.extend(_chr_tile(buf[start+q*32:start+(q+1)*32]) for q in (0, 2, 1, 3))
    sources.extend(_chr_tile(globe[offset:offset+32]) for offset in range(504*32,552*32,32))
    reserved = {0, 32, *map(ord, _FONT)}
    available = [x for x in range(256) if x not in reserved]
    frequencies = Counter(sources)
    # Preserve common source patterns. Distance heavily penalizes transparency
    # changes; remaining color/texture loss is measured rather than hidden.
    representatives = sorted(frequencies, key=lambda x: (-frequencies[x], x))[:len(available)]
    index = {tile: available[i] for i, tile in enumerate(representatives)}
    def distance(a, b):
        mask_a = bytes(x | y for x,y in zip(a[:8], a[8:]))
        mask_b = bytes(x | y for x,y in zip(b[:8], b[8:]))
        return (sum((x^y).bit_count() for x,y in zip(mask_a, mask_b))*8
                + sum((x^y).bit_count() for x,y in zip(a,b)))
    losses = []
    mapping = bytearray()
    nearest = {}
    for tile in sources:
        if tile not in nearest:
            nearest[tile] = tile if tile in index else min(representatives, key=lambda candidate: (distance(tile,candidate), candidate))
        chosen = nearest[tile]
        mapping.append(index[chosen]);losses.append(distance(tile, chosen))
    chr_data = bytearray(8192)
    for tile, number in index.items(): chr_data[number*16:number*16+16] = tile
    for char, rows in _FONT.items():
        chr_data[ord(char)*16:ord(char)*16+8] = bytes((0, *(row << 1 for row in rows)))
    # Authored small sprite silhouettes. Gameplay identity is the original
    # actor ID; this atlas is a deliberately disclosed NES art adaptation.
    icon_rows={
        1:(0x38,0x44,0x44,0x38,0x10,0x1C,0x10,0),
        6:(0x18,0x7E,0x5A,0xFF,0xFF,0x5A,0x7E,0x18),
        7:(0x18,0x7E,0x5A,0xFF,0xFF,0x5A,0x7E,0x18),
        8:(0x18,0x24,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C),
        9:(0x60,0x30,0x18,0x08,0x08,0x3C,0x7E,0),
        10:(0,0x22,0x74,0xFF,0x2E,0x44,0,0),
        11:(0x10,0x30,0x18,0x3C,0x18,0x0C,0x18,0x10),
        24:(0x18,0x3C,0x7E,0xFF,0x7E,0x3C,0x18,0),
        25:(0x18,0x3C,0x18,0x7E,0x5A,0x18,0x24,0x42),
        26:(0,0x18,0x5A,0x3C,0x7E,0x24,0x42,0),
        27:(0,0x7E,0x18,0x3C,0x18,0x3C,0x18,0x7E)}
    for actor in range(32):
        rows = [0x18,0x3C,0x7E,0xDB,0xFF,0x66,0x24,0x42]
        if actor in icon_rows:rows=icon_rows[actor]
        elif 2<=actor<=5:rows=(255,129,189,165,165,189,129,255)
        elif 12<=actor<=15:rows=(0x3C,0x7E,0xDB,0xFF,0xFF,0xDB,0x7E,0x3C)
        elif 16<=actor<=19:rows=(0x3C,0x7E,0xBD,0xFF,0xE7,0x7E,0x3C,0x18)
        elif 20<=actor<=23:rows=(0x08,0x18,0x38,0x6C,0x7E,0xFF,0x7E,0x3C)
        elif actor == 0: rows = [0x3C,0x7E,0xDB,0xFF,0x7E,0x3C,0x66,0x42]
        base = 4096 + actor*16
        chr_data[base:base+8] = bytes(rows)
        chr_data[base+8:base+16] = bytes((x & 0x66 for x in rows))
    for first,small in ((32,0),(36,2)):
        for quadrant in range(4):
            result=bytearray(16)
            for y in range(8):
                for x in range(8):
                    sx=((quadrant&1)*8+x)//2
                    sy=((quadrant>>1)*8+y)//2
                    at=4096+small*16
                    color=((chr_data[at+sy]>>(7-sx))&1)|(((chr_data[at+8+sy]>>(7-sx))&1)<<1)
                    result[y]|=(color&1)<<(7-x)
                    result[y+8]|=(color>>1)<<(7-x)
            start=4096+(first+quadrant)*16
            chr_data[start:start+16]=result
    projected = bytearray()
    source = rom[GLOBE_LUT:GLOBE_LUT+65536]
    for phase in range(256):
        for sprite in range(64):
            at = phase*64 + sprite
            x = source[at];x = x if x < 128 else x-256
            y = source[16384+at];y = y if y < 128 else y-256
            # screen center128,152; 8px quantization, error <=4px peraxis.
            column = (120 + x + 4)//8 - 8
            row = (144 + y + 4)//8 - 12
            if not 0 <= column < 15 or not 0 <= row < 15:
                raise ValueError('Projection outside the 16x16 NES globe viewport')
            projected.extend((row*16+column, source[32768+at], source[49152+at], 0))
    return {'chr': bytes(chr_data), 'terrain_ids': bytes(mapping[:1260]+mapping[-48:]),
            'terrain_frames': [bytes(mapping[i*1260:(i+1)*1260]) for i in range(32)],
            'ending_ids': bytes(mapping[-48:]),
            'projection': bytes(projected), 'objects': rom[OBJECT_LUT:OBJECT_LUT+65536],
            'rafts': rom[RAFT_LUT:RAFT_LUT+65536], 'ending': rom[ENDING_LUT:ENDING_LUT+12288],
            'metrics': {'source_terrain_chr_count': len(sources), 'unique_adapted_patterns': len(frequencies),
                        'resident_terrain_patterns': len(representatives),
                        'approximated_pattern_instances': sum(x != 0 for x in losses),
                        'weighted_pattern_distance_total': sum(losses),
                        'projection_axis_error_max_pixels': 4,
                        'sprite_art': 'authored NES icons; original actor identities and positions retained'}}
