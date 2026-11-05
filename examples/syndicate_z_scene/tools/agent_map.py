"""Read-only ASCII projection and conditional route proposals over a scene.

Positions remain integer game units; glyphs are never motion destinations.
This module has no debugger, input, teleport or memory-write capability.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any

XY_UNITS = 256
Z_UNITS = 128
SYMBOLS = {'agent': 'A', 'civilian': 'c', 'police': 'p', 'guard': 'g',
           'vehicle': 'v', 'door': '+', 'tree': 't',
           'window-open-class': 'w', 'window-closed-class': 'w', 'weapon': 'i'}


def checksum(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def raw_position(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError('Position must have three integer game coordinates')
    if any(type(v) is not int or not 0 <= v <= 65535 for v in value):
        raise ValueError('Position must use unsigned 16-bit integers, not floats')
    return tuple(value)


def exact_decimal(raw: int, units: int) -> str:
    # Both scales are powers of two; eight fractional decimal digits are exact.
    return f'{raw / units:.8f}'.rstrip('0').rstrip('.')


def position_text(position: Any) -> str:
    x, y, z = raw_position(position)
    return '(' + ', '.join(exact_decimal(v, scale)
                           for v, scale in zip((x, y, z), (XY_UNITS, XY_UNITS, Z_UNITS))) + ')'


def scene_entities(scene: dict) -> dict[str, dict]:
    if scene.get('coordinates', {}).get('x_y_units_per_tile') != XY_UNITS or \
       scene.get('coordinates', {}).get('z_units_per_level') != Z_UNITS:
        raise ValueError('Unsupported position units')
    entities = scene.get('entities')
    if not isinstance(entities, list) or len(entities) > 4096:
        raise ValueError('Missing or oversized entity inventory')
    by_id = {}
    for entity in entities:
        identity = entity.get('id')
        if not isinstance(identity, str) or not identity or identity in by_id:
            raise ValueError('Entity identity must be unique and nonempty')
        raw_position(entity.get('position_raw'))
        by_id[identity] = entity
    if scene.get('selected') not in by_id:
        raise ValueError('Selected entity absent')
    return by_id


class CandidateTerrain:
    """Adapter over the previous semantic map; never upgrades it to walkability."""
    def __init__(self, document: dict):
        dimensions = document.get('dimensions')
        if not isinstance(dimensions, list) or len(dimensions) != 3 or \
           any(type(v) is not int or v < 1 for v in dimensions):
            raise ValueError('Invalid semantic map dimensions')
        self.nx, self.ny, self.nz = dimensions
        if self.nx > 128 or self.ny > 128 or self.nz > 32:
            raise ValueError('Unsupported semantic map size')
        self.map_number = document['map_number']
        self.source_hashes = dict(document['source_hashes'])
        self.planes = {}
        for layer in document.get('layers', []):
            z, grid = layer['z'], layer['candidate']
            if type(z) is not int or not 0 <= z < self.nz or z in self.planes:
                raise ValueError('Duplicate or invalid layer')
            if len(grid) != self.ny or any(len(row) != self.nx for row in grid):
                raise ValueError('Incorrect layer extent')
            if any(type(v) not in (int, bool) or v not in (0, 1) for row in grid for v in row):
                raise ValueError('Candidate cells must be Boolean')
            self.planes[z] = tuple(tuple(bool(v) for v in row) for row in grid)
        self.identity = checksum({'dimensions': dimensions, 'sources': self.source_hashes,
                                  'planes': self.planes})

    def classify(self, x: int, y: int, z: int) -> dict:
        if not (0 <= x < self.nx and 0 <= y < self.ny) or z not in self.planes:
            return {'candidate': False, 'reason': 'outside or unmodeled'}
        return {'candidate': self.planes[z][y][x],
                'reason': 'conditional terrain only; physical traversal unqualified'}


def destination_decision(current: Any, destination: Any, *, attachments_settled: bool,
                         action_pending: bool = False) -> str:
    """Suppress duplicate exact relocations, never all movement within a tile."""
    current, destination = raw_position(current), raw_position(destination)
    if action_pending:
        return 'observe_pending_action'
    if current == destination:
        return 'already_at_exact_destination' if attachments_settled else 'observe_unsettled_attachments'
    return 'distinct_destination'


def render_ascii(scene: dict, terrain: Any, *, origin: tuple[int, int] | None = None,
                 width: int = 41, height: int = 19, layer: int | None = None,
                 subdivisions: int = 1, route: dict | None = None) -> dict:
    """Cells are half-open world intervals. Origin is in raw XY units.

    `subdivisions=4` magnifies existing tile evidence; it does not recover
    quarter-tile collisions. Same-glyph-cell entities remain in the sidecar.
    """
    by_id = scene_entities(scene)
    focus = raw_position(by_id[scene['selected']]['position_raw'])
    if type(width) is not int or type(height) is not int or not 1 <= width <= 80 or not 1 <= height <= 40:
        raise ValueError('ASCII viewport must be within 80 columns by 40 rows')
    if type(subdivisions) is not int or subdivisions not in (1, 2, 4, 8, 16, 32, 64, 128, 256):
        raise ValueError('Subdivisions must exactly divide the 256-unit tile')
    step = XY_UNITS // subdivisions
    if layer is None:
        layer = focus[2] // Z_UNITS
    if type(layer) is not int or not 0 <= layer < terrain.nz:
        raise ValueError('Invalid layer')
    if origin is None:
        ox = max(0, min((focus[0] // step - width // 2) * step,
                        max(0, terrain.nx * XY_UNITS - width * step)))
        oy = max(0, min((focus[1] // step - height // 2) * step,
                        max(0, terrain.ny * XY_UNITS - height * step)))
    else:
        if len(origin) != 2 or any(type(v) is not int or v < 0 for v in origin):
            raise ValueError('Origin must be two nonnegative raw integers')
        ox, oy = origin
    if ox % step or oy % step:
        raise ValueError('Origin must align with the overlay cell grid')
    grid = []
    for row in range(height):
        grid.append(['.' if 0 <= (ox + col * step) // XY_UNITS < terrain.nx
                     and 0 <= (oy + row * step) // XY_UNITS < terrain.ny
                     and terrain.classify((ox + col * step) // XY_UNITS,
                                          (oy + row * step) // XY_UNITS, layer)['candidate']
                     else '?' for col in range(width)])
    route_cells = set()
    if route is not None:
        if route.get('source_state_sha256') != scene.get('source_state_sha256'):
            raise ValueError('Route belongs to another scene observation')
        route_cells = {tuple(p) for p in route.get('path_cells', [])}
        for row in range(height):
            for col in range(width):
                cell = ((ox + col * step) // XY_UNITS, (oy + row * step) // XY_UNITS, layer)
                if cell in route_cells and grid[row][col] == '.':
                    grid[row][col] = ':'
    cells: dict[tuple[int, int], list[str]] = {}
    rows = []
    hidden_attached = 0
    for identity, entity in sorted(by_id.items()):
        if entity.get('owner_id'):
            hidden_attached += 1
            continue
        x, y, z = raw_position(entity['position_raw'])
        if z // Z_UNITS != layer:
            continue
        col, row = (x - ox) // step, (y - oy) // step
        if not (0 <= col < width and 0 <= row < height):
            continue
        glyph = ('@' if identity == scene['selected'] else '!' if entity.get('mission_critical')
                 else SYMBOLS.get(entity['category'], 'o'))
        cells.setdefault((col, row), []).append(identity)
        rows.append({'id': identity, 'glyph': glyph, 'category': entity['category'],
                     'mission_critical': bool(entity.get('mission_critical')),
                     'overlay': f'r{row:02d}c{col:02d}', 'position_raw': [x, y, z],
                     'position_exact': position_text((x, y, z)),
                     'tile': [x // XY_UNITS, y // XY_UNITS, z // Z_UNITS],
                     'subtile_raw': [x % XY_UNITS, y % XY_UNITS, z % Z_UNITS]})
    indexed = {r['id']: r for r in rows}
    for (col, row), occupants in cells.items():
        glyphs = [indexed[i]['glyph'] for i in occupants]
        grid[row][col] = ('@' if '@' in glyphs else '!' if '!' in glyphs
                          else '*' if len(occupants) > 1 else glyphs[0])
    meta = {'source_state_sha256': scene['source_state_sha256'], 'map_number': scene['map_number'],
            'origin_raw': [ox, oy], 'step_raw': step, 'width': width, 'height': height,
            'z_layer': layer, 'y_direction': 'increasing_down',
            'map_identity': getattr(terrain, 'identity', checksum({'map':getattr(terrain,'map_sha256',None), 'classes':getattr(terrain,'classes_sha256',None), 'dimensions':[terrain.nx,terrain.ny,terrain.nz]})),
            'cell_intervals': 'half-open', 'commands_use': 'exact raw coordinates and stable IDs'}
    overlay_id = checksum(meta)[:16]
    lines = [f'Local map / ASCII overlay {overlay_id}; z-layer={layer}; cell={Fraction(step, XY_UNITS)} tile',
             f'origin_raw=({ox},{oy}) raw_step={step}; display only; y increases downward',
             f'focus={scene["selected"]} raw={list(focus)} world={position_text(focus)}',
             '     ' + ''.join(str(c // 10) for c in range(width)),
             '     ' + ''.join(str(c % 10) for c in range(width))]
    lines += [f'{i:02d} | ' + ''.join(row) for i, row in enumerate(grid)]
    lines += ['@ focus  A agent  c civilian  p police  g guard  v car  + door  ! target',
              't tree  w window-class  i loose item  * stacked entities  : candidate route',
              '. candidate terrain  ? excluded/unresolved; neither is a walking certificate',
              'ENTITY KEY: overlay | ID | exact world XYZ | raw XYZ | sub-tile raw XYZ']
    lines += [f'{r["overlay"]} {r["glyph"]} {r["id"]}: {r["position_exact"]} '
              f'raw={r["position_raw"]} sub={r["subtile_raw"]}' for r in rows]
    stacks = [{'overlay': f'r{row:02d}c{col:02d}', 'ids': identities}
              for (col, row), identities in cells.items() if len(identities) > 1]
    if stacks:
        lines += ['STACKS: ' + '; '.join(f'{s["overlay"]}={",".join(s["ids"])}' for s in stacks)]
    if subdivisions > 1:
        lines += ['Zoom repeats tile evidence; sub-tile clearance is NOT inferred.']
    lines += [f'{hidden_attached} owned item records omitted from glyphs, retained in scene/inventory records.',
              'Scope: global diagnostic snapshot, not line-of-sight visibility.']
    return {'format': 'syndicate-ascii-observation-1', 'overlay_id': overlay_id,
            'viewport': meta, 'rows': [''.join(r) for r in grid], 'entities': rows,
            'stacks': stacks, 'text': '\n'.join(lines)}


def resolve_overlay_cell(view: dict, label: str, *, overlay_id: str) -> dict:
    """Return the cell's interval, NOT a guessed motion coordinate."""
    import re
    if overlay_id != view['overlay_id']:
        raise ValueError('Stale or different overlay')
    match = re.fullmatch(r'r(\d{2})c(\d{2})', label)
    if not match:
        raise ValueError('Expected rNNcNN overlay coordinates')
    row, col = map(int, match.groups())
    viewport = view['viewport']
    if row >= viewport['height'] or col >= viewport['width']:
        raise ValueError('Overlay coordinate outside viewport')
    step = viewport['step_raw']; ox, oy = viewport['origin_raw']
    return {'x_raw': [ox + col * step, ox + (col + 1) * step],
            'y_raw': [oy + row * step, oy + (row + 1) * step],
            'z_raw': [viewport['z_layer'] * Z_UNITS, (viewport['z_layer'] + 1) * Z_UNITS],
            'intervals': 'half-open', 'exact_destination': None,
            'instruction': 'Select an entity, named anchor or explicit raw point within this interval.'}


def plan_approach(scene: dict, terrain: Any, target_id: str, *,
                  blocked_cells: tuple = (), blocked_edges: tuple = ()) -> dict:
    """Four-neighbor candidate route to an adjacent cell, not to a car center.

    Uses the semantic graph, not rendered text/pixels. No movement is dispatched.
    Dynamic object footprints, boarding points and gates remain unqualified.
    """
    by_id = scene_entities(scene)
    if target_id not in by_id or target_id == scene['selected']:
        raise ValueError('A distinct known target entity is required')
    actor = raw_position(by_id[scene['selected']]['position_raw'])
    target = raw_position(by_id[target_id]['position_raw'])
    record = {'format': 'syndicate-candidate-route-1', 'source_state_sha256': scene['source_state_sha256'],
              'map_number': scene['map_number'], 'actor_id': scene['selected'], 'target_id': target_id,
              'start_raw': list(actor), 'target_raw': list(target), 'qualification': 'conditional_model_only',
              'native_movement': False, 'boarding_qualified': False, 'visibility': scene.get('scope'),
              'map_identity': getattr(terrain, 'identity', checksum({'map':getattr(terrain,'map_sha256',None), 'classes':getattr(terrain,'classes_sha256',None), 'dimensions':[terrain.nx,terrain.ny,terrain.nz]})),
              'observed_run': scene.get('observed_run'), 'runtime_revision': scene.get('runtime_revision'),
              'blocked_cells': [list(x) for x in blocked_cells],
              'blocked_edges': [[list(a), list(b)] for a, b in blocked_edges]}
    if actor[2] != target[2] or actor[2] % Z_UNITS:
        return {**record, 'status': 'unresolved_elevation_connector', 'path_cells': [], 'waypoints_raw': []}
    z = actor[2] // Z_UNITS; start = (actor[0] // XY_UNITS, actor[1] // XY_UNITS, z)
    end = (target[0] // XY_UNITS, target[1] // XY_UNITS, z)
    blocked = {tuple(c) for c in blocked_cells} | {end}
    edge_blocks = {(tuple(a), tuple(b)) for a, b in blocked_edges}
    # Known entity centers are excluded as a conservative candidate-planning
    # preference, not a claim about their actual collision footprint.
    for entity in by_id.values():
        if entity['id'] == scene['selected'] or entity.get('owner_id') or entity['category'] in ('weapon', 'door'):
            continue
        x, y, height = raw_position(entity['position_raw'])
        if height == actor[2]:
            blocked.add((x // XY_UNITS, y // XY_UNITS, z))
    blocked.discard(start)
    def neighbors(node):
        x, y, _ = node
        return ((x-1, y, z), (x, y-1, z), (x+1, y, z), (x, y+1, z))
    def admitted(node):
        x, y, height = node
        return node not in blocked and 0 <= x < terrain.nx and 0 <= y < terrain.ny and terrain.classify(x, y, height)['candidate']
    goals = {node for node in neighbors(end) if admitted(node)}
    if not admitted(start) or not goals:
        return {**record, 'status': 'no_candidate_approach', 'path_cells': [], 'waypoints_raw': []}
    queue = deque([start]); previous = {start: None}; goal = None
    while queue:
        node = queue.popleft()
        if node in goals:
            goal = node; break
        for nxt in neighbors(node):
            if nxt not in previous and admitted(nxt) and (node, nxt) not in edge_blocks:
                previous[nxt] = node; queue.append(nxt)
    if goal is None:
        return {**record, 'status': 'no_candidate_route', 'path_cells': [], 'waypoints_raw': []}
    path = []; cursor = goal
    while cursor is not None:
        path.append(list(cursor)); cursor = previous[cursor]
    path.reverse()
    waypoints = [list(actor)]
    for x, y, height in path[1:]:
        waypoints.append([x*XY_UNITS+128, y*XY_UNITS+128, height*Z_UNITS])
    approach = [goal[0]*XY_UNITS+128, goal[1]*XY_UNITS+128, z*Z_UNITS]
    if waypoints[-1] != approach:
        waypoints.append(approach)
    doors = []
    for entity in by_id.values():
        if entity['category'] != 'door':
            continue
        x, y, height = raw_position(entity['position_raw'])
        cell = [x // XY_UNITS, y // XY_UNITS, height // Z_UNITS]
        if cell in path:
            doors.append({'entity': entity['id'], 'path_index': path.index(cell),
                          'condition': 'gate transition unqualified; stop before crossing'})
    result = {**record, 'status': 'candidate_requires_validation', 'path_cells': path,
              'waypoints_raw': waypoints, 'approach_raw': approach, 'grid_steps': len(path)-1,
              'conditional_gates': doors,
              'arrival_contract': 'exact approach point only; interaction/boarding NOT established',
              'execution_policy': {'walk': 'requires explicit original-navigation opt-in; conditional plan is not traversal proof',
                                   'teleport': 'existing guarded adapter only; no walkability inference'},
              'remaining_limits': ['actor clearance', 'dynamic collision', 'door state',
                                   'sub-tile steering', 'interaction range', 'fair-play visibility']}
    result['plan_id'] = checksum(result)
    return result


@dataclass
class ProgressWatch:
    """Decision-only watchdog; never retries input or issues a teleport itself."""
    goal_raw: tuple[int, int, int]
    target_raw: tuple[int, int, int]
    stall_limit: int = 3
    last_revision: int = -1
    last_waypoint: int = -1
    best_distance_sq: int | None = None
    stagnant: int = 0
    stationary: int = 0
    last_position: tuple[int, int, int] | None = None
    halted: bool = False
    positions: deque = field(default_factory=lambda: deque(maxlen=4))

    def __post_init__(self):
        self.goal_raw = raw_position(self.goal_raw); self.target_raw = raw_position(self.target_raw)
        if type(self.stall_limit) is not int or self.stall_limit < 1:
            raise ValueError('Positive stall limit required')

    def observe(self, position: Any, *, revision: int, target_raw: Any,
                waypoint_raw: Any, waypoint_index: int, attachments_settled: bool,
                gate_ready: bool) -> str:
        position = raw_position(position); target_raw = raw_position(target_raw)
        waypoint_raw = raw_position(waypoint_raw)
        if type(attachments_settled) is not bool or type(gate_ready) is not bool:
            raise ValueError('Attachment and gate readiness must be explicitly qualified Booleans')
        if self.halted:
            return 'held_requires_new_plan'
        if type(revision) is not int or type(waypoint_index) is not int or waypoint_index < 0:
            raise ValueError('Integer revision and nonnegative waypoint index required')
        if revision <= self.last_revision:
            return 'obtain_fresh_observation'
        self.last_revision = revision
        if target_raw != self.target_raw:
            self.halted = True
            return 'target_moved_replan'
        if not gate_ready:
            self.halted = True
            return 'gate_unqualified_hold'
        if position == self.goal_raw:
            return 'arrived_at_approach' if attachments_settled else 'observe_attachment_settlement'
        self.stationary = self.stationary + 1 if position == self.last_position else 0
        self.last_position = position
        self.positions.append(position)
        if len(self.positions) == 4 and self.positions[0] == self.positions[2] and \
           self.positions[1] == self.positions[3] and self.positions[0] != self.positions[1]:
            self.halted = True
            return 'oscillation_replan'
        if waypoint_index < self.last_waypoint:
            self.halted = True
            return 'route_regressed_replan'
        distance = sum((a-b)**2 for a,b in zip(position, waypoint_raw))
        if waypoint_index > self.last_waypoint:
            self.last_waypoint = waypoint_index; self.best_distance_sq = distance; self.stagnant = 0
        elif self.best_distance_sq is None or distance < self.best_distance_sq:
            self.best_distance_sq = distance; self.stagnant = 0
        else:
            self.stagnant += 1
        if self.stagnant >= self.stall_limit:
            self.halted = True
            return 'stalled_replan' if self.stationary >= self.stall_limit else 'moving_without_progress_hold'
        return 'continue_bounded_observation'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--map-model', required=True, type=Path)
    parser.add_argument('--width', type=int, default=41)
    parser.add_argument('--height', type=int, default=19)
    parser.add_argument('--origin', nargs=2, type=int, help='Raw XY coordinates')
    parser.add_argument('--layer', type=int)
    parser.add_argument('--subdivisions', type=int, default=1)
    parser.add_argument('--target', help='Stable entity ID for a candidate approach')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    scene = json.loads(args.snapshot.read_text()); model = json.loads(args.map_model.read_text())
    terrain = CandidateTerrain(model)
    if scene['map_number'] != terrain.map_number:
        raise ValueError('Different mission map')
    route = plan_approach(scene, terrain, args.target) if args.target else None
    view = render_ascii(scene, terrain, origin=tuple(args.origin) if args.origin else None,
                        width=args.width, height=args.height, layer=args.layer,
                        subdivisions=args.subdivisions, route=route)
    result = {'view': view, 'route': route}
    print(json.dumps(result, indent=2) if args.json else view['text'])


if __name__ == '__main__':
    main()
