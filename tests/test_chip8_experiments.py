"""Host contracts for CHIP-8 paired experiments; no guest is run."""
from copy import deepcopy
import hashlib
import json
import struct
import pytest
from test_chip8_history import Harness,project
from fdisbull.chip8_experiments import Chip8ExperimentMixin,project_document,_candidate,_script
from fdisbull.chip8_history import KEY_SUBSET


def _qcow():
    data=bytearray(104);struct.pack_into('>IIQIIQI',data,0,0x514649fb,3,0,0,16,1024*1024,0)
    struct.pack_into('>I',data,100,104);return bytes(data)


class Subject(Chip8ExperimentMixin,Harness):
    def __init__(self,project,run):
        super().__init__(project,run)
        self.identity.update(cpu_subset=KEY_SUBSET,version_sha256=self.version['sha256'],profile='chip8-classic-pilot-default-v1')
        self.metadata.update(backend='qemu-chip8',version_sha256=self.version['sha256'])
        self._qemu_history_live=None;self.snap=self._snapshot();self.loads=[]
    def _artifact(self,name,kind,data,metadata):return self.project._debug_artifact(self.run_id,name,kind,data,metadata)
    def _event(self,*args):pass
    def _snapshot(self):
        keys={'epoch':1,'active':False,'generation':0,'accepted-edges':0,'held-mask':0,'key-mask':0,'state-generation':0}
        layers={'active':[],'generation':0,'ram_base':{},'ram_applied':{},'definitions':[]}
        from fdisbull.chip8_trial_observations import SEMANTIC
        from fdisbull.chip8_keys import KEY_ENV
        from fdisbull.chip8_layers import LAYER_MODEL
        from fdisbull.qemu_chip8 import RNG_MODEL,PROFILE
        from test_qemu_chip8_devices import environment
        env=environment();env.update({'cpu-subset':KEY_SUBSET,'env-model':KEY_ENV,'state-generation':0,
            'rng-model':RNG_MODEL,'rng-seed':0,'rng-state':0,'rng-draws':0,'layer-model':LAYER_MODEL,'layer-generation':0})
        blank=bytes(4096).hex();native={'model':LAYER_MODEL,'generation':0,'execute-mask-hex':blank,
            'execute-bytes-hex':blank,'execute-base-hex':blank,'execution-bytes':0,'faulted':False,
            'fault-address':0,'fault-pc':0,'stop-owned':False,'backing-valid':True,'mismatch-address':0}
        fault={'profile':PROFILE,'cpu-subset':KEY_SUBSET,'faulted':False,'fault-code':0,'fault-pc':0,'fault-opcode':0}
        from fdisbull.qemu_chip8 import REGISTER_NAMES
        ram=bytes(4096);raw_regs={k:'0x0' for k in REGISTER_NAMES};raw_regs['pc']='0x200';regs={'registers':raw_regs}
        identity=deepcopy(self.identity) if self is not None else {'cpu_subset':KEY_SUBSET,'profile':PROFILE,'source_sha256':'1'*64,'version_sha256':'2'*64,'qemu_sha256':'3'*64}
        return dict(identity=identity,registers=regs,cpu={k:int(v,16) for k,v in raw_regs.items()},ram_hex=ram.hex(),memory=[],environment=env,
                    semantic={**{k:env[k] for k in SEMANTIC},'accepted-edges':0,'held-mask':0,'fault':fault},fault=fault,layers=layers,layer_native=native,hooks={'hooks':[],'pending':None},
                    keys={k:keys[k] for k in ('active','held-mask','key-mask','accepted-edges')},key_native=keys)
    def _chip8_experiment_snapshot(self,observations):
        result=deepcopy(self.snap);ram=bytes.fromhex(result['ram_hex'])
        result['memory']=[dict(address=r['address'],length=r['length'],hex=ram[int(r['address'],0):int(r['address'],0)+r['length']].hex(),
            sha256=hashlib.sha256(ram[int(r['address'],0):int(r['address'],0)+r['length']]).hexdigest()) for r in observations]
        return result
    def _chip8_experiment_controls(self):
        return dict(hooks=deepcopy(self.snap['hooks']),keys=deepcopy(self.snap['keys']),key_native=deepcopy(self.snap['key_native']),layers=deepcopy(self.snap['layers']))
    def save_state(self,name,*,timeout_ms=60000):
        x=self.snap;metadata={'format':'fdisbull-qemu-chip8-state-6','identity':self.identity,'host_files_restored':False,
            'ram_sha256':hashlib.sha256(bytes.fromhex(x['ram_hex'])).hexdigest(),'registers':x['registers'],'environment':x['environment'],
            'fault':x['fault'],'layer_state':x['layers'],'layer_native':x['layer_native'],'hook_state':x['hooks'],'key_state':x['key_native']}
        return self._artifact(name,'state',_qcow(),metadata)
    def load_state(self,artifact,*,timeout_ms=60000):self.loads.append(artifact);return {'host_files_restored':False}
    def layers(self,active=None,*,conflict='stop'):return {'active':active or []}


def _script_doc(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}


def test_real_fdb_experiment_roundtrip_preflight_and_hash_guards(project):
    s=Subject(project,'experiment');script=_script_doc({'op':'step'})
    saved=s.save_experiment('trial.json',script=script,observations=[{'address':0x300,'length':1}])
    doc=project_document(project,saved['artifact'],s.version['id'])
    assert doc['snapshot']['memory'][0]['hex']=='00' and doc['checkpoint']['metadata_sha256']
    assert s.restore_experiment(saved['artifact'])['active_layers']==[]
    rows=project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    s._qemu_history_live={'valid':True,'cursor':'old'}
    with pytest.raises(ValueError):s.save_experiment('bad.json',script=_script_doc({'op':'write-memory','address':0,'data_hex':'00','expected_hex':'00'}))
    assert s._qemu_history_live['valid'] and project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==rows
    state=doc['checkpoint']['artifact']
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',('{}',state))
    with pytest.raises(ValueError,match='checkpoint'):project_document(project,saved['artifact'])


def test_candidate_validation_uses_saved_base_and_does_not_touch_guest(project):
    s=Subject(project,'candidate');snap=s._snapshot()
    item=project.debug_layer('candidate',kind='ram',patches=[{'address':'0x300','expected_hex':'00','data_hex':'02'}])
    assert _candidate(project,s.version['id'],[item['layer']],snap)[item['layer']]==item['sha256']
    snap['layers'].update(active=['old'],ram_base={'768':0},ram_applied={'768':1})
    with pytest.raises(ValueError,match='changed backing'):_candidate(project,s.version['id'],[item['layer']],snap)
    assert not s.loads


def test_script_preflight_rejects_unsupported_and_hook_alias(project):
    s=Subject(project,'script')
    with pytest.raises(ValueError):_script(_script_doc({'op':'step'},{'op':'write-memory','address':0,'data_hex':'00','expected_hex':'00'}),s)
    with pytest.raises(ValueError):s.save_experiment('bad.json',script=_script_doc({'op':'delete-hook','hook':'unknown'}))
    before=project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    for invalid in ({},'',0):
        with pytest.raises(ValueError,match='observations'):s.save_experiment('bad.json',script=_script_doc({'op':'step'}),observations=invalid)
    assert not s.loads and project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==before


def _trial_report(s,steps,result):
    script=_script_doc(*steps);raw=json.dumps(script,sort_keys=True,separators=(',',':')).encode()
    script_art=s._artifact('script.json','script',raw,{})
    report={'ok':True,'run':s.run_id,'steps':[{'index':0,'op':steps[0]['op'],'ok':True,'result':result}],
            'requested_steps':1,'completed_steps':1,'script_artifact':script_art['artifact'],
            'script_sha256':hashlib.sha256(raw).hexdigest()}
    artifact=s._artifact('result.json','script-result',json.dumps(report).encode(),{})
    report['artifact']=artifact['artifact']
    return {'script':script,'observations':[]},report


def test_trial_memory_receipt_must_match_requested_read(project):
    from fdisbull.chip8_trial_observations import capture_trial
    s=Subject(project,'memory-proof')
    document,report=_trial_report(s,[{'op':'memory','address':0x300,'length':1}],
        {'address':'0x301','length':1,'space':'physical','hex':'00'})
    with pytest.raises(ValueError,match='memory receipt'):capture_trial(s,document,report)


def test_trial_screenshot_must_bind_pixels_and_metadata(project):
    import io
    from PIL import Image
    from fdisbull.chip8_trial_observations import capture_trial
    s=Subject(project,'image-proof');image=Image.new('RGBA',(64,32),(0,0,0,255));out=io.BytesIO();image.save(out,format='PNG')
    digest=hashlib.sha256(image.tobytes()).hexdigest();env={'test':'environment'}
    artifact=s._artifact('frame.png','screenshot',out.getvalue(),{'format':'chip8-frame-png-1','width':64,'height':32,
        'identity':s.identity,'environment':env,'pixel_sha256':digest})
    document,report=_trial_report(s,[{'op':'screenshot'}],dict(artifact=artifact['artifact'],sha256=artifact['sha256'],
        pixel_sha256='0'*64,environment=env))
    with pytest.raises(ValueError,match='pixel or source'):capture_trial(s,document,report)


def test_baseline_failure_skips_candidate_and_restores(project,monkeypatch):
    import fdisbull.debug_script as scripts
    import fdisbull.chip8_trial_observations as observations
    s=Subject(project,'failure');saved=s.save_experiment('trial.json',script=_script_doc({'op':'step'}))
    calls=[]
    def execute(*args,**kwargs):calls.append('execute');return {'failed':True}
    def capture(*args,**kwargs):return {'format':observations.FORMAT,'ok':False,'complete':False,'incomplete_reasons':['script_incomplete']}
    monkeypatch.setattr(scripts,'execute_script',execute);monkeypatch.setattr(observations,'capture_trial',capture)
    result=s.compare_experiment(saved['artifact'],layers=[])
    assert calls==['execute'] and len(s.loads)==2 and result['layer'] is None
    assert result['comparison'] is None and result['baseline_restored'] and not result['ok']


def _complete_trial(fmt):
    snapshot=Subject._snapshot(None);cpu=snapshot['cpu'];devices=snapshot['semantic']
    plan={'script_sha256':'a'*64,'memory':[],'observations':[],'screenshots':[]}
    return {'format':fmt,'ok':True,'complete':True,'incomplete_reasons':[],'script_report':'report',
            'registers':cpu,'memory':[],'observations':[],'screenshots':[],'devices':devices,'identity':snapshot['identity'],'capture_plan':plan,
            'provenance':{'snapshot':snapshot,
                          'report':{'artifact':'report','script_sha256':'a'*64,'ok':True,'requested_steps':0,'completed_steps':0,'steps':[]}}}


def test_final_restore_failure_preserves_completed_arms_and_closes(project,monkeypatch):
    import fdisbull.debug_script as scripts
    import fdisbull.chip8_trial_observations as observations
    s=Subject(project,'final-failure');saved=s.save_experiment('trial.json',script=_script_doc({'op':'step'}))
    monkeypatch.setattr(scripts,'execute_script',lambda *args,**kwargs:{'ok':True})
    monkeypatch.setattr(observations,'capture_trial',lambda *args,**kwargs:_complete_trial(observations.FORMAT))
    original=s.load_state
    def fail_final(*args,**kwargs):
        if len(s.loads)==2:raise RuntimeError('lost final restore')
        return original(*args,**kwargs)
    s.load_state=fail_final
    result=s.compare_experiment(saved['artifact'],layers=[])
    assert result['baseline'] and result['layer'] and result['comparison']['complete']
    assert not result['ok'] and not result['baseline_restored'] and s.closed
    assert result['error']['do_not_replay'] and result['error']['owner_closed']


def test_publish_failure_retains_result_and_closes(project,monkeypatch):
    import fdisbull.debug_script as scripts
    import fdisbull.chip8_trial_observations as observations
    s=Subject(project,'publish-failure');saved=s.save_experiment('trial.json',script=_script_doc({'op':'step'}))
    monkeypatch.setattr(scripts,'execute_script',lambda *args,**kwargs:{'ok':True})
    monkeypatch.setattr(observations,'capture_trial',lambda *args,**kwargs:_complete_trial(observations.FORMAT))
    original=s._artifact
    def fail_publish(name,kind,data,metadata):
        if kind=='experiment-comparison':raise RuntimeError('publication lost')
        return original(name,kind,data,metadata)
    s._artifact=fail_publish
    with pytest.raises(RuntimeError,match='publication') as error:s.compare_experiment(saved['artifact'],layers=[])
    assert error.value.result['baseline_restored'] and error.value.result['baseline'] and error.value.result['layer']
    assert s.closed


def test_forged_empty_complete_trials_never_establish_equality():
    from fdisbull.chip8_trial_observations import compare_trials,FORMAT
    empty={'format':FORMAT,'ok':True,'complete':True,'incomplete_reasons':[],
           'registers':{},'memory':[],'observations':[],'screenshots':[],'devices':{}}
    with pytest.raises(ValueError,match='CPU'):compare_trials(empty,empty)
    partial={'format':FORMAT,'ok':False,'complete':False,'incomplete_reasons':['partial']}
    assert compare_trials(partial,partial)['observed_difference'] is None


def test_png_comparison_uses_decoded_pixels_not_file_encoding():
    from fdisbull.chip8_trial_observations import compare_trials,FORMAT
    left=_complete_trial(FORMAT);right=deepcopy(left)
    left['capture_plan']['screenshots']=[0];right['capture_plan']['screenshots']=[0]
    left['screenshots']=[{'step':0,'artifact':'a','sha256':'1'*64,'pixel_sha256':'3'*64}]
    right['screenshots']=[{'step':0,'artifact':'b','sha256':'2'*64,'pixel_sha256':'3'*64}]
    for trial in (left,right):
        image=trial['screenshots'][0];report=trial['provenance']['report']
        report.update(requested_steps=1,completed_steps=1,steps=[{'index':0,'op':'screenshot','ok':True,'result':deepcopy(image)}])
    assert compare_trials(left,right)['observed_difference'] is False
    right['screenshots'][0]['pixel_sha256']='4'*64
    right['provenance']['report']['steps'][0]['result']['pixel_sha256']='4'*64
    assert compare_trials(left,right)['observed_difference'] is True


def test_hooked_runs_require_single_hit_and_bounded_report_plan(project):
    from fdisbull.chip8_experiments import _report_budget
    hooks=[{'actions':[{'op':'registers','registers':{}} for _ in range(16)]}]
    with pytest.raises(ValueError,match='stop_on_hook'):_report_budget(project,project.version()['id'],[{'op':'run'}],hooks)
    with pytest.raises(ValueError,match='report plan'):
        _report_budget(project,project.version()['id'],[{'op':'run','stop_on_hook':True} for _ in range(4)],hooks)


def test_completed_script_receipt_survives_observation_failure(project,monkeypatch):
    import fdisbull.debug_script as scripts
    import fdisbull.chip8_trial_observations as observations
    s=Subject(project,'observe-failure');saved=s.save_experiment('trial.json',script=_script_doc({'op':'step'}))
    monkeypatch.setattr(scripts,'execute_script',lambda *args,**kwargs:{'artifact':'completed-report','ok':True})
    def fail(*args,**kwargs):raise ValueError('bad evidence')
    monkeypatch.setattr(observations,'capture_trial',fail)
    result=s.compare_experiment(saved['artifact'],layers=[])
    assert result['baseline']['script_report']=='completed-report' and result['layer'] is None
    assert result['error']['do_not_replay'] and result['error']['owner_closed'] and not result['baseline_restored']


@pytest.mark.parametrize('field',['version','origin'])
def test_offline_identity_refuses_rehashed_foreign_document(project,field):
    s=Subject(project,'foreign-'+field);saved=s.save_experiment('trial.json',script=_script_doc({'op':'step'}))
    row=project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(saved['artifact'],)).fetchone()
    document=json.loads(bytes(row['data']))
    if field=='version':document['version_sha256']='f'*64;document['runtime']['version_sha256']='f'*64
    else:document['origin_run']='foreign-run'
    data=json.dumps(document,sort_keys=True,separators=(',',':')).encode()
    with project.transaction(True):
        project.db.execute('UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?',
                           (data,hashlib.sha256(data).hexdigest(),saved['artifact']))
    with pytest.raises(ValueError,match='source/version|origin'):project_document(project,saved['artifact'])


def test_intermediate_value_must_match_retained_report():
    from fdisbull.chip8_trial_observations import compare_trials,FORMAT
    trial=_complete_trial(FORMAT)
    trial['capture_plan']['observations']=[{'step':0,'op':'memory'}]
    trial['observations']=[{'step':0,'op':'memory','value':{'address':'0x300','length':1,'hex':'01'}}]
    trial['provenance']['report'].update(requested_steps=1,completed_steps=1,steps=[
        {'index':0,'op':'memory','ok':True,'result':{'address':'0x300','length':1,'hex':'02'}}])
    with pytest.raises(ValueError,match='differs from report'):compare_trials(trial,trial)


def test_screenshot_png_must_match_native_framebuffer_pixels(project):
    import io
    from PIL import Image
    from fdisbull.chip8_trial_observations import capture_trial
    s=Subject(project,'native-pixels');image=Image.new('RGBA',(64,32),(0,0,0,255));out=io.BytesIO();image.save(out,format='PNG')
    pixel_sha=hashlib.sha256(image.tobytes()).hexdigest();environment=deepcopy(s.snap['environment'])
    # Valid native proof has a white second pixel, while this PNG is all black.
    artifact=s._artifact('frame.png','screenshot',out.getvalue(),{'format':'chip8-frame-png-1','width':64,'height':32,
        'identity':s.identity,'environment':environment,'pixel_sha256':pixel_sha})
    document,report=_trial_report(s,[{'op':'screenshot'}],dict(artifact=artifact['artifact'],sha256=artifact['sha256'],
        pixel_sha256=pixel_sha,environment=environment))
    with pytest.raises(ValueError,match='native pixels'):capture_trial(s,document,report)
