import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('production_gui_transport',Path(__file__).resolve().parents[1]/'scripts/ci/production_gui_transport.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
# Test fakes load the uninstalled source modules explicitly; activation does this only after hash checks.
m.provider=m._load('production_transport.py');m.source=m._load('production_source_transport.py')


def installed(tmp_path,*,allowed=('credential_probe','provider','source'),clock=lambda:1000,kick=None,runner=None,gui_check=None,probe=None):
    parent=tmp_path/'control';parent.mkdir(mode=0o700,exist_ok=True)
    spool=parent/'spool';spool.mkdir(mode=0o700,exist_ok=True);anchor=parent/'anchor.json'
    marker={'installation_id':m.INSTALLATION_ID,'volume_uuid':m.CACHE_UUID}
    history={'schema':'fdisbull-gui-history-1','sequence':0,'requests':{}}
    for path,data in ((spool/'installation.json',m._bytes(marker)),(spool/'history.json',m._bytes(history)),
                      (spool/'lane.lock',b''),(anchor,m._bytes({'installation_id':m.INSTALLATION_ID,'sequence':0,'history_sha256':m._digest(m._bytes(history))}))):
        path.write_bytes(data);path.chmod(0o600)
    kicks=[]
    def default_kick():kicks.append('once')
    obj=m.GuiSpool(spool,anchor,mount=lambda s,a:True,clock=clock,kick=kick or default_kick,runner=runner,
                   activation=lambda:{'allowed_kinds':list(allowed)},gui_check=gui_check or (lambda:True),probe=probe)
    return obj,kicks


def provider_doc():return {'operation':'request','provider':'gitlab','method':'GET','path':m.provider.GL+'/jobs/20','payload':None}


def canonical_read_doc():
    return {'operation':'canonical_read',
            'action_key':'induced-missing-policy-23fa9831-20261114-01',
            'request_sha256':'ac8a51ab8263044d78cf1c5726fdbb19851c2824197534b2c90fee244dea219d',
            'prestate_sha256':'cd4326afdb1ce6dd848c6bba5b7e429c1168d2d82d834abb2089d0762ea4cf28'}


def test_historical_read_requires_explicit_kind_and_exact_binding(tmp_path):
    spool,kicks=installed(tmp_path,allowed=('credential_probe',))
    with pytest.raises(RuntimeError,match='not approved'):
        spool.submit('canonical_read',canonical_read_doc(),1100,'a'*64)
    spool.activation=lambda:{'allowed_kinds':['credential_probe','canonical_read']}
    for field in ('operation','action_key','request_sha256','prestate_sha256'):
        changed=dict(canonical_read_doc());changed[field]='different'
        with pytest.raises(ValueError,match='binding differs'):
            spool.submit('canonical_read',changed,1100,'a'*64)
    assert not kicks


def test_historical_read_runs_only_fixed_collector_once(tmp_path):
    calls=[]
    def child(argv,data,timeout):
        calls.append((argv,json.loads(data)))
        return {'returncode':0,'stdout':b'{"status":"complete","canonical":{}}',
                'timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,allowed=('credential_probe','canonical_read'),runner=child)
    request=spool.submit('canonical_read',canonical_read_doc(),1100,'a'*64)
    assert spool.worker()['status']=='complete'
    assert spool.worker()['status']=='idle'
    assert calls==[([m.SOURCE_PYTHON,'-I',str(m.BRIDGE/'production_held_reconcile.py')],canonical_read_doc())]
    assert spool.result(request['request_id'])['result']['status']=='complete'
    assert kicks==['once']


def test_probe_only_default_and_no_credential_data_persisted(tmp_path):
    probe_calls=[]
    def probe(timeout):probe_calls.append(timeout);return {'available':True}
    spool,kicks=installed(tmp_path,allowed=('credential_probe',),probe=probe)
    with pytest.raises(RuntimeError,match='not approved'):spool.submit('provider',provider_doc(),1100,'a'*64)
    request=spool.submit('credential_probe',{},1100,'a'*64);assert kicks==['once']
    assert spool.worker()['status']=='complete'
    result=spool.result(request['request_id'])
    assert result['result']=={'available':True} and probe_calls==[15]
    assert b'synthetic-credential' not in b''.join(p.read_bytes() for p in spool.spool.iterdir() if p.is_file())


def test_boolean_probe_discards_credential_stdout():
    calls=[]
    def fake(argv,**kwargs):
        calls.append(argv);return {'returncode':0,'stdout':b'synthetic-credential','stderr':b'', 'timed_out':False,'overflow':False}
    assert m.credential_availability(runner=fake,activation_check=lambda:None)=={'available':True}
    assert calls==[[m.provider.GH_BIN,'auth','token','--user','seeker-cyber-maker','--hostname','github.com','--no-refresh']]


def test_fixed_provider_argv_and_immutable_request(tmp_path):
    calls=[]
    def child(argv,data,timeout):
        calls.append((argv,json.loads(data),timeout))
        return {'returncode':0,'stdout':b'{"http_status":200,"data":{"id":20},"request_id":null}', 'timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,runner=child);doc=provider_doc();request=spool.submit('provider',doc,1100,'a'*64)
    assert spool.worker()['status']=='complete'
    result=spool.result(request['request_id'])
    assert result['result']['data']=={'id':20}
    assert calls==[(['/usr/bin/python3','-I',str(m.BRIDGE/'production_transport.py')],doc,100)] and kicks==['once']
    assert spool.submit('provider',doc,1100,'a'*64)['phase']=='complete' and kicks==['once']


def test_unknown_started_never_relaunches(tmp_path):
    calls=[]
    def child(argv,data,timeout):calls.append(argv);return {'returncode':0,'stdout':b'partial', 'timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,runner=child);doc=provider_doc();first=spool.submit('provider',doc,1100,'a'*64)
    assert spool.worker()['status']=='unknown' and spool.result(first['request_id'])['status']=='unknown'
    assert spool.submit('provider',doc,1100,'a'*64)['phase']=='started'
    assert spool.worker()['status']=='idle' and len(calls)==1 and kicks==['once']
    with pytest.raises(RuntimeError,match='lane occupied'):spool.submit('credential_probe',{},1100,'b'*64)


def test_kickstart_loss_never_reissues(tmp_path):
    calls=[]
    def kick():calls.append(1);raise TimeoutError()
    spool,_=installed(tmp_path,kick=kick);doc=provider_doc();first=spool.submit('provider',doc,1100,'a'*64)
    assert first['status']=='unknown' and spool.submit('provider',doc,1100,'a'*64)['phase']=='submitted' and calls==[1]


def test_expiry_closes_without_child_launch(tmp_path):
    now=[1000];calls=[]
    spool,_=installed(tmp_path,clock=lambda:now[0],runner=lambda *args,**kw:calls.append(args))
    request=spool.submit('provider',provider_doc(),1001,'a'*64);now[0]=1001
    assert spool.worker()['status']=='expired' and spool.result(request['request_id'])['status']=='expired' and not calls


def test_wrong_volume_missing_or_changed_state_refuses(tmp_path):
    spool,kicks=installed(tmp_path);spool.mount=lambda *args:False
    with pytest.raises(RuntimeError,match='mount'):spool.submit('credential_probe',{},1100,'a'*64)
    assert not kicks
    spool.mount=lambda *args:True;(spool.spool/'installation.json').unlink()
    with pytest.raises(ValueError):spool.submit('credential_probe',{},1100,'a'*64)
    assert not kicks


def test_history_anchor_and_partial_result_are_fail_closed(tmp_path):
    spool,kicks=installed(tmp_path);req=spool.submit('provider',provider_doc(),1100,'a'*64)
    (spool.spool/(req['request_id']+'.done')).write_bytes(b'partial')
    with pytest.raises(RuntimeError,match='partial'):spool.result(req['request_id'])
    assert kicks==['once']


def test_explicit_overflow_and_retention_cap_do_not_launch(tmp_path,monkeypatch):
    spool,kicks=installed(tmp_path)
    with pytest.raises(ValueError):spool.submit('credential_probe',{},1601,'a'*64)
    monkeypatch.setattr(m,'MAX_RETAINED',1024)
    with pytest.raises(RuntimeError,match='budget'):spool.submit('credential_probe',{},1100,'a'*64)
    assert not kicks


def test_child_overflow_and_aqua_failure_preserve_unknown(tmp_path):
    calls=[]
    def child(*args,**kwargs):calls.append(1);return {'returncode':0,'stdout':b'x','timed_out':False,'overflow':True}
    spool,kicks=installed(tmp_path,runner=child,gui_check=lambda:False);request=spool.submit('provider',provider_doc(),1100,'a'*64)
    with pytest.raises(RuntimeError,match='Aqua'):spool.worker()
    assert not calls and spool.result(request['request_id'])['status']=='pending'
    spool.gui_check=lambda:True
    assert spool.worker()['status']=='unknown' and spool.result(request['request_id'])['status']=='unknown'


@pytest.mark.parametrize('doc',[
 {'operation':'request','provider':'gitlab','method':'POST','path':'/projects/88349936/settings','payload':{},'action_key':'x'},
 {'operation':'request','provider':'github','method':'GET','path':'https://example.com','payload':None},
 {'operation':'request','provider':'gitlab','method':'GET','path':'/projects/88349936/jobs/20;echo','payload':None},
])
def test_arbitrary_commands_and_paths_refused(tmp_path,doc):
    spool,kicks=installed(tmp_path)
    with pytest.raises(ValueError):spool.submit('provider',doc,1100,'a'*64)
    assert not kicks


def test_nonce_conflicts_refused_and_new_logical_read_allowed(tmp_path):
    def child(argv,data,timeout):return {'returncode':0,'stdout':b'{"http_status":200,"data":{},"request_id":null}','timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,runner=child);doc=provider_doc()
    first=spool.submit('provider',doc,1100,'a'*64);assert spool.worker()['status']=='complete'
    with pytest.raises(ValueError,match='nonce conflicts'):spool.submit('provider',doc,1101,'a'*64)
    second=spool.submit('provider',doc,1100,'b'*64)
    assert first['request_id']!=second['request_id'] and kicks==['once','once']


def test_missing_anchor_and_copied_empty_history_fail_without_kick(tmp_path):
    spool,kicks=installed(tmp_path);spool.submit('provider',provider_doc(),1100,'a'*64)
    spool.anchor.unlink()
    with pytest.raises(ValueError):spool.result('a'*64)
    assert kicks==['once']


def test_source_worker_command_is_fixed_not_supplied_by_request(tmp_path):
    target={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':'a'*40,
            'job_name':'test-and-package','runner_id':'58990209','ref':'main'}
    doc={'operation':'repair','key':'incident:repair','payload':{'target':target,'source_prepare':{'event_key':'c'*64}}}
    calls=[]
    def child(argv,data,timeout):
        calls.append((argv,json.loads(data)))
        return {'returncode':0,'stdout':b'{"result":{"status":"completed"}}','timed_out':False,'overflow':False}
    spool,_=installed(tmp_path,runner=child);req=spool.submit('source',doc,1100,'a'*64)
    assert spool.worker()['status']=='complete'
    assert calls==[([m.SOURCE_PYTHON,'-I',str(m.BRIDGE/'production_source_transport.py')],doc)]
    assert spool.result(req['request_id'])['status']=='complete'


def test_input_size_and_nonce_are_bounded(tmp_path,monkeypatch):
    spool,kicks=installed(tmp_path)
    with pytest.raises(ValueError,match='nonce'):spool.submit('credential_probe',{},1100,'not-a-nonce')
    monkeypatch.setattr(m,'MAX_INPUT',64)
    with pytest.raises(ValueError,match='exceeds'):spool.submit('credential_probe',{},1100,'a'*64)
    assert not kicks


def test_history_rollback_is_detected_against_separate_anchor(tmp_path):
    spool,kicks=installed(tmp_path);spool.submit('provider',provider_doc(),1100,'a'*64)
    genesis={'schema':'fdisbull-gui-history-1','sequence':0,'requests':{}}
    (spool.spool/'history.json').write_bytes(m._bytes(genesis))
    with pytest.raises(RuntimeError,match='anchor mismatch'):spool.result('a'*64)
    assert kicks==['once']


def test_helper_modules_are_not_imported_before_activation():
    fresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(fresh)
    assert fresh.provider is None and fresh.source is None


def test_bounded_child_uses_verified_runner_and_strips_credentials(monkeypatch):
    seen=[]
    def runner(argv,**kwargs):
        seen.append((argv,kwargs));return {'returncode':0,'stdout':b'{}','stderr':b'', 'timed_out':False,'overflow':False}
    monkeypatch.setattr(m.provider._source,'run_command',runner)
    monkeypatch.setenv('GITHUB_TOKEN','sensitive-example');monkeypatch.setenv('GH_CONFIG_DIR','/unsafe')
    argv=['/usr/bin/python3','-I',str(m.BRIDGE/'production_transport.py')]
    assert m._child(argv,b'{}',timeout=5)['returncode']==0
    assert seen[0][0]==argv and seen[0][1]['input_bytes']==b'{}' and seen[0][1]['timeout']==5
    assert 'GITHUB_TOKEN' not in seen[0][1]['env'] and 'GH_CONFIG_DIR' not in seen[0][1]['env']


def test_real_bounded_child_times_out_when_stdin_is_not_read():
    import sys
    import time
    started=time.monotonic()
    result=m._child([sys.executable,'-I','-c','import time; time.sleep(10)'],b'x'*(2*1024*1024),timeout=0.25)
    assert result['timed_out'] is True and time.monotonic()-started<4


def test_real_bounded_child_marks_aggregate_output_overflow():
    import sys
    code="import sys; sys.stdout.buffer.write(b'x'*1100000); sys.stderr.buffer.write(b'y'*1100000)"
    result=m._child([sys.executable,'-I','-c',code],b'',timeout=5)
    assert result['overflow'] is True and len(result['stdout'])+len(result['stderr'])>m.MAX_OUTPUT
