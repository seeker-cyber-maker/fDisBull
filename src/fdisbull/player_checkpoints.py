"""Private durable live-player checkpoints over native experiment artifacts."""
from copy import deepcopy
import hashlib
import json
import re
import secrets
import uuid

from .progressive_scenes import _encoded
from .scene_bundles import identity


def _init(project):
    project.db.execute('CREATE TABLE IF NOT EXISTS player_checkpoints (id TEXT PRIMARY KEY, document TEXT NOT NULL, sha256 TEXT NOT NULL)')
    project.db.execute('CREATE TABLE IF NOT EXISTS player_checkpoint_slots (slot TEXT PRIMARY KEY, checkpoint TEXT NOT NULL)')
    project.db.execute('CREATE TABLE IF NOT EXISTS player_checkpoint_events (id TEXT PRIMARY KEY, operation TEXT NOT NULL, checkpoint TEXT, detail TEXT NOT NULL)')


def _event(project, operation, checkpoint, detail):
    with project.transaction(True):
        project.db.execute('INSERT INTO player_checkpoint_events VALUES (?,?,?,?)',
                           (uuid.uuid4().hex, operation, checkpoint, json.dumps(detail, sort_keys=True)))


def _slot(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Invalid checkpoint slot')
    return value


def _failed(handle, value):
    handle.session._player_checkpoint_failed=value
    handle._checkpoint_failed=value


def _compatibility(handle):
    session=handle.session
    handle.workflow._fresh()
    info=handle.session.project.debug_text_projection_info(handle.info['id'],version=session.version['id'])
    if info['id'] != handle.info['id'] or info['definition']['workflow_revision'] != handle.workflow.revision:
        raise ValueError('Projection identity changed')
    metadata=session.metadata
    keys=('source_sha256','version_sha256','emulator_sha256','runtime_load_segment','runtime_profile')
    if any(metadata.get(k) is None for k in keys[:3]): raise ValueError('Missing native identity')
    return {'source':identity(session.project,session.version['id']), 'version':session.version['id'],
            'native':{k:metadata.get(k) for k in keys}, 'projection':info['id'],
            'projection_sha256':info['sha256'], 'workflow':handle.workflow.revision,
            'workflow_sha256':handle.workflow.info['sha256'],
            'inventory':deepcopy(handle.workflow.info['definition']['inventory'])}


def _bindings(session):
    recipes=[]
    for name,key in sorted(getattr(session,'_runtime_names',{}).items()):
        item=session._runtime_bindings[key]
        captured=session.runtime_memory(name,offset=0,length=len(bytes.fromhex(item['expected_hex'])))
        recipes.append({k:deepcopy(item[k]) for k in ('name','address','length','expected_hex','mask_hex','provenance')} |
                       {'witness_hex':captured['witness_hex']})
    if len(recipes)!=len(getattr(session,'_runtime_bindings',{})): raise ValueError('Untracked runtime bindings')
    return recipes


def save(handle, slot='live'):
    project=handle.session.project; checkpoint=None
    with handle.lock:
        try:
            _slot(slot); _init(project)
            if getattr(handle.session,'_player_checkpoint_failed',False): raise ValueError('Prior restore incomplete')
            if handle.session.call('session.status').get('state') != 'stopped': raise ValueError('Guest is not paused')
            compatibility=_compatibility(handle)
            if handle._read() is None: raise ValueError('Projection unavailable at checkpoint')
            recipes=_bindings(handle.session)
            experiment=handle.session.save_experiment('player-checkpoint.json',script={'format':'fdisbull-script-1','steps':[{'op':'status'}]})
            checkpoint=uuid.uuid4().hex
            document={'format':'fdisbull-player-checkpoint-1','compatibility':compatibility,
                      'experiment':experiment['artifact'],'bindings':recipes}
            raw=_encoded(document); digest=hashlib.sha256(raw).hexdigest()
            with project.transaction(True):
                project.db.execute('INSERT INTO player_checkpoints VALUES (?,?,?)',(checkpoint,raw.decode(),digest))
                project.db.execute('INSERT INTO player_checkpoint_slots VALUES (?,?) ON CONFLICT(slot) DO UPDATE SET checkpoint=excluded.checkpoint',(slot,checkpoint))
            _event(project,'save',checkpoint,{'status':'saved','slot':slot})
            return {'status':'saved','complete':True,'checkpoint':checkpoint,'slot':slot}
        except Exception as error:
            try: _event(project,'save',checkpoint,{'status':'incomplete','error':str(error),'type':type(error).__name__})
            except Exception: pass
            return {'status':'incomplete','complete':False}


def load(handle, checkpoint='live', *, prepare_guest_ms=100, timeout_ms=10000):
    project=handle.session.project; selected=None
    with handle.lock:
        try:
            _init(project)
            slot_row=None
            explicit_id=isinstance(checkpoint,str) and re.fullmatch(r'id:[0-9a-f]{32}',checkpoint)
            if explicit_id:
                selected=checkpoint[3:]
            elif isinstance(checkpoint,str):
                try:
                    _slot(checkpoint)
                except ValueError:
                    pass
                else:
                    slot_row=project.db.execute('SELECT checkpoint FROM player_checkpoint_slots WHERE slot=?',(checkpoint,)).fetchone()
            if not explicit_id:
                if slot_row is not None:
                    selected=slot_row['checkpoint']
                elif isinstance(checkpoint,str) and re.fullmatch(r'[0-9a-f]{32}', checkpoint):
                    selected=checkpoint
                else:
                    _slot(checkpoint)
                    if getattr(handle.session,'_player_checkpoint_failed',False): raise ValueError('Prior restore incomplete')
                    return {'status':'missing','complete':True}
            row=project.db.execute('SELECT document,sha256 FROM player_checkpoints WHERE id=?',(selected,)).fetchone()
            if row is None: raise ValueError('Checkpoint record missing')
            raw=row['document'].encode()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']: raise ValueError('Checkpoint hash mismatch')
            doc=json.loads(raw)
            if set(doc)!={'format','compatibility','experiment','bindings'} or doc['format']!='fdisbull-player-checkpoint-1': raise ValueError('Invalid checkpoint')
            if _compatibility(handle)!=doc['compatibility']: raise ValueError('Checkpoint compatibility mismatch')
            if type(prepare_guest_ms) is not int or not 1<=prepare_guest_ms<=10000: raise ValueError('Invalid restore preparation')
            if type(timeout_ms) is not int or not 1<=timeout_ms<=600000: raise ValueError('Invalid restore timeout')
            if handle.session.call('session.status').get('state') != 'stopped': raise ValueError('Guest is not paused')
            # Preflight stored experiment integrity before any guest mutation.
            handle.session.project._experiment_document(doc['experiment'],handle.session.version['id'])
            handle.secret=secrets.token_bytes(32); _failed(handle,True)
            handle.session.restore_experiment(doc['experiment'])
            for item in doc['bindings']:
                recipe=deepcopy(item); witness=recipe.pop('witness_hex')
                result=handle.session.bind_runtime_memory(**recipe)
                if result['witness_hex']!=witness: raise ValueError('Restored binding witness differs')
            run=handle.session.run(guest_ms=prepare_guest_ms,timeout_ms=timeout_ms,fast_forward=True,stop_on_hook=True)
            if (run.get('outcome')!='guest_time' or run.get('hook_hits') != [] or
                    type(run.get('guest_elapsed_ms')) is not int or run['guest_elapsed_ms']<prepare_guest_ms):
                raise ValueError('Checkpoint preparation stopped')
            if _bindings(handle.session)!=doc['bindings']:
                raise ValueError('Binding witnesses changed during checkpoint preparation')
            _failed(handle,False)
            if handle._read() is None: raise ValueError('Restored projection unavailable')
            _event(project,'load',selected,{'status':'restored','preparation':run})
            return {'status':'restored','complete':True,'checkpoint':selected,
                    'preparation':{'requested_guest_ms':prepare_guest_ms,'guest_elapsed_ms':run['guest_elapsed_ms']}}
        except Exception as error:
            _failed(handle,True)
            try: _event(project,'load',selected,{'status':'incomplete','error':str(error),'type':type(error).__name__})
            except Exception: pass
            return {'status':'incomplete','complete':False}
