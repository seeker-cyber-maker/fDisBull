"""Pure, bounded point-domain audits of thin rectangle-complement edge bands.

This derives static predicate transitions, not movement, reachability, intent,
physical interaction range or native execution. Bands are not claims about
isolated connected components of the full two-dimensional complement.
"""
from hashlib import sha256

from .scene_geometry import dimensions, integer, region


def audit_rectangle_boundary(rectangle, *, width, height, convention,
                             directions=('down',), start=None,
                             reachable_mask=None, max_band_width=1,
                             max_checks=1_000_000, max_runs=256):
    """Report thin terminal complement bands with adjacent origin witnesses.

    ``convention`` must be ``inclusive`` or ``half-open``. Rectangles may extend
    beyond the domain and are clipped before using the shared half-open region
    geometry. Empty inside/complement regions are valid. Coordinates denote
    points; no actor footprint is silently added to the rectangle predicate.

    Directions are up/down/left/right, in caller order. RLE entries are
    ``[y, x0, x1)``. ``start`` selects a perpendicular witness projection; it
    does not establish a path. An optional immutable width*height byte mask
    marks caller-supplied reachable origins with nonzero values. Its presence
    is reported separately and never establishes native reachability.

    Cell and RLE budgets apply globally. Partial scans retain prior runs and
    set complete:false. A derived witness may remain available on a partial
    scan; its geometry is independent of the enumerated cell/mask counts.
    """
    dimensions(width, height)
    if convention not in ('inclusive', 'half-open'):
        raise ValueError('Rectangle convention must be inclusive or half-open')
    if not isinstance(rectangle, (tuple, list)) or len(rectangle) != 4:
        raise ValueError('Rectangle requires four declared coordinates')
    for value in rectangle:
        integer(value, -(1 << 63), (1 << 63)-1)
    left, top, right, bottom = rectangle
    if left > right or top > bottom:
        raise ValueError('Reversed rectangle')
    if convention == 'inclusive':
        right += 1
        bottom += 1
    if (not isinstance(directions, (tuple, list)) or not 1 <= len(directions) <= 4
            or any(type(d) is not str or d not in ('up', 'down', 'left', 'right') for d in directions)
            or len(set(directions)) != len(directions)):
        raise ValueError('Expected distinct cardinal step directions')
    if start is not None:
        if not isinstance(start, (tuple, list)) or len(start) != 2:
            raise ValueError('Start requires x,y')
        integer(start[0], 0, width-1)
        integer(start[1], 0, height-1)
    if reachable_mask is not None and (type(reachable_mask) is not bytes
                                      or len(reachable_mask) != width*height):
        raise ValueError('Reachable mask requires one immutable byte per domain point')
    integer(max_band_width, 1, max(width, height))
    integer(max_checks, 1, 1_000_000)
    integer(max_runs, 1, 4096)

    x0, x1 = (max(0, min(width, x)) for x in (left, right))
    y0, y1 = (max(0, min(height, y)) for y in (top, bottom))
    inside_count = (x1-x0)*(y1-y0)
    result = {'format': 'fdisbull-scene-boundary-audit-1',
              'status': 'static_candidates_only', 'complete': True, 'examined': 0,
              'domain': {'width': width, 'height': height},
              'rectangle': {'convention': convention, 'input': list(rectangle),
                            'half_open': [left, top, right, bottom],
                            'clipped_half_open': [x0, y0, x1, y1]},
              'predicate': 'outside_rectangle', 'directions': list(directions),
              'complement_count': width*height-inside_count, 'bands': [],
              'component_analysis': 'not_performed',
              'scope': 'Static point-predicate edge bands; no physical range, intent or native execution claim.'}
    if not inside_count:
        return result
    # Construct only the nonempty inside region. The complement may be empty;
    # region(subtract(...)) would reject that valid constant-false predicate.
    inside = region({'rect': [x0, y0, x1, y1]}, width, height).tobytes()
    specifications = {
        'up': ('top', y0, (x0, 0, x1, y0)),
        'down': ('bottom', height-y1, (x0, y1, x1, height)),
        'left': ('left', x0, (0, y0, x0, y1)),
        'right': ('right', width-x1, (x1, y0, width, y1)),
    }
    runs_used = 0
    mask_sha = sha256(reachable_mask).hexdigest() if reachable_mask is not None else None
    for direction in directions:
        edge, thickness, (bx0, by0, bx1, by1) = specifications[direction]
        if not 0 < thickness <= max_band_width:
            continue
        vertical = direction in ('up', 'down')
        low, high = (x0, x1) if vertical else (y0, y1)
        selected = (low+high-1)//2 if start is None else start[0 if vertical else 1]
        projected = max(low, min(high-1, selected))
        selection = ('midpoint' if start is None else 'start_projection'
                     if selected == projected else 'clamped_start_projection')
        witness = {
            'up': ([projected, y0], [projected, y0-1]),
            'down': ([projected, y1-1], [projected, y1]),
            'left': ([x0, projected], [x0-1, projected]),
            'right': ([x1-1, projected], [x1, projected]),
        }[direction]
        within, outside = witness
        band = {'kind': 'terminal-domain-edge-complement-band', 'edge': edge,
                'direction': direction, 'thickness': thickness, 'count': 0,
                'row_runs': [], 'complete': True,
                'witness': {'inside': within, 'outside': outside, 'selection': selection},
                'reachability': {'status': 'unknown'}}
        reachable_count = 0
        for y in range(by0, by1):
            if runs_used == max_runs:
                band['complete'] = False
                break
            row = None
            for x in range(bx0, bx1):
                if result['examined'] == max_checks:
                    band['complete'] = False
                    break
                result['examined'] += 1
                if inside[y*width+x]:
                    raise ValueError('Rectangle complement geometry disagrees')
                if row is None:
                    row = [y, x, x+1]
                    band['row_runs'].append(row)
                    runs_used += 1
                else:
                    row[2] = x+1
                band['count'] += 1
                if reachable_mask is not None:
                    reachable_count += bool(reachable_mask[y*width+x])
            if not band['complete']:
                break
        if reachable_mask is not None:
            band['reachability'] = {
                'status': 'present_in_supplied_mask' if reachable_count else
                          'absent_from_supplied_mask' if band['complete'] else 'unknown',
                'count': reachable_count, 'mask_sha256': mask_sha,
                'inside_witness_in_mask': bool(reachable_mask[within[1]*width+within[0]]),
                'outside_witness_in_mask': bool(reachable_mask[outside[1]*width+outside[0]]),
                'native_validation': 'not_established'}
        if band['count']:
            result['bands'].append(band)
        if not band['complete']:
            result['complete'] = False
            break
    return result
