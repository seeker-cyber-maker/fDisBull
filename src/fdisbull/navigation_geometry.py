"""Game-space navigation geometry; no guest input or state changes."""
from .scene_geometry import dimensions, integer, region


def validate_navigation(doc):
    if not isinstance(doc, dict) or set(doc) - {'space', 'width', 'height', 'actor', 'walkable', 'colliders', 'portals', 'anchors', 'provenance'}:
        raise ValueError('Invalid navigation definition')
    if not isinstance(doc.get('space'), str) or not doc['space'] or doc['space'] in ('native', 'screen', 'native-frame'):
        raise ValueError('Navigation requires an explicitly named game coordinate space')
    w, h = doc.get('width'), doc.get('height')
    dimensions(w, h)
    actor = doc.get('actor')
    if not isinstance(actor, dict) or set(actor) != {'width', 'height', 'anchor'}:
        raise ValueError('Actor requires width, height and anchor')
    integer(actor['width'], 1, w); integer(actor['height'], 1, h)
    _point(actor['anchor'], actor['width'], actor['height'])
    region(doc.get('walkable'), w, h)
    colliders = doc.get('colliders', [])
    if not isinstance(colliders, list) or len(colliders) > 128 or (len(colliders)+1)*w*h > 32*1024*1024:
        raise ValueError('Invalid navigation colliders')
    ids = set()
    for item in colliders:
        if not isinstance(item, dict) or set(item) != {'id', 'area', 'when'} or not isinstance(item['id'], str) or not item['id'] or item['id'] in ids:
            raise ValueError('Collider requires unique id, area and predicate')
        ids.add(item['id']); region(item['area'], w, h)
        if not isinstance(item['when'], dict) or len(item['when']) != 1: raise ValueError('Collider requires predicate')
    for key in ('anchors', 'portals'):
        items = doc.get(key, [])
        if not isinstance(items, list) or len(items) > 128: raise ValueError('Invalid navigation ' + key)
        names = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or item['id'] in names:
                raise ValueError('Navigation locations require unique ids')
            names.add(item['id']); _point(item.get('point'), w, h)
    provenance = doc.get('provenance')
    if not isinstance(provenance, dict) or not all(k in provenance for k in ('extraction_rule', 'source_facts', 'evidence_status')):
        raise ValueError('Navigation requires extraction rule, source facts and evidence status')
    if not isinstance(provenance['extraction_rule'], str) or not provenance['extraction_rule'] or not isinstance(provenance['source_facts'], list) or not provenance['source_facts'] or not isinstance(provenance['evidence_status'], str) or not provenance['evidence_status']:
        raise ValueError('Invalid navigation provenance')
    return doc


def _point(point, width, height):
    if not isinstance(point, (list, tuple)) or len(point) != 2: raise ValueError('Expected coordinate pair')
    integer(point[0], 0, width-1); integer(point[1], 0, height-1)


def _compile(doc, conditions, footprint):
    validate_navigation(doc)
    w, h = doc['width'], doc['height']
    actor = footprint if footprint is not None else doc['actor']
    if not isinstance(actor, dict) or set(actor) != {'width', 'height', 'anchor'}: raise ValueError('Invalid actor footprint')
    integer(actor['width'], 1, w); integer(actor['height'], 1, h); _point(actor['anchor'], actor['width'], actor['height'])
    conditions = {} if conditions is None else conditions
    if not isinstance(conditions, dict) or any(v is not None and type(v) is not bool for v in conditions.values()): raise ValueError('Conditions must be true, false or unknown')
    walkable=region(doc['walkable'],w,h)
    colliders=[(c['id'],region(c['area'],w,h)) for c in doc.get('colliders',[])]
    return actor,conditions,walkable,colliders


def _check(doc, point, compiled):
    actor,conditions,walkable,colliders=compiled
    w,h=doc['width'],doc['height'];_point(point,w,h)
    x0,y0=point[0]-actor['anchor'][0],point[1]-actor['anchor'][1]
    x1,y1=x0+actor['width'],y0+actor['height']
    clipped=(max(0,x0),max(0,y0),min(w,x1),min(h,y1))
    outside=x0<0 or y0<0 or x1>w or y1>h
    if not outside: outside=walkable.crop((x0,y0,x1,y1)).getextrema()[0] == 0
    blocked,unknown=[],[]
    for cid,mask in colliders:
        if clipped[0]<clipped[2] and clipped[1]<clipped[3] and mask.crop(clipped).getbbox() is not None:
            state=conditions.get(cid)
            if state is True:blocked.append(cid)
            elif state is None:unknown.append(cid)
    classification='blocked' if outside or blocked else 'unknown' if unknown else 'clear'
    return dict(space=doc['space'],point=list(point),footprint=actor,classification=classification,
                outside_walkable=outside,blocked_colliders=blocked,unknown_colliders=unknown,conditions=dict(conditions))


def navigation_check(doc, point, *, conditions=None, footprint=None):
    return _check(doc,point,_compile(doc,conditions,footprint))


def route_first_boundary(doc, points, *, conditions=None, footprint=None):
    if not isinstance(points,(list,tuple)) or not 1<=len(points)<=4096:raise ValueError('Route requires 1..4096 points')
    compiled=_compile(doc,conditions,footprint)
    for point in points:_point(point,doc['width'],doc['height'])
    if sum(max(abs(b[0]-a[0]),abs(b[1]-a[1])) for a,b in zip(points,points[1:]))>65536:
        raise ValueError('Route exceeds 65536 discrete steps')
    for index,endpoint in enumerate(points):
        start=points[index-1] if index else endpoint
        dx,dy=endpoint[0]-start[0],endpoint[1]-start[1]
        steps=max(abs(dx),abs(dy))
        for step in range(1 if index else 0,steps+1):
            point=[start[0]+round(dx*step/steps),start[1]+round(dy*step/steps)] if steps else list(endpoint)
            result=_check(doc,point,compiled)
            if result['classification']!='clear':return dict(index=index,result=result)
    return None
