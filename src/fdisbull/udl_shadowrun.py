"""Source-bound Shadowrun Genesis procedural slices, not a whole-game lift.

The first recovered component is the input-state part of the original player
one polling routine. Hardware reads, flags, CPU registers, movement and scene
behavior remain outside this procedure's contract.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from .game_il import author_program

ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
ROM_SIZE = 2097152
INPUT_START = 0x1960
INPUT_END = 0x199a
INPUT_SHA256 = '28d2ee0a50f86fd5e3fd5f3b11cd0a6f9e7459434d9881d63531214b254837b2'
TABLE_START = 0x19d2
TABLE_END = 0x19f2
TABLE_SHA256 = '8300f35e1274c5c98fb26cac020a8d82548cecae9208cf2920c48430cce44197'
HEADING_START = 0xb530
HEADING_END = 0xb56a
HEADING_SHA256 = '43765f4787c2cdc4757121590fa7466731d3d2dae73f65ec77c34c9589114994'
SOURCE = Path(__file__).with_name('game_sources') / 'shadowrun_input.c'


def checked_rom(rom: bytes) -> bytes:
    if not isinstance(rom, bytes) or len(rom) != ROM_SIZE or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Expected the exact reviewed Shadowrun Genesis cartridge')
    return rom


def lift_input(rom: bytes) -> dict:
    """Return one typed, source-bound input-state procedure and its scope.

    The caller supplies the normalized byte returned by the original hardware
    reader. The ROM table stays in a hash-bound external region. No actual
    physical controller, timing, condition-code or register state is modeled.
    """
    checked_rom(rom)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    if digest(rom[INPUT_START:INPUT_END]) != INPUT_SHA256 or digest(rom[TABLE_START:TABLE_END]) != TABLE_SHA256:
        raise ValueError('Reviewed Shadowrun input code or table differs')
    source = SOURCE.read_bytes()
    evidence = {'kind': 'reviewed-source-bound-procedural-slice',
                'source_sha256': ROM_SHA256,
                'code_range': [INPUT_START, INPUT_END], 'code_sha256': INPUT_SHA256,
                'table_range': [TABLE_START, TABLE_END], 'table_sha256': TABLE_SHA256,
                'authoring_sha256': digest(source),
                'inputs': ['normalized controller byte', 'previous held word'],
                'outputs': ['held word', 'newly pressed and held word', 'direction angle'],
                'source_ram': {'held': 0xffdd20, 'sample': 0xffdd22, 'angle': 0xffdd04},
                'excluded': ['hardware controller read', 'CPU registers and flags',
                             'input scheduling', 'movement', 'collision', 'interaction',
                             'graphics', 'audio', 'natural reachability'],
                'claim': 'manually reviewed bounded translation; native comparisons are separate'}
    program = author_program(source.decode('utf-8'),
                             [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
                             evidence=evidence)
    if SOURCE.read_bytes() != source:
        raise ValueError('Shadowrun input source changed during lifting')
    return program

# Four authored NES palettes in index/RGB order. Color matching uses these
# reference RGB approximations; an NES core or display may render them
# differently. They are target palette choices, not source graphics.
_NES_PALETTES = (
    ((0x0f, (0, 0, 0)), (0x2d, (60, 60, 60)), (0x00, (84, 84, 84)), (0x10, (152, 152, 152))),
    ((0x0f, (0, 0, 0)), (0x06, (80, 28, 24)), (0x16, (152, 76, 40)), (0x27, (236, 160, 96))),
    ((0x0f, (0, 0, 0)), (0x0c, (0, 56, 80)), (0x1c, (0, 116, 152)), (0x2c, (104, 192, 236))),
    ((0x0f, (0, 0, 0)), (0x09, (0, 68, 0)), (0x19, (40, 148, 40)), (0x29, (152, 224, 128))),
)


def project_observed_frame(rom: bytes, image_png: bytes) -> dict:
    """Derive an NES background from a caller-supplied original-core frame.

    The left 256 by 224 pixels of a 320 by 224 screenshot are converted to
    four 16x16-cell palettes and at most 256 native 2bpp tile patterns. The
    supplied screenshot's association with the original core and controller
    sequence is a caller-provided observation, not proved by this function.
    Sprites and all animated content are frozen into the captured background;
    the right edge and any off-screen scene are omitted. Returned image assets
    contain source-derived pixels and must remain outside source control.
    """
    from io import BytesIO
    from PIL import Image

    checked_rom(rom)
    if not isinstance(image_png, bytes) or len(image_png) > 4_000_000:
        raise ValueError('Expected a bounded PNG screenshot')
    with Image.open(BytesIO(image_png)) as loaded:
        if loaded.format != 'PNG' or loaded.size != (320, 224):
            raise ValueError('Expected a 320x224 PNG screenshot')
        pixels = loaded.convert('RGB').crop((0, 0, 256, 224))
    raster = pixels.load()
    indices = bytearray(256 * 224)
    cells = []
    for by in range(0, 224, 16):
        for bx in range(0, 256, 16):
            colors = [raster[x, y] for y in range(by, by + 16) for x in range(bx, bx + 16)]
            candidates = []
            for palette in _NES_PALETTES:
                values = []
                error = 0
                for color in colors:
                    distances = [sum((color[j] - entry[1][j]) ** 2 for j in range(3)) for entry in palette]
                    value = min(range(4), key=distances.__getitem__)
                    values.append(value)
                    error += distances[value]
                candidates.append((error, values))
            selected = min(range(4), key=lambda i: candidates[i][0])
            cells.append(selected)
            for i, value in enumerate(candidates[selected][1]):
                indices[(by + i // 16) * 256 + bx + i % 16] = value
    # Tile zero is blank so the two unpopulated nametable rows stay blank.
    patterns = [bytes(16)]
    by_pattern = {patterns[0]: 0}
    names = bytearray(32 * 30)
    for y in range(28):
        for x in range(32):
            tile = bytearray(16)
            for row in range(8):
                for col in range(8):
                    value = indices[(y * 8 + row) * 256 + x * 8 + col]
                    tile[row] |= (value & 1) << (7 - col)
                    tile[row + 8] |= ((value >> 1) & 1) << (7 - col)
            key = bytes(tile)
            if key not in by_pattern:
                if len(patterns) >= 256:
                    raise ValueError('Observed scene exceeds the 256-tile NES background budget')
                by_pattern[key] = len(patterns)
                patterns.append(key)
            names[y * 32 + x] = by_pattern[key]
    # Eight-by-eight attribute bytes each describe four 16x16-cell palettes.
    attributes = bytearray(64)
    for y in range(14):
        for x in range(16):
            attributes[(y // 2) * 8 + x // 2] |= cells[y * 16 + x] << ((y % 2) * 4 + (x % 2) * 2)
    chr_data = b''.join(patterns).ljust(4096, b'\0')
    palette_data = bytes(c[0] for p in _NES_PALETTES for c in p)
    return {'chr': chr_data, 'nametable': bytes(names), 'attributes': bytes(attributes),
            'palette': palette_data,
            'evidence': {'source_rom_sha256': ROM_SHA256,
                         'observed_png_sha256': hashlib.sha256(image_png).hexdigest(),
                         'projection': 'left 256x224 crop; frozen observed frame; four 16x16-cell NES palettes',
                         'unique_tiles': len(patterns),
                         'limits': ['caller-declared source observation', 'not ROM graphic extraction',
                                    'right 64 columns omitted', 'sprites and animation frozen',
                                    'target RGB palette is approximate', 'not a gameplay model']}}


def lift_heading(rom: bytes) -> dict:
    """Lift the reviewed field-record heading approach; no position effects."""
    checked_rom(rom)
    start, end = HEADING_START, HEADING_END
    if hashlib.sha256(rom[start:end]).hexdigest() != HEADING_SHA256:
        raise ValueError('Reviewed Shadowrun heading routine differs')
    path = SOURCE.with_name('shadowrun_heading.c')
    source = path.read_bytes()
    evidence = {'kind': 'reviewed-source-bound-procedural-slice',
                'source_sha256': ROM_SHA256, 'code_range': [start, end],
                'code_sha256': HEADING_SHA256, 'authoring_sha256': hashlib.sha256(source).hexdigest(),
                'source_record_offsets': {'heading': 0x2e, 'target': 0x34},
                'excluded': ['CPU registers and flags', 'input scheduling', 'position updates',
                             'collision', 'interaction', 'graphics', 'audio', 'natural reachability'],
                'claim': 'manually reviewed bounded heading translation; native comparisons are separate'}
    program = author_program(source.decode('utf-8'), evidence=evidence)
    if path.read_bytes() != source:
        raise ValueError('Shadowrun heading source changed during lifting')
    return program


def lift_move_proposal(rom: bytes) -> dict:
    """Lift exactly the field step before the original collision call."""
    checked_rom(rom)
    spans = [(0xbabc, 0xbae8, '8391dd98e14cf052cc31b2125336600e9914ed0acc07008e401aa347f98a7e2f'),
             (0xb77e, 0xb79a, '1a608a5cb6d91aebb71cf29d3f4af077c831d8e224f7513bb021448ece51d895'),
             (0xc002, 0xc022, '52c0f37852ae62bd12fcc0903e87b014ad809dc2be76d9ca1d4d65fbdbda579e')]
    if any(hashlib.sha256(rom[a:b]).hexdigest() != h for a, b, h in spans):
        raise ValueError('Reviewed Shadowrun movement code or vectors differ')
    path = SOURCE.with_name('shadowrun_move.c')
    source = path.read_bytes()
    evidence = {'kind': 'reviewed-source-bound-procedural-slice',
                'source_sha256': ROM_SHA256,
                'source_spans': [{'range': [a, b], 'sha256': h} for a, b, h in spans],
                'authoring_sha256': hashlib.sha256(source).hexdigest(),
                'source_record_offsets': {'x': 0, 'y': 4, 'heading': 0x2e,
                                          'record_offset': 8, 'step_timer': 0xca},
                'scope': 'pre-collision tentative movement only',
                'excluded': ['collision', 'position commit', 'events', 'interaction',
                             'CPU flags and stack', 'hardware timing', 'natural reachability'],
                'claim': 'manually reviewed bounded translation; native comparisons are separate'}
    program = author_program(source.decode('utf-8'),
                             [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
                             evidence=evidence)
    if path.read_bytes() != source:
        raise ValueError('Shadowrun movement source changed during lifting')
    return program


def lift_raw_terrain_probe(rom: bytes) -> dict:
    """Lift bounded 2816-byte-map sampling, before collision/event resolution."""
    checked_rom(rom)
    start, end = 0xe8a0, 0xe9cc
    digest = 'b6eca8df0c9ab6463f1240c0901a2cba9db998537f085b581b1c205bc6a8c091'
    if hashlib.sha256(rom[start:end]).hexdigest() != digest:
        raise ValueError('Reviewed Shadowrun terrain probe differs')
    path = SOURCE.with_name('shadowrun_collision.c')
    source = path.read_bytes()
    evidence = {'kind': 'reviewed-source-bound-procedural-slice',
                'source_sha256': ROM_SHA256, 'code_range': [start, end], 'code_sha256': digest,
                'authoring_sha256': hashlib.sha256(source).hexdigest(),
                'inputs': ['pixel coordinates in source D5/D6', 'source object flags', '2816-byte work RAM map'],
                'scope': 'one- or four-corner raw terrain sampling before collision/event resolution',
                'assumptions': ['all computed 16-bit map offsets are below 2816',
                                'map is the caller-provided captured mutable RAM, not a ROM asset'],
                'excluded': ['rectangle collisions', 'movement acceptance and position commit',
                             'event dispatch', 'interaction', 'CPU flags and non-result registers',
                             'hardware timing', 'natural reachability'],
                'claim': 'manually reviewed bounded terrain translation; native comparisons are separate'}
    program = author_program(source.decode('utf-8'), evidence=evidence)
    if path.read_bytes() != source:
        raise ValueError('Shadowrun terrain source changed during lifting')
    return program


def lift_collision_check(rom: bytes) -> dict:
    """Lift scene collision status including bounds, map, rectangles and slopes.

    The mutable map and bounds remain explicit inputs; the caller must supply
    in-range map offsets and an original-ROM rectangle table base. Negative
    event return codes are preserved but not dispatched here.
    """
    checked_rom(rom)
    spans = [(0xe7c8,0xe8a0,'1e81a9357b452c6f9626f230ee31bf382d524f3d734082bb35f9cd9ba4a6fa9e'),
             (0xe8a0,0xe9cc,'b6eca8df0c9ab6463f1240c0901a2cba9db998537f085b581b1c205bc6a8c091'),
             (0xe9ee,0xeb4e,'3949e36cf43abfbacbd66c347a0e55950caeec082b7ae59c230eea18dd949544'),
             (0xedfa,0xee10,'661274e46e2e8e8d7a488ac7057f3aa2cb2d3ff4a28383f757045bf7b1581c53')]
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in spans):
        raise ValueError('Reviewed Shadowrun collision source differs')
    files = [SOURCE.with_name('shadowrun_collision.c'), SOURCE.with_name('shadowrun_collision_resolve.c')]
    chunks = [p.read_bytes() for p in files]
    evidence = {'kind':'reviewed-source-bound-procedural-slice','source_sha256':ROM_SHA256,
                'source_spans':[{'range':[a,b],'sha256':h} for a,b,h in spans],
                'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
                'assumptions':['all map offsets below 2816','rectangle table is inside the source ROM'],
                'scope':'field collision result and documented RAM scratch outputs',
                'excluded':['movement commit and fallback paths','negative event dispatch',
                            'interaction','CPU registers and flags','natural reachability'],
                'claim':'manually reviewed bounded collision translation; native comparisons are separate'}
    program = author_program('\n'.join(x.decode('utf-8') for x in chunks),
                             [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if any(p.read_bytes()!=x for p,x in zip(files,chunks)):
        raise ValueError('Shadowrun collision source changed during lifting')
    return program


def lift_clear_walk(rom: bytes) -> dict:
    """Lift the direct zero-collision walk branch, refusing other outcomes."""
    checked_rom(rom)
    proposal = lift_move_proposal(rom)
    collision = lift_collision_check(rom)
    base = SOURCE.parent
    paths = [base/'shadowrun_move.c', base/'shadowrun_collision.c',
             base/'shadowrun_collision_resolve.c', base/'shadowrun_walk.c']
    parts = [p.read_bytes() for p in paths]
    # These are authored component units with identical cc65-width aliases.
    # Retain each typedef exactly once in the combined typed translation unit.
    seen = set()
    units = []
    for part in parts:
        lines = []
        for line in part.decode('utf-8').splitlines():
            if line.startswith('typedef '):
                if line in seen: continue
                seen.add(line)
            lines.append(line)
        units.append('\n'.join(lines))
    evidence = {'kind':'reviewed-source-bound-procedural-slice','source_sha256':ROM_SHA256,
                'parts':[proposal['evidence'],collision['evidence']],
                'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in parts],
                'scope':'direct field-record movement only when collision status is exactly zero',
                'unsupported':'nonzero collision status: fallback and event handling are not modeled',
                'excluded':['blocked movement','event dispatch','interaction','animation',
                            'CPU registers and flags','hardware timing','natural reachability']}
    program = author_program('\n'.join(units),
                             [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if any(p.read_bytes()!=x for p,x in zip(paths,parts)):
        raise ValueError('Shadowrun clear-walk source changed during lifting')
    return program


def project_vdp_scene(rom: bytes, scene, *, actor_sat_index: int) -> dict:
    """Project a decoded, caller-identified sprite and independent background.

    The VDP decoder's 320x224 background is cropped at x=256. Sprite pixels
    are kept transparent and emitted as NES 8x8 OAM tiles rather than baked
    into the background. The caller must establish the selected SAT entry's
    identity and the association of this snapshot with the source cartridge.
    This finite visual projection does not lift actor movement or interactions.
    """
    from io import BytesIO
    from PIL import Image
    from .shadowrun_scene_assets import SceneAssets

    checked_rom(rom)
    if not isinstance(scene, SceneAssets) or (scene.width, scene.height) != (320, 224):
        raise ValueError('Expected a decoded 320x224 Genesis VDP scene')
    matches = [sprite for sprite in scene.sprites if sprite.sat_index == actor_sat_index]
    if len(matches) != 1:
        raise ValueError('Expected one explicitly selected SAT sprite')
    actor = matches[0]
    if (actor.width % 8 or actor.height % 8 or actor.width * actor.height != len(actor.pixels)
            or actor.width // 8 * (actor.height // 8) > 64):
        raise ValueError('Unsupported actor sprite geometry')
    if any(actor.effects):
        raise ValueError('Actor uses unmodeled Genesis sprite effects')
    if not (0 <= actor.x < 256 and 1 <= actor.y < 224
            and actor.x + actor.width <= 256 and actor.y + actor.height <= 224):
        raise ValueError('Selected actor is outside the cropped NES viewport')
    image = Image.new('RGB', (320, 224))
    image.putdata([scene.palette_rgb[value] for value in scene.background])
    encoded = BytesIO()
    image.save(encoded, format='PNG')
    output = project_observed_frame(rom, encoded.getvalue())
    candidates = []
    for palette in _NES_PALETTES:
        error = 0
        indices = []
        for value in actor.pixels:
            if value == 0:
                indices.append(0)
                continue
            color = scene.palette_rgb[actor.palette * 16 + value]
            distances = [sum((color[j] - entry[1][j]) ** 2 for j in range(3)) for entry in palette]
            choice = min((1, 2, 3), key=distances.__getitem__)
            indices.append(choice)
            error += distances[choice]
        candidates.append((error, indices))
    selected = min(range(4), key=lambda i: candidates[i][0])
    indices = candidates[selected][1]
    tiles = []
    oam = bytearray()
    for y in range(0, actor.height, 8):
        for x in range(0, actor.width, 8):
            pattern = bytearray(16)
            for row in range(8):
                for col in range(8):
                    value = indices[(y + row) * actor.width + x + col]
                    pattern[row] |= (value & 1) << (7 - col)
                    pattern[row + 8] |= ((value >> 1) & 1) << (7 - col)
            tiles.append(bytes(pattern))
            oam.extend((actor.y + y - 1, len(tiles) - 1, selected, actor.x + x))
    output['sprite_chr'] = b''.join(tiles).ljust(4096, b'\0')
    output['sprite_oam'] = bytes(oam)
    output['sprite_palette'] = bytes(c[0] for p in _NES_PALETTES for c in p)
    output['evidence'].update({'projection':'decoded VDP background crop and separately selected SAT actor',
                               'vdp_input_hashes':dict(scene.input_hashes),
                               'actor_sat_index':actor_sat_index,
                               'actor_origin':[actor.x,actor.y],
                               'actor_size':[actor.width,actor.height],
                               'actor_oam_sprites':len(tiles),
                               'limits':['caller-declared source observation and actor identity',
                                         'right 64 columns omitted', 'target palettes approximate',
                                         'Genesis layer priority approximated',
                                         'sprite animation and movement not modeled',
                                         *scene.limitations]})
    return output


def lift_player_move_proposal(rom: bytes) -> dict:
    """Lift the explicitly guarded BEC2 normal-player pre-collision path."""
    checked_rom(rom)
    spans = [(0xb530,0xb56a,'43765f4787c2cdc4757121590fa7466731d3d2dae73f65ec77c34c9589114994'),
             (0xb574,0xb69a,'03bdfb4cdcb31ec5c1b847917a9b417894bfb4382e6ad32b95bbb8930613c88a'),
             (0xb77e,0xb79a,'1a608a5cb6d91aebb71cf29d3f4af077c831d8e224f7513bb021448ece51d895'),
             (0xbec2,0xbee2,'a64a1cb738e227c85e7aea0cfd96456ddb10d89dd995f370bd3088426fe897f2')]
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in spans):
        raise ValueError('Reviewed Shadowrun player movement path differs')
    path = SOURCE.with_name('shadowrun_player_move.c')
    source = path.read_bytes()
    evidence = {'kind':'reviewed-source-bound-procedural-slice','source_sha256':ROM_SHA256,
                'source_spans':[{'range':[a,b],'sha256':h} for a,b,h in spans],
                'authoring_sha256':hashlib.sha256(source).hexdigest(),
                'scope':'guarded player step before collision using the BEC2 vector table',
                'assumptions':['non-13 object kind','record flags bits 1 and 3 set',
                               'global mode and vector flag clear','equipment bit 5 clear',
                               'nonzero contact word'],
                'unsupported':'all other table-selection branches return supported=0',
                'excluded':['collision','position commit','events','interaction','animation',
                            'CPU flags and stack','hardware timing','full natural reachability'],
                'claim':'manually reviewed bounded translation; native comparisons are separate'}
    program = author_program(source.decode('utf-8'),
                             [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if path.read_bytes()!=source:
        raise ValueError('Shadowrun player movement source changed during lifting')
    return program


def lift_player_clear_walk(rom: bytes) -> dict:
    """Lift guarded BEC2 player movement when the collision status is zero."""
    checked_rom(rom)
    proposal = lift_player_move_proposal(rom)
    collision = lift_collision_check(rom)
    base = SOURCE.parent
    paths = [base/'shadowrun_player_move.c', base/'shadowrun_collision.c',
             base/'shadowrun_collision_resolve.c', base/'shadowrun_player_walk.c']
    parts = [p.read_bytes() for p in paths]
    seen = set()
    units = []
    for part in parts:
        lines = []
        for line in part.decode('utf-8').splitlines():
            if line.startswith('typedef '):
                if line in seen: continue
                seen.add(line)
            lines.append(line)
        units.append('\n'.join(lines))
    evidence = {'kind':'reviewed-source-bound-procedural-slice','source_sha256':ROM_SHA256,
                'parts':[proposal['evidence'],collision['evidence']],
                'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in parts],
                'scope':'guarded BEC2 player movement only when collision status is zero',
                'unsupported':'all other player table selections and nonzero collision outcomes',
                'excluded':['blocked movement','negative event dispatch','interaction',
                            'animation','CPU registers and flags','hardware timing','natural reachability']}
    program = author_program('\n'.join(units),
                             [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if any(p.read_bytes()!=x for p,x in zip(paths,parts)):
        raise ValueError('Shadowrun player clear-walk source changed during lifting')
    return program


def lift_opening_walk(rom: bytes) -> dict:
    """Compose input and guarded direct walk; unknown action paths refuse.

    The direction-to-target selector is lifted as a bounded source procedure.
    The timing/order of the composed calls remains an observed route. Animation,
    camera, negative collision events, inventory, audio and actions remain outside.
    """
    checked_rom(rom)
    input_program = lift_input(rom)
    walk_program = lift_player_clear_walk(rom)
    direction_program = lift_direction_select(rom)
    fallback_spans = [(0xb442,0xb48c,'381377c34d185f7e8a7dee414114f4b89541b4e03ab5389750eb6453025b4980'),
                      (0xb732,0xb7b8,'0074c264a9514f2e3c6db2535987c7a0ad124ac239f459018b0b76f9d4629907'),
                      (0xbade,0xbbf6,'7af90810b391dcf863d39bbd38fd02a31a77ae149a289aaeafb5add380a285e7'),
                      (0xc052,0xc062,'077b6cc85fa3f228334ae54b94a0565b899650f4412bbc028fb3beae6d3c142d')]
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in fallback_spans):
        raise ValueError('Reviewed Shadowrun wall fallback source differs')
    base = SOURCE.parent
    paths = [SOURCE, base/'shadowrun_player_move.c', base/'shadowrun_collision.c',
             base/'shadowrun_collision_resolve.c', base/'shadowrun_player_walk.c', base/'shadowrun_direction.c',
             base/'shadowrun_player_fallback.c',
             base/'shadowrun_opening.c']
    parts = [p.read_bytes() for p in paths]
    seen = set()
    units = []
    for part in parts:
        lines = []
        for line in part.decode('utf-8').splitlines():
            if line.startswith('typedef ') or line in ('u16 shadowrun_direction_angle;',
                                                       'u16 shadowrun_player_target_heading;'):
                if line in seen: continue
                seen.add(line)
            lines.append(line)
        units.append('\n'.join(lines))
    evidence = {'kind':'reviewed-source-bound-partial-opening-composition',
                'source_sha256':ROM_SHA256,'components':[input_program['evidence'],direction_program['evidence'],walk_program['evidence']],
                'fallback_spans':[{'range':[a,b],'sha256':h} for a,b,h in fallback_spans],
                'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in parts],
                'scope':'direction input and guarded player movement with wall fallback',
                'assumptions':['composition order observed for one 60-frame Right route',
                               'captured scene map, bounds and player state supplied by caller'],
                'unsupported':['action buttons','initial negative event collision','other player vector selection'],
                'excluded':['event dispatch','interaction','animation','camera','audio','full scene reachability']}
    program = author_program('\n'.join(units),
                             [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if any(p.read_bytes()!=x for p,x in zip(paths,parts)):
        raise ValueError('Shadowrun opening source changed during lifting')
    return program


def lift_direction_select(rom: bytes) -> dict:
    """Lift the source input-angle to player target/callback selector."""
    checked_rom(rom)
    start,end=0xae26,0xae5e
    digest='d5d1d02ee1c850fcebe571ef6fdadba7efbe41ed94b62c769aa1ce6c61f02c3d'
    if hashlib.sha256(rom[start:end]).hexdigest()!=digest:
        raise ValueError('Reviewed Shadowrun direction selector differs')
    path=SOURCE.with_name('shadowrun_direction.c');source=path.read_bytes()
    evidence={'kind':'reviewed-source-bound-procedural-slice','source_sha256':ROM_SHA256,
              'code_range':[start,end],'code_sha256':digest,'authoring_sha256':hashlib.sha256(source).hexdigest(),
              'scope':'input angle to field-record target, callback identity and flag bit',
              'excluded':['upstream input scheduling','callback execution','CPU flags/registers','timing','reachability']}
    program=author_program(source.decode('utf-8'),evidence=evidence)
    if path.read_bytes()!=source:raise ValueError('Shadowrun direction source changed during lifting')
    return program


def project_world_atlas(rom: bytes, rgb: bytes, coverage: bytes, conflicts: bytes, *,
                        world_y0: int, max_pattern_merges: int = 0) -> dict:
    """Convert a captured 512x256 or 512x480 world atlas to NES nametables.

    The atlas RGB and coverage are caller-supplied observations. Conflicts are
    refused. Unknown pixels are filled for storage only, and a separately
    returned validity bitset marks camera views with no unknowns.
    The explicit merge budget controls lossy CHR pattern reduction.
    """
    checked_rom(rom)
    height = len(coverage)//512 if isinstance(coverage, bytes) else 0
    if (height not in (256,480) or len(coverage)!=512*height or
            not isinstance(rgb, bytes) or len(rgb)!=512*height*3 or
            not isinstance(conflicts, bytes) or len(conflicts)!=512*height or
            type(world_y0) is not int or not 0<=world_y0<256 or
            type(max_pattern_merges) is not int or not 0<=max_pattern_merges<=64):
        raise ValueError('Invalid bounded captured world atlas')
    if height==480 and world_y0!=0:
        raise ValueError('Unwrapped 512x480 atlas must start at its first row')
    if any(conflicts):
        raise ValueError('Conflicting observed world pixels require review')
    render_height=240 if height==256 else 480
    viewport_height=208 if height==256 else 224
    max_camera_y=32 if height==256 else 255
    pixels = bytearray(512*render_height)
    cells = []
    for by in range(0,render_height,16):
        for bx in range(0,512,16):
            colors=[]
            for y in range(by,by+16):
                for x in range(bx,bx+16):
                    at=((world_y0+y)%height)*512+x
                    colors.append(tuple(rgb[at*3:at*3+3]) if coverage[at] else (0,0,0))
            options=[]
            for palette in _NES_PALETTES:
                values=[];error=0
                for color in colors:
                    distances=[sum((color[j]-entry[1][j])**2 for j in range(3)) for entry in palette]
                    value=min(range(4),key=distances.__getitem__)
                    values.append(value);error+=distances[value]
                options.append((error,values))
            selected=min(range(4),key=lambda i:options[i][0]);cells.append(selected)
            for i,value in enumerate(options[selected][1]):
                pixels[(by+i//16)*512+bx+i%16]=value
    patterns=[bytes(16)];lookup={patterns[0]:0};tiles=[];frequency=[0]
    for y in range(render_height//8):
        for x in range(64):
            tile=bytearray(16)
            for row in range(8):
                for col in range(8):
                    value=pixels[(y*8+row)*512+x*8+col]
                    tile[row]|=(value&1)<<(7-col)
                    tile[row+8]|=((value>>1)&1)<<(7-col)
            key=bytes(tile)
            if key not in lookup:
                lookup[key]=len(patterns);patterns.append(key);frequency.append(0)
            index=lookup[key];tiles.append(index);frequency[index]+=1
    original_patterns=len(patterns)
    if original_patterns-256>max_pattern_merges:
        raise ValueError(f'Atlas requires {original_patterns} patterns; explicit merge budget is insufficient')
    merged_occurrences=0;changed_index_pixels=0
    while len(patterns)>256:
        # Keep tile zero as a stable blank. Prefer the least-used source tile;
        # deterministic ties and two-bit per-pixel distance make the loss auditable.
        victim=min(range(1,len(patterns)),key=lambda i:(frequency[i],i))
        def pixel_distance(a,b):
            return sum((((a[row]^b[row]) | (a[row+8]^b[row+8])).bit_count()) for row in range(8))
        replacement=min((i for i in range(len(patterns)) if i!=victim),
                        key=lambda i:(pixel_distance(patterns[victim],patterns[i]),i))
        distance=pixel_distance(patterns[victim],patterns[replacement])
        merged_occurrences+=frequency[victim];changed_index_pixels+=frequency[victim]*distance
        for j,index in enumerate(tiles):
            if index==victim:tiles[j]=replacement
        frequency[replacement]+=frequency[victim]
        patterns.pop(victim);frequency.pop(victim)
        tiles=[index-1 if index>victim else index for index in tiles]
    count=2 if height==256 else 4
    names=[bytearray(960) for _ in range(count)];attributes=[bytearray(64) for _ in range(count)]
    for y in range(render_height//8):
        for x in range(64):names[(y//30)*2+x//32][(y%30)*32+(x%32)]=tiles[y*64+x]
    for y in range(render_height//16):
        for x in range(32):
            attributes[(y//15)*2+x//16][((y%15)//2)*8+(x%16)//2] |= cells[y*32+x] << (((y%15)%2)*4+((x%2)*2))
    # The bounded view is allowed only when every source pixel was
    # observed. The two dimensions are bounded so target code can fail closed.
    row_missing=[]
    for y in range(render_height):
        at=((world_y0+y)%height)*512
        row=coverage[at:at+512]
        extended=row+row[:255];prefix=[0]
        for value in extended:prefix.append(prefix[-1]+(not value))
        row_missing.append([prefix[x+256]-prefix[x] for x in range(256)])
    valid=bytearray((256*(max_camera_y+1)+7)//8)
    for x in range(256):
        total=sum(row_missing[y][x] for y in range(viewport_height))
        for y in range(max_camera_y+1):
            if total==0:
                bit=y*256+x;valid[bit//8]|=1<<(bit%8)
            if y<max_camera_y:total+=row_missing[y+viewport_height][x]-row_missing[y][x]
    return {'chr':b''.join(patterns).ljust(4096,b'\0'),
            'nametables':tuple(bytes(names[i]+attributes[i]) for i in range(count)),
            'palette':bytes(c[0] for p in _NES_PALETTES for c in p),
            'camera_valid':bytes(valid),
            'evidence':{'source_rom_sha256':ROM_SHA256,'rgb_sha256':hashlib.sha256(rgb).hexdigest(),
                        'coverage_sha256':hashlib.sha256(coverage).hexdigest(),
                        'conflicts_sha256':hashlib.sha256(conflicts).hexdigest(),
                        'world_y0':world_y0,'viewport':[256,viewport_height],
                        'camera_y_max':max_camera_y,'nametable_count':count,
                        'source_patterns':original_patterns,'target_patterns':len(patterns),
                        'merged_patterns':original_patterns-len(patterns),
                        'merged_tile_occurrences':merged_occurrences,
                        'changed_index_pixels':changed_index_pixels,
                        'limits':['caller-declared VDP observation','unknown atlas pixels excluded by camera validity mask',
                                  'target colors and merged tiles approximate',f'cropped {viewport_height}-line viewport',
                                  'no dynamic source layer streaming or animation']}}


def lift_opening_camera(rom: bytes) -> dict:
    """Compose guarded opening movement and the source-bound follow camera."""
    from .game_il import emit_c
    from .shadowrun_camera import lift_camera
    opening = lift_opening_walk(rom)
    camera = lift_camera(rom)
    camera_path = SOURCE.with_name('shadowrun_camera.c')
    frame_path = SOURCE.with_name('shadowrun_opening_camera.c')
    camera_raw = camera_path.read_bytes()
    frame_raw = frame_path.read_bytes()
    # Both reviewed programs use the same cc65-width aliases; retain existing
    # aliases from the emitted opening tree and add only the signed-long alias.
    lines = [line for line in camera_raw.decode('utf-8').splitlines()
             if not line.startswith('typedef ') or line == 'typedef signed long i32;']
    source = emit_c(opening) + '\n' + '\n'.join(lines) + '\n' + frame_raw.decode('utf-8')
    evidence = {'kind':'reviewed-source-bound-partial-opening-with-camera',
                'source_sha256':ROM_SHA256,'components':[opening['evidence'],camera['evidence']],
                'composition_source_sha256':hashlib.sha256(frame_raw).hexdigest(),
                'scope':'guarded field movement and normal follow-camera state',
                'assumptions':['camera runs after current player movement, observed for 60 Right frames',
                               'caller supplies captured scene, camera and player state'],
                'unsupported':['actions','initial negative collision event','other player vector selection',
                               'scripted camera mode 3'],
                'excluded':['interaction','source tile streaming','animation','audio','full opening reachability']}
    program = author_program(source,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if camera_path.read_bytes()!=camera_raw or frame_path.read_bytes()!=frame_raw:
        raise ValueError('Shadowrun opening/camera source changed during lifting')
    return program


def lift_opening_stoker(rom: bytes) -> dict:
    """Compose the bounded player, camera, and guarded Stoker request.

    The activity-dispatch carry and scene variables remain explicit captured
    inputs; the modal input state machine is a target-specific projection.
    """
    from .game_il import emit_c
    from .shadowrun_interaction import lift_stoker_interaction, SOURCE as interaction_source
    opening = lift_opening_camera(rom)
    interaction = lift_stoker_interaction(rom)
    raw = interaction_source.read_bytes()
    composition_path = SOURCE.with_name('shadowrun_opening_stoker.c')
    composition = composition_path.read_bytes()
    interaction_lines = [line for line in raw.decode('utf-8').splitlines()
                         if not line.startswith('typedef ')]
    source = emit_c(opening) + '\n' + '\n'.join(interaction_lines) + '\n' + composition.decode('utf-8')
    evidence = {'kind':'bounded-opening-and-guarded-stoker-composition',
                'source_sha256':ROM_SHA256,
                'components':[opening['evidence'], interaction['evidence']],
                'composition_source_sha256':hashlib.sha256(composition).hexdigest(),
                'assumptions':['captured scene and activity dispatch carry are caller supplied',
                               'A/B/A modal input is a target-specific projection'],
                'unsupported':['other events and actions','activity-dispatch side effects',
                               'original dialogue engine','full opening reachability']}
    program = author_program(source,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence=evidence)
    if interaction_source.read_bytes()!=raw or composition_path.read_bytes()!=composition:
        raise ValueError('Shadowrun opening interaction source changed during lifting')
    return program
