import hashlib
import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image

from fdisbull.project import Project
from fdisbull.cli import invoke
from fdisbull.spatial import SpatialSessionMixin
from fdisbull.assisted_travel import AssistedTravelSessionMixin
from fdisbull.debugger import DebugSession


def spatial_doc(digest):
    return {'format':'fdisbull-spatial-map-1','source':{'sha256':digest,'context':'fixture','room':'1','resource':'pic1'},'space':{'name':'room','width':8,'height':6,'unit':'game'},'actor':{'width':1,'height':1,'anchor':[0,0]},'known':{'rect':[0,0,8,6]},'safe':{'rect':[0,0,8,6]},'layers':[{'id':'door','kind':'obstacle','area':{'rect':[4,3,5,4]},'when':'door_closed'},{'id':'item','kind':'object','area':{'rect':[4,3,5,4]},'interaction_points':[[4,3]]}],'evidence':{'test':{'description':'synthetic fixture; no real walking observed'}}}


def action(revision, version):
    pred=lambda field,value:{'field':field,'op':'eq','value':value}
    obs={k:{'status':k} for k in ('room','ready','done','x','y')}
    return {'format':'fdisbull-spatial-action-1','id':'item','version':version,'map_revision':revision,'observations':obs,'context':pred('room',1),'nonspatial_before':pred('ready',1),'nonspatial_after':pred('ready',1),'outcome':pred('done',1),'proximity':pred('x',4),'position':{'x':'x','y':'y'},'inputs':[{'key':'enter'}],'guest_ms':100,'slice_ms':50,'stationary':True,'spatial_guards':[]}


class Session(SpatialSessionMixin, AssistedTravelSessionMixin):
    run_id='synthetic'
    def __init__(self, project):
        self.project=project; self.version=dict(project.version()); self.values={'room':1,'ready':1,'done':0,'x':4,'y':3}; self.events=[]; self.presses=0
    def _event(self,name,data): self.events.append((name,data))
    def scene(self, revision):
        session=self
        class Scene:
            def __init__(self): self.revision=revision
            def check(self): return getattr(session,'scene_result',{'complete':True,'scene_matched':True,'status':'matched','content':{'requested':True,'displayed':True,'ready':True}})
        return Scene()
    def keyboard_state(self): return {'keyboard':{'pending_events':0,'owned_keys':0}}
    def keyboard_press(self,**kwargs): self.presses+=1; return {}
    def run(self,**kwargs): self.values['done']=1; return {'outcome':'guest_time','guest_elapsed_ms':50,'hook_hits':[]}


def test_offline_api_reopened_revision_and_png(tmp_path):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21'); db=tmp_path/'x.fdb'
    with Project.create(db,binary,image='com') as project:
        doc=spatial_doc(project.version()['sha256']); first=project.debug_save_spatial_map('room',doc)
        new=deepcopy(doc); new['source']['resource']='pic2'; second=project.debug_save_spatial_map('room',new,parent=first['id'])
    info=invoke('debug-spatial-map-info',{'project':str(db),'revision':first['id']})
    assert info['document']['source']['resource']=='pic1' and first['id']!=second['id']
    params={'project':str(db),'revision':first['id'],'point':[4,3]}
    assert invoke('debug-spatial-check',params)['classification']=='unknown'
    assert invoke('debug-spatial-check',params|{'conditions':{'door_closed':False}})['classification']=='clear'
    output=tmp_path/'map.png'; response=invoke('debug-spatial-overlay',{'project':str(db),'revision':first['id'],'output':str(output)})
    assert response['revision']==first['id'] and Image.open(BytesIO(output.read_bytes())).size==(8,6)
    with pytest.raises(FileExistsError): invoke('debug-spatial-overlay',{'project':str(db),'revision':first['id'],'output':str(output)})


def test_fresh_room_and_unknown_anchor_refuse_before_guest(tmp_path,monkeypatch):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path/'x.fdb',binary,image='com') as project:
        saved=project.debug_save_spatial_map('room',spatial_doc(project.version()['sha256']))
        session=Session(project); definition=action(saved['id'],session.version['id'])
        capture=lambda s,specs:{'complete':True,'values':dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial.capture_observations',capture)
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',capture)
        session.values['room']=2
        with pytest.raises(ValueError,match='context changed'): session.spatial_action(saved['id'],definition,zone='item')
        assert session.presses==0
        session.values['room']=1
        result=session.spatial_action(saved['id'],definition,zone='item')
        assert not result['ok'] and 'No qualified clear interaction anchor' in result['error'] and session.presses==0
        session.spatial_policy('physical',fair_play=True)
        with pytest.raises(ValueError,match='Fair play'): session.spatial_policy('story')
        with pytest.raises(ValueError,match='Fair play'): session.spatial_policy('assisted',fair_play=False)
        assert session.assisted_travel({})['status']=='refused'
        assert session.spatial_action(saved['id'],definition,zone='item')['ok']
        assert session.presses==1


def test_state_load_keeps_session_policy():
    class Rows:
        def execute(self,*a): return self
        def fetchone(self): return self.row
    class Fake(SpatialSessionMixin):
        rpc = SimpleNamespace(capabilities={})
        load_state=DebugSession.load_state
        def __init__(self):
            self.version={'id':1}; self.events=[]; self.metadata={k:'same' for k in ('source_sha256','version_sha256','emulator_sha256','runtime_load_segment','runtime_profile','game_dir')}; self.project=type('P',(),{})(); self.project.db=Rows()
        def _event(self,*a): self.events.append(a)
        def _disk_manifest(self): return []
        def call(self,*a): return {}
        def registers(self): return {'general':{},'segments':{},'instruction_pointer':0,'flags':0}
        def _restore_layer_state(self, state): pass
        def _invalidate_runtime_bindings(self): pass
    s=Fake(); s.spatial_policy('physical',fair_play=True); data=b'synthetic'
    metadata=s.metadata|{'disk_manifest':[],'registers':s.registers()}
    s.project.db.row={'kind':'state','version':1,'metadata':json.dumps(metadata),'data':data,'sha256':hashlib.sha256(data).hexdigest()}
    s.load_state('state-id')
    assert (s._spatial_mode,s._fair_play,s._allow_assisted_travel)==('physical',True,False)
    with pytest.raises(ValueError,match='Fair play'): s.spatial_policy('story')


def test_room_change_after_map_preflight_is_refused(tmp_path,monkeypatch):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path/'x.fdb',binary,image='com') as project:
        saved=project.debug_save_spatial_map('room',spatial_doc(project.version()['sha256']))
        session=Session(project); session.spatial_policy('physical',fair_play=True)
        definition=action(saved['id'],session.version['id'])
        # Context may contain additional non-room conditions: map's independently
        # observed room must still be checked for every fresh observation.
        definition['context']={'field':'ready','op':'eq','value':1}
        monkeypatch.setattr('fdisbull.spatial.capture_observations',lambda s,specs:{'complete':True,'values':dict(s.values)})
        def next_observation(s,specs):
            s.values['room']=2
            return {'complete':True,'values':dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',next_observation)
        result=session.spatial_action(saved['id'],definition,zone='item')
        assert not result['ok'] and session.presses==0


def test_native_checkpoint_refuses_active_or_failed_spatial_guard():
    session=object.__new__(DebugSession)
    session._spatial_guard_active=True
    with pytest.raises(ValueError,match='Cannot checkpoint'): session.save_state()
    session._spatial_guard_active=False; session._spatial_guard_failed=True
    with pytest.raises(ValueError,match='Cannot checkpoint'): session.save_state()


def test_inactive_object_zone_cannot_authorize_assisted_placement(tmp_path,monkeypatch):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path/'x.fdb',binary,image='com') as project:
        doc=spatial_doc(project.version()['sha256'])
        doc['layers'][-1]['when']='object_present'
        saved=project.debug_save_spatial_map('room',doc)
        session=Session(project); definition=action(saved['id'],session.version['id'])
        capture=lambda s,specs:{'complete':True,'values':dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial.capture_observations',capture)
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',capture)
        result=session.spatial_action(saved['id'],definition,zone='item',
            conditions={'object_present':{'field':'done','op':'eq','value':1}})
        assert not result['ok'] and session.presses==0 and 'inactive or unqualified' in result['error']
def test_same_room_requires_fresh_scene_context(tmp_path,monkeypatch):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path/'x.fdb',binary,image='com') as project:
        saved=project.debug_save_spatial_map('room',spatial_doc(project.version()['sha256']))
        session=Session(project); definition=action(saved['id'],session.version['id'])
        capture=lambda s,specs:{'complete':True,'values':dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial.capture_observations',capture)
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',capture)
        nav=session.spatial_navigation(saved['id'],observations=definition['observations'])
        assert nav.navigation_check([1,1])['classification']=='clear'
        session.scene_result={'complete':True,'scene_matched':True,'status':'mismatch','content':{'requested':True,'displayed':True,'ready':False}}
        assert nav.navigation_check([1,1])['classification']=='clear'
        session.scene_result['content']['displayed']=False
        assert nav.navigation_check([1,1])['classification']=='unknown'
        with pytest.raises(ValueError,match='context|content'): session.spatial_action(saved['id'],definition)
        assert session.presses==0
        session.scene_result={'complete':False,'scene_matched':True,'status':'ambiguous','content':{}}
        assert nav.navigation_check([1,1])['classification']=='unknown'


def test_scene_changes_after_initial_map_check_refuses_input(tmp_path,monkeypatch):
    binary=tmp_path/'x.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path/'x.fdb',binary,image='com') as project:
        saved=project.debug_save_spatial_map('room',spatial_doc(project.version()['sha256']))
        session=Session(project); session.spatial_policy('physical',fair_play=True)
        definition=action(saved['id'],session.version['id'])
        capture=lambda s,specs:{'complete':True,'values':dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial.capture_observations',capture)
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',capture)
        calls=[]
        def scene(revision):
            class Scene:
                def __init__(self): self.revision=revision
                def check(self):
                    calls.append(1)
                    return {'complete':True,'scene_matched':len(calls)==1,'status':'matched','content':{}}
            return Scene()
        session.scene=scene
        result=session.spatial_action(saved['id'],definition)
        assert not result['ok'] and session.presses==0 and len(calls)>=2
