"""Read-only, bounded spatial projection of a shared Shadowrun field state.

The caller supplies a fresh snapshot from the authoritative runtime. Terrain is
an investigator observation, not a visibility or walkability map. No game
state or source bytes are retained by this module.
"""
from .shadowrun_world import SCENE_COUNT, SOURCE_SHA256

WIDTH, HEIGHT, CELL_SIZE = 64, 44, 32


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid ' + name)
    return value


def validate_snapshot(state):
    if not isinstance(state, dict) or state.get('source_sha256') != SOURCE_SHA256:
        raise ValueError('Snapshot source identity mismatch')
    _integer(state.get('scene_id'), 0, SCENE_COUNT - 1, 'scene ID')
    if not isinstance(state.get('revision'), str) or not state['revision']:
        raise ValueError('A current runtime revision is required')
    for name in ('player_x', 'player_y', 'camera_x', 'camera_y'):
        _integer(state.get(name), 0, 65535, name)
    terrain = state.get('terrain')
    if not isinstance(terrain, bytes) or len(terrain) != WIDTH * HEIGHT:
        raise ValueError('Expected the complete 2816-byte captured terrain map')
    bounds = state.get('bounds')
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 4:
        raise ValueError('Expected field bounds')
    x0, x1, y0, y1 = (_integer(v, 0, 65535, 'bound') for v in bounds)
    if not x0 < x1 or not y0 < y1 or x1 > WIDTH * CELL_SIZE or y1 > HEIGHT * CELL_SIZE:
        raise ValueError('Invalid or unsupported field bounds')
    x, y = state['player_x'] >> 4, state['player_y'] >> 4
    if not x0 <= x < x1 or not y0 <= y < y1:
        raise ValueError('Player is outside the qualified field bounds')
    return state


def _cell_id(scene_id, x, y):
    return f'shadowrun.scene.{scene_id:02d}.cell.{x:02d}.{y:02d}'


def project_city(state, *, radius_x=8, radius_y=5):
    """Return coarse regions and a local grid; raw terrain requires investigator access.

    Positions and bounds come from the same current snapshot. Bounds are
    half-open in source pixel units. No terrain code is classified as passable.
    """
    state = validate_snapshot(state)
    radius_x = _integer(radius_x, 1, 16, 'horizontal radius')
    radius_y = _integer(radius_y, 1, 12, 'vertical radius')
    scene = state['scene_id']
    px, py = state['player_x'] >> 4, state['player_y'] >> 4
    cx, cy = px // CELL_SIZE, py // CELL_SIZE
    x0, x1, y0, y1 = state['bounds']
    regions = []
    for ry in range(0, HEIGHT, 8):
        for rx in range(0, WIDTH, 8):
            ex, ey = min(rx + 8, WIDTH), min(ry + 8, HEIGHT)
            intersects = rx * CELL_SIZE < x1 and ex * CELL_SIZE > x0 and ry * CELL_SIZE < y1 and ey * CELL_SIZE > y0
            if intersects:
                regions.append({'id': f'shadowrun.scene.{scene:02d}.region.{rx // 8:02d}.{ry // 8:02d}',
                                'cell_bounds': [rx, ex, ry, ey], 'visibility': 'unknown',
                                'contains_player': rx <= cx < ex and ry <= cy < ey})
    actors = []
    for actor in state.get('captured_entities', []):
        actor = dict(actor)
        actor['captured_position'] = {'x': actor['x'], 'y': actor['y']}
        actor['hp_current'] = None
        actor['hp_current_status'] = 'unknown'
        address = actor.get('slot_address')
        hp = state.get('model_actor_hp')
        if (type(address) is int and 0xff0400 <= address <= 0xff0a00 and
                (address - 0xff0400) % 0x100 == 0 and isinstance(hp, list) and len(hp) == 7):
            value = hp[(address - 0xff0400) // 0x100]
            if type(value) is int and 0 <= value <= 255:
                actor['hp_current'] = value
                actor['hp_current_status'] = 'shared model'
        if actor.get('slot_address') == 0xff0100:
            actor['x'], actor['y'] = state['player_x'], state['player_y']
            actor['current_position'] = 'shared model'
        ax, ay = actor['x'] >> 4, actor['y'] >> 4
        actor['inside_camera_rectangle'] = (state['camera_x'] >> 4 <= ax < (state['camera_x'] >> 4) + 256 and
                                            state['camera_y'] >> 4 <= ay < (state['camera_y'] >> 4) + 224)
        actor['visibility'] = 'unknown'
        actors.append(actor)
    cells = []
    for y in range(max(0, cy - radius_y), min(HEIGHT, cy + radius_y + 1)):
        for x in range(max(0, cx - radius_x), min(WIDTH, cx + radius_x + 1)):
            cells.append({'id': _cell_id(scene, x, y), 'x': x, 'y': y,
                          'terrain_code': state['terrain'][y * WIDTH + x],
                          'visibility': 'unknown', 'walkability': 'unknown',
                          'contains_player': x == cx and y == cy,
                          'captured_entity_ids': [a['id'] for a in actors if a['x'] >> 9 == x and a['y'] >> 9 == y]})
    return {'format': 'fdisbull-shadowrun-city-1', 'source_sha256': SOURCE_SHA256,
            'scene_id': scene, 'scene_key': f'shadowrun.scene.{scene:02d}',
            'revision': state['revision'], 'observation_profile': 'investigator',
            'units': {'position': '1/16 source pixel', 'bounds': 'source pixels',
                      'cell': '32 by 32 source pixels'},
            'player': {'x': state['player_x'], 'y': state['player_y'], 'cell': [cx, cy]},
            'camera': {'x': state['camera_x'], 'y': state['camera_y'],
                       'graphics_coverage': 'unknown'},
            'field_bounds': list(state['bounds']), 'terrain_grid': [WIDTH, HEIGHT],
            'regions': regions, 'local_cells': cells, 'captured_entities': actors,
            'coverage': {'terrain': 'captured runtime map', 'visibility': 'unknown',
                         'cross_scene_connections': 'unknown', 'graphics': 'unknown',
                         'walkability': 'unknown', 'partial': True}}


def describe_scene_source(rom, scene_id):
    """Report source table provenance without exporting ROM or decoded bytes."""
    from .shadowrun_world import read_scene, decode_scene_stream
    scene = read_scene(rom, scene_id)
    result = {'scene_id': scene.scene_id, 'profile_address': scene.profile,
              'collision_records': len(scene.collision),
              'compressed_stream_selected': bool(scene.stream_source & 1),
              'stream_decoded_bytes': None,
              'qualification': 'static source candidate; runtime loading is not established'}
    if scene.stream_source & 1:
        decoded, _ = decode_scene_stream(rom, scene_id)
        result['stream_decoded_bytes'] = len(decoded)
    return result


def terrain_symbols(state):
    """Return 64x44 numeric category symbols, not collision or visibility.

    Codes: 0 outside field bounds, 1 raw 0, 2 raw 127, 3 raw 1..126,
    4 raw 128..255. A cell crossing a bound is kept as its raw category;
    individual coordinates still require the runtime's exact bounds check.
    """
    state = validate_snapshot(state)
    x0, x1, y0, y1 = state['bounds']
    symbols = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if (x * CELL_SIZE >= x1 or (x + 1) * CELL_SIZE <= x0 or
                    y * CELL_SIZE >= y1 or (y + 1) * CELL_SIZE <= y0):
                symbols.append(0)
                continue
            value = state['terrain'][y * WIDTH + x]
            symbols.append(1 if value == 0 else 2 if value == 127 else 3 if value < 127 else 4)
    return bytes(symbols)


def render_city_text(state, *, radius_x=8, radius_y=5):
    """Render a compact investigator grid, preserving opaque terrain codes."""
    state = validate_snapshot(state)
    city = project_city(state, radius_x=radius_x, radius_y=radius_y)
    symbols = terrain_symbols(state)
    lines = [f"Scene {city['scene_id']} — investigator terrain categories, visibility unknown",
             'Legend: @ player; ? outside field bounds; . raw 0; # raw 127; + raw 1..126; ! raw 128..255.',
             'Symbols are not walkability or visible objects. Coordinates are terrain cells.']
    lookup = '? .#+!'.replace(' ', '')
    rows = {}
    for cell in city['local_cells']:
        rows.setdefault(cell['y'], []).append(cell)
    for y, row in rows.items():
        values = ''.join('@' if c['contains_player'] else lookup[symbols[y * WIDTH + c['x']]] for c in row)
        lines.append(f"{y:02d} {row[0]['x']:02d} {values} {row[-1]['x']:02d}")
    return '\n'.join(lines)


def render_region_text(state):
    """Coarse scene coverage; does not imply traversability or line of sight."""
    city = project_city(state, radius_x=1, radius_y=1)
    index = {tuple(r['cell_bounds'][i] // 8 for i in (0, 2)): r for r in city['regions']}
    lines = ['Scene regions (8 by 8 terrain cells; y increases downward):',
             '@ player region, r intersects field bounds, ? outside field bounds; visibility unknown.']
    for y in range(6):
        lines.append(f"{y:02d} " + ''.join('@' if index.get((x, y), {}).get('contains_player')
                                            else 'r' if (x, y) in index else '?' for x in range(8)))
    return '\n'.join(lines)


def captured_entities(rom, snapshot_path):
    """Read qualified capture slots; no AI, persistence or current visibility claim."""
    import hashlib
    from .shadowrun_replay import _source_capture
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256:
        raise ValueError('Entity extraction requires the exact reviewed source')
    spans = ((0x11dd6, 0x11e04, 'cf72d26e32b3399f58d9eca74ce931c7d5d10e0c63887ebd33d75711180609de'),
             (0x287a, 0x28a2, '582f06bc632097f67604b52469eed68265f0de906eb9ec83b95c99acdf75168a'),
             (0x55a62, 0x55a9e, '19d3d2dbc395843d25d242e246a1f648531674211bdfb3d71ce717fab9f80a0f'))
    if any(hashlib.sha256(rom[a:b]).hexdigest() != digest for a, b, digest in spans):
        raise ValueError('Entity source qualification changed')
    identity, arrays, _ = _source_capture(snapshot_path, SOURCE_SHA256)
    if identity['frame'] != 5999 or identity['capture_json_sha256'] != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':
        raise ValueError('Expected the reviewed scene-2 prepared capture')
    raw = arrays['ram']
    memory = bytes(raw[i ^ 1] for i in range(len(raw)))
    def word(offset): return int.from_bytes(memory[offset:offset+2], 'big')
    entities = []
    for slot in range(1, 17):
        offset = slot * 0x100
        flags = memory[offset + 0x10]
        if not flags & 1:
            continue
        entities.append({'id': f'shadowrun.capture.5999.actor.ff{offset:04x}',
                         'slot_address': 0xff0000 + offset,
                         'x': word(offset), 'y': word(offset + 4),
                         'kind': word(offset + 0x0e), 'flags': flags,
                         'hp_byte_4c': memory[offset + 0x4c],
                         'source': 'captured frame 5999', 'current_position': 'unknown',
                         'visibility': 'unknown', 'kind_meaning': 'unknown' if slot != 1 else 'player candidate'})
    return {'format': 'fdisbull-shadowrun-captured-entities-1', 'source_sha256': SOURCE_SHA256,
            'capture_frame': 5999, 'capture_receipt_sha256': identity['capture_json_sha256'],
            'entities': entities,
            'qualification': 'slot activity and health-byte consumers source checked; captured positions are not live AI',
            'source_spans': [{'start': a, 'end': b, 'sha256': digest} for a,b,digest in spans]}
