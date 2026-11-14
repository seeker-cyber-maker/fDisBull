import importlib.util
import base64
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec=importlib.util.spec_from_file_location('production_transport',Path(__file__).resolve().parents[1]/'scripts/ci/production_transport.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


def ok(stdout,rc=0):return {'returncode':rc,'stdout':stdout,'stderr':b'private stderr','timed_out':False,'overflow':False}


def response(code,body=b''):
    return b'HTTP/2 '+str(code).encode()+b'\r\nX-Request-Id: req-1\r\nAuthorization: private\r\n\r\n'+body


class Runner:
    def __init__(self):self.calls=[];self.output=response(201,b'{"id":21,"sensitive":"hidden"}')
    def __call__(self,argv,**kwargs):
        self.calls.append((argv,kwargs))
        if argv[:3]==[t.GH_BIN,'auth','token']:return ok(b'synthetic-token\n')
        if argv[0]==t.GLAB_BIN and argv[-1]=='user':return ok(response(200,b'{"id":123,"username":"fixture"}'))
        return ok(self.output)


def bridge(tmp_path,runner):
    state=tmp_path/'state';state.mkdir(mode=0o700,exist_ok=True)
    marker=state/'installation.json'
    if not marker.exists():
        marker.write_text(json.dumps({'installation_id':t.INSTALLATION_ID,'volume_uuid':t.VOLUME_UUID}));marker.chmod(0o600)
    (state/'actions.lock').touch(mode=0o600,exist_ok=True)
    parent=tmp_path/'control';parent.mkdir(mode=0o700,exist_ok=True);anchor=parent/'bridge-anchor.json'
    if not anchor.exists():
        anchor.write_text(json.dumps({'installation_id':t.INSTALLATION_ID,'volume_uuid':t.VOLUME_UUID,'sequence':0,'actions':{}}));anchor.chmod(0o600)
    status_dir=tmp_path/'shared-status';status_dir.mkdir(exist_ok=True)
    for provider,(host,repo) in t.SCOPES.items():
        scope=t._status._directory(status_dir,host.lower(),repo.lower());scope.mkdir(exist_ok=True)
        path=scope/'state.json'
        if not path.exists():
            t._status._write(path,{'schema':1,'host':host.lower(),'repo':repo.lower(),'owner':None,'next_allowed_at':0,'provider_stop':None})
    b=t.ProviderBridge(state,runner,anchor_file=anchor,mount_validator=lambda s,a:True,gitlab_principal=(123,'fixture'),
                       status_dir=status_dir,clock=lambda:1000)
    for provider in t.SCOPES:b.reserve(provider)
    return b


def test_gitlab_retry_is_durable_idempotent_and_redacted(tmp_path):
    r=Runner();b=bridge(tmp_path,r);path=t.GL+'/jobs/20/retry'
    first=b.request('gitlab','POST',path,{},'one')
    assert first=={'http_status':201,'data':{'id':21},'request_id':'req-1'}
    assert b.request('gitlab','POST',path,{},'one')==first and len(r.calls)==2
    stored=b._file('one').read_text()
    assert 'sensitive' not in stored and 'private' not in stored
    assert b.receipt('one')['status']=='accepted'
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/22/retry',{},'one')


def test_unknown_action_never_replays_even_after_restart(tmp_path):
    r=Runner();r.output=b'invalid response';path=t.GL+'/jobs/20/retry'
    with pytest.raises(RuntimeError):bridge(tmp_path,r).request('gitlab','POST',path,{},'key')
    assert bridge(tmp_path,r).receipt('key')['status']=='unknown'
    with pytest.raises(RuntimeError):bridge(tmp_path,r).request('gitlab','POST',path,{},'key')
    assert len(r.calls)==2


def test_github_token_in_environment_only_and_no_headers_saved(tmp_path,monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN','wrong');r=Runner();r.output=response(201)
    b=bridge(tmp_path,r)
    out=b.request('github','POST',t.GH+'/jobs/22/rerun',{},'gh')
    assert out['http_status']==201 and len(r.calls)==2
    argv,kw=r.calls[1]
    assert 'synthetic-token' not in str(argv) and kw['env']['GH_TOKEN']=='synthetic-token'
    assert 'GITHUB_TOKEN' not in kw['env']
    assert 'synthetic-token' not in b._file('gh').read_text()


def test_original_ansi_job_log_is_captured_privately_without_terminal_output(tmp_path, capsys):
    raw = b'\x1b[32moriginal CI log\x1b[0m\n'
    runner = Runner(); runner.output = response(200, raw)
    boundary = bridge(tmp_path, runner)
    value = boundary.request('github', 'GET', t.GH + '/jobs/22/logs')
    assert base64.b64decode(value['data']['data']) == raw
    assert '--allow-escape-sequences' in runner.calls[-1][0]
    assert capsys.readouterr().out == ''
    runner.output = response(200, b'{"id":22}')
    boundary.request('github', 'GET', t.GH + '/jobs/22')
    assert '--allow-escape-sequences' not in runner.calls[-1][0]


@pytest.mark.parametrize('provider,method,path,payload',[
 ('github','GET','/repos/other/repo/actions/runs/1',None),
 ('github','POST',t.GH+'/jobs/1/cancel',{}),
 ('gitlab','GET',t.GL+'/variables',None),
 ('gitlab','POST',t.GL+'/pipeline',{'ref':'main','variables':[]}),
 ('gitlab','GET',t.GL+'/jobs/1?per_page=1',None),
 ('github','GET',t.GH+'/runs/1/jobs?page=11',None),
 ('github','GET',t.GH+'/jobs/1%2Flogs',None),
])
def test_allowlist_rejects_unapproved_requests(tmp_path,provider,method,path,payload):
    r=Runner();b=bridge(tmp_path,r)
    with pytest.raises(ValueError):b.request(provider,method,path,payload,'key' if method=='POST' else None)
    assert not r.calls


def test_raw_trace_is_bounded_hash_and_base64(tmp_path):
    r=Runner();r.output=response(200,b'private-trace')
    result=bridge(tmp_path,r).request('gitlab','GET',t.GL+'/jobs/20/trace')
    assert result['data']['size']==13 and result['data']['encoding']=='base64'


def test_restriction_returns_code_and_prevents_replay(tmp_path):
    r=Runner();r.output=response(403,b'{"message":"secret"}')
    b=bridge(tmp_path,r)
    assert b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')=={'http_status':403,'data':None,'request_id':'req-1'}
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    assert len(r.calls)==2


def test_ssh_client_uses_fixed_argv_and_json_stdin_only():
    calls=[]
    def runner(argv,**kwargs):
        calls.append((argv,kwargs));return ok(b'{"http_status":204,"data":null,"request_id":null}')
    c=t.SSHProviderTransport('github','/Volumes/CODEX/private/bridge.py',runner=runner)
    path=t.GH+'/workflows/417757453/dispatches'
    body={'ref':'codex/control','inputs':{'nonce':'one','candidate_sha':'a'*40}}
    assert c.for_action('incident:1')('POST',path,body)['http_status']==204
    argv,kwargs=calls[0]
    assert argv==['/usr/bin/tailscale','ssh','tiga@100.76.103.43','/usr/bin/python3','/Volumes/CODEX/private/bridge.py']
    assert json.loads(kwargs['input_bytes'])['payload']==body and 'incident:1' not in argv
    with pytest.raises(ValueError):c.request('POST',path,body)


def test_raw_output_budget_is_explicit(tmp_path):
    r=Runner();r.output=response(200,b'x'*(1024*1024+1))
    with pytest.raises(t.BudgetExceeded):
        bridge(tmp_path,r).request('gitlab','GET',t.GL+'/jobs/20/trace')


def test_metadata_response_strips_credential_fields(tmp_path):
    r=Runner();r.output=response(200,b'{"id":20,"token":"hidden","runner":{"secret":"hidden","id":9}}')
    out=bridge(tmp_path,r).request('gitlab','GET',t.GL+'/jobs/20')
    assert out['data']=={'id':20,'runner':{'id':9}}


def test_missing_external_mount_never_touches_state_or_provider(tmp_path):
    runner=Runner();state=tmp_path/'absent';anchor=tmp_path/'also-absent'
    b=t.ProviderBridge(state,runner,anchor_file=anchor,mount_validator=lambda s,a:False,gitlab_principal=(123,'fixture'))
    for operation in (lambda:b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key'),
                      lambda:b.request('gitlab','GET',t.GL+'/jobs/20'),lambda:b.receipt('key')):
        with pytest.raises(RuntimeError):operation()
    assert not state.exists() and not anchor.exists() and not runner.calls


def test_missing_state_or_marker_refuses_without_initializing(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner)
    (tmp_path/'state'/'installation.json').unlink()
    with pytest.raises(RuntimeError):b.request('github','POST',t.GH+'/jobs/20/rerun',{},'key')
    assert not (tmp_path/'state'/'installation.json').exists() and not runner.calls
    state=tmp_path/'missing-state'
    b=t.ProviderBridge(state,runner,anchor_file=tmp_path/'control/bridge-anchor.json',mount_validator=lambda s,a:True)
    with pytest.raises(RuntimeError):b.receipt('key')
    assert not state.exists() and not runner.calls


def test_missing_or_wrong_anchor_and_marker_refuses(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner);anchor=tmp_path/'control/bridge-anchor.json'
    anchor.unlink()
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    assert not anchor.exists() and not runner.calls
    other=tmp_path/'other';other.mkdir()
    b=bridge(other,runner);marker=other/'state/installation.json'
    marker.write_text(json.dumps({'installation_id':'wrong','volume_uuid':t.VOLUME_UUID}))
    with pytest.raises(RuntimeError):b.receipt('key')
    assert not runner.calls


def test_rollback_to_empty_copied_state_is_detected(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner)
    b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'one')
    before=len(runner.calls)
    b._file('one').unlink()
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'new-key')
    with pytest.raises(RuntimeError):b.receipt('one')
    assert len(runner.calls)==before


def test_interrupted_anchor_update_fails_closed_and_preserves_anchor(tmp_path,monkeypatch):
    runner=Runner();b=bridge(tmp_path,runner);original=t._atomic_existing
    def interrupted(path,value):
        if path.parent==tmp_path/'state':raise OSError('interrupted')
        return original(path,value)
    previous=json.loads((tmp_path/'control/bridge-anchor.json').read_text())['sequence']
    monkeypatch.setattr(t,'_atomic_existing',interrupted)
    with pytest.raises(OSError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    anchor=json.loads((tmp_path/'control/bridge-anchor.json').read_text())
    assert anchor['sequence']==previous+1 and anchor['actions'] and not runner.calls
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    assert not runner.calls


def test_wrong_gitlab_principal_never_posts_or_falls_back(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner);b.principal=(456,'other')
    with pytest.raises(RuntimeError,match='account mismatch'):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    assert len(runner.calls)==1 and runner.calls[0][0][-1]=='user'
    assert b.receipt('key')['status']=='unknown'
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    assert len(runner.calls)==1


def test_shared_reservation_cooldown_and_expiry_block_provider_calls(tmp_path):
    runner=Runner();runner.output=response(200,b'{}');b=bridge(tmp_path,runner)
    result=b.reserve('github')
    assert result=={'allowed':False,'reason':'cooldown','next_refresh_at':1300}
    assert b.request('github','GET',t.GH+'/jobs/20')['http_status']==200
    before=len(runner.calls);b.clock=lambda:1300
    with pytest.raises(RuntimeError,match='expired'):b.request('github','GET',t.GH+'/jobs/20')
    assert len(runner.calls)==before
    assert b.reserve('github')['allowed'] is True
    assert b.request('github','GET',t.GH+'/jobs/20')['http_status']==200


def test_owner_conflict_and_provider_stop_prevent_requests(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner)
    host,repo,directory,scope=b._scope_state('github');path=scope/'state.json'
    state=json.loads(path.read_text());state['owner']='different-owner';t._status._write(path,state)
    with pytest.raises(RuntimeError,match='batch'):b.request('github','GET',t.GH+'/jobs/20')
    assert not runner.calls
    state['owner']=t.OWNER;state['provider_stop']={'reason':'provider_http_429','observed_at':1000};t._status._write(path,state)
    with pytest.raises(RuntimeError,match='batch'):b.request('github','GET',t.GH+'/jobs/20')
    assert not runner.calls


def test_http_stop_is_durable_in_shared_state(tmp_path):
    runner=Runner();runner.output=response(429,b'ignored');b=bridge(tmp_path,runner)
    assert b.request('github','GET',t.GH+'/jobs/20')['http_status']==429
    _,_,_,scope=b._scope_state('github')
    assert json.loads((scope/'state.json').read_text())['provider_stop']['reason']=='provider_http_429'
    before=len(runner.calls)
    with pytest.raises(RuntimeError):b.request('github','GET',t.GH+'/jobs/20')
    assert len(runner.calls)==before


def test_batch_budget_persisted_before_each_http_request(tmp_path):
    runner=Runner();runner.output=response(200,b'{}');b=bridge(tmp_path,runner)
    for _ in range(100): b.request('gitlab','GET',t.GL+'/jobs/20')
    before=len(runner.calls)
    with pytest.raises(RuntimeError,match='batch'):b.request('gitlab','GET',t.GL+'/jobs/20')
    assert len(runner.calls)==before
    assert json.loads(b._file(t.BATCH_PREFIX+'gitlab').read_text())['remaining']==0


def test_unreserved_bridge_cannot_contact_provider(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner)
    # A consumed or expired reservation cannot be revived by a failed cooldown reservation.
    b.clock=lambda:1300
    _,_,_,scope=b._scope_state('gitlab')
    state=json.loads((scope/'state.json').read_text());state['next_allowed_at']=1400;t._status._write(scope/'state.json',state)
    assert b.reserve('gitlab')['allowed'] is False
    with pytest.raises(RuntimeError):b.request('gitlab','GET',t.GL+'/jobs/20')
    assert not runner.calls


def test_ssh_reserve_uses_fixed_structured_request():
    calls=[]
    def runner(argv,**kwargs):calls.append(json.loads(kwargs['input_bytes']));return ok(b'{"allowed":true,"reason":"reserved","next_refresh_at":1300}')
    client=t.SSHProviderTransport('gitlab','/Volumes/CODEX/private/bridge.py',runner=runner)
    assert client.reserve()['allowed'] is True
    assert calls==[{'operation':'reserve','provider':'gitlab'}]


class PublicResponse:
    def __init__(self, body=b'{"id":1}', status=200, url=None, headers=None):
        self.body, self.status = body, status
        self.url = url or 'https://api.github.com/repos/seeker-cyber-maker/fDisBull/actions/runs/1'
        self.headers = headers or {'X-GitHub-Request-Id': 'public-1'}
        self.read_limit = None
        self.closed = False
    def geturl(self): return self.url
    def getcode(self): return self.status
    def read(self, maximum):
        self.read_limit = maximum
        return self.body[:maximum]
    def close(self): self.closed = True


class PublicOpener:
    def __init__(self, response): self.response, self.calls = response, []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.response, BaseException): raise self.response
        return self.response


class AuthenticatedStub:
    provider = 'github'
    request_budget = 2
    request_window_seconds = 180
    action_window_seconds = 75
    def __init__(self): self.calls = []
    def request(self, *args): self.calls.append(('request', args)); return {'authenticated': True}
    def for_action(self, key):
        def perform(*args): self.calls.append(('action', key, args)); return {'action': True}
        return perform
    def receipt(self, key): self.calls.append(('receipt', key)); return {'receipt': True}


class AdmissionStub:
    def __init__(self): self.calls = 0
    def reserve(self): self.calls += 1; return {'allowed': True}


def public_transport(response):
    authenticated, admission = AuthenticatedStub(), AdmissionStub()
    opener = PublicOpener(response)
    client = t.PublicGitHubMetadataTransport(authenticated, admission, opener=opener)
    return client, authenticated, admission, opener


def test_public_metadata_uses_fixed_anonymous_https_and_redacts_response():
    path = t.GH + '/runs/43604381587/attempts/2'
    response = PublicResponse(b'{"id":1,"token":"private","runner":{"secret":"x","id":2}}',
                             url='https://api.github.com' + path)
    client, auth, _, opener = public_transport(response)
    assert client.request('GET', path) == {
        'http_status': 200, 'data': {'id': 1, 'runner': {'id': 2}}, 'request_id': 'public-1'}
    request, timeout = opener.calls[0]
    assert request.full_url == 'https://api.github.com' + path
    assert request.get_header('Authorization') is None
    assert timeout == 30 and response.read_limit == t._source.LIMIT + 1 and response.closed
    assert not auth.calls
    assert (client.request_budget, client.request_window_seconds, client.action_window_seconds) == (2, 180, 75)


def test_public_metadata_keeps_raw_logs_artifacts_and_mutations_authenticated():
    client, auth, admission, opener = public_transport(PublicResponse())
    log = t.GH + '/jobs/132498683205/logs'
    artifacts = t.GH + '/runs/43604381587/artifacts'
    artifact = t.GH + '/artifacts/1234'
    assert client.request('GET', log) == {'authenticated': True}
    assert client.request('GET', artifacts) == {'authenticated': True}
    assert client.request('GET', artifact) == {'authenticated': True}
    body = {'ref': 'codex/control', 'inputs': {'nonce': 'n', 'candidate_sha': 'a' * 40}}
    assert client.for_action('action-1')('POST', t.GH + '/workflows/417757453/dispatches', body) == {'action': True}
    assert client.receipt('action-1') == {'receipt': True}
    assert client.reserve() == {'allowed': True}
    assert [call[0] for call in auth.calls] == ['request', 'request', 'request', 'action', 'receipt']
    assert admission.calls == 1 and opener.calls == []


@pytest.mark.parametrize('response', [
    PublicResponse(b'not-json'),
    PublicResponse(b'x' * (t._source.LIMIT + 1)),
    PublicResponse(b'{"id":1}', status=403),
    PublicResponse(b'{"id":1}', status=429),
    PublicResponse(b'{"id":1}', url='https://example.invalid/repos/seeker-cyber-maker/fDisBull/actions/runs/1'),
])
def test_public_metadata_failures_are_terminal_without_authenticated_fallback(response):
    client, auth, _, _ = public_transport(response)
    with pytest.raises(t.PublicGitHubMetadataError):
        client.request('GET', t.GH + '/runs/1')
    assert not auth.calls


def test_public_metadata_http_error_is_terminal_without_fallback():
    error = HTTPError('https://api.github.com/repos/seeker-cyber-maker/fDisBull/actions/runs/1',
                      403, 'Forbidden', {}, None)
    client, auth, _, _ = public_transport(error)
    with pytest.raises(t.PublicGitHubMetadataError) as caught:
        client.request('GET', t.GH + '/runs/1')
    assert caught.value.reason == 'http_error' and caught.value.status == 403
    assert not auth.calls


def test_public_metadata_allowlist_rejects_unapproved_path_before_network():
    client, auth, _, opener = public_transport(PublicResponse())
    with pytest.raises(ValueError):
        client.request('GET', t.GH + '/runs/1/attempts/1/jobs/1')
    assert not opener.calls and not auth.calls


def test_github_auth_failure_durably_stops_shared_provider(tmp_path):
    class MissingAuth(Runner):
        def __call__(self,argv,**kwargs):
            self.calls.append((argv,kwargs))
            return ok(b'',rc=1)
    runner=MissingAuth();b=bridge(tmp_path,runner)
    with pytest.raises(t.ProviderStop):b.request('github','GET',t.GH+'/jobs/20')
    _,_,_,scope=b._scope_state('github')
    assert json.loads((scope/'state.json').read_text())['provider_stop']['reason']=='provider_authentication_required'
    with pytest.raises(RuntimeError):b.request('github','GET',t.GH+'/jobs/20')
    assert len(runner.calls)==1


def test_wrong_gitlab_account_is_durable_shared_stop(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner);b.principal=(999,'wrong')
    with pytest.raises(RuntimeError):b.request('gitlab','POST',t.GL+'/jobs/20/retry',{},'key')
    _,_,_,scope=b._scope_state('gitlab')
    assert json.loads((scope/'state.json').read_text())['provider_stop']['reason']=='provider_account_mismatch'
    assert len(runner.calls)==1


def held_fixture(tmp_path, monkeypatch):
    import hashlib
    runner=Runner(); b=bridge(tmp_path,runner)
    key='fixture-held'; path=t.GH+'/workflows/417757453/dispatches'
    payload={'ref':'codex/test','inputs':{'nonce':'a'*64,'candidate_sha':'b'*40}}
    digest=t.request_digest('github','POST',path,payload)
    monkeypatch.setattr(t,'HELD_ACTION_KEY',key);monkeypatch.setattr(t,'HELD_REQUEST_SHA256',digest)
    old={'action_key':key,'request_sha256':digest,'status':'unknown'}
    with b._bridge_lock():b._save_mirrored(b._file(key),old)
    original=b._file(key).read_bytes()
    old_sha=hashlib.sha256(original).hexdigest();monkeypatch.setattr(t,'HELD_RECORD_SHA256',old_sha)
    verified={'schema':'fdisbull-held-no-send-certificate-1','verified':True,'action_key':key,'request_sha256':digest}
    monkeypatch.setattr(t,'_verify_held_current_state',lambda bridge,canonical,host,repo,scope:None)
    monkeypatch.setattr(t,'_verify_held',lambda facts,canonical:verified)
    b.install_held_certificate({}, {})
    return b,runner,key,path,payload,original


def test_certified_held_dispatch_preserves_original_and_deduplicates(tmp_path,monkeypatch):
    b,runner,key,path,payload,original=held_fixture(tmp_path,monkeypatch)
    runner.output=response(204)
    assert b.receipt(key)['status']=='certified_not_sent'
    first=b.request('github','POST',path,payload,key)
    assert first['http_status']==204
    assert b._file(key).read_bytes()==original
    assert b.receipt(key)['status']=='accepted'
    assert b.request('github','POST',path,payload,key)==first
    assert len(runner.calls)==2


def test_certified_held_lost_response_is_never_resent(tmp_path,monkeypatch):
    b,runner,key,path,payload,original=held_fixture(tmp_path,monkeypatch)
    runner.output=b'invalid response'
    with pytest.raises(RuntimeError):b.request('github','POST',path,payload,key)
    assert b.receipt(key)['status']=='unknown'
    assert b._file(key).read_bytes()==original
    with pytest.raises(RuntimeError):b.request('github','POST',path,payload,key)
    assert len(runner.calls)==2


def test_stopped_provider_does_not_consume_certified_permit(tmp_path,monkeypatch):
    b,runner,key,path,payload,_=held_fixture(tmp_path,monkeypatch)
    host,repo,directory,scope=b._scope_state('github')
    state=t._status._load_state(scope/'state.json',host.lower(),repo.lower())
    state['provider_stop']={'reason':'provider_authentication_required','observed_at':1000}
    t._status._write(scope/'state.json',state)
    with pytest.raises(RuntimeError):b.request('github','POST',path,payload,key)
    assert b.receipt(key)['status']=='certified_not_sent'
    assert not runner.calls


def test_held_certificate_install_rejects_unverified_and_duplicate(tmp_path,monkeypatch):
    b,runner,key,path,payload,original=held_fixture(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError):b.install_held_certificate({}, {})
    assert b._file(key).read_bytes()==original and not runner.calls
    # The fixed source pin must be present; no implicit verifier trust.
    monkeypatch.setattr(t,'HELD_VERIFIER_SHA256',None)
    monkeypatch.undo()
    with pytest.raises(RuntimeError):t._verify_held({}, {})


def test_held_certificate_tampering_fails_closed(tmp_path,monkeypatch):
    b,runner,key,path,payload,_=held_fixture(tmp_path,monkeypatch)
    cert=b._held_read(key,'certificate');cert['verifier_certificate']['request_sha256']='f'*64
    # Simulate an authorized state writer updating the mirror, to exercise the
    # independent certificate hash check rather than only the outer anchor.
    with b._bridge_lock():b._save_mirrored(b._held_path(key,'certificate'),cert)
    with pytest.raises(ValueError):b.receipt(key)
    with pytest.raises(ValueError):b.request('github','POST',path,payload,key)
    assert not runner.calls



def test_held_install_rejects_stale_post_snapshot_under_both_locks(tmp_path,monkeypatch):
    b=bridge(tmp_path,Runner())
    with b._bridge_lock():
        b._save_mirrored(b._file(t.HELD_ACTION_KEY),{'status':'unknown'})
        host,repo,_,scope=b._scope_state('github')
        with b.status_api._locked(scope) as acquired:
            assert acquired
            with pytest.raises(RuntimeError,match='post-state mismatch'):
                t._verify_held_current_state(b,{'mirror_post':{}},host,repo,scope)


def test_rpc_action_cannot_occupy_held_internal_namespace(tmp_path):
    runner=Runner();b=bridge(tmp_path,runner)
    with pytest.raises(ValueError,match='reserved action key'):
        b.request('github','POST',t.GH+'/jobs/22/rerun',{},'__held_certificate__:attack')
    assert not runner.calls


def test_pinned_held_verifier_rejects_invalid_facts_without_private_io():
    with pytest.raises(RuntimeError,match='local_facts_schema_invalid'):
        t._verify_held({}, {})


def test_source_verifier_result_installs_in_mirrored_journal(tmp_path,monkeypatch):
    # Real collector/verifier logic; prestate decoding and current filesystem
    # snapshot are fixture stand-ins, so no historical private receipt is read.
    import hashlib
    p=Path(__file__).with_name('test_production_held_reconcile.py')
    spec=importlib.util.spec_from_file_location('held_fixture',p)
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    canonical,source_sha=fixture.make_collected(monkeypatch)
    assert source_sha==t.HELD_VERIFIER_SHA256
    facts=fixture.make_facts(monkeypatch)
    b=bridge(tmp_path,Runner());key=t.HELD_ACTION_KEY
    with b._bridge_lock():
        b._save_mirrored(b._file(key),{'action_key':key,'request_sha256':t.HELD_REQUEST_SHA256,'status':'unknown'})
    monkeypatch.setattr(t,'HELD_RECORD_SHA256',hashlib.sha256(b._file(key).read_bytes()).hexdigest())
    monkeypatch.setattr(t,'_verify_held_current_state',lambda bridge,doc,host,repo,scope:None)
    monkeypatch.setattr(t,'_verify_held',lambda f,c:fixture.held.verify_no_send_certificate(f,c,expected_collector_sha256=source_sha))
    receipt=b.install_held_certificate(facts,canonical)
    assert receipt['status']=='certified_not_sent'
    stored=b._held_read(key,'certificate')
    assert stored['verifier_certificate']['mirror_post']==canonical['mirror_post']
    assert receipt['verifier_cert_sha256']==hashlib.sha256(t._held_json(stored['verifier_certificate'])).hexdigest()
    assert b._ensure()['actions'][b._held_path(key,'certificate').name]
