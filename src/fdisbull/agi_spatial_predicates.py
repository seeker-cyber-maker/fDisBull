"""Bounded source-local AGI posn/complement audits, without native execution.

The adapter recognizes adjacent AND-guarded posn / NOT-posn IFs, compares
lexical action effects, and delegates point-domain bands to scene_boundaries.
PIC baselines are a separate static filter, never a reachable-world mask.
"""
from hashlib import sha256

from .agi import AGI2917Processor
from .agi_layout import logic_layout, _ACTION_WIDTHS
from .processor import Location
from .scene_boundaries import audit_rectangle_boundary


class _BudgetStop(Exception):
    pass


def _spend(budget, count=1):
    if budget['used']+count > budget['limit']:
        raise _BudgetStop
    budget['used'] += count


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid '+label)
    return value


def _point(value, width, height, label):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError('Invalid '+label)
    return [_integer(value[0], 0, width-1, label+' x'),
            _integer(value[1], 0, height-1, label+' y')]


def _conditions(facts):
    """Return factual operands only; do not export retained instruction bytes."""
    result, negated = [], False
    for condition in facts:
        if condition.get('marker') == 'not':
            negated = True
        elif 'marker' in condition:
            result.append({'marker': condition['marker']})
        else:
            result.append({'opcode': condition['opcode'],
                           'arguments': list(condition['operands']), 'negated': negated})
            negated = False
    return result


def _signature(conditions):
    position, context = None, []
    for condition in conditions:
        if 'marker' in condition:
            return None
        op, args = condition['opcode'], condition['arguments']
        if op == 11:
            if position is not None or args[0] != 0 or args[1] > args[3] or args[2] > args[4]:
                return None
            position = (tuple(args), condition['negated'])
        elif op in (1, 3, 5, 7):
            context.append((op, tuple(args), condition['negated']))
        else:
            return None
    return None if position is None else (position, tuple(sorted(context)))


def _context(signature, variables, flags):
    records, known = [], []
    for op, args, negated in signature:
        value = (flags if op == 7 else variables).get(str(args[0]))
        result = None
        if value is not None:
            result = (value if op == 7 else value == args[1] if op == 1
                      else value < args[1] if op == 3 else value > args[1])
            if negated:
                result = not result
        records.append({'opcode': op, 'arguments': list(args), 'negated': negated,
                        'supplied_value': value, 'matches': result})
        known.append(result)
    matches = None if any(value is None for value in known) else all(known)
    return {'conditions': records, 'matches_supplied_state': matches,
            'scope': 'Derived from supplied values; ancestor guards and native evaluation are not established.'}


def _effects(code, starts, nodes, branch, labels, score_variable, budget):
    """Group a DROP with its nearest lexical IF, preserving conditional caveats."""
    groups = {}
    try:
        for pc in starts:
            _spend(budget)
            if not branch['true'] <= pc < branch['false'] or code[pc] != 94:
                continue
            item = code[pc+1]
            parents = []
            for node in nodes.values():
                _spend(budget)
                if (branch['true'] <= node['offset'] and node['true'] <= pc < node['false']
                        and node['false'] <= branch['false']):
                    parents.append(node)
            action = max(parents, key=lambda n: n['offset']) if parents else branch
            key = (item, action['offset'])
            if key in groups:
                continue
            operations, score, nonlinear = [], 0, False
            group = {'item': item, 'label': labels.get(item, 'item '+str(item)),
                     'action_if_offset': action['offset'], 'guard': action['conditions'],
                     'body_bounds': [action['true'], action['false']], 'operations': operations,
                     'score_variable': score_variable, 'linear_score_delta': None, 'complete': False,
                     'linear_score_delta_scope': 'Mathematical sum of unconditional constant ADDN/SUBN operands only; byte wrap and incoming score are unproved. Not an unconditional native score change.',
                     'scope': 'Lexical true-body effects; control-flow reachability is not proved.'}
            groups[key] = group
            for offset in starts:
                _spend(budget)
                if not action['true'] <= offset < action['false']:
                    continue
                op = code[offset]
                names = {0: 'return', 1: 'increment', 2: 'decrement', 3: 'assign',
                         4: 'assign_variable', 5: 'add', 6: 'add_variable', 7: 'subtract',
                         8: 'subtract_variable', 9: 'indirect_assign_variable',
                         10: 'assign_indirect', 11: 'indirect_assign_constant',
                         22: 'call', 23: 'call_variable', 39: 'get_position',
                         49: 'last_cel', 50: 'current_cel', 51: 'current_loop',
                         52: 'current_view', 53: 'number_of_loops', 57: 'get_priority',
                         87: 'get_direction', 92: 'get', 94: 'drop', 101: 'print',
                         130: 'random', 254: 'goto', 255: 'conditional'}
                # Unknown actions conservatively invalidate a sum. This small
                # whitelist only admits known non-score actor/flag/item effects.
                non_score = {12, 13, 14, 15, 16, 17, 30, 33, 35, 36, 37, 38, 41, 43,
                             47, 54, 61, 62, 63, 64, 65, 66, 67, 68, 70, 71, 72, 73,
                             75, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 88, 89, 90,
                             91, 92, 93, 94, 95, 96, 101, 102}
                size = 2 if op == 254 else 0 if op == 255 else _ACTION_WIDTHS[op]
                args = list(code[offset+1:offset+1+size])
                control = op in (0, 22, 23, 254, 255)
                unknown_action = op not in names and op not in non_score
                score_write = (op in (9, 11)
                               or op in (1, 2, 3, 4, 6, 8, 10) and args[0] == score_variable
                               or op == 39 and score_variable in args[1:]
                               or op in (49, 50, 51, 52, 53, 57, 87) and args[1] == score_variable
                               or op == 130 and args[2] == score_variable)
                nonlinear |= control or unknown_action or score_write
                conditional = False
                for node in nodes.values():
                    _spend(budget)
                    if action['offset'] < node['offset'] and node['true'] <= offset < node['false']:
                        conditional = True
                        break
                operations.append({'source_offset': offset, 'opcode': op,
                                   'operation': names.get(op, 'non_score_action' if op in non_score else 'unclassified_action'),
                                   'arguments': args, 'nested_conditional': conditional,
                                   'invalidates_linear_sum': bool(control or unknown_action or score_write)})
                if op in (5, 7) and args[0] == score_variable:
                    score += args[1] if op == 5 else -args[1]
                    nonlinear |= conditional
            group.update(complete=True, linear_score_delta=None if nonlinear else score)
    except _BudgetStop:
        return list(groups.values()), False
    return list(groups.values()), True


def _baseline(plane, point, width, image_width):
    x, y = point
    if x+width > image_width:
        return {'origin': list(point), 'passable': False, 'reason': 'footprint outside picture'}
    values = plane[y*image_width+x:y*image_width+x+width]
    blocked = [i for i, value in enumerate(values) if value in (0, 2)]
    return {'origin': list(point), 'width': width, 'priority_values': sorted(set(values)),
            'blocked_offsets': blocked, 'requires_ignore_blocks': 1 in values,
            'all_water': all(value == 3 for value in values),
            'passable': not blocked and not all(value == 3 for value in values)}


def _ray(origin, outside, direction, plane, actor_width, width, allow_one):
    """Cardinal candidate: perpendicular alignment, then the selected ray."""
    vertical = direction in ('up', 'down')
    aligned = [outside[0], origin[1]] if vertical else [origin[0], outside[1]]
    points = [list(origin)]
    for target in (aligned, outside):
        while points[-1] != target:
            x, y = points[-1]
            x += (target[0] > x)-(target[0] < x)
            y += (target[1] > y)-(target[1] < y)
            points.append([x, y])
    first = None
    for point in points:
        record = _baseline(plane, point, actor_width, width)
        if not record['passable'] or record.get('requires_ignore_blocks') and not allow_one:
            first = record
            break
    return {'waypoints': [list(origin), aligned, list(outside)], 'unit_steps': len(points)-1,
            'examined': len(points) if first is None else points.index(first['origin'])+1,
            'static_passable': first is None, 'first_blocked': first,
            'scope': 'Static PIC baseline proposal; drawn actors, script motion and native reachability are unknown.'}


def _geometry(band, origin, plane, actor_width, width, height, allow_one, adjacent_columns):
    if origin is None or plane is None:
        return {'status': 'not_supplied', 'native_reachability': 'unknown'}
    outside = band['witness']['outside']
    direct = _ray(origin, outside, band['direction'], plane, actor_width, width, allow_one)
    proposal = None
    if direct['static_passable']:
        proposal = {'inside': band['witness']['inside'], 'outside': outside, 'ray': direct}
    else:
        vertical = band['direction'] in ('up', 'down')
        axis, limit = (0, width) if vertical else (1, height)
        for distance in range(1, adjacent_columns+1):
            for sign in (-1, 1):
                candidate = list(outside); candidate[axis] += sign*distance
                if not 0 <= candidate[axis] < limit:
                    continue
                # The same terminal band must contain the alternate origin.
                if not any(y == candidate[1] and x0 <= candidate[0] < x1
                           for y, x0, x1 in band['row_runs']):
                    continue
                ray = _ray(origin, candidate, band['direction'], plane, actor_width, width, allow_one)
                if ray['static_passable']:
                    inside = list(candidate)
                    inside[1 if vertical else 0] += (-1 if band['direction'] in ('down', 'right') else 1)
                    proposal = {'inside': inside, 'outside': candidate, 'ray': ray}
                    break
            if proposal is not None:
                break
    return {'status': 'static_pic_only', 'origin_ray': direct, 'proposal': proposal,
            'priority_one_policy': 'allowed' if allow_one else 'blocked',
            'native_reachability': 'unknown'}


def _contrast(origin, band, geometry, actor, actor_width):
    if origin is None or actor is None:
        return {'status': 'not_supplied'}
    witness = geometry.get('proposal') or band['witness']
    def distance(point):
        return abs(point[0]+actor_width//2-actor['x']-actor['width']//2)+abs(point[1]-actor['y'])
    start, within, outside = (distance(point) for point in
                              (origin, witness['inside'], witness['outside']))
    return {'status': 'derived_fixed_pose_comparison', 'metric': 'center-Manhattan',
            'reference_actor': dict(actor), 'origin_distance': start,
            'inside_distance': within, 'outside_distance': outside,
            'outside_no_closer_than_inside': outside >= within,
            'outside_no_closer_than_origin': outside >= start,
            'scope': 'One supplied frozen actor pose; not a throw-range predicate, live distance measurement or catch threshold.'}


def analyze_posn_boundaries(payload, *, logic_number, origin=None, actor_width=6,
                            width=160, height=168, priority_plane=None, picture_sha256=None,
                            allow_priority_one=False, reference_actor=None, variables=None,
                            flags=None, item_labels=None, score_variable=3, max_pairs=16,
                            max_checks=1_000_000, max_source_steps=100_000, adjacent_columns=8):
    """Derive paired inclusive posn bands and guarded lexical effect contrasts.

    Completeness applies to this narrow structural recognizer. Source-local
    candidates do not imply reachability. No native-qualified input is accepted.
    """
    _integer(logic_number, 0, 255, 'logic number')
    _integer(width, 1, 160, 'width'); _integer(height, 1, 168, 'height')
    _integer(actor_width, 1, width, 'actor width'); _integer(score_variable, 0, 255, 'score variable')
    _integer(max_pairs, 1, 64, 'pair budget'); _integer(max_checks, 1, 1_000_000, 'cell budget')
    _integer(max_source_steps, 1, 1_000_000, 'source-operation budget')
    _integer(adjacent_columns, 0, 32, 'adjacent-column budget')
    if type(allow_priority_one) is not bool:
        raise ValueError('Priority-one policy must be explicit boolean')
    if origin is not None:
        origin = _point(origin, width, height, 'origin')
    if priority_plane is not None and (type(priority_plane) is not bytes or len(priority_plane) != width*height
                                     or any(value > 15 for value in priority_plane)):
        raise ValueError('Expected a complete immutable AGI priority plane')
    if priority_plane is not None and (not isinstance(picture_sha256, str) or len(picture_sha256) != 64
                                      or any(c not in '0123456789abcdef' for c in picture_sha256)):
        raise ValueError('Missing source picture hash')
    if reference_actor is not None:
        if not isinstance(reference_actor, dict):
            raise ValueError('Invalid reference actor')
        reference_actor = {key: _integer(reference_actor.get(key), -32768 if key != 'width' else 1,
                                         32767 if key != 'width' else 160, 'reference '+key)
                           for key in ('x', 'y', 'width')}
    variables = {} if variables is None else variables
    flags = {} if flags is None else flags
    labels = {} if item_labels is None else item_labels
    for mapping, boolean in ((variables, False), (flags, True)):
        if not isinstance(mapping, dict) or any(not isinstance(k, str) or not k.isdigit()
                or not 0 <= int(k) <= 255 or (type(v) is not bool if boolean else type(v) is not int or not 0 <= v <= 255)
                for k, v in mapping.items()):
            raise ValueError('Invalid supplied scalar context')
    if not isinstance(labels, dict) or any(type(k) is not int or not 0 <= k <= 255
            or not isinstance(v, str) or not v or len(v) > 64 for k, v in labels.items()):
        raise ValueError('Invalid item labels')
    layout = logic_layout(payload); code = payload[2:layout['code_end']]
    starts = [pc-2 for pc in layout['instructions']]
    resource_sha = sha256(payload).hexdigest()
    space = 'agi-boundary-'+resource_sha
    decoder = AGI2917Processor(space)
    report = {'format': 'fdisbull-agi-spatial-predicates-1', 'status': 'source_candidates_only',
              'complete': True, 'examined': 0,
              'source': {'logic': logic_number, 'resource_sha256': resource_sha},
              'domain': {'width': width, 'height': height}, 'origin': origin,
              'actor_width': actor_width, 'source_pairs': [], 'findings': [],
              'native_reachability': 'not_established_by_this_capture',
              'scope': 'Adjacent source-local posn/complement parents; no full control-flow, walkable-world, range or native execution claim.'}
    budget = {'limit': max_source_steps, 'used': 0, 'instruction_cap': 4096,
              'instruction_count': len(starts)}
    report['source_work'] = budget
    if len(starts) > budget['instruction_cap']:
        report.update(complete=False, budget_stop='source instruction cap')
        return report
    nodes = {}
    try:
        for pc in starts:
            _spend(budget)
            if code[pc] != 255:
                continue
            decoded = decoder.decode(code, Location(space, pc))
            edges = {edge.kind: edge.target.offset for edge in decoded.successors if edge.target is not None}
            if set(edges) != {'true', 'false'}:
                continue
            _spend(budget, len(decoded.facts['conditions']))
            conditions = _conditions(decoded.facts['conditions'])
            nodes[pc] = {'offset': pc, 'conditions': conditions,
                         'signature': _signature(conditions), **edges}
    except _BudgetStop:
        report.update(complete=False, budget_stop='source parsing budget')
        return report
    for pc, first in nodes.items():
        try:
            _spend(budget)
        except _BudgetStop:
            report.update(complete=False, budget_stop='source pair budget')
            break
        second = nodes.get(first['false'])
        one, two = first['signature'], second['signature'] if second else None
        if one is None or two is None or one[0][0] != two[0][0] or one[0][1] == two[0][1] or one[1] != two[1]:
            continue
        if len(report['source_pairs']) == max_pairs:
            report['complete'] = False; report['budget_stop'] = 'pair budget'; break
        if report['examined'] == max_checks:
            report['complete'] = False; report['budget_stop'] = 'cell budget'; break
        inside, outside = (second, first) if one[0][1] else (first, second)
        pair = {'inside_if_offset': inside['offset'], 'outside_if_offset': outside['offset'],
                'arguments': list(one[0][0]), 'convention': 'inclusive',
                'shared_scalar_context': _context(one[1], variables, flags)}
        report['source_pairs'].append(pair)
        audit = audit_rectangle_boundary(one[0][0][1:], width=width, height=height,
                    convention='inclusive', directions=('up', 'down', 'left', 'right'),
                    start=origin, max_band_width=1, max_checks=max_checks-report['examined'])
        report['examined'] += audit['examined']
        if not audit['complete']:
            report['complete'] = False
        if not audit['bands']:
            continue
        inner, inner_complete = _effects(code, starts, nodes, inside, labels, score_variable, budget)
        outer, outer_complete = _effects(code, starts, nodes, outside, labels, score_variable, budget)
        if not inner_complete or not outer_complete:
            report.update(complete=False, budget_stop='source effect budget')
        contrasts = []
        try:
            for a in inner:
                for b in outer:
                    _spend(budget)
                    if a['item'] == b['item']:
                        contrasts.append({'item': a['item'], 'label': a['label'], 'inside': a, 'outside': b})
        except _BudgetStop:
            inner_complete = outer_complete = False
            report.update(complete=False, budget_stop='source contrast budget')
        finding = {**pair, 'boundary_audit': audit, 'action_contrasts': contrasts,
                   'effect_groups': {'inside': inner, 'outside': outer},
                   'effects_complete': inner_complete and outer_complete,
                   'source_picture_sha256': picture_sha256, 'bands': []}
        for band in audit['bands']:
            geometry = _geometry(band, origin, priority_plane, actor_width, width, height,
                                 allow_priority_one, adjacent_columns)
            finding['bands'].append({'predicate_band': band, 'static_geometry': geometry,
                'geometric_contrast': _contrast(origin, band, geometry, reference_actor, actor_width)})
        report['findings'].append(finding)
        if not inner_complete or not outer_complete:
            break
    return report


def describe_posn_boundaries(report, *, focus_item=None):
    """Short authored annotation; findings and qualification limits stay explicit."""
    for finding in report['findings']:
        contrasts = [c for c in finding['action_contrasts'] if focus_item is None or c['item'] == focus_item]
        if focus_item is not None and not contrasts:
            continue
        for record in finding['bands']:
            band = record['predicate_band']
            if not band['complete']:
                continue
            runs = band['row_runs']
            x0, x1 = min(r[1] for r in runs), max(r[2] for r in runs)
            y0, y1 = min(r[0] for r in runs), max(r[0] for r in runs)
            unit = 'row' if band['direction'] in ('up', 'down') else 'column'
            text = (('Partial source audit. ' if not report['complete'] else '')+
                    'Source-derived boundary candidate: '+str(band['count'])+' origins in a '+
                    str(band['thickness'])+'-'+unit+' '+band['edge']+' band, x='+str(x0)+'..'+
                    str(x1-1)+', y='+str(y0)+('..'+str(y1) if y1 != y0 else '')+'. ')
            geometry = record['static_geometry']
            if geometry.get('origin_ray') and not geometry['origin_ray']['static_passable']:
                point = geometry['origin_ray']['first_blocked']['origin']
                text += 'The captured-origin ray meets a static PIC barrier at '+str(tuple(point))+'. '
            if geometry.get('proposal'):
                text += 'Static proposal: '+str(tuple(geometry['proposal']['outside']))+'. '
            contrast = record['geometric_contrast']
            if contrast.get('outside_no_closer_than_inside'):
                text += 'The outside point is no closer under the supplied fixed-pose geometric comparison. '
            return text+'Native reachability and this band outcome are not established by the fixed-route capture.'
    return ('Source audit incomplete. ' if not report['complete'] else '')+'No complete thin posn boundary candidate was derived within this audit.'
