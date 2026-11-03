"""Immutable scene manifests, evidence and shared headless object overlays.

Runtime recognizers never cache availability across calls. Definitions are
version-bound; snapshots and observations retain their own run/context identity.
"""
from copy import deepcopy
from functools import wraps
import hashlib
import io
import json
import re
import time
import uuid

from .scene_geometry import dimensions, integer, region
from .scene_values import ObservationReads, before_refs, comparison, evaluate_comparison, compact_result
from .scene_bundles import SceneBundleMixin


def register_scene_observer(session, observer, *, breakpoint_ids):
    """Explicitly allow one local observer's exact hooks during scene waits.

    This changes no debugger run policy. Refresh registration when the observer
    adds/removes hooks; restoration or a version/epoch change invalidates it.
    An observer name in a reply alone is never permission to resume a stop.
    """
    if not isinstance(observer,str) or not 1<=len(observer)<=128:
        raise ValueError('Invalid scene observer name')
    if not isinstance(breakpoint_ids,(list,tuple,set,frozenset)) or len(breakpoint_ids)>10000:
        raise ValueError('Scene observer requires bounded breakpoint IDs')
    if any(not isinstance(x,str) or not 1<=len(x)<=128 for x in breakpoint_ids):
        raise ValueError('Invalid scene observer breakpoint ID')
    registry=getattr(session,'_scene_observers',None)
    if registry is None:session._scene_observers=registry={}
    registry[observer]={'breakpoints':frozenset(breakpoint_ids),'run':session.run_id,
                        'epoch':getattr(session,'_runtime_epoch',None),
                        'version':getattr(session,'version',{}).get('id')}
    return {'observer':observer,'run':session.run_id,'breakpoints':len(set(breakpoint_ids))}


def scene_observer_stop(session, stop):
    """Recognize one explicitly registered observer stop, retaining raw evidence."""
    hits=stop.get('hook_hits')
    if stop.get('outcome')!='hook' or not isinstance(hits,list) or len(hits)!=1:
        return False
    hit=hits[0]
    if not isinstance(hit,dict) or not isinstance(hit.get('observer'),str):return False
    policy=getattr(session,'_scene_observers',{}).get(hit.get('observer'))
    native=stop.get('session')
    if not isinstance(native,dict):return False
    reason=native.get('stop_reason',{})
    if not isinstance(reason,dict):return False
    return bool(policy and stop.get('run')==policy['run']==session.run_id and
                policy['epoch']==getattr(session,'_runtime_epoch',None) and
                policy['version']==getattr(session,'version',{}).get('id') and
                reason.get('kind')=='breakpoint' and reason.get('breakpoint_id') in policy['breakpoints'])

SCENE_DDL = '''
CREATE TABLE IF NOT EXISTS debug_scenes(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 name TEXT NOT NULL, UNIQUE(version,name));
CREATE TABLE IF NOT EXISTS debug_scene_objects(
 id TEXT PRIMARY KEY, scene TEXT NOT NULL REFERENCES debug_scenes(id));
CREATE TABLE IF NOT EXISTS debug_scene_revisions(
 id TEXT PRIMARY KEY, scene TEXT NOT NULL REFERENCES debug_scenes(id),
 parent TEXT REFERENCES debug_scene_revisions(id), created TEXT NOT NULL,
 author TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS debug_scene_evidence(
 revision TEXT NOT NULL REFERENCES debug_scene_revisions(id), object TEXT,
 artifact TEXT NOT NULL REFERENCES debug_artifacts(id),
 PRIMARY KEY(revision,object,artifact));
CREATE TABLE IF NOT EXISTS debug_scene_observations(
 id TEXT PRIMARY KEY, revision TEXT NOT NULL REFERENCES debug_scene_revisions(id),
 run TEXT NOT NULL REFERENCES debug_runs(id), created TEXT NOT NULL,
 kind TEXT NOT NULL, document TEXT NOT NULL);
'''


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def video_signature(metadata):
    result={k:metadata[k] for k in ('width','height','source_bpp','double_width','double_height')}
    if metadata.get('backend') in ('scummvm-agi','scummvm-gob'):
        digest=metadata.get('resource_manifest_sha256')
        layers=metadata.get('resource_layers_sha256')
        if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
            raise ValueError('ScummVM scene requires a resource manifest identity')
        if not isinstance(layers,str) or not re.fullmatch(r'[0-9a-f]{64}',layers):
            raise ValueError('ScummVM scene requires a resource layer identity')
        result.update(backend=metadata['backend'],resource_manifest_sha256=digest,resource_layers_sha256=layers)
        if metadata['backend']=='scummvm-gob':
            for key in ('script_loaded_sha256','script_decompressed_sha256','scummvm_sha256'):
                value=metadata.get(key)
                if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value):
                    raise ValueError('Gob scene requires loaded script and runtime identities')
                result[key]=value
            script=metadata.get('script')
            if not isinstance(script,str) or not script:
                raise ValueError('Gob scene requires a loaded script name')
            result['script']=script.casefold()
    return result


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}', value):
        raise ValueError('Scene/object name must be a simple persistent identifier')
    return value


def context(value):
    if not isinstance(value, dict) or not isinstance(value.get('state'), str) or not value['state']:
        raise ValueError('Object context requires the state it represents')
    if not isinstance(value.get('triggers'), list) or not value['triggers']:
        raise ValueError('Object context requires explicit triggers (unknown may be recorded)')
    encoded(value)


def predicate(value, width, height, depth=0, allow_before=False):
    if depth > 8 or not isinstance(value, dict) or len(value) != 1:
        raise ValueError('Invalid scene predicate')
    op, data = next(iter(value.items()))
    if op == 'constant':
        if type(data) is not bool: raise ValueError('constant requires a boolean')
    elif op in ('all', 'any'):
        if not isinstance(data, list) or not 1 <= len(data) <= 64:
            raise ValueError('Predicate requires 1..64 operands')
        for child in data: predicate(child, width, height, depth+1,allow_before)
    elif op == 'not':
        predicate(data, width, height, depth+1,allow_before)
    elif op == 'pixels':
        if not isinstance(data, dict) or set(data)-{'samples','min_matches','tolerance'}:
            raise ValueError('Invalid pixel predicate')
        samples=data.get('samples')
        if not isinstance(samples,list) or not 1<=len(samples)<=4096:
            raise ValueError('pixels requires 1..4096 samples')
        seen=set()
        for sample in samples:
            if not isinstance(sample,dict) or set(sample)!={'x','y','rgb'}:
                raise ValueError('Pixel samples require x,y,rgb')
            integer(sample['x'],0,width-1);integer(sample['y'],0,height-1)
            coordinate=(sample['x'],sample['y'])
            if coordinate in seen:raise ValueError('Duplicate pixel predicate coordinate')
            seen.add(coordinate)
            if not isinstance(sample['rgb'],list) or len(sample['rgb'])!=3:raise ValueError('Expected RGB triple')
            for channel in sample['rgb']:integer(channel,0,255)
        integer(data.get('min_matches',len(samples)),1,len(samples))
        integer(data.get('tolerance',0),0,255)
    elif op == 'memory':
        if not isinstance(data,dict) or set(data)-{'address','length','hex','mask','cs'}:
            raise ValueError('Invalid scene memory predicate')
        integer(data.get('length'),1,256)
        if not isinstance(data.get('address'),str):raise ValueError('Expected project memory address')
        expected=bytes.fromhex(data.get('hex',''))
        mask=bytes.fromhex(data.get('mask','ff'*len(expected)))
        if len(expected)!=data['length'] or len(mask)!=len(expected):raise ValueError('Memory predicate length mismatch')
    elif op=='runtime_memory':
        if not isinstance(data,dict) or set(data)-{'binding','offset','length','hex','mask'} or not isinstance(data.get('binding'),str) or not data['binding']:
            raise ValueError('Invalid runtime memory predicate')
        integer(data.get('offset',0),0,65535);integer(data.get('length'),1,256)
        expected=bytes.fromhex(data.get('hex',''));mask=bytes.fromhex(data.get('mask','ff'*len(expected)))
        if len(expected)!=data['length'] or len(mask)!=len(expected):raise ValueError('Runtime predicate length mismatch')
    elif op=='compare':comparison(data,allow_before=allow_before)
    else: raise ValueError('Unknown scene predicate '+op)


def points(value):
    op,data=next(iter(value.items()))
    if op=='pixels':return {(p['x'],p['y']) for p in data['samples']}
    if op in ('all','any'):return set().union(*(points(x) for x in data))
    if op=='not':return points(data)
    return set()


def action(value):
    if not isinstance(value,dict):raise ValueError('Expected scene input action')
    kind=value.get('kind')
    if kind=='click':
        if set(value)-{'kind','button','hold_ms'}:raise ValueError('Invalid click action')
        if value.get('button','left') not in ('left','right','middle'):raise ValueError('Invalid mouse button')
        integer(value.get('hold_ms',80),1,1000)
    elif kind in ('press','type'):
        from .keyboard_input import validate_keyboard
        if (kind=='press' and ('key' not in value or 'text' in value)) or (kind=='type' and ('text' not in value or 'key' in value)):
            raise ValueError('Input kind does not match keyboard fields')
        validate_keyboard(**{k:v for k,v in value.items() if k!='kind'})
    else:raise ValueError('Scene actions must use guest click, press or type input')


class SceneProjectMixin(SceneBundleMixin):
    def _scene_snapshot(self, artifact, version):
        row=self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(artifact,)).fetchone()
        if row is None or row['kind']!='screenshot' or row['version']!=version:
            raise ValueError('Scene evidence requires a clean screenshot of the same byte version')
        if hashlib.sha256(row['data']).hexdigest()!=row['sha256']:raise ValueError('Scene snapshot hash mismatch')
        metadata=json.loads(row['metadata'])
        from PIL import Image
        with Image.open(io.BytesIO(row['data'])) as image:
            if image.size!=(metadata['width'],metadata['height']):raise ValueError('Scene snapshot dimensions mismatch')
            image.verify()
        return row,metadata

    def debug_save_scene(self, name, definition, *, parent=None, version=None, author='agent'):
        scene_name=globals()['name'](name);v=self.version(version)['id']
        if not isinstance(author,str) or not 1<=len(author)<=256:raise ValueError('Scene author required')
        if len(encoded(definition))>1024*1024:raise ValueError('Scene exceeds 1 MiB')
        doc=deepcopy(definition)
        if doc.get('format')!='fdisbull-scene-1':raise ValueError('Expected fdisbull-scene-1')
        width,height=doc.get('width'),doc.get('height');dimensions(width,height)
        integer(doc.get('mode_id'),0,(1<<53)-1)
        context(doc.get('context'));predicate(doc.get('match'),width,height)
        if 'content' in doc:
            if not isinstance(doc['content'],dict) or set(doc['content'])!={'requested','displayed','ready'}:raise ValueError('Content requires requested, displayed and ready predicates')
            for value in doc['content'].values():predicate(value,width,height)
        if 'navigation' in doc:
            from .navigation_geometry import validate_navigation
            validate_navigation(doc['navigation'])
            for collider in doc['navigation'].get('colliders',[]):predicate(collider['when'],width,height)
        if 'coordinate_domains' in doc:
            from .scene_domains import validate_coordinate_domains
            validate_coordinate_domains(doc['coordinate_domains'])
        doc.setdefault('exclusive_group','main');globals()['name'](doc['exclusive_group'])
        objects=doc.get('objects')
        if not isinstance(objects,list) or not 1<=len(objects)<=64:raise ValueError('Scene requires 1..64 objects')
        root=self.db.execute('SELECT id FROM debug_scenes WHERE version=? AND name=?',(v,scene_name)).fetchone()
        root_id=root['id'] if root else uuid.uuid4().hex
        previous=self.db.execute('SELECT id FROM debug_scene_revisions WHERE scene=? ORDER BY rowid DESC LIMIT 1',(root_id,)).fetchone()
        if (previous['id'] if previous else None)!=parent:raise ValueError('Scene parent must be the current revision')
        prior=self.debug_scene_info(parent,version=v)['definition'] if parent else {'objects':[]}
        old_by_name={o['name']:o for o in prior['objects']};old_ids={o['id']:o for o in prior['objects']}
        names=set();ids=set();evidence=[]
        reference=doc.get('reference');_,metadata=self._scene_snapshot(reference,v)
        if (metadata['width'],metadata['height'],metadata['mode_id'])!=(width,height,doc['mode_id']):raise ValueError('Scene dimensions/mode differ from reference frame')
        doc['video']=video_signature(metadata)
        evidence.append((None,reference))
        for obj in objects:
            globals()['name'](obj['name']);context(obj.get('context'))
            oid=obj.get('id',old_by_name.get(obj['name'],{}).get('id',uuid.uuid4().hex))
            if oid in ids or (obj.get('id') is not None and oid not in old_ids):raise ValueError('Unknown or duplicate persistent object id')
            obj['id']=oid;ids.add(oid)
            aliases=obj.setdefault('aliases',[])
            if not isinstance(aliases,list) or len(aliases)>32:raise ValueError('Invalid object aliases')
            if oid in old_ids and obj['name']!=old_ids[oid]['name']:
                aliases[:]=list(dict.fromkeys([a for a in aliases if a!=obj['name']]+[old_ids[oid]['name']]))
            for label in [obj['name'],*aliases]:
                globals()['name'](label)
                if label in names:raise ValueError('Duplicate scene object name or alias')
                names.add(label)
            mask=region(obj.get('area'),width,height)
            obj.setdefault('original_area',deepcopy(old_ids.get(oid,{}).get('original_area',obj['area'])))
            region(obj['original_area'],width,height)
            if 'exclusive_group' in obj:globals()['name'](obj['exclusive_group'])
            obj['area_sha256']=hashlib.sha256(mask.tobytes()).hexdigest()
            point=obj.get('point')
            if not isinstance(point,list) or len(point)!=2:raise ValueError('Object needs an explicit interior click point')
            integer(point[0],0,width-1);integer(point[1],0,height-1)
            if not mask.getpixel(tuple(point)):raise ValueError('Click point is outside object action mask')
            for key in ('visible','ready','enabled'):predicate(obj.get(key),width,height)
            action(obj.get('action'))
            predicate(obj.get('outcome'),width,height,allow_before=True)
            if obj.get('outcome_phase','unspecified') not in ('state','interface','persistence','unspecified'):raise ValueError('Invalid outcome phase')
            integer(obj.setdefault('guest_ms',5000),1,120000);integer(obj.setdefault('timeout_ms',5000),1,60000)
            obj.setdefault('evidence',[reference])
            if not isinstance(obj['evidence'],list) or not 1<=len(obj['evidence'])<=32:raise ValueError('Every object needs supporting snapshots')
            for artifact in obj['evidence']:
                self._scene_snapshot(artifact,v);evidence.append((oid,artifact))
        doc.setdefault('handlers',[])
        if not isinstance(doc['handlers'],list) or len(doc['handlers'])>16:raise ValueError('Too many popup handlers')
        for handler in doc['handlers']:
            globals()['name'](handler['name']);predicate(handler['when'],width,height);predicate(handler['outcome'],width,height,allow_before=True)
            action(handler['action'])
            if handler['action']['kind']=='click':
                p=handler.get('point')
                if not isinstance(p,list) or len(p)!=2:raise ValueError('Popup click needs point')
                integer(p[0],0,width-1);integer(p[1],0,height-1)
        all_points=set().union(*(points(p) for p in _predicates(doc)))
        if len(all_points)>4096:raise ValueError('Scene exceeds 4096 probe coordinates')
        digest=hashlib.sha256(encoded(doc)).hexdigest();revision=uuid.uuid4().hex
        from .project import now
        with self.transaction(True):
            # Serialize parent checks with the write, including another connection.
            current=self.db.execute('SELECT id FROM debug_scene_revisions WHERE scene=? ORDER BY rowid DESC LIMIT 1',(root_id,)).fetchone()
            if (current['id'] if current else None)!=parent:raise ValueError('Scene revision changed during save')
            if not root:self.db.execute('INSERT INTO debug_scenes VALUES (?,?,?)',(root_id,v,scene_name))
            for oid in ids:self.db.execute('INSERT OR IGNORE INTO debug_scene_objects VALUES (?,?)',(oid,root_id))
            self.db.execute('INSERT INTO debug_scene_revisions VALUES (?,?,?,?,?,?,?)',(revision,root_id,parent,now(),author,digest,encoded(doc).decode()))
            for oid,artifact in evidence:self.db.execute('INSERT OR IGNORE INTO debug_scene_evidence VALUES (?,?,?)',(revision,oid,artifact))
        return self.debug_scene_info(revision,version=v)

    def debug_scene_info(self, scene, *, version=None):
        v=self.version(version)['id']
        row=self.db.execute('SELECT r.*,s.version,s.name FROM debug_scene_revisions r JOIN debug_scenes s ON s.id=r.scene WHERE s.version=? AND (r.id=? OR s.name=?) ORDER BY r.rowid DESC LIMIT 1',(v,scene,scene)).fetchone()
        if row is None:raise ValueError('Unknown scene revision for this byte version')
        doc=json.loads(row['document'])
        if hashlib.sha256(encoded(doc)).hexdigest()!=row['sha256']:raise ValueError('Scene manifest hash mismatch')
        if 'coordinate_domains' in doc:
            from .scene_domains import validate_coordinate_domains
            validate_coordinate_domains(doc['coordinate_domains'])
        for item in self.db.execute('SELECT DISTINCT artifact FROM debug_scene_evidence WHERE revision=?',(row['id'],)):
            self._scene_snapshot(item['artifact'],v)
        for obj in doc['objects']:
            if hashlib.sha256(region(obj['area'],doc['width'],doc['height']).tobytes()).hexdigest()!=obj['area_sha256']:
                raise ValueError('Scene geometry raster differs from the saved definition')
        return {k:row[k] for k in ('id','scene','version','name','parent','created','author','sha256')}|{'definition':doc}

    def debug_scene_domain_audit(self, scene, *, version=None, max_checks=4096):
        """Inspect stored layout declarations; never grant live movement authority."""
        from .scene_domains import audit_coordinate_domains
        integer(max_checks,1,8192)
        info=self.debug_scene_info(scene,version=version)
        result=dict(format='fdisbull-stored-scene-domain-audit-1',scene_revision=info['id'],
                    manifest_sha256=info['sha256'],reference=info['definition']['reference'],
                    historical_only=True,live_state_verified=False,navigation_authority='none')
        descriptor=info['definition'].get('coordinate_domains')
        if descriptor is None:
            return dict(result,status='not_defined',complete=False,audit=None)
        audit=audit_coordinate_domains(descriptor,max_checks=max_checks)
        return dict(result,status='audited',complete=audit['complete'],audit=audit)

    def debug_scenes(self, *, version=None):
        v=self.version(version)['id']
        return {'version':v,'scenes':[self.debug_scene_info(r['name'],version=v) for r in self.db.execute('SELECT name FROM debug_scenes WHERE version=? ORDER BY name',(v,))]}

    def debug_scene_observations(self, *, revision=None, run=None, limit=100):
        integer(limit,1,1000)
        rows=self.db.execute('SELECT * FROM debug_scene_observations WHERE (? IS NULL OR revision=?) AND (? IS NULL OR run=?) ORDER BY rowid DESC LIMIT ?',(revision,revision,run,run,limit))
        return {'observations':[dict(id=r['id'],revision=r['revision'],run=r['run'],created=r['created'],kind=r['kind'],result=json.loads(r['document'])) for r in rows]}

    def debug_scene_observation(self, observation, *, compact=False):
        row=self.db.execute('SELECT * FROM debug_scene_observations WHERE id=?',(observation,)).fetchone()
        if row is None:raise ValueError('Unknown scene observation')
        if type(compact) is not bool:raise ValueError('compact must be boolean')
        result=dict(json.loads(row['document']),observation=row['id'])
        return dict(id=row['id'],revision=row['revision'],run=row['run'],created=row['created'],
                    historical=True,live_state_verified=False,result=compact_result(result) if compact else result)

    def debug_scene_overlay(self, scene, *, artifact=None, name='scene-overlay.png', grid_step=8, version=None, labels='names'):
        from PIL import Image,ImageDraw,ImageFilter
        from .screenshot_grid import coordinate_grid
        from .external_files import _file_name
        _file_name(name)
        if labels not in ('names','numbers'):raise ValueError('labels must be names or numbers')
        info=self.debug_scene_info(scene,version=version);doc=info['definition']
        artifact=artifact or doc['reference'];row,meta=self._scene_snapshot(artifact,info['version'])
        if video_signature(meta)!=doc['video']:raise ValueError('Overlay frame does not match scene video signature')
        base=bytes(row['data'])
        if grid_step is not None:base,_=coordinate_grid(base,step=grid_step)
        with Image.open(io.BytesIO(base)) as original:image=original.convert('RGBA')
        colors=[(0,255,170),(255,150,50),(140,160,255),(255,100,180)]
        legend=[]
        for index,obj in enumerate(doc['objects']):
            color=colors[index%len(colors)];mask=region(obj['area'],doc['width'],doc['height'])
            tint=Image.new('RGBA',image.size,(*color,0));tint.putalpha(mask.point(lambda x:48 if x else 0))
            image=Image.alpha_composite(image,tint)
            edge=mask.filter(ImageFilter.FIND_EDGES);image.paste((*color,255),(0,0),edge)
            pen=ImageDraw.Draw(image);x,y=obj['point'];pen.ellipse((x-2,y-2,x+2,y+2),fill=(*color,255))
            box=mask.getbbox();text=str(index+1) if labels=='numbers' else obj['name']
            pen.text((box[0]+2,box[1]+2),text,fill=(*color,255),stroke_width=1,stroke_fill=(0,0,0,255))
            legend.append(dict(marker=index+1,object_id=obj['id'],name=obj['name'],aliases=obj['aliases'],point=obj['point'],area_sha256=obj['area_sha256'],color=list(color)))
        stream=io.BytesIO();image.save(stream,format='PNG')
        metadata=dict(source_artifact=artifact,source_sha256=row['sha256'],scene_revision=info['id'],manifest_sha256=info['sha256'],width=doc['width'],height=doc['height'],mode_id=meta['mode_id'],coordinate_space='native_pixels',geometry='rect-half-open; polygon-raster-inclusive',grid_step=grid_step,labels=labels,legend=legend)
        result=self._debug_artifact(row['run'],name,'scene-overlay',stream.getvalue(),metadata)
        if labels=='numbers':
            data=dict(format='fdisbull-scene-legend-1',scene_revision=info['id'],manifest_sha256=info['sha256'],source_artifact=artifact,targets=legend)
            result['legend_artifact']=self._debug_artifact(row['run'],name+'.legend.json','scene-legend',encoded(data),dict(scene_revision=info['id'],manifest_sha256=info['sha256']))['artifact']
        return result


def _predicates(doc):
    yield doc['match']
    yield from doc.get('content',{}).values()
    for collider in doc.get('navigation',{}).get('colliders',[]):yield collider['when']
    for obj in doc['objects']:
        for key in ('visible','ready','enabled','outcome'):yield obj[key]
    for handler in doc.get('handlers',[]):
        yield handler['when'];yield handler['outcome']


class SceneError(ValueError):
    def __init__(self, result):
        self.result=result
        super().__init__('Scene operation '+result['status']+'; observation '+result.get('observation','not stored'))


def _evaluate(spec, session, samples, observations, reads, baseline=None):
    op,data=next(iter(spec.items()))
    if op=='constant':return data
    if op in ('all','any'):
        values=[_evaluate(p,session,samples,observations,reads,baseline) for p in data]
        if None in values:return None
        return all(values) if op=='all' else any(values)
    if op=='not':
        value=_evaluate(data,session,samples,observations,reads,baseline)
        return None if value is None else not value
    if op=='pixels':
        tolerance=data.get('tolerance',0)
        score=sum(all(abs(a-b)<=tolerance for a,b in zip(samples[(p['x'],p['y'])],p['rgb'])) for p in data['samples'])
        matched=score>=data.get('min_matches',len(data['samples']))
        observations.append(dict(kind='pixels',spec=spec,matches=score,matched=matched))
        return matched
    try:
        if op=='compare':
            matched,left,right=evaluate_comparison(data,reads,baseline)
            observations.append(dict(kind='compare',spec=spec,left=left,right=right,matched=matched))
            return matched
        if op=='runtime_memory':actual,capture=reads.read_runtime(data['binding'],data.get('offset',0),data['length'])
        else:actual,capture=reads.read(data['address'],data['length'],data.get('cs'))
        expected=bytes.fromhex(data['hex']);mask=bytes.fromhex(data.get('mask','ff'*len(expected)))
        if len(actual)!=len(expected):raise ValueError('Incomplete scene memory capture')
        matched=all((a&m)==(b&m) for a,b,m in zip(actual,expected,mask,strict=True))
        observations.append(dict(kind='memory',spec=spec,hex=actual.hex(),matched=matched,capture=capture))
        return matched
    except Exception as error:
        observations.append(dict(kind=op,spec=spec,error=str(error)))
        return None


def reply_option(method):
    @wraps(method)
    def wrapped(self,*args,compact=False,**kwargs):
        if type(compact) is not bool:raise ValueError('compact must be boolean')
        try:result=method(self,*args,**kwargs)
        except SceneError as error:
            if compact:raise SceneError(compact_result(error.result)) from error
            raise
        return compact_result(result) if compact else result
    return wrapped


class SceneSessionMixin:
    def scene(self, scene):return SceneHandle(self,scene)

    def frame_probe(self, points):
        if not isinstance(points,list) or len(points)>4096:raise ValueError('Probe requires at most 4096 native points')
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2:raise ValueError('Invalid probe point')
            integer(point[0],0,4095);integer(point[1],0,4095)
        if not self.rpc.capabilities.get('video',{}).get('pixel_probe'):
            raise ValueError('Backend lacks native video.probe; rebuild with the current DOSBox patch')
        result=self.call('video.probe',{'points':[list(p) for p in points]})
        if result.get('format')!='rgb-samples' or len(result.get('samples',[]))!=len(points):raise ValueError('Incomplete native pixel probe')
        for point,sample in zip(points,result['samples'],strict=True):
            if [sample['x'],sample['y']]!=list(point) or len(sample['rgb'])!=3:raise ValueError('Native probe identity mismatch')
            for channel in sample['rgb']:integer(channel,0,255)
        if 'png_base64' in result:raise ValueError('Native probe unexpectedly transferred a screenshot')
        self._event('frame-probe',result)
        return result

    def scene_navigation(self, scene, point, *, footprint=None):return self.scene(scene).navigation_check(point,footprint=footprint)

    def scene_check(self, scene, *, object=None, compact=False):return self.scene(scene).check(object,compact=compact)

    def scene_assert(self, scene, *, object=None, compact=False):return self.scene(scene).assert_current(object,compact=compact)

    def scene_click(self, scene, object, *, handle_popups=False, timeout_ms=None, compact=False):return self.scene(scene).click(object,handle_popups=handle_popups,timeout_ms=timeout_ms,compact=compact)

    def scene_act(self, scene, object, *, handle_popups=False, timeout_ms=None, compact=False):return self.scene(scene).act(object,handle_popups=handle_popups,timeout_ms=timeout_ms,compact=compact)

    def scene_wait(self, scene, *, object=None, guest_ms=5000, timeout_ms=5000, slice_ms=100, compact=False):
        return self.scene(scene).wait(object,guest_ms=guest_ms,timeout_ms=timeout_ms,slice_ms=slice_ms,compact=compact)


class SceneHandle:
    def __init__(self, session, scene):
        self.session=session
        self.info=session.project.debug_scene_info(scene,version=session.version['id'])
        self.revision=self.info['id']

    def _observer_stop(self, stop, previous=None):
        # Keep full native evidence in the project, not repeatedly in replies.
        retained=self._store({'status':'stopped','complete':False,'kind':'scene-observer-stop',
                              'previous_observer_stop':previous,'stop':deepcopy(stop)})
        return {'observation':retained['observation'],'observer':stop['hook_hits'][0]['observer'],
                'breakpoint_id':stop['session']['stop_reason']['breakpoint_id'],
                'guest_elapsed_ms':stop.get('guest_elapsed_ms',0)}

    def _object(self, target):
        found=[o for o in self.info['definition']['objects'] if target in [o['id'],o['name'],*o['aliases']]]
        if len(found)!=1:raise ValueError('Unknown scene object')
        return found[0]

    def object(self, target):return SceneObject(self,target)

    def _observe(self, target=None, extra=None, baseline=None):
        d=self.session;p=d.project
        # Reverify persisted manifest/evidence on each operation, never a cached
        # availability result, including across load_state/camera/layer changes.
        self.info=p.debug_scene_info(self.revision,version=d.version['id']);doc=self.info['definition']
        selected=self._object(target) if target is not None else None
        others=[s for s in p.debug_scenes(version=d.version['id'])['scenes'] if s['scene']!=self.info['scene'] and s['definition']['video']==doc['video']]
        result=dict(scene_revision=self.revision,manifest_sha256=self.info['sha256'],object_id=selected['id'] if selected else None,
                    status='unavailable',complete=False,availability={},evidence=[],conflicts=[],handlers=[],run=d.run_id)
        reads=ObservationReads(d)
        try:
            if d.status()['state']!='stopped':raise ValueError('Scene checks require a paused guest')
            specs=list(_predicates(doc))+[s['definition']['match'] for s in others]+([extra] if extra else [])
            coordinates=sorted(set().union(*(points(v) for v in specs)))
            if len(coordinates)>4096:raise ValueError('Combined scene checks exceed 4096 points')
            frame=d.frame_probe([list(v) for v in coordinates]);result['frame']=frame
            if video_signature(frame)!=doc['video']:
                raise ValueError('Scene video dimensions or mode changed')
            samples={(s['x'],s['y']):s['rgb'] for s in frame['samples']}
            evaluate=lambda v:_evaluate(v,d,samples,result['evidence'],reads,baseline)
            matched=evaluate(doc['match']);result['scene_matched']=matched
            result['content']={k:evaluate(v) for k,v in doc.get('content',{}).items()}
            result['navigation_conditions']={c['id']:evaluate(c['when']) for c in doc.get('navigation',{}).get('colliders',[])}
            missing_required=False
            for other in others:
                if other['definition']['exclusive_group']==doc['exclusive_group']:
                    other_match=evaluate(other['definition']['match'])
                    missing_required|=other_match is None
                    if other_match is True and matched is True:
                        result['conflicts'].append(dict(kind='scene-recognition',scene_revision=other['id']))
            available={}
            for obj in doc['objects']:
                available[obj['id']]={k:evaluate(obj[k]) for k in ('visible','ready','enabled')}
                missing_required|=None in available[obj['id']].values()
            result['objects']=available
            groups={}
            for obj in doc['objects']:
                if obj.get('exclusive_group') and available[obj['id']]['visible'] is True:
                    groups.setdefault(obj['exclusive_group'],[]).append(obj['id'])
            for group,matched_ids in groups.items():
                if len(matched_ids)>1:result['conflicts'].append(dict(kind='object-recognition',group=group,object_ids=matched_ids))
            result['handlers']=[]
            for handler in doc['handlers']:
                value=evaluate(handler['when']);missing_required|=value is None
                if value is True:result['handlers'].append(handler['name'])
            refs=list(before_refs(selected['outcome'])) if selected else []
            if extra is not None:refs+=list(before_refs(extra))
            for handler in doc['handlers']:
                if handler['name'] in result['handlers']:refs+=list(before_refs(handler['outcome']))
            binding=dict(run=d.run_id,version=d.version['id'],scene_revision=self.revision)
            if baseline is not None:
                if any(baseline.get(k)!=v for k,v in binding.items()):raise ValueError('Pre-action baseline context differs')
            elif refs:
                baseline=reads.freeze(refs,dict(binding,frame={k:frame[k] for k in ('frame_id','mode_id','state_revision')}))
            if baseline is not None:
                result['baseline']=baseline
                missing_required|=any('error' in value for value in baseline['values'].values())
            if selected:
                result['availability']=available[selected['id']]
                result['initial_outcome']=evaluate(selected['outcome'])
                missing_required|=result['initial_outcome'] is None
                for obj in doc['objects']:
                    if obj['id']==selected['id']:continue
                    state=available[obj['id']]
                    if state['visible'] is not False and state['enabled'] is not False and region(obj['area'],doc['width'],doc['height']).getpixel(tuple(selected['point'])):
                        result['conflicts'].append(dict(kind='action-area',object_id=obj['id']))
            if extra is not None:result['predicate_matched']=evaluate(extra)
            after=d.frame_probe([])
            if any(after[k]!=frame[k] for k in ('frame_id','mode_id','state_revision')):raise ValueError('Scene observations span different frame/context revisions')
            required=[matched,*result['content'].values(),*result['availability'].values()]
            if extra is not None:required.append(result['predicate_matched'])
            if result['conflicts'] or len(result['handlers'])>1:result['status']='ambiguous'
            elif None in required or missing_required:result['status']='unavailable'
            elif result['handlers']:result['status']='blocked'
            else:result['status']='matched' if all(required) else 'mismatch'
            result['complete']=result['status'] not in ('ambiguous','unavailable')
        except Exception as error:
            result['error']=str(error)
        result['read_statistics']=reads.stats()
        result['memory_captures']=list(reads.captures.values())
        return result

    def navigation_check(self, point, *, footprint=None):
        from .navigation_geometry import navigation_check
        observed=self._observe()
        doc=self.info['definition'].get('navigation')
        if doc is None:raise ValueError('Scene has no navigation definition')
        result=navigation_check(doc,point,conditions=observed.get('navigation_conditions',{}),footprint=footprint)
        if observed['status'] != 'matched':result['classification']='unknown'
        result.update(scene_revision=self.revision,manifest_sha256=self.info['sha256'],observation=observed)
        return result

    def _store(self, result, diagnostic=False):
        d=self.session;p=d.project
        if diagnostic:
            try:
                raw=d.screenshot('scene-diagnostic.png',hooks=False);result['snapshot']=raw['artifact']
                result['snapshot_matches_probe']=raw['metadata'].get('frame_id')==result.get('frame',{}).get('frame_id')
                try:result['overlay']=p.debug_scene_overlay(self.revision,artifact=raw['artifact'],version=d.version['id'])['artifact']
                except Exception as error:result['overlay_error']=str(error)
                result['conflict_overlays']=[]
                for conflict in result.get('conflicts',[]):
                    if 'scene_revision' in conflict:
                        try:
                            overlay=p.debug_scene_overlay(conflict['scene_revision'],artifact=raw['artifact'],name='scene-conflict.png',version=d.version['id'])
                            result['conflict_overlays'].append(overlay['artifact'])
                        except Exception as error:result['overlay_error']=str(error)
            except Exception as error:result['snapshot_error']=str(error)
        oid=uuid.uuid4().hex
        if result.get('baseline') is not None:result['baseline'].setdefault('observation',oid)
        from .project import now
        with p.transaction(True):
            p.db.execute('INSERT INTO debug_scene_observations VALUES (?,?,?,?,?,?)',
                         (oid,self.revision,d.run_id,now(),result['status'],encoded(result).decode()))
        return dict(result,observation=oid)

    @reply_option
    def check(self, object=None):
        result=self._observe(object)
        return self._store(result,diagnostic=result['status']=='ambiguous')

    @reply_option
    def assert_current(self, object=None):
        result=self._observe(object)
        result=self._store(result,diagnostic=result['status']!='matched')
        if result['status']!='matched':raise SceneError(result)
        return result

    def _advance(self, *, guest_ms, timeout_ms):
        hooks=getattr(self.session,'native_hooks_available',True)
        if type(hooks) is not bool:
            raise ValueError('Session must declare Boolean native hook support')
        return self.session.run(guest_ms=guest_ms,timeout_ms=timeout_ms,
                                fast_forward=True,stop_on_hook=hooks)

    def _wait(self, object, predicate, *, guest_ms, timeout_ms, slice_ms):
        integer(guest_ms,1,120000);integer(timeout_ms,1,60000);integer(slice_ms,1,1000)
        started=time.monotonic();elapsed=0;polls=[];observer_stops=[]
        while True:
            result=self._observe(object,extra=predicate)
            if observer_stops:
                result['observer_stops']=deepcopy(observer_stops[-16:])
                result['observer_stop_count']=len(observer_stops)
            polls.append(dict(frame_id=result.get('frame',{}).get('frame_id'),status=result['status']))
            remaining=timeout_ms-int((time.monotonic()-started)*1000)
            if result['status']=='matched' and remaining>0:
                result.update(polls=polls,guest_elapsed_ms=elapsed,host_elapsed_ms=round((time.monotonic()-started)*1000,3))
                return self._store(result)
            if result['status'] in ('ambiguous','unavailable','blocked') or elapsed>=guest_ms or remaining<=0 or len(polls)>=1000:
                result.update(status='timeout' if result['status'] in ('mismatch','matched') else result['status'],complete=False,polls=polls,guest_elapsed_ms=elapsed)
                raise SceneError(self._store(result,diagnostic=True))
            stop=self._advance(guest_ms=min(slice_ms,guest_ms-elapsed),timeout_ms=max(1,remaining))
            elapsed+=stop.get('guest_elapsed_ms',0)
            if scene_observer_stop(self.session,stop):
                observer_stops.append(self._observer_stop(stop,observer_stops[-1]['observation'] if observer_stops else None))
                continue
            if stop['outcome']!='guest_time' or stop.get('hook_hits'):
                result.update(status='stopped',complete=False,stop=stop,polls=polls,guest_elapsed_ms=elapsed)
                raise SceneError(self._store(result,diagnostic=True))

    @reply_option
    def wait(self, object=None, *, guest_ms=5000, timeout_ms=5000, slice_ms=100):
        return self._wait(object,None,guest_ms=guest_ms,timeout_ms=timeout_ms,slice_ms=slice_ms)

    def _input(self, spec, point, frame):
        d=self.session
        if spec['kind']=='click':
            return d.click(*point,button=spec.get('button','left'),hold_ms=spec.get('hold_ms',80),mode_id=frame['mode_id'],frame_id=frame['frame_id'])
        return getattr(d,'keyboard_'+spec['kind'])(**{k:v for k,v in spec.items() if k!='kind'})

    def _input_failure(self, error, queued, handlers, **context):
        failure=(error.result if isinstance(error,SceneError) else
                 dict(status='observation-failed',complete=False,run=self.session.run_id,
                      error=str(error),error_type=type(error).__name__))
        failed=dict(failure,scene_revision=self.revision,input=queued,handlers=handlers,
                    outcome_observation=failure.get('observation'),**context)
        return SceneError(self._store(failed,diagnostic=not isinstance(error,SceneError)))

    @reply_option
    def click(self, object, *, handle_popups=False, timeout_ms=None):
        obj=self._object(object)
        if obj['action']['kind']!='click':raise ValueError('Named click requires a mouse action')
        return self.act(object,handle_popups=handle_popups,timeout_ms=timeout_ms)

    @reply_option
    def act(self, object, *, handle_popups=False, timeout_ms=None):
        if type(handle_popups) is not bool:raise ValueError('handle_popups must be boolean')
        self.info=self.session.project.debug_scene_info(self.revision,version=self.session.version['id'])
        obj=self._object(object);handlers=[];elapsed=0
        if timeout_ms is not None:integer(timeout_ms,1,60000)
        deadline=time.monotonic()+min(timeout_ms or obj['timeout_ms'],obj['timeout_ms'])/1000
        def budgets():
            host=int((deadline-time.monotonic())*1000);guest=obj['guest_ms']-elapsed
            if host<=0 or guest<=0:
                result=dict(status='timeout',complete=False,scene_revision=self.revision,run=self.session.run_id,guest_elapsed_ms=elapsed)
                raise SceneError(self._store(result,diagnostic=True))
            return dict(guest_ms=guest,timeout_ms=host)
        for _ in range(5):
            before=self._observe(object)
            if before['status']=='blocked' and handle_popups and len(before['handlers'])==1:
                handler=next(h for h in self.info['definition']['handlers'] if h['name']==before['handlers'][0])
                checked_handler=self._store(before)
                queued=self._input(handler['action'],handler.get('point'),before['frame'])
                handlers.append(queued)
                # Verify the popup's own postcondition without requiring its
                # containing scene's main-match predicate during dismissal.
                try:
                    outcome=self._wait_outcome(handler['outcome'],baseline=before.get('baseline'),
                                               dismissing_handler=handler['name'],**budgets())
                except Exception as error:
                    raise self._input_failure(error,queued,handlers,
                        handler_name=handler['name'],action_object=obj['id'],action_name=obj['name'],
                        before_observation=checked_handler['observation']) from error
                elapsed+=outcome.get('guest_elapsed_ms',0)
                handlers.append(outcome)
                continue
            break
        else:before['status']='handler-limit';before['complete']=False
        if before['status']!='matched':raise SceneError(self._store(before,diagnostic=True))
        if before.get('initial_outcome') is not False:
            before.update(status='outcome-already-matched' if before.get('initial_outcome') is True else 'unavailable',complete=False)
            raise SceneError(self._store(before,diagnostic=True))
        checked=self._store(before)
        budgets()
        try:
            queued=self._input(obj['action'],obj['point'],before['frame'])
        except Exception as error:
            before.update(status='input-rejected',complete=False,error=str(error))
            raise SceneError(self._store(before,diagnostic=True)) from error
        # Postconditions describe the destination, so its pixels may no longer
        # match the containing scene. Observe only that explicit predicate.
        try:
            outcome=self._wait_outcome(obj['outcome'],baseline=before.get('baseline'),**budgets())
        except Exception as error:
            # Preserve the single queued input even when its destination wait
            # fails. A later observation must never have to replay the action
            # to discover whether an input was submitted.
            raise self._input_failure(error,queued,handlers,action_object=obj['id'],
                        action_name=obj['name'],before_observation=checked['observation']) from error
        outcome['guest_elapsed_ms']+=elapsed
        outcome.update(action_object=obj['id'],outcome_phase=obj.get('outcome_phase','unspecified'),before_observation=checked['observation'],input=queued,handlers=handlers)
        return self._store(outcome)

    def _wait_outcome(self, predicate, *, guest_ms, timeout_ms, baseline=None, dismissing_handler=None):
        started=time.monotonic();elapsed=0;polls=[];observer_stops=[]
        while True:
            result=self._observe(extra=predicate,baseline=baseline)
            if observer_stops:
                result['observer_stops']=deepcopy(observer_stops[-16:])
                result['observer_stop_count']=len(observer_stops)
            # A destination match is independent of the old scene name; keep
            # conflicts, absent captures and blocking modals as explicit failures.
            ok=result.get('predicate_matched') is True and result['status'] not in ('ambiguous','unavailable','blocked')
            # The handler being dismissed remains visible until its queued
            # input executes. It must disappear before success, but must not
            # prevent that execution. A different blocking modal still stops.
            own_handler=(result['status']=='blocked' and dismissing_handler is not None
                         and result.get('handlers')==[dismissing_handler])
            polls.append(dict(frame_id=result.get('frame',{}).get('frame_id'),matched=ok))
            remaining=timeout_ms-int((time.monotonic()-started)*1000)
            if ok and remaining>0:
                result.update(status='matched',complete=True,polls=polls,guest_elapsed_ms=elapsed)
                return result
            if (remaining<=0 or elapsed>=guest_ms or result['status'] in ('ambiguous','unavailable')
                    or result['status']=='blocked' and not own_handler or len(polls)>=1000):
                result.update(status='timeout' if result['status'] in ('mismatch','matched') else result['status'],complete=False,polls=polls,guest_elapsed_ms=elapsed)
                raise SceneError(self._store(result,diagnostic=True))
            stop=self._advance(guest_ms=min(100,guest_ms-elapsed),timeout_ms=max(1,remaining))
            elapsed+=stop.get('guest_elapsed_ms',0)
            if scene_observer_stop(self.session,stop):
                observer_stops.append(self._observer_stop(stop,observer_stops[-1]['observation'] if observer_stops else None))
                continue
            if stop['outcome']!='guest_time' or stop.get('hook_hits'):
                result.update(status='stopped',complete=False,stop=stop,polls=polls,guest_elapsed_ms=elapsed)
                raise SceneError(self._store(result,diagnostic=True))


class SceneObject:
    def __init__(self, handle, target):self.handle=handle;self.target=target;handle._object(target)
    def check(self,**options):return self.handle.check(self.target,**options)
    def click(self, **options):return self.handle.click(self.target,**options)
    def act(self, **options):return self.handle.act(self.target,**options)
    def exists(self):
        result=self.check()
        if result['status'] in ('ambiguous','unavailable'):raise SceneError(result)
        return result.get('scene_matched') is True and result['availability'].get('visible') is True and not result['handlers']
