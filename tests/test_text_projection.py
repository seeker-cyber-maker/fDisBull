import copy
import io
import json
import sqlite3
from contextlib import contextmanager

import pytest

from fdisbull.progressive_scenes import ProgressiveSceneProjectMixin, ProgressiveSceneSessionMixin, resource_inventory
from fdisbull.scene_bundles import identity
from fdisbull.text_projection import TextProjectionProjectMixin, TextProjectionSessionMixin, serve_stream


class Project(TextProjectionProjectMixin, ProgressiveSceneProjectMixin):
    def __init__(self, path):
        self.db = sqlite3.connect(path); self.db.row_factory = sqlite3.Row
        self.meta = {'source_sha256':'source','format':'MZ','arch':'x86','bits':16}
    def version(self, version=None): return {'id':1,'sha256':'mapped'}
    @contextmanager
    def transaction(self, write=False):
        with self.db: yield
    def debug_scene_info(self, name, *, version=None):
        if name not in ('scene1','scene2'): raise ValueError('private scene failure')
        return {'id':name,'definition':{'objects':[{'id':'private-object'}]}}


class Scene:
    def __init__(self, session, revision): self.session = session; self.revision = revision
    def check(self, object=None):
        s = self.session
        status = s.status.get(self.revision,'mismatch')
        return {'status':status,'complete': status not in ('unavailable','ambiguous'),
                'frame':{'frame_id':s.frame,'mode_id':1,'state_revision':s.state_revision},
                'objects':{'private-object':{'visible':s.visible,'ready':s.ready,'enabled':s.ready}},
                'availability':{'visible':s.visible,'ready':s.ready,'enabled':s.ready},
                'private_error':'SECRET'}
    def act(self, target):
        self.session.inputs += 1
        return self.session.action_result


class Session(TextProjectionSessionMixin, ProgressiveSceneSessionMixin):
    def __init__(self,p):
        self.project=p; self.version={'id':1}; self.run_id='private-run'; self._runtime_epoch='epoch'
        self.frame=1; self.state_revision=1; self.status={'scene1':'matched','scene2':'mismatch'}
        self.visible=True; self.ready=True; self.inputs=0; self.action_result={'status':'matched','complete':True}
    def scene(self, revision): return Scene(self, revision)


@pytest.fixture
def setup(tmp_path):
    p = Project(tmp_path/'real.sqlite'); root = tmp_path/'assets'; root.mkdir(); (root/'game').write_bytes(b'fixture')
    action = {'name':'private-action','kind':'scene','scene_revision':'scene1','object_id':'private-object',
              'dependencies':[{'name':'secret','status':'resolved','evidence':['private']}], 'evidence':['private']}
    wf = p.debug_save_workflow('wf',{'format':'fdisbull-progressive-workflow-1','source':identity(p,1),
        'inventory':resource_inventory(root,engine='test',profile='test',adapter='test'), 'research':[], 'actions':[action]},resource_root=root)
    obj = {'id':'internal-door','label':'door','aliases':['gate'],'description':'A door.', 'scene_object':'private-object', 'inventory':False,
           'bindings':[{'verb':'open','item':None,'action':'private-action','dispatch':{'kind':'scene'}}]}
    doc = {'format':'fdisbull-text-projection-1','workflow_revision':wf['id'],'contexts':[
        {'id':'internal-room','title':'Room','description':'A room.','scene_revision':'scene1','partial':True,'objects':[obj]},
        {'id':'internal-other','title':'Other','description':'Other room.','scene_revision':'scene2','partial':True,'objects':[]}]}
    return p,root,doc


def backend(setup):
    p,root,doc=setup; saved=p.debug_save_text_projection('text',doc); s=Session(p)
    return p,s,s.text_projection(saved['id'],root)


def test_persistence_privacy_and_outcome(setup):
    p,s,h=backend(setup); obs=h.observe(); data=json.dumps(obs)
    assert obs['complete'] and 'SECRET' not in data and 'private' not in data and 'internal' not in data
    assert h.observe() == obs
    req={'verb':'open','target':obs['objects'][0]['id'],'item':None,'context_token':obs['context']['token']}
    s.action_result={'status':'accepted','complete':True}
    assert h.act(req)['status']=='incomplete' and s.inputs==1
    s.action_result={'status':'matched','complete':True}
    assert h.act(req)['status']=='success' and s.inputs==2
    assert p.debug_text_projection_info('text')['sha256']
    assert len(p.debug_workflow_receipts('wf')) == 4


def test_protocol_channels_preserve_identity_and_invalidate_after_restore(setup):
    p,s,h=backend(setup)
    projection=h.info['id'];root=h.workflow.resource_root
    first=s.text_observe(projection,resource_root=root)
    assert first==s.text_observe(projection,resource_root=root)
    request={'verb':'open','target':first['objects'][0]['id'],'item':None,'context_token':first['context']['token']}
    assert s.text_act(projection,request,resource_root=root)['status']=='success'
    s._runtime_epoch='restored epoch'
    assert s.text_act(projection,request,resource_root=root)['status']=='rejected'
    assert s.inputs==1


def test_stale_unknown_ambiguous_and_hidden_never_send_input(setup):
    p,s,h=backend(setup); obs=h.observe(); req={'verb':'open','target':obs['objects'][0]['id'],'item':None,'context_token':obs['context']['token']}
    s.state_revision += 1
    assert h.act(req)['status']=='rejected' and s.inputs==0
    s.status['scene2']='matched'
    assert h.observe()=={'complete':False} and h.act(req)['status']=='incomplete' and s.inputs==0
    s.status['scene2']='unavailable'
    assert h.observe()=={'complete':False}
    s.status['scene2']='mismatch'; s.visible=False
    assert not h.observe()['objects'] and h.act(req)['status']=='rejected' and s.inputs==0


def test_not_ready_or_dependency_unknown_blocks_without_private_leak(setup):
    p,s,h=backend(setup); s.ready=False; obs=h.observe()
    req={'verb':'open','target':obs['objects'][0]['id'],'item':None,'context_token':obs['context']['token']}
    response=h.act(req)
    assert response['status']=='rejected' and s.inputs==0 and 'SECRET' not in json.dumps(response)


def test_revision_chain_and_wire(setup):
    p,root,doc=setup
    first=p.debug_save_text_projection('text',doc); second=p.debug_save_text_projection('text',doc,parent=first['id'])
    assert first['id'] != second['id'] and p.debug_text_projection_info('text')['id']==second['id']
    with pytest.raises(ValueError): p.debug_save_text_projection('text',doc,parent=first['id'])
    h=Session(p).text_projection(first['id'],root); output=io.StringIO()
    serve_stream(h,io.StringIO('{"op":"observe"}\n{"op":"bogus","secret":1}\n'),output)
    values=[json.loads(line) for line in output.getvalue().splitlines()]
    assert values[0]['complete'] and values[1]=={'complete':False}


def test_unresolved_dependency_and_resource_drift_are_private_and_block_input(setup):
    p,root,doc=setup
    wf=p.debug_workflow_info(doc['workflow_revision'])
    changed=copy.deepcopy(wf['definition']); changed['actions'][0]['dependencies'][0]['status']='unknown'
    revised=p.debug_save_workflow('wf',changed,resource_root=root,parent=wf['id'])
    doc['workflow_revision']=revised['id']
    saved=p.debug_save_text_projection('text',doc); s=Session(p); h=s.text_projection(saved['id'],root)
    obs=h.observe(); req={'verb':'open','target':obs['objects'][0]['id'],'item':None,'context_token':obs['context']['token']}
    response=h.act(req)
    assert response['status']=='incomplete' and s.inputs==0 and 'secret' not in json.dumps(response)
    (root/'game').write_bytes(b'drift')
    assert h.observe()=={'complete':False} and s.inputs==0


def test_movement_dispatch_uses_pinned_descriptor(setup):
    p,root,doc=setup
    wf=p.debug_workflow_info(doc['workflow_revision']); changed=copy.deepcopy(wf['definition'])
    changed['actions'][0]['kind']='movement'; changed['actions'][0]['object_id']=None
    revised=p.debug_save_workflow('wf',changed,resource_root=root,parent=wf['id'])
    doc['workflow_revision']=revised['id']
    args={'macro_set':'walk','start':{},'stop':{},'observations':[],'until':{},'progress':{},'settle':{}}
    doc['contexts'][0]['objects'][0]['bindings'][0]['dispatch']={'kind':'movement','args':args}
    saved=p.debug_save_text_projection('text',doc); s=Session(p); calls=[]
    s.move=lambda **kwargs: calls.append(kwargs) or {'ok':True,'complete':True}
    h=s.text_projection(saved['id'],root); obs=h.observe()
    result=h.act({'verb':'open','target':obs['objects'][0]['id'],'item':None,'context_token':obs['context']['token']})
    assert result['status']=='success' and calls==[args]


def test_wire_rejects_oversized_line_without_dispatch():
    class Backend:
        called = False
        def observe(self): self.called = True; return {'complete':True}
    backend = Backend(); output = io.StringIO()
    serve_stream(backend, io.StringIO('x' * (1024 * 1024) + '\n{"op":"observe"}\n'), output)
    assert output.getvalue() == '{"complete":false}\n' and not backend.called
