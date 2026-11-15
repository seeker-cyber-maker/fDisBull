"""Host-only real-FDB CHIP-8 opaque delta storage witnesses."""
from copy import deepcopy
import json
import uuid
import pytest
from fdisbull.chip8_frame_storage import FORMAT, DELTA_KIND,materialize
from fdisbull.chip8_history import KEY_SUBSET,KEY_STATE_FORMAT
from test_chip8_frames import FrameHarness,project


class DeltaHarness(FrameHarness):
    def __init__(self,project,run):
        super().__init__(project,run);self.identity['cpu_subset']=KEY_SUBSET
        self.capabilities.update(frame_delta_storage=True,frame_key_ownership=True);self.captures=[]
    def _frame_admit(self,**kwargs):pass
    def _chip8_keys_query(self):return {'held':[],'held-mask':0,'key-mask':0,'active':False,
        'generation':0,'state-generation':self.generation,'accepted-edges':0}
    def chip8_environment(self,**kwargs):
        from test_qemu_chip8_devices import environment
        from fdisbull.chip8_keys import KEY_ENV
        from fdisbull.qemu_chip8 import RNG_MODEL
        from fdisbull.chip8_layers import LAYER_MODEL
        return environment()|{'cpu-subset':KEY_SUBSET,'env-model':KEY_ENV,'layer-model':LAYER_MODEL,
            'layer-generation':0,'rng-model':RNG_MODEL,'rng-seed':0,'rng-state':0,'rng-draws':0}|super().chip8_environment(**kwargs)|{'key-mask':0}
    def _capture_state(self,name,*,max_bytes=None,timeout_ms=60000):
        state={'pc':self.pc,'tick':self.tick,'phase':self.phase,'deadline':self.deadline,'now':self.now,'generation':self.generation}
        data=bytes([self.tick&255])+b'X'*8191
        metadata={'format':KEY_STATE_FORMAT,'identity':deepcopy(self.identity),'host_files_restored':False,
                  'environment':self.chip8_environment(),'fixture_state':state,
                  'key_state':{'epoch':1,'active':False,'generation':0,'accepted-edges':0,
                               'held-mask':0,'key-mask':0,'state-generation':self.generation}}
        import hashlib
        result=dict(name=name,kind='state',data=data,size=len(data),sha256=hashlib.sha256(data).hexdigest(),metadata=metadata)
        self.captures.append(deepcopy(result));return result
    def _load_state_data(self,data,metadata,*,source_id,timeout_ms=60000):
        for name,value in metadata['fixture_state'].items():setattr(self,name,value)
        self.vm.history_epoch=uuid.uuid4().hex
        return {'host_files_restored':False,'artifact':source_id}


def test_delta_exact_reconstruction_branch_pin_and_cold_restore(project):
    a=DeltaHarness(project,'da');root=a.timeline_start(storage_mode='delta',keyframe_interval=3,max_frames=6,
        max_bytes=200000,max_state_bytes=16384,max_image_bytes=4096)
    assert root['format']==FORMAT
    first=a.timeline_advance(frames=2);manifest=a._frame_manifest(first['timeline'])
    assert [n['checkpoint']['storage']['kind'] for n in manifest['nodes']]==['full','delta','delta']
    rows=project.db.execute("SELECT kind,count(*) AS n FROM debug_artifacts WHERE kind IN ('state',?) GROUP BY kind",(DELTA_KIND,)).fetchall()
    assert {r['kind']:r['n'] for r in rows}=={'state':1,DELTA_KIND:2}
    for node,captured in zip(manifest['nodes'],a.captures):
        restored=materialize(a,manifest,node)
        assert restored['data']==captured['data'] and restored['metadata']==captured['metadata']
    pin=a.timeline_pin();row=project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',(pin['artifact'],)).fetchone()
    assert bytes(row['data'])==a.captures[-1]['data'] and json.loads(row['metadata'])==a.captures[-1]['metadata']
    old=first['point'];a.timeline_rewind(point=root['point']);branch=a.timeline_advance()
    assert old in [n['id'] for n in branch['nodes']] and branch['nodes'][-1]['parent']==root['point']
    b=DeltaHarness(project,'db');assert not b.timeline_start(timeline=branch['timeline'])['valid']
    restored=b.timeline_rewind(timeline=branch['timeline'],point=old,frames=0)
    assert restored['point']==old and b.tick==2


def test_corrupt_delta_base_refuses_before_restore_intent(project):
    a=DeltaHarness(project,'da');a.timeline_start(storage_mode='delta',keyframe_interval=3,max_frames=4,
        max_bytes=200000,max_state_bytes=16384,max_image_bytes=4096)
    history=a.timeline_advance();manifest=a._frame_manifest(history['timeline']);root=manifest['nodes'][0]
    # Keep index identity/size plausible while corrupting source bytes.
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'Z'*root['checkpoint']['size'],root['checkpoint']['artifact']))
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    with pytest.raises(ValueError,match='hash|identity'):a.timeline_rewind(point=history['point'],frames=0)
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]==before
    assert not a.closed


def test_incompressible_state_falls_back_to_full_without_delta_row(project):
    import hashlib
    class Dense(DeltaHarness):
        def _capture_state(self,name,*,max_bytes=None,timeout_ms=60000):
            result=super()._capture_state(name,max_bytes=max_bytes,timeout_ms=timeout_ms)
            result['data']=hashlib.shake_256(str(self.tick).encode()).digest(8192)
            result['size']=len(result['data']);result['sha256']=hashlib.sha256(result['data']).hexdigest()
            return result
    a=Dense(project,'dense');a.timeline_start(storage_mode='delta',max_frames=3,max_bytes=200000,max_state_bytes=16384,max_image_bytes=4096)
    result=a.timeline_advance()
    assert result['nodes'][-1]['checkpoint']['storage']['kind']=='full' and result['delta_state_points']==0
    assert project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',(DELTA_KIND,)).fetchone()[0]==0


def test_delta_sidecar_tamper_refuses_before_restore_intent(project):
    a=DeltaHarness(project,'da');a.timeline_start(storage_mode='delta',max_frames=4,max_bytes=200000,max_state_bytes=16384,max_image_bytes=4096)
    result=a.timeline_advance();manifest=a._frame_manifest(result['timeline']);cp=manifest['nodes'][-1]['checkpoint']
    row=project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(cp['artifact'],)).fetchone()
    metadata=json.loads(row['metadata']);metadata['full_metadata']['key_state']['accepted-edges']=99
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',(json.dumps(metadata),cp['artifact']))
    with pytest.raises(ValueError,match='metadata hash'):a.timeline_rewind(point=result['point'],frames=0)
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]==before and not a.closed
