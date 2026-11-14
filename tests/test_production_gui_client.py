import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/ci';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('gui_client',SCRIPTS/'production_gui_client.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def setup(tmp_path,runner,clock=lambda:1000,sleep=lambda seconds:None):
    root=tmp_path/'client';root.mkdir(mode=0o700)
    (root/'installation.json').write_text('{"schema":"fdisbull-gui-client-1"}')
    (root/'installation.json').chmod(0o600);(root/'client.lock').touch(mode=0o600)
    (root/'history.json').write_text('{"schema":"fdisbull-gui-client-history-1","entries":{}}');(root/'history.json').chmod(0o600)
    return m.GuiClient(root,runner=runner,clock=clock,sleep=sleep)


def envelope(value):return {'returncode':0,'stdout':json.dumps(value).encode(),'stderr':b'', 'timed_out':False,'overflow':False}


def test_action_submit_then_result_and_exact_fixed_ssh(tmp_path,monkeypatch):
    calls=[];monkeypatch.setenv('GITHUB_TOKEN','credential-should-not-transfer')
    def runner(argv,**kw):
        request=json.loads(kw['input_bytes']);calls.append((argv,request,kw))
        if request['operation']=='submit':return envelope({'status':'pending','request_id':request['nonce']})
        return envelope({'status':'complete','request_id':request['request_id'],
                         'result':{'http_status':201,'data':None,'request_id':'safe'}})
    c=setup(tmp_path,runner);tr=m.GuiProviderTransport('github',c)
    result=tr.for_action('incident:retry')('POST','/repos/x/actions/jobs/20/rerun',{})
    assert result['http_status']==201 and [c[1]['operation'] for c in calls]==['submit','result']
    assert calls[0][0]==['/usr/bin/tailscale','ssh','tiga@100.76.103.43',m.PYTHON,'-I',m.HELPER,'request']
    assert 'GITHUB_TOKEN' not in calls[0][2]['env']
    record=next(c.state.glob('*.json')) if False else next(p for p in c.state.glob('*.json') if p.name not in ('installation.json','history.json'))
    assert 'credential-should-not-transfer' not in record.read_text()


def test_lost_submit_never_submits_again_even_after_restart(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':raise TimeoutError()
        return envelope({'status':'missing'})
    c=setup(tmp_path,runner);doc={'operation':'request','provider':'github','method':'POST','path':'/some/path','payload':{},'action_key':'k'}
    for _ in range(2):
        with pytest.raises(RuntimeError,match='unknown'):c.call('provider',doc,key='provider-action:k',timeout=60)
    assert [x['operation'] for x in calls]==['submit','result','result']


def test_conflicting_action_content_never_submits(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'ok':True}})
    c=setup(tmp_path,runner);assert c.call('provider',{'first':1},key='k',timeout=60)=={'ok':True}
    before=len(calls)
    with pytest.raises(ValueError,match='binding'):c.call('provider',{'first':2},key='k',timeout=60)
    assert len(calls)==before


def test_completed_result_retrievable_after_expiry_without_resubmit(tmp_path):
    now=[1000];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'ok':True}})
    c=setup(tmp_path,runner,clock=lambda:now[0]);assert c.call('provider',{'x':1},key='k',timeout=60)=={'ok':True}
    now[0]=2000;assert c.call('provider',{'x':1},key='k',timeout=60)=={'ok':True}
    assert [d['operation'] for d in calls]==['submit','result','result']


def test_started_unknown_times_out_without_resubmit(tmp_path):
    now=[1000];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        return envelope({'status':'pending','request_id':doc['nonce']}) if doc['operation']=='submit' else envelope({'status':'unknown','request_id':doc['request_id']})
    c=setup(tmp_path,runner,clock=lambda:now[0],sleep=lambda seconds:now.__setitem__(0,now[0]+seconds))
    with pytest.raises(RuntimeError,match='unknown'):c.call('provider',{'x':1},key='k',timeout=3)
    assert sum(x['operation']=='submit' for x in calls)==1


def test_source_adapter_keeps_exact_minimal_server_payload():
    class Client:
        def __init__(self):self.calls=[]
        def call(self,kind,doc,**kwargs):self.calls.append((kind,doc,kwargs));return {'result':{'status':'completed'}}
    client=Client();source=m.GuiSourceTransport(client);payload={'target':{'provider':'github'},'source_prepare':{'event_key':'a'*64}}
    assert source.repair('action',payload)=={'status':'completed'}
    assert client.calls[0][1]=={'operation':'repair','key':'action','payload':payload}
    assert client.calls[0][2]['key']=='source-repair:action'
    source.reconcile('action',payload)
    assert client.calls[1][1]=={'operation':'reconcile','key':'action','payload':payload} and client.calls[1][2]['key'] is None


def test_uninitialized_state_never_created_or_submitted(tmp_path):
    calls=[];c=m.GuiClient(tmp_path/'missing',runner=lambda *a,**kw:calls.append(1))
    with pytest.raises(ValueError):c.call('provider',{'x':1},key='a')
    assert not calls and not c.state.exists()


def test_missing_prior_nonce_record_fails_closed_without_submit(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'ok':True}})
    client=setup(tmp_path,runner);assert client.call('provider',{'x':1},key='k',timeout=60)=={'ok':True}
    item=next(p for p in client.state.glob('*.json') if p.name not in ('history.json','installation.json'))
    item.unlink();before=len(calls)
    with pytest.raises(ValueError,match='history'):client.call('provider',{'x':1},key='k',timeout=60)
    assert len(calls)==before


def test_gui_source_preparation_uses_stable_binding_for_same_evidence():
    class Client:
        def __init__(self):self.calls=[]
        def call(self,kind,doc,**kw):self.calls.append((kind,doc,kw));return {'result':{'status':'verified_reproducer'}}
    c=Client();source=m.GuiSourceTransport(c);target={'provider':'gitlab'};evidence={'junit':'closed'}
    source.prepare(target,evidence);source.prepare(target,evidence)
    assert c.calls[0][2]['key']==c.calls[1][2]['key'] and c.calls[0][1]==c.calls[1][1]


def test_actual_gui_spool_and_client_never_relaunch_action(tmp_path):
    spec2=importlib.util.spec_from_file_location('gui_spool_fixture',SCRIPTS/'production_gui_transport.py')
    shim=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(shim)
    shim.provider=shim._load('production_transport.py');shim.source=shim._load('production_source_transport.py')
    parent=tmp_path/'spool-parent';parent.mkdir(mode=0o700);spool_dir=parent/'spool';spool_dir.mkdir(mode=0o700);anchor=parent/'anchor.json'
    history={'schema':'fdisbull-gui-history-1','sequence':0,'requests':{}}
    files={spool_dir/'installation.json':shim._bytes({'installation_id':shim.INSTALLATION_ID,'volume_uuid':shim.CACHE_UUID}),
           spool_dir/'history.json':shim._bytes(history),spool_dir/'lane.lock':b'',
           anchor:shim._bytes({'installation_id':shim.INSTALLATION_ID,'sequence':0,'history_sha256':shim._digest(shim._bytes(history))})}
    for path,data in files.items():path.write_bytes(data);path.chmod(0o600)
    child_calls=[]
    def child(argv,payload,timeout):
        child_calls.append((argv,json.loads(payload)))
        return {'returncode':0,'stdout':b'{"http_status":201,"data":null,"request_id":null}',
                'stderr':b'', 'timed_out':False,'overflow':False}
    spool=shim.GuiSpool(spool_dir,anchor,mount=lambda s,a:True,clock=lambda:1000,activation=lambda:{'allowed_kinds':['credential_probe','provider']},
                        gui_check=lambda:True,runner=child,kick=lambda:None)
    def ssh(argv,**kw):
        doc=json.loads(kw['input_bytes'])
        if doc['operation']=='submit':
            result=spool.submit(doc['kind'],doc['request'],doc['expires_epoch'],doc['nonce']);spool.worker()
        else:result=spool.result(doc['request_id'])
        return envelope(result)
    now=[1000]
    client=setup(tmp_path,ssh,clock=lambda:now[0],sleep=lambda seconds:now.__setitem__(0,now[0]+seconds))
    provider=m.GuiProviderTransport('github',client)
    action=provider.for_action('incident:1')
    path='/repos/seeker-cyber-maker/fDisBull/actions/jobs/20/rerun'
    assert action('POST',path,{})['http_status']==201
    assert action('POST',path,{})['http_status']==201
    assert len(child_calls)==1 and child_calls[0][1]['action_key']=='incident:1'


def actual_spool_client(tmp_path,client_clock,child_runner,client_sleep=lambda seconds:None):
    spec2=importlib.util.spec_from_file_location('gui_spool_retry_fixture',SCRIPTS/'production_gui_transport.py')
    shim=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(shim)
    shim.provider=shim._load('production_transport.py');shim.source=shim._load('production_source_transport.py')
    parent=tmp_path/'spool-parent';parent.mkdir(mode=0o700);spool_dir=parent/'spool';spool_dir.mkdir(mode=0o700);anchor=parent/'anchor.json'
    history={'schema':'fdisbull-gui-history-1','sequence':0,'requests':{}}
    files={spool_dir/'installation.json':shim._bytes({'installation_id':shim.INSTALLATION_ID,'volume_uuid':shim.CACHE_UUID}),
           spool_dir/'history.json':shim._bytes(history),spool_dir/'lane.lock':b'',
           anchor:shim._bytes({'installation_id':shim.INSTALLATION_ID,'sequence':0,'history_sha256':shim._digest(shim._bytes(history))})}
    for path,data in files.items():path.write_bytes(data);path.chmod(0o600)
    spool=shim.GuiSpool(spool_dir,anchor,mount=lambda s,a:True,clock=client_clock,
        activation=lambda:{'allowed_kinds':['credential_probe','provider']},gui_check=lambda:True,
        runner=child_runner,kick=lambda:None)
    def ssh(argv,**kw):
        doc=json.loads(kw['input_bytes'])
        if doc['operation']=='submit':
            result=spool.submit(doc['kind'],doc['request'],doc['expires_epoch'],doc['nonce'])
            if result.get('status')=='pending':spool.worker()
        else:result=spool.result(doc['request_id'])
        return envelope(result)
    client=setup(tmp_path,ssh,clock=client_clock,sleep=client_sleep)
    return shim,spool,client


def test_get_retries_once_after_only_completed_runner_unknown(tmp_path):
    child_calls=[]
    def child(argv,payload,timeout):
        child_calls.append(json.loads(payload))
        if len(child_calls)==1:
            return {'returncode':1,'stdout':b'private child error','stderr':b'private trace',
                    'timed_out':False,'overflow':False}
        return {'returncode':0,'stdout':b'{"http_status":200,"data":{"id":43571017539},"request_id":"r-safe"}',
                'stderr':b'', 'timed_out':False,'overflow':False}
    now=[1000]
    shim,spool,client=actual_spool_client(tmp_path,lambda:now[0],child)
    provider=m.GuiProviderTransport('github',client)
    response=provider.request('GET','/repos/seeker-cyber-maker/fDisBull/actions/runs/43571017539')
    assert response=={'http_status':200,'data':{'id':43571017539},'request_id':'r-safe'}
    history=spool._check()['requests']
    terminal=[(key,value) for key,value in history.items() if value['phase']=='terminalunknown']
    complete=[(key,value) for key,value in history.items() if value['phase']=='complete']
    assert len(terminal)==len(complete)==1 and terminal[0][0]!=complete[0][0]
    assert json.loads((spool.spool/(terminal[0][0]+'.done')).read_bytes())['reason']=='runner_nonzero'
    assert json.loads((spool.spool/(terminal[0][0]+'.done')).read_bytes())['runner']=={
        'returncode':1,'timed_out':False,'overflow':False}
    assert b'private child error' not in b''.join(p.read_bytes() for p in spool.spool.iterdir() if p.is_file())
    assert b'private trace' not in b''.join(p.read_bytes() for p in spool.spool.iterdir() if p.is_file())
    assert len(child_calls)==2 and all(doc['method']=='GET' for doc in child_calls)


def test_post_completed_unknown_is_never_retried(tmp_path):
    child_calls=[]
    def child(argv,payload,timeout):
        child_calls.append(json.loads(payload))
        return {'returncode':1,'stdout':b'private error','stderr':b'', 'timed_out':False,'overflow':False}
    now=[1000]
    shim,spool,client=actual_spool_client(tmp_path,lambda:now[0],child)
    provider=m.GuiProviderTransport('github',client)
    action=provider.for_action('incident:retry')
    with pytest.raises(m.CompletedGuiFailure):
        action('POST','/repos/seeker-cyber-maker/fDisBull/actions/jobs/20/rerun',{})
    history=spool._check()['requests']
    assert len(history)==1 and next(iter(history.values()))['phase']=='terminalunknown'
    assert len(child_calls)==1 and child_calls[0]['method']=='POST'


def test_held_unknown_get_is_not_retried(tmp_path):
    now=[1000];child_calls=[]
    def child(argv,payload,timeout):
        child_calls.append(json.loads(payload))
        raise TimeoutError('outer process cleanup uncertain')
    shim,spool,client=actual_spool_client(tmp_path,lambda:now[0],child,
                                          client_sleep=lambda seconds:now.__setitem__(0,now[0]+seconds))
    provider=m.GuiProviderTransport('github',client)
    with pytest.raises(RuntimeError,match='unknown'):
        provider.request('GET','/repos/seeker-cyber-maker/fDisBull/actions/runs/43571017539')
    history=spool._check()['requests']
    assert len(history)==1 and next(iter(history.values()))['phase']=='started'
    assert len(child_calls)==1 and child_calls[0]['method']=='GET'


def test_gui_get_retry_budget_is_charged_conservatively(tmp_path):
    spec_runtime=importlib.util.spec_from_file_location('gui_budget_runtime',SCRIPTS/'production_runtime.py')
    runtime=importlib.util.module_from_spec(spec_runtime);spec_runtime.loader.exec_module(runtime)
    class Raw:
        request_budget=2
        def reserve(self):return {'allowed':True,'next_refresh_at':1300}
        def request(self,*args):self.calls=getattr(self,'calls',0)+1;return {'ok':True}
    raw=Raw();gate=runtime._GatedTransport(raw,lambda:None,lambda:1000,'github')
    assert gate.request('GET','/fixed/read')=={'ok':True}
    assert gate.remaining==98 and raw.calls==1


def test_expired_retained_result_uses_independent_read_deadline(tmp_path):
    now=[1000];elapsed=[0.0];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append((doc,kw['timeout']))
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        if now[0]>=2000:
            assert kw['timeout']>1.014
            elapsed[0]+=1.014
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'ok':True}})
    c=setup(tmp_path,runner,clock=lambda:now[0]);c.monotonic=lambda:elapsed[0]
    assert c.call('provider',{'x':1},key='k',timeout=60)=={'ok':True}
    now[0]=2000
    assert c.call('provider',{'x':1},key='k',timeout=60)=={'ok':True}
    assert [d['operation'] for d,_ in calls]==['submit','result','result']
    assert calls[1][0]['request_id']==calls[2][0]['request_id']


def test_result_transport_retry_same_nonce_and_total_deadline(tmp_path):
    elapsed=[0.0];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append((doc,kw['timeout']))
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        if len(calls)==2:
            elapsed[0]+=20
            raise TimeoutError()
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'accepted':True}})
    c=setup(tmp_path,runner);c.monotonic=lambda:elapsed[0]
    doc={'operation':'request','method':'POST','provider':'github','path':'/fixed','payload':{}}
    assert c.call('provider',doc,key='action',timeout=60)=={'accepted':True}
    assert [x[0]['operation'] for x in calls]==['submit','result','result']
    assert calls[1][0]==calls[2][0]=={'operation':'result','request_id':calls[0][0]['nonce']}
    assert calls[1][1]==45 and calls[2][1]==25


def test_result_transport_retry_exhaustion_is_unknown_without_resubmit(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        raise TimeoutError()
    c=setup(tmp_path,runner)
    with pytest.raises(RuntimeError,match='GUI result outcome unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result','result']
    assert calls[1]==calls[2]


def test_result_validation_failure_does_not_retry(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return envelope({'status':'complete','request_id':'different','result':{'ok':True}})
    c=setup(tmp_path,runner)
    with pytest.raises(RuntimeError,match='identity mismatch'):c.call('provider',{'x':1},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result']


def test_expiry_before_submit_does_not_start_action(tmp_path):
    times=iter([1000,1001,1001]);calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        return envelope({'status':'pending','request_id':doc['request_id']})
    c=setup(tmp_path,runner,clock=lambda:next(times))
    with pytest.raises(RuntimeError,match='action outcome unknown'):c.call('provider',{'method':'POST'},key='k',timeout=1)
    assert [d['operation'] for d in calls]==['result']


def test_result_lookup_deadline_exhausted_never_starts_second_read(tmp_path):
    elapsed=[0.0];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        elapsed[0]+=45
        raise TimeoutError()
    c=setup(tmp_path,runner);c.monotonic=lambda:elapsed[0]
    with pytest.raises(RuntimeError,match='GUI result outcome unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result']


def test_malformed_result_json_is_not_retried(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return {'returncode':0,'stdout':b'not-json','timed_out':False,'overflow':False}
    c=setup(tmp_path,runner)
    with pytest.raises(RuntimeError,match='unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result']


def test_structured_helper_rejection_does_not_retry(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return {'returncode':1,'stdout':b'{"error":"gui_transport_unavailable"}',
                'timed_out':False,'overflow':False}
    c=setup(tmp_path,runner)
    with pytest.raises(RuntimeError,match='unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result']


def test_expired_retained_pending_one_lookup_no_submit(tmp_path):
    now=[1000];calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        if now[0]>=2000:return envelope({'status':'pending','request_id':doc['request_id']})
        return envelope({'status':'complete','request_id':doc['request_id'],'result':{'ok':True}})
    c=setup(tmp_path,runner,clock=lambda:now[0])
    assert c.call('provider',{'method':'POST'},key='k',timeout=60)=={'ok':True}
    now[0]=2000;before=len(calls)
    with pytest.raises(RuntimeError,match='action outcome unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls[before:]]==['result']
    assert calls[-1]['request_id']==calls[0]['nonce']


def test_overflow_response_is_not_retried(tmp_path):
    calls=[]
    def runner(argv,**kw):
        doc=json.loads(kw['input_bytes']);calls.append(doc)
        if doc['operation']=='submit':return envelope({'status':'pending','request_id':doc['nonce']})
        return {'returncode':1,'stdout':b'{}','timed_out':False,'overflow':True}
    c=setup(tmp_path,runner)
    with pytest.raises(RuntimeError,match='unknown'):c.call('provider',{'method':'POST'},key='k',timeout=60)
    assert [d['operation'] for d in calls]==['submit','result']
