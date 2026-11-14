import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

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
        return {'returncode':0,'stdout':b'{"status":"complete","canonical":{}}','stderr':b'',
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
        return {'returncode':0,'stdout':b'{"http_status":200,"data":{"id":20},"request_id":null}', 'stderr':b'', 'timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,runner=child);doc=provider_doc();request=spool.submit('provider',doc,1100,'a'*64)
    assert spool.worker()['status']=='complete'
    result=spool.result(request['request_id'])
    assert result['result']['data']=={'id':20}
    assert calls==[(['/usr/bin/python3','-I',str(m.BRIDGE/'production_transport.py')],doc,100)] and kicks==['once']
    assert spool.submit('provider',doc,1100,'a'*64)['phase']=='complete' and kicks==['once']


def test_unknown_started_never_relaunches(tmp_path):
    calls=[]
    def child(argv,data,timeout):calls.append(argv);return {'returncode':0,'stdout':b'partial','stderr':b'', 'timed_out':False,'overflow':False}
    spool,kicks=installed(tmp_path,runner=child);doc=provider_doc();first=spool.submit('provider',doc,1100,'a'*64)
    assert spool.worker()['status']=='unknown' and spool.result(first['request_id'])['status']=='unknown'
    assert spool.submit('provider',doc,1100,'a'*64)['phase']=='terminalunknown'
    assert spool.worker()['status']=='idle' and len(calls)==1 and kicks==['once']
    assert spool.submit('provider',provider_doc(),1100,'b'*64)=={'status':'pending','request_id':'b'*64}


@pytest.mark.parametrize('outcome,reason',[
    ({'returncode':7,'stdout':b'secret stdout','stderr':b'secret stderr','timed_out':False,'overflow':False},'runner_nonzero'),
    ({'returncode':0,'stdout':b'{bad-json','stderr':b'', 'timed_out':False,'overflow':False},'runner_invalid_json'),
    ({'returncode':0,'stdout':b'{"error":"private details"}','stderr':b'', 'timed_out':False,'overflow':False},'runner_error'),
])
def test_cleanup_proven_runner_failure_closes_unknown_without_raw_output(tmp_path,outcome,reason):
    spool,_=installed(tmp_path,runner=lambda *a,**k:outcome)
    request=spool.submit('provider',provider_doc(),1100,'a'*64)
    result=spool.worker()
    assert result['status']=='unknown' and result['request_id']==request['request_id'] and result['reason']==reason
    assert result['runner']=={'returncode':outcome['returncode'],'timed_out':outcome['timed_out'],
                              'overflow':outcome['overflow']}
    assert spool.result(request['request_id'])==result
    assert spool.submit('provider',provider_doc(),1100,'a'*64)['phase']=='terminalunknown'
    retained=b''.join(p.read_bytes() for p in spool.spool.iterdir() if p.is_file())
    assert b'secret stdout' not in retained and b'secret stderr' not in retained and b'private details' not in retained


def test_timeout_overflow_and_signalled_runner_results_remain_held(tmp_path):
    outcomes=[{'returncode':-9,'stdout':b'', 'stderr':b'', 'timed_out':True,'overflow':False},
              {'returncode':-9,'stdout':b'', 'stderr':b'', 'timed_out':False,'overflow':True},
              {'returncode':-15,'stdout':b'', 'stderr':b'', 'timed_out':False,'overflow':False}]
    for index,outcome in enumerate(outcomes):
        root=tmp_path/str(index);root.mkdir()
        spool,_=installed(root,runner=lambda *a,**k:outcome)
        spool.submit('provider',provider_doc(),1100,'a'*64)
        assert spool.worker()['status']=='unknown'
        assert spool.submit('provider',provider_doc(),1100,'a'*64)['phase']=='started'
        with pytest.raises(RuntimeError,match='lane occupied'):
            spool.submit('provider',provider_doc(),1100,'b'*64)


def test_nested_session_outlives_outer_timeout_so_gui_lane_stays_held(tmp_path):
    inner_code="import time; time.sleep(0.7)"
    outer_code=("import subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c',"+repr(inner_code)+"], "
                "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); "
                "print(p.pid,flush=True); time.sleep(5)")
    inner_pid=[]
    def runner(*args,**kwargs):
        outcome=m.provider._source.run_command([sys.executable,'-c',outer_code],cwd='/',
                                               env={'PATH':os.environ.get('PATH','/usr/bin:/bin')},timeout=0.2)
        try:inner_pid.append(int(outcome['stdout'].strip()))
        except (ValueError,KeyError,AttributeError):pass
        return outcome
    spool,_=installed(tmp_path,runner=runner)
    request=spool.submit('provider',provider_doc(),1100,'a'*64)
    try:
        assert spool.worker()['status']=='unknown'
        assert len(inner_pid)==1
        os.kill(inner_pid[0],0)
        assert spool.result(request['request_id'])['status']=='unknown'
        with pytest.raises(RuntimeError,match='lane occupied'):
            spool.submit('provider',provider_doc(),1100,'b'*64)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            try:os.kill(inner_pid[0],0)
            except ProcessLookupError:break
            time.sleep(0.05)
        else:pytest.fail('bounded nested test process did not self-exit')
    finally:
        if inner_pid:
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                try:os.kill(inner_pid[0],0)
                except ProcessLookupError:break
                time.sleep(0.05)


def test_runner_exception_or_untrusted_return_keeps_started_lane(tmp_path):
    for runner in (lambda *a,**k:(_ for _ in ()).throw(TimeoutError()),
                   lambda *a,**k:{'returncode':0,'stdout':b'{}','timed_out':False,'overflow':False}):
        root=tmp_path/str(len(list(tmp_path.iterdir())));root.mkdir()
        spool,_=installed(root,runner=runner);spool.submit('provider',provider_doc(),1100,'a'*64)
        assert spool.worker()['status']=='unknown'
        assert spool.submit('provider',provider_doc(),1100,'a'*64)['phase']=='started'
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
    def child(*args,**kwargs):calls.append(1);return {'returncode':0,'stdout':b'x','stderr':b'', 'timed_out':False,'overflow':True}
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
    def child(argv,data,timeout):return {'returncode':0,'stdout':b'{"http_status":200,"data":{},"request_id":null}','stderr':b'','timed_out':False,'overflow':False}
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
        return {'returncode':0,'stdout':b'{"result":{"status":"completed"}}','stderr':b'','timed_out':False,'overflow':False}
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


def cleanup_receipt(tmp_path,spool,key,clock,*,changes=None):
    pins={'production_gui_transport.py':'a'*64,'recovery_source.py':'b'*64}
    spool.activation=lambda:{'allowed_kinds':['credential_probe','provider','source'],'modules':pins}
    scan=tmp_path/'scan.json';scan.write_bytes(b'filtered empty process scan');scan.chmod(0o600)
    launch=tmp_path/'launch.json';launch.write_bytes(b'filtered stopped launchagent');launch.chmod(0o600)
    entry=spool._check()['requests'][key]
    request=json.loads((spool.spool/(key+'.request')).read_bytes())
    value={'schema':'fdisbull-gui-read-cleanup-1','request_id':key,'request_sha256':entry['request_sha256'],
           'history_sequence':spool._check()['sequence'],'request_expiry':request['expires_epoch'],
           'observed_epoch':clock[0],'helper_sha256':pins['production_gui_transport.py'],
           'recovery_source_sha256':pins['recovery_source.py'],
           'launchagent':{'label':m.LABEL,'runs':30,'last_exit_code':0,'running':False,'pid':None},
           'process_scan':{'matched_children':0,'path':str(scan),'sha256':m._digest(scan.read_bytes())},
           'launchctl_evidence':{'path':str(launch),'sha256':m._digest(launch.read_bytes())}}
    if changes:changes(value)
    path=tmp_path/'operator-receipt.json';path.write_bytes(m._bytes(value));path.chmod(0o600)
    return path,m._digest(path.read_bytes())


def historical_post_fixture(tmp_path,spool,clock,monkeypatch):
    state=tmp_path/'bridge-state';state.mkdir(mode=0o700)
    anchor=tmp_path/'bridge-anchor.json'
    record={'action_key':m.LOST_POST_ACTION_KEY,'request_sha256':m.LOST_POST_ACTION_SHA256,'status':'unknown'}
    record_bytes=(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode()
    record_path=state/m.LOST_POST_RECORD_NAME;record_path.write_bytes(record_bytes);record_path.chmod(0o600)
    (state/'installation.json').write_bytes(m._bytes({'installation_id':m.provider.INSTALLATION_ID,
                                                       'volume_uuid':m.provider.VOLUME_UUID}))
    (state/'installation.json').chmod(0o600);(state/'actions.lock').write_bytes(b'');(state/'actions.lock').chmod(0o600)
    anchor_value={'installation_id':m.provider.INSTALLATION_ID,'volume_uuid':m.provider.VOLUME_UUID,
                  'sequence':1,'actions':{record_path.name:m._digest(record_bytes)}}
    anchor.write_bytes(m._bytes(anchor_value));anchor.chmod(0o600)
    monkeypatch.setattr(m.provider,'STATE_DIR',str(state));monkeypatch.setattr(m.provider,'ANCHOR_FILE',str(anchor))
    monkeypatch.setattr(m.provider,'_mounted_codex',lambda state,anchor:True)
    monkeypatch.setattr(m.provider,'request_digest',lambda provider,method,path,payload:m.LOST_POST_ACTION_SHA256)
    pins={'production_gui_transport.py':'a'*64,'recovery_source.py':'b'*64}
    spool.activation=lambda:{'allowed_kinds':['credential_probe','provider'],'modules':pins}
    post={'operation':'request','provider':'github','method':'POST',
          'path':m.provider.GH+'/jobs/20/rerun','payload':{},'action_key':m.LOST_POST_ACTION_KEY}
    clock[0]=1000
    spool.submit('provider',post,1100,m.LOST_POST_REQUEST_ID)
    spool.runner=lambda *a,**k:(_ for _ in ()).throw(TimeoutError())
    assert spool.worker()['status']=='unknown'
    clock[0]=1200
    now_value=clock[0]
    scan=tmp_path/'post-scan.json';scan.write_bytes(b'filtered process scan: zero matching children');scan.chmod(0o600)
    launch=tmp_path/'post-launch.json';launch.write_bytes(b'launchctl stopped; runs 30; last exit 0');launch.chmod(0o600)
    entry=spool._check()['requests'][m.LOST_POST_REQUEST_ID]
    value={'schema':'fdisbull-gui-post-cleanup-1','request_id':m.LOST_POST_REQUEST_ID,
           'request_sha256':entry['request_sha256'],'history_sequence':spool._check()['sequence'],
           'request_expiry':1100,'observed_epoch':now_value,
           'helper_sha256':pins['production_gui_transport.py'],'recovery_source_sha256':pins['recovery_source.py'],
           'launchagent':{'label':m.LABEL,'runs':30,'last_exit_code':0,'running':False,'pid':None},
           'process_scan':{'matched_children':0,'path':str(scan),'sha256':m._digest(scan.read_bytes())},
           'launchctl_evidence':{'path':str(launch),'sha256':m._digest(launch.read_bytes())},
           'bridge_action_key':m.LOST_POST_ACTION_KEY,'bridge_request_sha256':m.LOST_POST_ACTION_SHA256,
           'bridge_record_path':str(record_path),'bridge_record_sha256':m.LOST_POST_RECORD_SHA256,
           'bridge_anchor_sequence':1,'bridge_anchor_sha256':m._digest(anchor.read_bytes())}
    receipt=tmp_path/'post-cleanup-receipt.json';receipt.write_bytes(m._bytes(value));receipt.chmod(0o600)
    return receipt,m._digest(receipt.read_bytes()),record_bytes,anchor.read_bytes(),pins


def test_historical_post_reconciliation_is_local_unknown_and_preserves_bridge(tmp_path,monkeypatch):
    now=[1000];spool,_=installed(tmp_path,allowed=('credential_probe','provider'),clock=lambda:now[0])
    receipt,digest,record_before,anchor_before,_=historical_post_fixture(tmp_path,spool,now,monkeypatch)
    request_before=(spool.spool/(m.LOST_POST_REQUEST_ID+'.request')).read_bytes()
    started_before=(spool.spool/(m.LOST_POST_REQUEST_ID+'.started')).read_bytes()
    result=spool.reconcile_expired_historical_post(receipt,digest)
    assert result=={'status':'unknown','request_id':m.LOST_POST_REQUEST_ID,
                    'reason':'operator_reconciled_post_cleanup'}
    assert spool.result(m.LOST_POST_REQUEST_ID)==result
    assert (spool.spool/(m.LOST_POST_REQUEST_ID+'.request')).read_bytes()==request_before
    assert (spool.spool/(m.LOST_POST_REQUEST_ID+'.started')).read_bytes()==started_before
    assert (spool.spool/(m.LOST_POST_REQUEST_ID+'.done')).is_file()
    assert (Path(m.provider.STATE_DIR)/m.LOST_POST_RECORD_NAME).read_bytes()==record_before
    assert Path(m.provider.ANCHOR_FILE).read_bytes()==anchor_before
    assert spool.submit('provider',provider_doc(),1300,'b'*64)=={'status':'pending','request_id':'b'*64}


def test_historical_post_reconciliation_rejects_wrong_bridge_record_and_receipt(tmp_path,monkeypatch):
    now=[1000];spool,_=installed(tmp_path,allowed=('credential_probe','provider'),clock=lambda:now[0])
    receipt,digest,_,_,_=historical_post_fixture(tmp_path,spool,now,monkeypatch)
    record=Path(m.provider.STATE_DIR)/m.LOST_POST_RECORD_NAME
    record.write_bytes(m._bytes({'action_key':m.LOST_POST_ACTION_KEY,
                                 'request_sha256':m.LOST_POST_ACTION_SHA256,'status':'accepted'}))
    with pytest.raises(RuntimeError):spool.reconcile_expired_historical_post(receipt,digest)
    assert spool.result(m.LOST_POST_REQUEST_ID)['status']=='unknown'
    assert not (spool.spool/(m.LOST_POST_REQUEST_ID+'.done')).exists()


def test_operator_reconciles_only_expired_get_and_preserves_unknown(tmp_path):
    now=[1000];calls=[]
    def child(*args,**kwargs):calls.append(1);raise TimeoutError()
    spool,kicks=installed(tmp_path,clock=lambda:now[0],runner=child)
    first=spool.submit('provider',provider_doc(),1100,'a'*64);assert spool.worker()['status']=='unknown'
    old_request=(spool.spool/('a'*64+'.request')).read_bytes();old_started=(spool.spool/('a'*64+'.started')).read_bytes()
    now[0]=1200;path,digest=cleanup_receipt(tmp_path,spool,'a'*64,now)
    assert spool.reconcile_expired_read(path,digest)=={'status':'unknown','request_id':'a'*64,'reconciled':True}
    assert spool.result('a'*64)=={'status':'unknown','request_id':'a'*64}
    assert (spool.spool/('a'*64+'.request')).read_bytes()==old_request
    assert (spool.spool/('a'*64+'.started')).read_bytes()==old_started
    assert not (spool.spool/('a'*64+'.done')).exists()
    assert spool.submit('provider',provider_doc(),1300,'b'*64)['status']=='pending'
    with pytest.raises(ValueError,match='invalid expiry'):
        spool.submit('provider',provider_doc(),1100,'a'*64)
    assert calls==[1] and kicks==['once','once']


@pytest.mark.parametrize('change',[
    lambda v:v.update(history_sequence=v['history_sequence']+1),
    lambda v:v.update(request_sha256='f'*64),
    lambda v:v.update(request_expiry=1300),
    lambda v:v['launchagent'].update(running=True,pid=1),
    lambda v:v['process_scan'].update(matched_children=1),
    lambda v:v.update(helper_sha256='f'*64),
    lambda v:v['launchctl_evidence'].update(sha256='0'*64),
])
def test_operator_cleanup_refuses_invalid_evidence(tmp_path,change):
    now=[1000];spool,_=installed(tmp_path,clock=lambda:now[0],runner=lambda *a,**k:{'returncode':0,'stdout':b'bad','timed_out':False,'overflow':False})
    spool.submit('provider',provider_doc(),1100,'a'*64);spool.worker();now[0]=1200
    path,digest=cleanup_receipt(tmp_path,spool,'a'*64,now,changes=change)
    with pytest.raises(ValueError):spool.reconcile_expired_read(path,digest)
    assert spool.result('a'*64)['status']=='unknown'
    with pytest.raises(RuntimeError,match='lane occupied'):spool.submit('credential_probe',{},1300,'b'*64)


def test_operator_cleanup_refuses_mutation_probe_unexpired_and_unstarted(tmp_path):
    def child(*a,**k):raise TimeoutError()
    for name in ('post','probe','pending','unexpired'):(tmp_path/name).mkdir()
    now=[1000];spool,_=installed(tmp_path/'post',clock=lambda:now[0],runner=child)
    doc={'operation':'request','provider':'gitlab','method':'POST','path':m.provider.GL+'/jobs/20/retry','payload':{},'action_key':'post'}
    spool.submit('provider',doc,1100,'a'*64);spool.worker();now[0]=1200
    path,digest=cleanup_receipt(tmp_path/'post',spool,'a'*64,now)
    with pytest.raises(ValueError,match='provider GET'):spool.reconcile_expired_read(path,digest)
    now=[1000];spool,_=installed(tmp_path/'probe',clock=lambda:now[0],probe=lambda **kwargs:None)
    spool.submit('credential_probe',{},1100,'b'*64);spool.worker();now[0]=1200
    path,digest=cleanup_receipt(tmp_path/'probe',spool,'b'*64,now)
    with pytest.raises(ValueError,match='provider GET'):spool.reconcile_expired_read(path,digest)
    now=[1000];spool,_=installed(tmp_path/'pending',clock=lambda:now[0])
    spool.submit('provider',provider_doc(),1100,'c'*64);now[0]=1200
    path,digest=cleanup_receipt(tmp_path/'pending',spool,'c'*64,now)
    with pytest.raises(ValueError,match='history changed'):spool.reconcile_expired_read(path,digest)
    now=[1000];spool,_=installed(tmp_path/'unexpired',clock=lambda:now[0],runner=child)
    spool.submit('provider',provider_doc(),1100,'d'*64);spool.worker()
    path,digest=cleanup_receipt(tmp_path/'unexpired',spool,'d'*64,now)
    with pytest.raises(ValueError,match='time or identity'):spool.reconcile_expired_read(path,digest)


def test_operator_cleanup_refuses_source_worker(tmp_path):
    now=[1000]
    target={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':'a'*40,
            'job_name':'test-and-package','runner_id':'58990209','ref':'main'}
    doc={'operation':'repair','key':'incident:repair','payload':{'target':target,'source_prepare':{'event_key':'c'*64}}}
    spool,_=installed(tmp_path,clock=lambda:now[0],runner=lambda *a,**k:{'returncode':0,'stdout':b'bad','timed_out':False,'overflow':False})
    spool.submit('source',doc,1100,'a'*64);spool.worker();now[0]=1200
    path,digest=cleanup_receipt(tmp_path,spool,'a'*64,now)
    with pytest.raises(ValueError,match='provider GET'):spool.reconcile_expired_read(path,digest)
    assert spool.result('a'*64)['status']=='unknown'


def test_reconciled_read_certificate_tampering_fails_closed(tmp_path):
    now=[1000];spool,_=installed(tmp_path,clock=lambda:now[0],runner=lambda *a,**k:{'returncode':0,'stdout':b'bad','timed_out':False,'overflow':False})
    spool.submit('provider',provider_doc(),1100,'a'*64);spool.worker();now[0]=1200
    path,digest=cleanup_receipt(tmp_path,spool,'a'*64,now);spool.reconcile_expired_read(path,digest)
    cert=spool.spool/('a'*64+'.read-reconciliation.json');cert.write_bytes(b'{}')
    with pytest.raises(RuntimeError,match='read reconciliation changed'):spool.result('a'*64)
