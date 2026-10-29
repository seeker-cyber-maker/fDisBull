"""Immutable, resource-bound partial scene workflows for a single live controller."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import threading
import uuid

from .scene_bundles import identity


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def resource_inventory(root, *, engine, profile, adapter):
    """Hash every regular file in a caller-supplied resource tree; never copy it."""
    for value in (engine, profile, adapter):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Engine, profile and adapter identities are required')
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Resource root must be a directory, not a symlink')
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Resource inventory does not follow symlinks')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Resource inventory requires regular files')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(chunk)
        files.append({'path': path.relative_to(root).as_posix(), 'sha256': h.hexdigest()})
    if not files: raise ValueError('Resource inventory must contain at least one file')
    return {'format': 'fdisbull-resource-inventory-1', 'engine': engine,
            'profile': profile, 'adapter': adapter, 'files': files}


def _init(project):
    # DDL is deliberately local and lazily installed; no scene bundle migration.
    project.db.execute('CREATE TABLE IF NOT EXISTS debug_workflows (id TEXT PRIMARY KEY, version INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE(version,name))')
    project.db.execute('CREATE TABLE IF NOT EXISTS debug_workflow_revisions (id TEXT PRIMARY KEY, workflow TEXT NOT NULL REFERENCES debug_workflows(id), parent TEXT, created TEXT NOT NULL, author TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL)')
    project.db.execute('CREATE TABLE IF NOT EXISTS debug_workflow_receipts (id TEXT PRIMARY KEY, attempt TEXT NOT NULL, revision TEXT NOT NULL REFERENCES debug_workflow_revisions(id), created TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL)')


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(label + ' must be a non-empty string of at most 256 characters')
    return value


def _validate(project, doc, version):
    if not isinstance(doc, dict) or doc.get('format') != 'fdisbull-progressive-workflow-1':
        raise ValueError('Expected fdisbull-progressive-workflow-1')
    if set(doc) != {'format', 'inventory', 'source', 'research', 'actions'}:
        raise ValueError('Workflow fields must be format, inventory, source, research and actions')
    if doc['source'] != identity(project, version):
        raise ValueError('Workflow source identity differs from byte version')
    inventory = doc['inventory']
    if not isinstance(inventory, dict) or set(inventory) != {'format','engine','profile','adapter','files'} or inventory['format'] != 'fdisbull-resource-inventory-1':
        raise ValueError('Invalid resource inventory')
    for field in ('engine', 'profile', 'adapter'): _text(inventory[field], 'Inventory '+field)
    files = inventory['files']
    if not isinstance(files, list) or not files: raise ValueError('Inventory files must be non-empty')
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}: raise ValueError('Invalid inventory entry')
        path = item['path']
        if not isinstance(path, str) or not path or '\\' in path or PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path or any(part in ('.', '..') for part in path.split('/')) or '//' in path:
            raise ValueError('Inventory path must be canonical and relative')
        if path in seen: raise ValueError('Duplicate inventory path')
        seen.add(path)
        if not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']): raise ValueError('Invalid inventory SHA-256')
    if [x['path'] for x in files] != sorted(seen): raise ValueError('Inventory entries must be sorted')
    if not isinstance(doc['research'], list) or not isinstance(doc['actions'], list):
        raise ValueError('Research and actions must be lists')
    if len(doc['actions']) > 256 or len(doc['research']) > 1024 or len(_encoded(doc)) > 1024 * 1024:
        raise ValueError('Workflow exceeds size limits')
    names = set()
    for item in doc['research']:
        if not isinstance(item, dict) or set(item) != {'context','question','status','evidence'} or item['status'] not in ('unknown','resolved') or not isinstance(item['evidence'], list):
            raise ValueError('Invalid research record')
        _text(item['context'], 'Research context'); _text(item['question'], 'Research question')
    for action in doc['actions']:
        if not isinstance(action, dict) or set(action) != {'name','kind','scene_revision','object_id','dependencies','evidence'}:
            raise ValueError('Invalid action contract')
        _text(action['name'], 'Action name')
        if action['name'] in names: raise ValueError('Duplicate action name')
        names.add(action['name'])
        if action['kind'] not in ('scene','movement','assisted-travel'):
            raise ValueError('Unsupported action kind')
        scene = project.debug_scene_info(action['scene_revision'], version=version)
        if scene['id'] != action['scene_revision']:
            raise ValueError('Action must pin a scene revision')
        if (action['kind'] == 'scene' or action['object_id'] is not None) and not any(o['id'] == action['object_id'] for o in scene['definition']['objects']):
            raise ValueError('Action must pin an object identity in its scene revision')
        if not isinstance(action['evidence'], list) or not action['evidence']:
            raise ValueError('Action requires evidence')
        if not isinstance(action['dependencies'], list): raise ValueError('Invalid action dependencies')
        for dep in action['dependencies']:
            if not isinstance(dep, dict) or set(dep) != {'name','status','evidence'} or dep['status'] not in ('unknown','resolved') or not isinstance(dep['evidence'], list):
                raise ValueError('Invalid dependency')
            _text(dep['name'], 'Dependency name')
            if not dep['evidence']:
                raise ValueError('Dependency requires evidence')


class ProgressiveSceneProjectMixin:
    def debug_save_workflow(self, name, definition, *, resource_root, parent=None, version=None, author='agent'):
        _init(self); _text(name, 'Workflow name'); _text(author, 'Author')
        v = self.version(version)['id']; doc = deepcopy(definition)
        _validate(self, doc, v)
        inv = doc['inventory']
        if resource_inventory(resource_root, engine=inv['engine'], profile=inv['profile'], adapter=inv['adapter']) != inv:
            raise ValueError('Resource inventory differs from supplied root')
        from .project import now
        with self.transaction(True):
            root = self.db.execute('SELECT id FROM debug_workflows WHERE version=? AND name=?', (v,name)).fetchone()
            root_id = root['id'] if root else uuid.uuid4().hex
            latest = self.db.execute('SELECT id FROM debug_workflow_revisions WHERE workflow=? ORDER BY rowid DESC LIMIT 1', (root_id,)).fetchone()
            if (latest['id'] if latest else None) != parent:
                raise ValueError('Workflow parent must be the current revision')
            if not root: self.db.execute('INSERT INTO debug_workflows VALUES (?,?,?)', (root_id,v,name))
            revision = uuid.uuid4().hex
            self.db.execute('INSERT INTO debug_workflow_revisions VALUES (?,?,?,?,?,?,?)',
                            (revision,root_id,parent,now(),author,_digest(doc),_encoded(doc).decode()))
        return self.debug_workflow_info(revision, version=v)

    def debug_workflow_info(self, workflow, *, version=None):
        _init(self); v = self.version(version)['id']
        row = self.db.execute('SELECT r.*,w.version,w.name FROM debug_workflow_revisions r JOIN debug_workflows w ON w.id=r.workflow WHERE w.version=? AND (r.id=? OR w.name=?) ORDER BY r.rowid DESC LIMIT 1', (v,workflow,workflow)).fetchone()
        if row is None: raise ValueError('Unknown workflow revision for this byte version')
        doc = json.loads(row['document'])
        if _digest(doc) != row['sha256']: raise ValueError('Workflow document hash mismatch')
        _validate(self, doc, v)
        return {k:row[k] for k in ('id','workflow','parent','created','author','sha256','version','name')} | {'definition':doc}


    def debug_workflow_receipts(self, workflow, *, version=None):
        _init(self)
        info = self.debug_workflow_info(workflow, version=version)
        rows = self.db.execute('SELECT t.* FROM debug_workflow_receipts t JOIN debug_workflow_revisions r ON r.id=t.revision WHERE r.workflow=? ORDER BY t.rowid', (info['workflow'],))
        result = []
        for row in rows:
            doc = json.loads(row['document'])
            if _digest(doc) != row['sha256']: raise ValueError('Workflow receipt hash mismatch')
            result.append({'id':row['id'], 'created':row['created'], 'sha256':row['sha256']} | doc)
        return result


_lock_setup = threading.Lock()


class ProgressiveSceneSessionMixin:
    def workflow(self, workflow, *, resource_root):
        return WorkflowHandle(self, workflow, resource_root)

    def workflow_observe(self, workflow, *, resource_root, action=None, research_context=None):
        return self.workflow(workflow,resource_root=resource_root).observe(action,context=research_context)

    def workflow_act(self, workflow, action, *, resource_root, timeout_ms=None):
        options={} if timeout_ms is None else {'timeout_ms':timeout_ms}
        return self.workflow(workflow,resource_root=resource_root).act(action,**options)


class WorkflowHandle:
    def __init__(self, session, workflow, resource_root):
        self.session = session; self.resource_root = Path(resource_root)
        with _lock_setup:
            if not hasattr(session, '_workflow_controller_lock'):
                session._workflow_controller_lock = threading.RLock()
        self.lock = session._workflow_controller_lock
        self.info = session.project.debug_workflow_info(workflow, version=session.version['id'])
        self.revision = self.info['id']; self.workflow_id = self.info['workflow']

    def adopt(self, revision):
        with self.lock:
            if getattr(self.session, '_workflow_action_active', False): raise ValueError('Cannot adopt during an action')
            info = self.session.project.debug_workflow_info(revision, version=self.session.version['id'])
            if info['id'] != revision or info['workflow'] != self.workflow_id:
                raise ValueError('Adoption requires an explicit revision of the same workflow')
            self.info = info; self.revision = info['id']
            return deepcopy(info)

    def _action(self, name):
        matches = [a for a in self.info['definition']['actions'] if a['name'] == name]
        if len(matches) != 1: raise ValueError('Unknown workflow action')
        return matches[0]

    def _fresh(self):
        self.info = self.session.project.debug_workflow_info(self.revision, version=self.session.version['id'])
        # This format qualifies the stored original byte version, not an
        # unrecorded execution/RAM overlay. Fresh pixels alone cannot validate
        # changed code. Layer experiments keep their separate qualification.
        if hasattr(self.session,'layers'):
            layers=self.session.layers()
            if not isinstance(layers,dict) or layers.get('active')!=[]:
                raise ValueError('Active code layers are outside this original-byte workflow qualification')
        inv = self.info['definition']['inventory']
        if resource_inventory(self.resource_root, engine=inv['engine'], profile=inv['profile'], adapter=inv['adapter']) != inv:
            raise ValueError('Resource inventory drift: action blocked')

    def observe(self, action=None, *, context=None):
        with self.lock:
            self._fresh()
            doc = self.info['definition']
            queue = [deepcopy(x) for x in doc['research'] if x['status'] == 'unknown' and (context is None or x['context'] == context)]
            result = {'workflow_revision': self.info['id'], 'inventory_sha256': _digest(doc['inventory']),
                      'actions': [a['name'] for a in doc['actions'] if all(d['status'] == 'resolved' for d in a['dependencies'])],
                      'blocked_actions': [a['name'] for a in doc['actions'] if any(d['status'] != 'resolved' for d in a['dependencies'])], 'work_queue': queue}
            if action is not None:
                contract = self._action(action)
                result['action'] = deepcopy(contract)
                result['unresolved_dependencies'] = [deepcopy(d) for d in contract['dependencies'] if d['status'] == 'unknown']
                result['work_queue'] = result['unresolved_dependencies'] + queue
                result['observation'] = self.session.scene(contract['scene_revision']).check(contract['object_id'])
            return result

    def _receipt(self, data):
        from .project import now
        p = self.session.project
        data = deepcopy(data)
        payload = _encoded(data)
        receipt_id = uuid.uuid4().hex
        with p.transaction(True):
            p.db.execute('INSERT INTO debug_workflow_receipts VALUES (?,?,?,?,?,?)',
                         (receipt_id, data['attempt'], data['workflow_revision'], now(), hashlib.sha256(payload).hexdigest(), payload.decode()))
        return receipt_id

    def execute(self, action, callback):
        if not callable(callback): raise ValueError('Action callback required')
        with self.lock:
            if getattr(self.session, '_workflow_action_active', False): raise ValueError('Workflow action already active')
            revision = self.revision
            attempt = uuid.uuid4().hex
            record = {'attempt':attempt, 'workflow_revision':revision, 'action':action,
                      'run':getattr(self.session, 'run_id', None), 'status':'started', 'observation':None}
            self._receipt(record)
            self.session._workflow_action_active = True
            try:
                self._fresh(); contract = deepcopy(self._action(action))
                record.update(inventory_sha256=_digest(self.info['definition']['inventory']),
                              scene_revision=contract['scene_revision'], object_id=contract['object_id'])
                unresolved = [d['name'] for d in contract['dependencies'] if d['status'] != 'resolved']
                if unresolved: raise ValueError('Unresolved dependencies block action: ' + ', '.join(unresolved))
                scene = self.session.scene(contract['scene_revision'])
                observation = scene.check(contract['object_id'])
                record['observation'] = observation
                if observation.get('status') != 'matched' or observation.get('complete') is not True:
                    raise ValueError('Fresh scene check did not match completely')
                self._fresh()  # Catch drift during recognition before guest input.
                result = callback(contract, scene, observation)
                record.update(status='returned', result=result)
                receipt_id = self._receipt(record)
                return {'workflow_revision':revision, 'inventory_sha256':record['inventory_sha256'],
                        'action':contract['name'], 'scene_revision':contract['scene_revision'],
                        'object_id':contract['object_id'], 'observation':observation, 'result':result,
                        'receipt':receipt_id, 'attempt':attempt}
            except Exception as error:
                record.update(status='failed', error={'type':type(error).__name__, 'message':str(error)})
                # A callback may have advanced the guest before failing. This record
                # makes no rollback or no-input claim.
                record.pop('result', None)
                self._receipt(record)
                raise
            finally:
                self.session._workflow_action_active = False

    def act(self, action, **options):
        def dispatch(contract, scene, observation):
            if contract['kind'] != 'scene': raise ValueError('Non-scene action requires execute callback')
            return scene.act(contract['object_id'], **options)
        return self.execute(action, dispatch)
