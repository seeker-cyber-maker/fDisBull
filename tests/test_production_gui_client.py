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
        return {'returncode':0,'stdout':b'{"http_status":201,"data":null,"request_id":null}', 'timed_out':False,'overflow':False}
    spool=shim.GuiSpool(spool_dir,anchor,mount=lambda s,a:True,clock=lambda:1000,activation=lambda:{'allowed_kinds':['credential_probe','provider']},
                        gui_check=lambda:True,runner=child,kick=lambda:None)
    def ssh(argv,**kw):
        doc=json.loads(kw['input_bytes'])
        if doc['operation']=='submit':
            result=spool.submit(doc['kind'],doc['request'],doc['expires_epoch'],doc['nonce']);spool.worker()
        else:result=spool.result(doc['request_id'])
        return envelope(result)
    client=setup(tmp_path,ssh);provider=m.GuiProviderTransport('github',client)
    action=provider.for_action('incident:1')
    path='/repos/seeker-cyber-maker/fDisBull/actions/jobs/20/rerun'
    assert action('POST',path,{})['http_status']==201
    assert action('POST',path,{})['http_status']==201
    assert len(child_calls)==1 and child_calls[0][1]['action_key']=='incident:1'
