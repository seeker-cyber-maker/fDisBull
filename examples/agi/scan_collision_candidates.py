"""Bounded static AGI collision candidates; no native execution or glitch proof.

Only selected owner-supplied PIC/LOGIC resources are read. Geometry assumes a
land actor's one-row baseline, destination-only unit steps and no dynamic
objects, horizon, overlays or runtime blocks. set(0) guards are potential
water hazards under the caller's game-specific flag interpretation; their
parents and reachability are not evaluated. Output retains hashes and derived
coordinates, never original resource bytes, messages or a raster plane.
"""
import argparse
from collections import deque
from hashlib import sha256
import json
from pathlib import Path

from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture, extract_v2_resource


DEFAULT_ROOMS = (8, 25, 33, 34, 39, 41, 42)
MAX_ROOMS = 32
MAX_GUARDS = 128
MAX_RECTANGLES = 256
MAX_CELLS = 160 * 168
PARENT_CAVEAT = ('Lexical parents, other control flow and runtime conditions are '
                 'not evaluated; this guard may be conditional or unreachable.')


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {name}')
    return value


def _geometry(plane, image_width, image_height, width, allow_priority_one):
    _integer(image_width, 1, 160, 'image width')
    _integer(image_height, 1, 168, 'image height')
    _integer(width, 1, image_width, 'baseline width')
    if type(allow_priority_one) is not bool:
        raise ValueError('Priority-one policy must be explicit boolean')
    if (not isinstance(plane, bytes) or len(plane) != image_width * image_height
            or any(value > 15 for value in plane)):
        raise ValueError('Invalid complete priority plane')


def _baseline(plane, x, y, image_width, width, allow_priority_one):
    values = plane[y * image_width + x:y * image_width + x + width]
    blocked = []
    if 0 in values:
        blocked.append('priority_zero')
    if 2 in values:
        blocked.append('priority_two')
    conditional = 1 in values
    if conditional and not allow_priority_one:
        blocked.append('priority_one_policy')
    all_water = all(value == 3 for value in values)
    if all_water:
        blocked.append('all_water')
    return dict(passable=not blocked, all_water=all_water,
                mixed_water=3 in values and not all_water,
                conditional_one=conditional, blocked_by=blocked)


def baseline_passability(plane, x, y, *, image_width=160, image_height=168,
                         width=6, allow_priority_one=False):
    """Classify a land baseline; any 0/2, forbidden 1, or all-3 is blocked."""
    _geometry(plane, image_width, image_height, width, allow_priority_one)
    _integer(x, 0, image_width - width, 'baseline x')
    _integer(y, 0, image_height - 1, 'baseline y')
    return _baseline(plane, x, y, image_width, width, allow_priority_one)


def _rectangle(rectangle):
    if not isinstance(rectangle, (tuple, list)) or len(rectangle) != 4:
        raise ValueError('Expected inclusive origin rectangle')
    x1, y1, x2, y2 = rectangle
    for value in rectangle:
        _integer(value, 0, 255, 'rectangle coordinate')
    if x1 > x2 or y1 > y2:
        raise ValueError('Inverted rectangle')
    return x1, y1, x2, y2


def extract_water_guards(payload, *, logic_number=0):
    """Extract only positive ego-posn/OR IFs immediately beginning set(flag0).

    Offsets are code-relative, with payload offsets separately retained.
    Established layout boundaries prevent instruction operands from becoming
    false guards. Rectangles constrain the baseline origin, not its full width.
    This narrow extractor does not establish flag meaning or reachability.
    """
    _integer(logic_number, 0, 255, 'logic number')
    layout = logic_layout(payload)
    starts = layout['instructions']
    following = dict(zip(starts, starts[1:] + [layout['code_end']]))
    qualified = set(starts) | {layout['code_end']}
    headers = []
    for offset in starts:
        if payload[offset] != 255:
            continue
        body = following[offset]
        end = body + int.from_bytes(payload[body - 2:body], 'little')
        if end not in qualified:
            raise ValueError('IF target is not a qualified forward boundary')
        headers.append((offset, body, end))
    result, rectangle_count = [], 0
    for offset, body, end in headers:
        if end < body + 2 or body not in following or payload[body:body + 2] != b'\x0c\x00':
            continue
        tokens = []
        cursor = offset + 1
        while cursor < body - 3:
            if payload[cursor] in (252, 253):
                tokens.append(payload[cursor])
                cursor += 1
            else:
                item = layout['conditions'][cursor]
                tokens.append((cursor, item))
                cursor = item['end']
        terms = tokens
        if len(tokens) >= 3 and tokens[0] == 252 and tokens[-1] == 252:
            terms = tokens[1:-1]
        elif len(tokens) != 1:
            continue
        rectangles, condition_offsets = [], []
        for term in terms:
            if not isinstance(term, tuple):
                break
            position, item = term
            if item['opcode'] != 11 or item['negated'] or payload[position + 1] != 0:
                break
            rectangle = list(payload[position + 2:item['end']])
            try:
                _rectangle(rectangle)
            except ValueError:
                break
            rectangles.append(rectangle)
            condition_offsets.append(position - 2)
        else:
            if not rectangles:
                continue
            rectangle_count += len(rectangles)
            if rectangle_count > MAX_RECTANGLES:
                raise ValueError('Water-guard rectangle budget exceeded')
            result.append(dict(
                logic=logic_number, if_offset=offset - 2, body_offset=body - 2,
                if_payload_offset=offset, body_payload_offset=body,
                false_offset=end - 2, condition_offsets=condition_offsets,
                rectangles=rectangles, predicate='positive_ego_posn_or',
                effect='set_flag_zero', source_sha256=sha256(payload).hexdigest(),
                if_sha256=sha256(payload[offset:body]).hexdigest(),
                writer_sha256=sha256(payload[body:body + 2]).hexdigest(),
                lexical_parent_if_offsets=[parent - 2 for parent, begin, finish in headers
                                           if begin <= offset < finish],
                parent_condition_caveat=PARENT_CAVEAT,
                status='static_conditional_guard'))
            if len(result) > MAX_GUARDS:
                raise ValueError('Water-guard extraction budget exceeded')
    return result


def edge_water_seams(plane, *, image_width=160, image_height=168, width=6,
                     allow_priority_one=False, max_candidates=256):
    """Find passable edge baselines with an inward all-water baseline.

    An edge can be fully dry or mixed. Results describe static picture geometry,
    not a reachable route or an observed native water-test outcome.
    """
    _geometry(plane, image_width, image_height, width, allow_priority_one)
    _integer(max_candidates, 1, 4096, 'candidate budget')
    origins = image_width - width + 1
    checks = []
    if origins > 1:
        for y in range(image_height):
            checks.extend((('left', 0, y, 1, y),
                           ('right', origins - 1, y, origins - 2, y)))
    if image_height > 1:
        for x in range(origins):
            checks.extend((('top', x, 0, x, 1),
                           ('bottom', x, image_height - 1, x, image_height - 2)))
    candidates, complete = [], True
    for edge, x, y, inner_x, inner_y in checks:
        outer = _baseline(plane, x, y, image_width, width, allow_priority_one)
        inner = _baseline(plane, inner_x, inner_y, image_width, width, allow_priority_one)
        if outer['passable'] and inner['all_water']:
            if len(candidates) < max_candidates:
                candidates.append(dict(edge=edge, x=x, y=y, inner_x=inner_x,
                                       inner_y=inner_y, status='static_edge_seam'))
            else:
                complete = False
    return dict(candidates=candidates, complete=complete, examined=len(checks))


def hazard_overlaps(plane, guards, *, image_width=160, image_height=168, width=6,
                    allow_priority_one=False, max_samples=8, max_checks=100000):
    """Count geometric land origins overlapped by conditional script guards."""
    _geometry(plane, image_width, image_height, width, allow_priority_one)
    _integer(max_samples, 0, 256, 'sample budget')
    _integer(max_checks, 1, 1_000_000, 'overlap budget')
    if not isinstance(guards, (list, tuple)) or len(guards) > MAX_GUARDS:
        raise ValueError('Invalid guard list or guard budget')
    rectangle_count = 0
    for guard in guards:
        if not isinstance(guard, dict) or not isinstance(guard.get('rectangles'), (list, tuple)):
            raise ValueError('Invalid guard rectangles')
        _integer(guard.get('if_offset'), 0, 65535, 'guard offset')
        rectangle_count += len(guard['rectangles'])
        if rectangle_count > MAX_RECTANGLES:
            raise ValueError('Overlap rectangle budget exceeded')
        for rectangle in guard['rectangles']:
            _rectangle(rectangle)
    overlaps, examined = [], 0
    for guard in guards:
        for rectangle in guard['rectangles']:
            x1, y1, x2, y2 = _rectangle(rectangle)
            count, samples = 0, []
            complete = True
            for y in range(y1, min(y2, image_height - 1) + 1):
                for x in range(x1, min(x2, image_width - width) + 1):
                    if examined == max_checks:
                        complete = False
                        break
                    examined += 1
                    if _baseline(plane, x, y, image_width, width, allow_priority_one)['passable']:
                        count += 1
                        if len(samples) < max_samples:
                            samples.append([x, y])
                if not complete:
                    break
            overlaps.append(dict(if_offset=guard['if_offset'], rectangle=list(rectangle),
                                 geometry_passable_count=count, sample_origins=samples,
                                 complete=complete, status='conditional_script_hazard',
                                 parent_condition_caveat=guard.get('parent_condition_caveat', PARENT_CAVEAT)))
            if not complete:
                return dict(overlaps=overlaps, complete=False, examined=examined)
    return dict(overlaps=overlaps, complete=True, examined=examined)


def bounded_path(plane, start, goal, *, image_width=160, image_height=168, width=6,
                 allow_priority_one=False, diagonals=False, hazards=(),
                 max_nodes=5000, max_steps=1024):
    """Return a bounded static 4/8-neighbor unit path, never a native route proof.

    Inclusive hazard rectangles apply to ego baseline origins. Diagonal moves
    check their destination only; no swept-volume or corner-clearance claim is
    made. A budget stop is explicitly incomplete, not unreachable.
    """
    _geometry(plane, image_width, image_height, width, allow_priority_one)
    _integer(max_nodes, 1, MAX_CELLS, 'node budget')
    _integer(max_steps, 0, MAX_CELLS, 'step budget')
    if type(diagonals) is not bool:
        raise ValueError('Diagonal policy must be boolean')
    if not isinstance(hazards, (tuple, list)) or len(hazards) > MAX_RECTANGLES:
        raise ValueError('Invalid hazard list or budget')
    rectangles = [_rectangle(rectangle) for rectangle in hazards]
    for point in (start, goal):
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError('Expected x,y path endpoint')
        _integer(point[0], 0, image_width - width, 'endpoint x')
        _integer(point[1], 0, image_height - 1, 'endpoint y')
    start, goal = tuple(start), tuple(goal)

    def admitted(point):
        x, y = point
        return (0 <= x <= image_width - width and 0 <= y < image_height
                and not any(a <= x <= c and b <= y <= d for a, b, c, d in rectangles)
                and _baseline(plane, x, y, image_width, width, allow_priority_one)['passable'])

    def result(status, path=()):
        return dict(status=status, path=[list(point) for point in path],
                    visited=len(parents), complete=status in ('found', 'unreachable', 'blocked_endpoint'),
                    claim='static_candidate_only', diagonal_policy='destination_only')

    parents = {}
    if not admitted(start) or not admitted(goal):
        return result('blocked_endpoint')
    parents[start] = None
    queue = deque([(start, 0)])
    moves = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if diagonals:
        moves += ((-1, -1), (-1, 1), (1, -1), (1, 1))
    node_limited = step_limited = False
    while queue:
        point, depth = queue.popleft()
        if point == goal:
            path = []
            while point is not None:
                path.append(point)
                point = parents[point]
            return result('found', reversed(path))
        for dx, dy in moves:
            next_point = point[0] + dx, point[1] + dy
            if next_point in parents or not admitted(next_point):
                continue
            if depth == max_steps:
                step_limited = True
            elif len(parents) == max_nodes:
                node_limited = True
            else:
                parents[next_point] = point
                queue.append((next_point, depth + 1))
    return result('node_budget' if node_limited else 'step_budget' if step_limited else 'unreachable')


def _owner_file(source, name):
    matches = [path for path in source.iterdir() if path.name.lower() == name.lower()]
    if len(matches) != 1 or not matches[0].is_file():
        raise ValueError(f'Missing or ambiguous {name}')
    size = matches[0].stat().st_size
    if not 0 < size <= 768 or size % 3:
        raise ValueError(f'Invalid bounded {name} size')
    return matches[0]


def _seam_summary(seams):
    """Keep contiguous candidate ranges rather than a large point catalogue."""
    segments = []
    for edge in ('left', 'right', 'top', 'bottom'):
        points = sorted((item for item in seams['candidates'] if item['edge'] == edge),
                        key=lambda item: (item['y'], item['x']))
        for item in points:
            dx, dy = item['inner_x'] - item['x'], item['inner_y'] - item['y']
            if (segments and segments[-1]['edge'] == edge
                    and ((edge in ('left', 'right') and item['y'] == segments[-1]['y_range'][1] + 1)
                         or (edge in ('top', 'bottom') and item['x'] == segments[-1]['x_range'][1] + 1))):
                segments[-1]['x_range'][1] = item['x']
                segments[-1]['y_range'][1] = item['y']
                segments[-1]['count'] += 1
            else:
                segments.append(dict(edge=edge, x_range=[item['x'], item['x']],
                                     y_range=[item['y'], item['y']], count=1,
                                     inward_delta=[dx, dy]))
    return dict(segments=segments, retained_candidate_count=len(seams['candidates']),
                complete=seams['complete'], examined=seams['examined'])


def _rooms(value):
    try:
        result = tuple(int(item) for item in value.split(','))
    except ValueError as exc:
        raise ValueError('Rooms must be comma-separated integers') from exc
    if not result or len(result) > MAX_ROOMS or len(set(result)) != len(result):
        raise ValueError('Invalid selected-room budget or duplicate')
    for room in result:
        _integer(room, 0, 255, 'selected room')
    return result


def _path_query(value):
    try:
        room, start, goal = value.split(':')
        points = [tuple(int(item) for item in point.split(',')) for point in (start, goal)]
        if any(len(point) != 2 for point in points):
            raise ValueError
        return int(room), *points
    except ValueError as exc:
        raise ValueError('Path must be ROOM:X,Y:X,Y') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--rooms', default=','.join(map(str, DEFAULT_ROOMS)))
    parser.add_argument('--width', type=int, default=6)
    parser.add_argument('--allow-priority-one', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--path', action='append', default=[], metavar='ROOM:X,Y:X,Y')
    parser.add_argument('--neighbors', type=int, choices=(4, 8), default=4)
    parser.add_argument('--avoid-script-guards', action='store_true',
                        help='Treat extracted conditional origin rectangles as excluded')
    parser.add_argument('--max-nodes', type=int, default=5000)
    parser.add_argument('--max-steps', type=int, default=1024)
    args = parser.parse_args(argv)
    source, output = args.source.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    if output.is_relative_to(source) or output.is_relative_to(checkout):
        raise ValueError('Output must be outside the source and checkout')
    if output.exists() or args.output.is_symlink():
        raise ValueError('Output must be a fresh file')
    if not source.is_dir():
        raise ValueError('Source must be an owner-supplied directory')
    rooms = _rooms(args.rooms)
    _integer(args.width, 1, 160, 'baseline width')
    _integer(args.max_nodes, 1, MAX_CELLS, 'node budget')
    _integer(args.max_steps, 0, MAX_CELLS, 'step budget')
    if len(args.path) > 8:
        raise ValueError('Path-query budget exceeded')
    queries = [_path_query(value) for value in args.path]
    if any(room not in rooms for room, *_ in queries):
        raise ValueError('Path queries must use selected rooms')
    picdir, logdir = _owner_file(source, 'PICDIR'), _owner_file(source, 'LOGDIR')
    report = dict(schema='agi-static-collision-candidates-v1', status='static_candidates_only',
                  native_validation='not_run', profile='AGI v2.917 layout',
                  assumptions=dict(width=args.width, allow_priority_one=args.allow_priority_one,
                                   actor='land_baseline', diagonal_policy='destination_only',
                                   flag_zero='potential_water_hazard_target_assumption',
                                   ignored=['horizon', 'dynamic_objects', 'overlays', 'runtime_blocks',
                                            'parent_conditions', 'control_flow_reachability']),
                  selected_rooms=list(rooms), complete=True,
                  directory_sha256={name: sha256(path.read_bytes()).hexdigest()
                                    for name, path in (('PICDIR', picdir), ('LOGDIR', logdir))},
                  rooms=[])
    for room in rooms:
        item = dict(room=room, status='static_candidates_only')
        try:
            picture = extract_v2_resource(picdir, source, room)
            logic = extract_v2_resource(logdir, source, room)
            decoded = decode_picture(picture['payload'])
            guards = extract_water_guards(logic['payload'], logic_number=room)
            plane = decoded['priority']
            policy = dict(width=args.width, allow_priority_one=args.allow_priority_one)
            seams = edge_water_seams(plane, **policy)
            overlaps = hazard_overlaps(plane, guards, **policy)
            item.update(picture_sha256=picture['sha256'], logic_sha256=logic['sha256'],
                        water_flag_guards=guards, edge_seams=_seam_summary(seams), hazard_overlaps=overlaps,
                        paths=[])
            rectangles = [rectangle for guard in guards for rectangle in guard['rectangles']]
            for query_room, start, goal in queries:
                if query_room == room:
                    path = bounded_path(plane, start, goal, **policy,
                                        diagonals=args.neighbors == 8,
                                        hazards=rectangles if args.avoid_script_guards else (),
                                        max_nodes=args.max_nodes, max_steps=args.max_steps)
                    item['paths'].append(dict(start=list(start), goal=list(goal),
                                              extracted_guards_excluded=args.avoid_script_guards,
                                              result=path))
            item['complete'] = (seams['complete'] and overlaps['complete']
                                and all(path['result']['complete'] for path in item['paths']))
        except (ValueError, OSError) as exc:
            item.update(status='unavailable_or_unsupported', complete=False, reason=str(exc))
        report['rooms'].append(item)
        report['complete'] = report['complete'] and item['complete']
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(output=str(output), rooms=len(report['rooms']),
                          complete=report['complete'], status=report['status'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
