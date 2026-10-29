"""Evidence-linked, immutable game-coordinate masks and bounded route proposals.

A clear result is relative to the supplied evidence and conditions; it does not
prove that a game will accept a movement. No guest input is performed here.
"""
from collections import deque
from array import array
import heapq
from copy import deepcopy
import hashlib
import io
import json
import sqlite3
import uuid

from PIL import Image, ImageDraw
from .scene_geometry import dimensions, integer, region
from .il_recovery import _verify_sources


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


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
    if not isinstance(doc, dict) or set(doc) != {'format','source','space','actor','known','safe','layers','evidence'} or doc['format'] != 'fdisbull-spatial-map-1':
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


def _clear_anchors(doc, compiled):
    """Classify anchors once, treating both unknown and blocked cells as invalid."""
    from PIL import ImageChops
    w,h=doc['space']['width'],doc['space']['height']
    known,safe,layers,conditions=compiled
    valid=ImageChops.darker(known,safe)
    for layer,mask in layers:
        if layer['kind'] in ('obstacle','hazard'):
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


def candidate_points(doc, *, zone=None, origin=None, limit=32, clearance=0, conditions=None):
    integer(limit,1,1024); integer(clearance,0,64)
    compiled=_compile(doc,conditions); w,h=doc['space']['width'],doc['space']['height']
    if origin is not None: _point(origin,w,h)
    mask=None
    if zone is not None:
        match=[(l,m) for l,m in compiled[2] if l['id']==zone and l['kind'] in ('object','portal')]
        if not match: raise ValueError('Unknown interaction zone')
        layer,zone_mask=match[0]
        if 'when' in layer and compiled[3].get(layer['when']) is not True: return []
        mask=zone_mask.tobytes()
    if 2*clearance+1>w or 2*clearance+1>h: return []
    anchors=_clear_anchors(doc,compiled)
    # Prefix invalid anchor positions, so a whole clearance square is O(1).
    sums=_prefix(bytes(1-v for v in anchors),w,h) if clearance else None
    stride=w+1
    def eligible():
        for y in range(clearance,h-clearance):
            for x in range(clearance,w-clearance):
                i=y*w+x
                if not anchors[i] or (mask is not None and not mask[i]): continue
                if sums is not None and _sum(sums,stride,x-clearance,y-clearance,x+clearance+1,y+clearance+1): continue
                yield [x,y]
    if origin is None:
        from itertools import islice
        return list(islice(eligible(),limit))
    return heapq.nsmallest(limit,eligible(),key=lambda p:(abs(p[0]-origin[0])+abs(p[1]-origin[1]),p[1],p[0]))


def plan_route(doc, start, goal, *, conditions=None, maxnodes=10000):
    integer(maxnodes,1,100000); compiled=_compile(doc,conditions); w,h=doc['space']['width'],doc['space']['height']
    _point(start,w,h); _point(goal,w,h)
    anchors=_clear_anchors(doc,compiled)
    if not anchors[start[1]*w+start[0]] or not anchors[goal[1]*w+goal[0]]: return {'status':'endpoint_not_clear','path':[],'visited':0}
    start=tuple(start); goal=tuple(goal); queue=deque([start]); parents={start:None}; visited=0
    while queue:
        if visited>=maxnodes: return {'status':'budget_exhausted','path':[],'visited':visited}
        p=queue.popleft(); visited+=1
        if p==goal:
            path=[]
            while p is not None: path.append(list(p)); p=parents[p]
            return {'status':'found','path':path[::-1],'visited':visited}
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            q=(p[0]+dx,p[1]+dy)
            if 0<=q[0]<w and 0<=q[1]<h and q not in parents and anchors[q[1]*w+q[0]]: parents[q]=p; queue.append(q)
    return {'status':'no_route','path':[],'visited':visited}


def render_spatial_map(doc, *, conditions=None):
    known,safe,layers,conditions=_compile(doc,conditions); w,h=doc['space']['width'],doc['space']['height']
    image=Image.new('RGB',(w,h),(128,128,128)); image.paste((225,225,225),mask=known); image.paste((72,168,88),mask=safe)
    from PIL import ImageFilter, ImageChops
    for layer,mask in layers:
        state=conditions.get(layer['when']) if 'when' in layer else True
        if state is False: continue
        if layer['kind'] in ('obstacle','hazard'):
            image.paste((128,128,128) if state is None else ((137,89,54) if layer['kind']=='obstacle' else (50,100,200)),mask=mask)
        else:
            outline=ImageChops.subtract(mask,mask.filter(ImageFilter.MinFilter(3)))
            image.paste((255,210,0) if layer['kind']=='object' else (180,80,210),mask=outline)
    out=io.BytesIO(); image.save(out,format='PNG')
    return {'png':out.getvalue(),'width':w,'height':h,'legend':{'unknown':'gray','known_non_safe':'light gray','safe':'green','obstacle':'brown','hazard':'blue','object':'yellow outline','portal':'purple outline'}}



def _verify_map_evidence(project, document, version):
    """Check stored evidence byte identity, not the accuracy of a derived mask."""
    _verify_sources(project, document, version)
    verified = {}
    for item in document['evidence'].values():
        if 'artifact' not in item:
            continue
        ident = item['artifact']; claimed = item.get('sha256')
        if (not isinstance(ident, str) or not ident or not isinstance(claimed, str)
                or len(claimed) != 64 or any(c not in '0123456789abcdef' for c in claimed)):
            raise ValueError('Screenshot evidence requires an artifact ID and SHA-256')
        if ident not in verified:
            try:
                row = project.db.execute('''SELECT a.kind,a.sha256,a.data,r.version
                    FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (ident,)).fetchone()
            except sqlite3.OperationalError as exc:
                raise ValueError('Screenshot evidence is unavailable') from exc
            if row is None or row['version'] != version or row['kind'] not in ('screenshot', 'screenshot-grid'):
                raise ValueError('Screenshot evidence must belong to the selected project version')
            data = bytes(row['data'])
            if len(data) > 16*1024*1024 or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('Stored screenshot evidence hash mismatch or size limit exceeded')
            verified[ident] = row['sha256']
        if verified[ident] != claimed:
            raise ValueError('Screenshot evidence claimed hash mismatch')


def save_spatial_map(project,name,document,*,version=None,parent=None,author='agent'):
    validate_spatial_map(document)
    if not isinstance(name,str) or not 1<=len(name)<=128 or not isinstance(author,str) or not author: raise ValueError('Revision requires name and author')
    encoded=_encoded(document)
    project.db.execute('''CREATE TABLE IF NOT EXISTS spatial_maps (id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id), name TEXT NOT NULL, parent TEXT REFERENCES spatial_maps(id), sha256 TEXT NOT NULL, author TEXT NOT NULL, document TEXT NOT NULL)''')
    with project.transaction(True):
        v=project.version(version)
        if document['source']['sha256'] != v['sha256']: raise ValueError('Source hash differs from project version')
        _verify_map_evidence(project,document,v['id'])
        previous=project.db.execute('SELECT * FROM spatial_maps WHERE version=? AND name=? ORDER BY rowid DESC LIMIT 1',(v['id'],name)).fetchone()
        if previous is not None and parent != previous['id']: raise ValueError('Updating map requires its current parent')
        if previous is None and parent is not None: raise ValueError('First map cannot have a parent')
        digest=hashlib.sha256(encoded).hexdigest()
        if previous is not None and previous['sha256']==digest: return load_spatial_map(project,previous['id'],version=v['id'])
        ident=uuid.uuid4().hex
        project.db.execute('INSERT INTO spatial_maps VALUES (?,?,?,?,?,?,?)',(ident,v['id'],name,parent,digest,author,encoded.decode()))
    return load_spatial_map(project,ident,version=v['id'])


def load_spatial_map(project,revision,*,version=None):
    v=project.version(version)
    try: row=project.db.execute('SELECT * FROM spatial_maps WHERE id=? AND version=?',(revision,v['id'])).fetchone()
    except sqlite3.OperationalError as exc: raise ValueError('No stored spatial maps') from exc
    if row is None: raise ValueError('Unknown spatial map revision')
    doc=json.loads(row['document']); validate_spatial_map(doc)
    if hashlib.sha256(_encoded(doc)).hexdigest()!=row['sha256']: raise ValueError('Stored spatial map hash mismatch')
    if doc['source']['sha256']!=v['sha256']: raise ValueError('Source hash differs from project version')
    _verify_map_evidence(project,doc,v['id'])
    return {k:row[k] for k in ('id','version','name','parent','sha256','author')} | {'document':deepcopy(doc)}
