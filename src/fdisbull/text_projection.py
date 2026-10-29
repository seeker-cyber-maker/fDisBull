"""Public text projection over pinned progressive workflows and live scenes."""
from copy import deepcopy
import hashlib
import hmac
import json
import secrets
import uuid

from .progressive_scenes import _digest, _encoded, _text


def _init(project):
    project.db.execute('CREATE TABLE IF NOT EXISTS debug_text_projections (id TEXT PRIMARY KEY, version INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE(version,name))')
    project.db.execute('CREATE TABLE IF NOT EXISTS debug_text_projection_revisions (id TEXT PRIMARY KEY, projection TEXT NOT NULL REFERENCES debug_text_projections(id), parent TEXT, created TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL)')


def _validate(project, doc, version):
    if not isinstance(doc, dict) or set(doc) != {'format', 'workflow_revision', 'contexts'} or doc['format'] != 'fdisbull-text-projection-1':
        raise ValueError('Invalid text projection format')
    wf = project.debug_workflow_info(doc['workflow_revision'], version=version)
    if wf['id'] != doc['workflow_revision']:
        raise ValueError('Projection must pin a workflow revision')
    actions = {a['name']: a for a in wf['definition']['actions']}
    contexts = doc['contexts']
    if not isinstance(contexts, list) or not contexts or len(contexts) > 128 or len(_encoded(doc)) > 1024 * 1024:
        raise ValueError('Invalid projection contexts')
    ids = set()
    for c in contexts:
        if not isinstance(c, dict) or set(c) != {'id','title','description','scene_revision','partial','objects'}:
            raise ValueError('Invalid public context')
        for key in ('id','title','description','scene_revision'): _text(c[key], 'Context '+key)
        if c['id'] in ids or type(c['partial']) is not bool or not isinstance(c['objects'], list): raise ValueError('Invalid public context')
        ids.add(c['id'])
        scene = project.debug_scene_info(c['scene_revision'], version=version)
        if scene['id'] != c['scene_revision']: raise ValueError('Context must pin a scene revision')
        scene_ids = {o['id'] for o in scene['definition']['objects']}
        object_ids = set()
        for o in c['objects']:
            if not isinstance(o, dict) or set(o) != {'id','label','aliases','description','scene_object','inventory','bindings'}: raise ValueError('Invalid public object')
            for key in ('id','label','description','scene_object'): _text(o[key], 'Object '+key)
            if o['id'] in object_ids or o['scene_object'] not in scene_ids or type(o['inventory']) is not bool or not isinstance(o['aliases'], list) or not isinstance(o['bindings'], list): raise ValueError('Invalid public object')
            object_ids.add(o['id'])
            for a in o['aliases']: _text(a, 'Alias')
        pairs = set()
        for o in c['objects']:
            for b in o['bindings']:
                if not isinstance(b, dict) or set(b) != {'verb','item','action','dispatch'}: raise ValueError('Invalid action binding')
                _text(b['verb'], 'Verb'); _text(b['action'], 'Action')
                if b['verb'] != b['verb'].casefold() or (b['item'] is not None and b['item'] not in object_ids): raise ValueError('Invalid action target')
                key = (b['verb'],o['id'],b['item'])
                if key in pairs: raise ValueError('Duplicate action binding')
                pairs.add(key)
                action = actions.get(b['action'])
                if not action or action['scene_revision'] != c['scene_revision'] or (action['object_id'] is not None and action['object_id'] != o['scene_object']):
                    raise ValueError('Binding must match workflow scene and object')
                dispatch = b['dispatch']
                if not isinstance(dispatch, dict) or dispatch.get('kind') != action['kind']: raise ValueError('Dispatch kind mismatch')
                kind = dispatch['kind']
                if kind == 'scene' and set(dispatch) != {'kind'}: raise ValueError('Invalid scene dispatch')
                if kind == 'movement':
                    allowed = {'macro_set','start','stop','observations','until','progress','settle','guest_ms','timeout_ms','slice_ms','cleanup_guest_ms','max_polls','context','scene','position','target','boundary_tolerance','spatial_map','map_conditions','room_field','target_tolerance'}
                    required = {'macro_set','start','stop','observations','until','progress','settle'}
                    args = dispatch.get('args')
                    if set(dispatch) != {'kind','args'} or not isinstance(args, dict) or not required <= set(args) <= allowed: raise ValueError('Invalid movement dispatch')
                if kind == 'assisted-travel':
                    from .assisted_travel import validate_travel
                    if set(dispatch) != {'kind','plan','timeout_ms'} or type(dispatch['timeout_ms']) is not int or not 1 <= dispatch['timeout_ms'] <= 60000: raise ValueError('Invalid travel dispatch')
                    validate_travel(dispatch['plan'])
                    if dispatch['plan']['scene_revision'] != c['scene_revision']: raise ValueError('Travel scene differs')
                if kind == 'spatial':
                    allowed = {'map_revision','definition','room_field','conditions','zone','actor_recipe','travel_plan','timeout_ms'}
                    args = dispatch.get('args')
                    if set(dispatch) != {'kind','args'} or not isinstance(args,dict) or not {'map_revision','definition'} <= set(args) <= allowed:
                        raise ValueError('Invalid spatial action dispatch')
                    info = project.debug_spatial_map_info(args['map_revision'], version=version)
                    if info['id'] != args['map_revision'] or args['definition'].get('map_revision') != info['id']:
                        raise ValueError('Spatial action must pin its map revision')
    return wf


class TextProjectionProjectMixin:
    def debug_save_text_projection(self, name, definition, *, parent=None, version=None):
        _init(self); _text(name, 'Projection name')
        v = self.version(version)['id']; doc = deepcopy(definition); _validate(self, doc, v)
        from .project import now
        with self.transaction(True):
            row = self.db.execute('SELECT id FROM debug_text_projections WHERE version=? AND name=?', (v,name)).fetchone()
            root = row['id'] if row else uuid.uuid4().hex
            latest = self.db.execute('SELECT id FROM debug_text_projection_revisions WHERE projection=? ORDER BY rowid DESC LIMIT 1', (root,)).fetchone()
            if (latest['id'] if latest else None) != parent: raise ValueError('Projection parent must be current revision')
            if not row: self.db.execute('INSERT INTO debug_text_projections VALUES (?,?,?)', (root,v,name))
            revision = uuid.uuid4().hex
            self.db.execute('INSERT INTO debug_text_projection_revisions VALUES (?,?,?,?,?,?)', (revision,root,parent,now(),_digest(doc),_encoded(doc).decode()))
        return self.debug_text_projection_info(revision, version=v)

    def debug_text_projection_info(self, name, *, version=None):
        _init(self); v = self.version(version)['id']
        row = self.db.execute('SELECT r.*,p.name,p.version FROM debug_text_projection_revisions r JOIN debug_text_projections p ON p.id=r.projection WHERE p.version=? AND (r.id=? OR p.name=?) ORDER BY r.rowid DESC LIMIT 1', (v,name,name)).fetchone()
        if not row: raise ValueError('Unknown text projection')
        doc = json.loads(row['document'])
        if _digest(doc) != row['sha256']: raise ValueError('Text projection hash mismatch')
        _validate(self, doc, v)
        return {k: row[k] for k in ('id','projection','parent','created','sha256','name','version')} | {'definition':doc}


class TextProjectionSessionMixin:
    def text_projection(self, name, resource_root):
        return TextProjectionHandle(self, name, resource_root)

    def _text_channel(self, projection, resource_root):
        from pathlib import Path
        import threading
        from .progressive_scenes import _lock_setup
        with _lock_setup:
            if not hasattr(self,'_text_channel_lock'):
                self._text_channel_lock=threading.RLock()
                self._text_channels={}
        with self._text_channel_lock:
            info=self.project.debug_text_projection_info(projection,version=self.version['id'])
            key=(info['id'],str(Path(resource_root).resolve()))
            if key not in self._text_channels:
                self._text_channels[key]=self.text_projection(info['id'],resource_root)
            return self._text_channels[key]

    def text_observe(self, projection, *, resource_root):
        return self._text_channel(projection,resource_root).observe()

    def text_act(self, projection, request, *, resource_root):
        return self._text_channel(projection,resource_root).act(request)


class TextProjectionHandle:
    def __init__(self, session, name, resource_root):
        self.session = session
        self.info = session.project.debug_text_projection_info(name, version=session.version['id'])
        self.workflow = session.workflow(self.info['definition']['workflow_revision'], resource_root=resource_root)
        self.lock = self.workflow.lock
        self.secret = secrets.token_bytes(32)

    def _opaque(self, data):
        return hmac.new(self.secret, _encoded(data), hashlib.sha256).hexdigest()

    def _read(self):
        if getattr(self.session, '_player_checkpoint_failed', False): return None
        self.info = self.session.project.debug_text_projection_info(self.info['id'], version=self.session.version['id'])
        self.workflow._fresh()
        matched = []; frames = []
        for c in self.info['definition']['contexts']:
            check = self.session.scene(c['scene_revision']).check()
            if check.get('complete') is not True or check.get('status') not in ('matched','mismatch'): return None
            frame = check.get('frame')
            if not isinstance(frame, dict) or any(k not in frame for k in ('frame_id','mode_id','state_revision')): return None
            frames.append({k: frame[k] for k in ('frame_id','mode_id','state_revision')})
            if check['status'] == 'matched': matched.append((c,check))
        if len(matched) != 1 or any(f != frames[0] for f in frames): return None
        c, check = matched[0]
        objects = check.get('objects')
        if not isinstance(objects, dict): return None
        public_objects = []; inventory = []; mapping = {}
        allow_travel = getattr(self.session, '_allow_assisted_travel', True)
        policy = {'assisted_travel':allow_travel,
                  'spatial_mode':getattr(self.session,'_spatial_mode','assisted'),
                  'fair_play':getattr(self.session,'_fair_play',False)}
        for o in c['objects']:
            availability = objects.get(o['scene_object'])
            if not isinstance(availability, dict) or any(availability.get(k) not in (True,False) for k in ('visible','ready','enabled')): return None
            if availability['visible'] is not True: continue
            bindings = [b for b in o['bindings'] if allow_travel or b['dispatch']['kind'] != 'assisted-travel']
            if o['bindings'] and not bindings: continue
            o = dict(o, bindings=bindings)
            oid = self._opaque(['object',c['id'],o['id']]); mapping[oid] = o
            public = {'id':oid,'label':o['label'],'aliases':o['aliases'],'description':o['description'],
                      'verbs':list(dict.fromkeys(b['verb'] for b in o['bindings']))}
            (inventory if o['inventory'] else public_objects).append(public)
        freshness = {'projection':self.info['id'],'workflow':self.workflow.revision,'context':c['id'],
                     'frame':frames[0], 'run':getattr(self.session,'run_id',None),
                     'epoch':getattr(self.session,'_runtime_epoch',None), 'runtime_load':getattr(self.session,'runtime_load',None),
                     'policy': policy,
                     'version':self.session.version['id'], 'closed':getattr(self.session,'closed',False), 'objects':objects}
        token = self._opaque(['token',freshness])
        obs = {'complete':True,'context':{'id':self._opaque(['context',c['id']]),'token':token,'title':c['title'],'description':c['description']},
               'objects':public_objects,'inventory':inventory,'coverage':{'partial':c['partial']},
               'policy': policy}
        return obs, c, mapping, check

    def observe(self):
        with self.lock:
            try:
                result = self._read()
                return result[0] if result else {'complete':False}
            except Exception:
                return {'complete':False}

    def save(self, slot='live'):
        from .player_checkpoints import save
        return save(self,slot)

    def load(self, checkpoint='live'):
        from .player_checkpoints import load
        return load(self,checkpoint,prepare_guest_ms=getattr(self,'checkpoint_prepare_guest_ms',100),
                    timeout_ms=getattr(self,'checkpoint_timeout_ms',10000))

    def act(self, request):
        def result(status, complete, message): return {'status':status,'complete':complete,'message':message}
        with self.lock:
            try:
                current = self._read()
                if not current: return result('incomplete',False,'Observation unavailable.')
                obs, c, mapping, check = current
                if not isinstance(request, dict) or request.get('context_token') != obs['context']['token']:
                    return result('rejected',True,'Context changed.')
                target = mapping.get(request.get('target')); item = mapping.get(request.get('item')) if request.get('item') is not None else None
                if not target or (request.get('item') is not None and not item): return result('incomplete',False,'Action unavailable.')
                availability = check['objects'].get(target['scene_object'], {})
                if any(availability.get(k) is not True for k in ('visible','ready','enabled')):
                    return result('rejected',True,'Action unavailable.')
                matches = [b for b in target['bindings'] if b['verb'] == request.get('verb') and b['item'] == (item['id'] if item else None)]
                if len(matches) != 1: return result('incomplete',False,'Action unavailable.')
                binding = matches[0]
                def dispatch(contract, scene, check):
                    current = self._read()
                    if not current or current[0]['context']['token'] != obs['context']['token']: raise ValueError('Context changed')
                    availability = (check.get('availability',{}) if contract['object_id'] is not None
                                    else current[3]['objects'].get(target['scene_object'], {}))
                    if any(availability.get(k) is not True for k in ('visible','ready','enabled')): raise ValueError('Action unavailable')
                    descriptor = binding['dispatch']; kind = descriptor['kind']
                    if kind == 'scene': return scene.act(contract['object_id'])
                    if kind == 'movement': return self.session.move(**deepcopy(descriptor['args']))
                    if kind == 'spatial': return self.session.spatial_action(**deepcopy(descriptor['args']))
                    return self.session.assisted_travel(deepcopy(descriptor['plan']), timeout_ms=descriptor['timeout_ms'])
                outcome = self.workflow.execute(binding['action'], dispatch)['result']
                kind = binding['dispatch']['kind']
                success = isinstance(outcome,dict) and outcome.get('complete') is True and ((kind == 'scene' and outcome.get('status') == 'matched') or (kind != 'scene' and outcome.get('ok') is True))
                response = result('success',True,'Action completed.') if success else result('incomplete',False,'Action outcome incomplete.')
                if kind in ('movement', 'assisted-travel'):
                    response['assistance'] = {'kind': kind}
                if kind == 'spatial':
                    response['assistance'] = {'kind': 'spatial', 'mode':getattr(self.session,'_spatial_mode','assisted')}
                return response
            except Exception:
                return result('incomplete',False,'Action unavailable or incomplete.')


def serve_stream(backend, reader, writer):
    """Serve requests sequentially; never serialize private exceptions."""
    limit = 1024 * 1024
    while True:
        line = reader.readline(limit + 1)
        if not line:
            return
        if not line.endswith('\n') or len(line.encode('utf-8')) > limit:
            writer.write('{"complete":false}\n'); writer.flush()
            return
        try:
            request = json.loads(line)
            if not isinstance(request,dict): raise ValueError('Invalid request')
            if request.get('op') == 'observe' and set(request) == {'op'}: response = backend.observe()
            elif request.get('op') == 'act' and set(request) == {'op','action'}: response = backend.act(request['action'])
            elif request.get('op') == 'save' and set(request) in ({'op'}, {'op','slot'}): response = backend.save(request.get('slot','live'))
            elif request.get('op') == 'load' and set(request) in ({'op'}, {'op','checkpoint'}): response = backend.load(request.get('checkpoint','live'))
            else: raise ValueError('Invalid request')
            encoded = json.dumps(response, separators=(',',':')) + '\n'
            if len(encoded.encode('utf-8')) > limit: raise ValueError('Response exceeds limit')
        except Exception:
            encoded = '{"complete":false}\n'
        writer.write(encoded); writer.flush()
