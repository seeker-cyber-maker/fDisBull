"""Host-only sample timeline DAG and native-fence ownership contracts."""
from copy import deepcopy
import hashlib
import io
import json
import uuid
import pytest
from PIL import Image
from fdisbull.chip8_frames import Chip8FramesMixin,FORMAT,MODEL,ENV
from fdisbull.chip8_history import FRAME_SUBSET,FRAME_STATE_FORMAT
from fdisbull.qemu_chip8 import Chip8DebugSession
from test_chip8_history import Harness,project
from test_chip8_layers import machine


class FrameHarness(Chip8FramesMixin,Harness):
    def __init__(self,project,run):
        super().__init__(project,run);self.identity['cpu_subset']=FRAME_SUBSET
        self.capabilities={'frame_timeline':True};self._chip8_hook_pending=None;self.tick=0;self.phase=0;self.deadline=100;self.now=0;self.generation=0
    def _artifact(self,name,kind,data,metadata):return self.project._debug_artifact(self.run_id,name,kind,data,metadata)
    def _chip8_frame_idle(self):pass
    def _frame_admit(self):
        if self._chip8_hook_pending is not None:raise ValueError('pending hook')
    def chip8_environment(self,**kwargs):
        return {'virtual-ticks':self.tick,'pixels-hex':bytes(2048).hex(),'pixels-sha256':hashlib.sha256(bytes(2048)).hexdigest(),'frame-generation':0,'phase-numerator':self.phase,'next-deadline-ns':self.deadline,'virtual-now-ns':self.now,'state-generation':self.generation}
    def save_state(self,name,*,max_bytes=None,timeout_ms=60000):
        data=json.dumps({'pc':self.pc,'tick':self.tick,'phase':self.phase,'deadline':self.deadline,'now':self.now,'generation':self.generation,'padding':'x'*getattr(self,'padding',0)}).encode()
        return self.project._debug_artifact(self.run_id,name,'state',data,
                {'format':FRAME_STATE_FORMAT,'identity':self.identity,'host_files_restored':False,'environment':self.chip8_environment()})
    def load_state(self,artifact,*,timeout_ms=60000):
        row=self.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        state=json.loads(bytes(row['data']));self.pc=state['pc'];self.tick=state['tick'];self.phase=state['phase'];self.deadline=state['deadline'];self.now=state['now'];self.generation=state['generation'];self.vm.history_epoch=uuid.uuid4().hex
        return {'host_files_restored':False}
    def frame_rgba(self,*,timeout_ms=10000):
        rgba=bytes.fromhex('000000ff')*2048
        return {'rgba':rgba,'sha256':hashlib.sha256(rgba).hexdigest(),'environment':self.chip8_environment()}
    def _frame_run(self):
        baseline=self.deadline;phase=self.phase;self.tick+=1;self.generation+=1;self.now=baseline
        self.phase=phase-20 if phase>=20 else phase+40;self.deadline+=16666667 if phase>=20 else 16666666
        proof={'completed-virtual-ticks':self.tick,'sampled-virtual-now-ns':self.now,'baseline-deadline-ns':baseline,
            'pixels-sha256':hashlib.sha256(bytes(2048)).hexdigest(),'frame-generation':0,
            'phase-numerator':self.phase,'state-generation':self.generation}
        return {'outcome':'frame','frame_fence':{'observed':proof,'baseline_phase':phase}}


def test_timeline_sample_branch_cold_attach_and_image(project):
    a=FrameHarness(project,'fa');root=a.timeline_start(max_frames=5,max_bytes=65536,max_state_bytes=4096,max_image_bytes=4096)
    assert root['format']==FORMAT and root['nodes'][0]['frame']['kind']=='initial-paused'
    first=a.timeline_advance(frames=2);old=first['point'];assert first['completed_frames']==2
    assert first['nodes'][-1]['frame']['kind']=='native-60hz-sample'
    a.timeline_rewind(point=root['point']);branch=a.timeline_advance()
    assert old in [n['id'] for n in branch['nodes']] and branch['nodes'][-1]['parent']==root['point']
    assert a.timeline_image(point=old)['stored_frame'] and a.timeline_pin()['kind']=='state'
    b=FrameHarness(project,'fb');assert not b.timeline_start(timeline=branch['timeline'])['valid']
    restored=b.timeline_rewind(timeline=branch['timeline'],point=root['point'])
    assert restored['valid'] and restored['point']==root['point'] and b.tick==0


def test_timeline_refuses_unsupported_options_before_intent(project):
    a=FrameHarness(project,'fa')
    for params in ({'storage_mode':'delta'},{'period_ns':1},{'max_frames':0}):
        with pytest.raises(ValueError):a.timeline_start(**params)
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]==0
    a.timeline_start(max_frames=3,max_bytes=65536,max_state_bytes=4096,max_image_bytes=4096)
    a._chip8_hook_pending='pending'
    with pytest.raises(ValueError,match='pending'):a.timeline_advance()
    with pytest.raises(ValueError,match='input'):a.timeline_advance(inputs=[{'frame':0}])
    with pytest.raises(ValueError,match='partial'):a.timeline_rewind(policy={'registers':True})


def test_owned_frame_stop_and_nonowned_breakpoint_cancel_before_dispatch():
    s,add,layer,env=machine();s.identity['cpu_subset']=FRAME_SUBSET;s.vm.fault['cpu-subset']=FRAME_SUBSET
    env['cpu-subset']=FRAME_SUBSET;env['env-model']=ENV;env['state-generation']=4;s._chip8_frame_context={'token':'a'*32,'ticks':3,'deadline':100,'phase':20}
    s._chip8_frame_driving=True;pixels=bytes(2048)
    sample={'model':MODEL,'subset':FRAME_SUBSET,'environment-model':ENV,'state':'completed','token':'a'*32,
        'control-generation':1,'state-generation':4,'baseline-virtual-ticks':3,'baseline-deadline-ns':100,
        'completed-virtual-ticks':4,'completed-deadline-ns':100,'sampled-virtual-now-ns':100,'phase-numerator':0,
        'frame-generation':0,'pixels-hex':pixels.hex(),'pixels-sha256':hashlib.sha256(pixels).hexdigest(),
        'stop-pending':False,'stop-owned':True,'stop-consumed':True,'faulted':False,'key-wait':False,'layer-conflict':False}
    idle=sample|{'state':'idle','token':'','control-generation':2,'baseline-virtual-ticks':0,'baseline-deadline-ns':0,'completed-virtual-ticks':0,
        'completed-deadline-ns':0,'sampled-virtual-now-ns':0,'pixels-hex':'','pixels-sha256':'','stop-owned':False,'stop-consumed':False}
    old=s.vm.qmp.call;current=deepcopy(sample)
    def call(name,args=None,**kwargs):
        nonlocal current
        if name=='query-chip8-frame':return deepcopy(current)
        if name=='x-chip8-cancel-frame':current=deepcopy(idle);return deepcopy(current)
        return old(name,args,**kwargs)
    s.vm.qmp.call=call
    result=s._execute('c',1000);assert result['outcome']=='frame' and result['frame_fence']['owned'] and s._chip8_frame_context is None
    s._chip8_frame_context={'token':'a'*32,'ticks':3,'deadline':100,'phase':20};current=sample|{'state':'armed','stop-owned':False,'stop-consumed':False,'stop-pending':True}
    point=s.breakpoint(0x200);result=s._execute('c',1000)
    assert result['outcome']=='breakpoint' and result['session']['stop_reason']['breakpoint_ids']==[point['breakpoint_id']]
    assert not result['frame_fence']['owned'] and s._chip8_frame_context is None
    # A layer guard can mutate the live generation after the pending sample;
    # cancellation must compare against that live value, not its older latch.
    s._chip8_frame_context={'token':'a'*32,'ticks':3,'deadline':100,'phase':20}
    current=sample|{'state':'armed','stop-owned':False,'stop-consumed':False,'stop-pending':True,'layer-conflict':True}
    env['state-generation']=5;idle['state-generation']=5
    layer.update({'faulted':True,'fault-address':0x200,'fault-pc':0x200,'backing-valid':True,'stop-owned':False})
    # Exercise the stop-boundary path: the guest reaches the guard after the
    # preflight query but before the stopped-state query.
    layer['faulted']=False;layer['fault-address']=layer['fault-pc']=0
    def guard_stop(command,timeout):
        layer.update({'faulted':True,'fault-address':0x200,'fault-pc':0x200})
        return b'T05',False
    s.vm.gdb.execute=guard_stop
    result=s._execute('c',1000)
    assert result['outcome']=='layer_conflict' and not result['frame_fence']['owned']
    assert s._chip8_frame_context is None and not s.closed


def test_image_budget_refuses_before_publication(project):
    a=FrameHarness(project,'fa')
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0]
    with pytest.raises(ValueError,match='image budget'):a._frame_image(1)
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0]==before


def test_valid_other_png_cannot_be_substituted_for_checkpoint_pixels(project):
    a=FrameHarness(project,'fa');root=a.timeline_start(max_frames=3,max_bytes=65536,max_state_bytes=4096,max_image_bytes=4096)
    manifest=a._frame_manifest(root['timeline']);node=deepcopy(manifest['nodes'][0])
    rgba=bytes.fromhex('ffffffff')*2048;out=io.BytesIO();Image.frombytes('RGBA',(64,32),rgba).save(out,format='PNG')
    other=project._debug_artifact(a.run_id,'other.png','screenshot',out.getvalue(),{})
    node['frame']['image']={'artifact':other['artifact'],'sha256':other['sha256'],'size':other['size'],
                            'pixel_sha256':hashlib.sha256(rgba).hexdigest()}
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    with pytest.raises(ValueError,match='image and checkpoint'):a._history_validate_node_before_restore(node)
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]==before


def test_manifest_rejects_timing_and_combined_image_budget(project):
    a=FrameHarness(project,'fa');a.timeline_start(max_frames=3,max_bytes=65536,max_state_bytes=4096,max_image_bytes=4096)
    manifest=a._frame_manifest(a.timeline_advance()['timeline']);bad=deepcopy(manifest)
    bad['nodes'][-1]['frame']['next_deadline_ns']+=1
    with pytest.raises(ValueError,match='recurrence'):a._validate_manifest(bad)
    bad=deepcopy(manifest);bad['frame_config']['max_image_bytes']=1
    with pytest.raises(ValueError,match='budget'):a._validate_manifest(bad)


def test_known_key_wait_refuses_before_any_frame_arm():
    s,add,layer,env=machine();s.identity['cpu_subset']=FRAME_SUBSET;s.vm.fault['cpu-subset']=FRAME_SUBSET
    env.update({'cpu-subset':FRAME_SUBSET,'env-model':ENV,'key-wait':True})
    idle={'model':MODEL,'subset':FRAME_SUBSET,'environment-model':ENV,'state':'idle','token':'',
          'control-generation':0,'state-generation':env['state-generation'],'baseline-virtual-ticks':0,
          'baseline-deadline-ns':0,'completed-virtual-ticks':0,'completed-deadline-ns':0,
          'sampled-virtual-now-ns':0,'phase-numerator':0,'frame-generation':0,'pixels-hex':'','pixels-sha256':'',
          'stop-pending':False,'stop-owned':False,'stop-consumed':False,'faulted':False,'key-wait':True,'layer-conflict':False}
    calls=[];old=s.vm.qmp.call
    def call(name,args=None,**kwargs):
        calls.append(name)
        if name=='query-chip8-frame':return deepcopy(idle)
        return old(name,args,**kwargs)
    s.vm.qmp.call=call
    with pytest.raises(ValueError,match='key wait'):s._frame_admit()
    assert 'x-chip8-arm-frame' not in calls


def test_later_journal_failure_reports_durable_prefix_without_replay(project):
    a=FrameHarness(project,'fa');root=a.timeline_start(max_frames=4,max_bytes=65536,max_state_bytes=4096,max_image_bytes=4096)
    pending=a._history_pending;calls=[]
    def fails_later(*args,**kwargs):
        calls.append(True)
        if len(calls)==2:raise OSError('journal failure')
        return pending(*args,**kwargs)
    a._history_pending=fails_later
    with pytest.raises(OSError) as raised:a.timeline_advance(frames=2)
    receipt=raised.value.result
    assert receipt['completed_frames']==1 and len(receipt['frames'])==1 and receipt['requested_count']==2
    assert receipt['phase']=='pending-intent' and receipt['do_not_replay'] and receipt['owner_closed']
    assert receipt['last_committed_point']==receipt['frames'][0]['point'] and receipt['last_committed_history']!=root['timeline']
    row=project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(receipt['last_committed_history'],)).fetchone()
    assert json.loads(bytes(row['data']))['cursor']==receipt['last_committed_point'] and a.tick==1


def test_unrecorded_batch_failure_reports_completed_prefix(project):
    a=FrameHarness(project,'fa');run=a._frame_run;calls=[]
    def fails_later():
        calls.append(True)
        if len(calls)==2:raise TimeoutError('unknown sample outcome')
        return run()
    a._frame_run=fails_later
    with pytest.raises(TimeoutError) as raised:a.advance_frames(frames=2)
    receipt=raised.value.result
    assert receipt['completed_frames']==1 and len(receipt['frames'])==1 and receipt['requested_count']==2
    assert receipt['do_not_replay'] and receipt['owner_closed'] and a.tick==1


def test_post_execution_growth_exhaustion_reports_prefix_and_artifacts(project):
    a=FrameHarness(project,'fa');root=a.timeline_start(max_frames=4,max_bytes=17000,max_state_bytes=16000,max_image_bytes=1000)
    run=a._frame_run
    def growing():
        result=run();a.padding=7000 if a.tick==1 else 11000
        return result
    a._frame_run=growing
    with pytest.raises(ValueError,match='byte budget exceeded') as raised:a.timeline_advance(frames=2)
    receipt=raised.value.result
    assert receipt['completed_frames']==1 and receipt['owner_closed'] and receipt['do_not_replay']
    assert receipt['checkpoint']['size']>10000 and receipt['image']['size']>0
    assert receipt['last_committed_point']==receipt['frames'][0]['point'] and a.tick==2
    assert receipt['last_observed_journal']!=receipt['last_committed_history']
