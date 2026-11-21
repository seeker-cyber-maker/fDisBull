"""Evidence-linked, immutable game-coordinate masks and bounded route proposals.

A clear result is relative to the supplied evidence and conditions; it does not
prove that a game will accept a movement. No guest input is performed here.
"""

# First-party extraction from fDisBull 0.34.1: fdisbull/spatial_map.py
# Original file SHA-256: 878344201690fb076ffc15f6ab28d86810490c1e6222fc4d7d8f388020ec245f
# Pure geometry retained; Project/FDB persistence and analyzer imports omitted.

from array import array
import heapq
from copy import deepcopy
import json

from PIL import Image, ImageDraw
from .scene_geometry import dimensions, integer, region


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError('Spatial data requires finite bounded JSON') from error


def _point(p, w, h):
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise ValueError('Expected a coordinate pair')
    integer(p[0], 0, w-1); integer(p[1], 0, h-1)


def _mask(shape, w, h):
    """Compile bounded geometry; row runs may occur at any expression depth."""
    from PIL import ImageChops
    nodes = 0

    def compile_node(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 8 or nodes > 128 or not isinstance(item, dict) or len(item) != 1:
            raise ValueError('Invalid or excessive spatial geometry')
        op, data = next(iter(item.items()))
        if op == 'row_runs':
            if not isinstance(data, list) or len(data) > min(w*h, 100000):
                raise ValueError('Invalid row runs')
            image = Image.new('L', (w, h)); pen = ImageDraw.Draw(image)
            previous = None
            for run in data:
                if not isinstance(run, list) or len(run) != 3:
                    raise ValueError('Row run requires [y,x0,x1]')
                y, x0, x1 = run
                integer(y, 0, h-1); integer(x0, 0, w-1); integer(x1, 1, w)
                if x0 >= x1 or (previous is not None and (y < previous[0] or (y == previous[0] and x0 < previous[2]))):
                    raise ValueError('Row runs must be ordered, nonoverlapping and nonempty')
                pen.line((x0, y, x1-1, y), fill=255); previous = run
            return image
        if op in ('rect', 'polygon'):
            return region(item, w, h)
        if op not in ('union', 'intersection', 'subtract') or not isinstance(data, list):
            raise ValueError('Unknown spatial geometry operation')
        if not 2 <= len(data) <= 64 or (op == 'subtract' and len(data) != 2):
            raise ValueError('Invalid spatial geometry operands')
        image = compile_node(data[0], depth+1)
        combine = {'union': ImageChops.lighter, 'intersection': ImageChops.darker,
                   'subtract': ImageChops.subtract}[op]
        for child in data[1:]:
            image = combine(image, compile_node(child, depth+1))
        return image

    return compile_node(shape)


def validate_spatial_map(doc):
    required={'format','source','space','actor','known','safe','layers','evidence'}
    if (not isinstance(doc, dict) or not required <= set(doc)
            or set(doc)-required-{'coordinate_domains'} or doc['format'] != 'fdisbull-spatial-map-1'):
        raise ValueError('Invalid spatial map schema')
    if len(_encoded(doc)) > 1024*1024: raise ValueError('Spatial map exceeds one MiB')
    source = doc['source']
    if not isinstance(source, dict) or set(source) != {'sha256','context','room','resource'} or any(not isinstance(source[k], str) or not source[k] for k in source):
        raise ValueError('Source requires hash, context, room and resource identity')
    if len(source['sha256']) != 64 or any(c not in '0123456789abcdef' for c in source['sha256']): raise ValueError('Invalid source hash')
    space = doc['space']
    if not isinstance(space, dict) or set(space) != {'name','width','height','unit'} or any(not isinstance(space[k], str) or not space[k] for k in ('name','unit')):
        raise ValueError('Invalid game coordinate space')
    w,h=space['width'],space['height']; dimensions(w,h)
    if 'coordinate_domains' in doc:
        from .scene_domains import validate_coordinate_domains
        domains=validate_coordinate_domains(doc['coordinate_domains'])
        if domains['space'] != {'name':space['name'],'unit':space['unit']}:
            raise ValueError('Map coordinate domains must use the map coordinate space and unit')
        if domains['bounds']['room'] not in (None,[0,0,w,h]):
            raise ValueError('Map room bounds must match its declared dimensions')
    actor=doc['actor']
    if not isinstance(actor,dict) or set(actor) != {'width','height','anchor'}: raise ValueError('Invalid actor footprint')
    integer(actor['width'],1,w); integer(actor['height'],1,h); _point(actor['anchor'],actor['width'],actor['height'])
    layers=doc['layers']
    if not isinstance(layers,list) or len(layers)>128 or (len(layers)+2)*w*h>32*1024*1024: raise ValueError('Spatial mask budget exceeded')
    known=_mask(doc['known'],w,h); safe=_mask(doc['safe'],w,h)
    from PIL import ImageChops
    if ImageChops.subtract(safe,known).getbbox(): raise ValueError('Safe region must be known')
    ids=set()
    for item in layers:
        if not isinstance(item,dict) or set(item)-{'id','kind','area','when','interaction_points'} or not {'id','kind','area'} <= set(item): raise ValueError('Invalid spatial layer')
        if not isinstance(item['id'],str) or not item['id'] or item['id'] in ids or item['kind'] not in ('obstacle','hazard','object','portal'): raise ValueError('Invalid spatial layer identity or kind')
        ids.add(item['id']); layer_mask=_mask(item['area'],w,h)
        if 'when' in item and (not isinstance(item['when'],str) or not item['when']): raise ValueError('Invalid condition key')
        points=item.get('interaction_points',[])
        if not isinstance(points,list) or len(points)>128 or ('interaction_points' in item and item['kind'] not in ('object','portal')): raise ValueError('Invalid interaction points')
        for p in points:
            _point(p,w,h)
            if not layer_mask.getpixel(tuple(p)): raise ValueError('Interaction point must lie inside its zone')
    if not isinstance(doc['evidence'],dict) or not doc['evidence'] or any(not isinstance(k,str) or not k or not isinstance(v,dict) for k,v in doc['evidence'].items()): raise ValueError('Spatial map requires evidence records')
    return doc


def _compile(doc, conditions):
    validate_spatial_map(doc)
    if conditions is None: conditions={}
    if not isinstance(conditions,dict) or any(not isinstance(k,str) or (v is not None and type(v) is not bool) for k,v in conditions.items()): raise ValueError('Conditions must be true, false or unknown')
    w,h=doc['space']['width'],doc['space']['height']
    return (_mask(doc['known'],w,h),_mask(doc['safe'],w,h),[(l,_mask(l['area'],w,h)) for l in doc['layers']],conditions)


def _check(doc, point, compiled):
    w,h=doc['space']['width'],doc['space']['height']; _point(point,w,h)
    actor=doc['actor']; x0=point[0]-actor['anchor'][0]; y0=point[1]-actor['anchor'][1]; x1=x0+actor['width']; y1=y0+actor['height']
    known,safe,layers,conditions=compiled; blocked=[]; unknown=[]
    if x0<0 or y0<0 or x1>w or y1>h: blocked.append('outside_bounds')
    else:
        box=(x0,y0,x1,y1)
        if known.crop(box).getextrema()[0] == 0: unknown.append('unverified_region')
        # A known point outside safe is explicitly non-walkable; unknown stays unknown.
        from PIL import ImageChops
        if ImageChops.subtract(known.crop(box),safe.crop(box)).getbbox(): blocked.append('outside_safe')
        for layer,mask in layers:
            if layer['kind'] not in ('obstacle','hazard') or not mask.crop(box).getbbox(): continue
            state=conditions.get(layer['when']) if 'when' in layer else True
            if state is True: blocked.append(layer['id'])
            elif state is None: unknown.append(layer['id'])
    return {'classification':'blocked' if blocked else 'unknown' if unknown else 'clear','point':list(point),'footprint':deepcopy(actor),'reasons':{'blocked':blocked,'unknown':unknown}}


def spatial_check(doc, point, *, conditions=None):
    """Classify evidence/footprint obstacles; route policy also excludes portals."""
    return _check(doc,point,_compile(doc,conditions))


def _prefix(bits, w, h):
    """Summed-area counts of nonzero cells, with a zero top and left border."""
    stride=w+1
    sums=array('I',[0])*(stride*(h+1))
    for y in range(h):
        total=0; src=y*w; dst=(y+1)*stride; above=y*stride
        for x in range(w):
            total+=bool(bits[src+x]); sums[dst+x+1]=sums[above+x+1]+total
    return sums


def _sum(sums, stride, x0, y0, x1, y1):
    return sums[y1*stride+x1]-sums[y0*stride+x1]-sums[y1*stride+x0]+sums[y0*stride+x0]


def _clear_anchors(doc, compiled, *, block_portals=False):
    """Classify anchors once, treating both unknown and blocked cells as invalid."""
    from PIL import ImageChops
    w,h=doc['space']['width'],doc['space']['height']
    known,safe,layers,conditions=compiled
    valid=ImageChops.darker(known,safe)
    for layer,mask in layers:
        if block_portals and layer['kind'] == 'portal':
            # Approach a portal before a separately qualified room transition.
            # Its condition cannot authorize crossing in this offline slice.
            valid=ImageChops.subtract(valid,mask)
        elif layer['kind'] in ('obstacle','hazard'):
            state=conditions.get(layer['when']) if 'when' in layer else True
            if state is not False: valid=ImageChops.subtract(valid,mask)
    invalid=ImageChops.invert(valid).tobytes()
    sums=_prefix(invalid,w,h); stride=w+1; actor=doc['actor']; ax,ay=actor['anchor']; aw,ah=actor['width'],actor['height']
    anchors=bytearray(w*h)
    for y in range(h):
        y0=y-ay; y1=y0+ah
        if y0<0 or y1>h: continue
        for x in range(w):
            x0=x-ax; x1=x0+aw
            if x0>=0 and x1<=w and _sum(sums,stride,x0,y0,x1,y1)==0:
                anchors[y*w+x]=1
    return anchors


def plan_route(doc, start, goal, *, conditions=None, maxnodes=10000):
    """Propose a cardinal route minimizing (distance, turns), without inputs.

    DotBox replaces the upstream four-neighbor BFS with heading-aware A*.
    Manhattan distance and zero future turns are admissible lower bounds;
    remaining distance and insertion order break ties deterministically.
    A heading is part of each state: equal-cost arrivals at one coordinate can
    have different future turn costs. The first step incurs no turn.

    ``maxnodes`` bounds expanded heading states, not just map coordinates.
    Unknown cells, unresolved obstacles/hazards and every portal footprint are
    unavailable. Long straight legs do not imply uninterruptible input holds.
    """
    integer(maxnodes, 1, 100000)
    compiled = _compile(doc, conditions)
    width, height = doc['space']['width'], doc['space']['height']
    _point(start, width, height)
    _point(goal, width, height)
    anchors = _clear_anchors(doc, compiled, block_portals=True)

    def unavailable(status, visited):
        return {'status': status, 'path': [], 'distance': None,
                'turns': None, 'visited': visited}

    if not anchors[start[1] * width + start[0]] or not anchors[goal[1] * width + goal[0]]:
        return unavailable('endpoint_not_clear', 0)
    start, goal = tuple(start), tuple(goal)
    initial = (*start, 4)
    remaining = abs(start[0] - goal[0]) + abs(start[1] - goal[1])
    frontier = [(remaining, 0, remaining, 0, initial, 0)]
    costs, parents = {initial: (0, 0)}, {initial: None}
    visited, sequence = 0, 0
    directions = ((0, -1), (-1, 0), (1, 0), (0, 1))
    while frontier:
        _, turns, _, _, state, distance = heapq.heappop(frontier)
        if costs[state] != (distance, turns):
            continue
        if visited >= maxnodes:
            return unavailable('budget_exhausted', visited)
        visited += 1
        x, y, heading = state
        if (x, y) == goal:
            path = []
            while state is not None:
                path.append(list(state[:2]))
                state = parents[state]
            return {'status': 'found', 'path': path[::-1], 'distance': distance,
                    'turns': turns, 'visited': visited}
        for next_heading, (dx, dy) in enumerate(directions):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height) or not anchors[ny * width + nx]:
                continue
            following = (nx, ny, next_heading)
            cost = (distance + 1, turns + (heading != 4 and heading != next_heading))
            if following in costs and costs[following] <= cost:
                continue
            costs[following], parents[following] = cost, state
            sequence += 1
            remaining = abs(nx - goal[0]) + abs(ny - goal[1])
            heapq.heappush(frontier, (cost[0] + remaining, cost[1], remaining,
                                      sequence, following, cost[0]))
    return unavailable('no_route', visited)
