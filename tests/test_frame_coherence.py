"""Authored frame/state fixtures; no native frames or guest execution."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
import fdisbull.frame_coherence as frame_coherence
from fdisbull.frame_coherence import capture_frame_state
from fdisbull.native_controller import BoundedNativeController, NativeControlError


def status(frame=4, revision=9, session='session', mode=5):
    return {'state':'stopped','session_id':session,'state_revision':revision,'frame_id':frame,'mode_id':mode}


def frame(item=None):
    s=status() if item is None else item
    return {'path':'frame.png','sha256':'a'*64,'metadata':{'source':'last_completed_guest_frame',
            'session_id':s['session_id'],'state_revision':s['state_revision'],
            'frame_id':s['frame_id'],'mode_id':s['mode_id'],'captured_ticks':123}}


class Fake:
    def __init__(self):
        self.journal=[];self.frame_captures=[];self.guest_elapsed=0;self.guest_budget_ms=500
        self.deadline=10;self.now=0;self.blocked_reason=None;self.calls=[];self.states=[{'score':1}]
        self.on_advance=lambda ms:None;self.session=SimpleNamespace(session_id='session')
    def clock(self):return self.now
    def _active(self):
        if self.blocked_reason:raise NativeControlError('blocked')
        if self.now>=self.deadline:raise NativeControlError('wall exhausted')
    def _block(self,error):
        if self.blocked_reason is None:self.blocked_reason=str(error)
    def advance(self,ms):
        self.calls.append(ms);self.on_advance(ms)
    def read_state(self):
        item=self.states.pop(0) if len(self.states)>1 else self.states[0]
        if isinstance(item,Exception):raise item
        return deepcopy(item)


def run(c, *, frames=None, statuses=None, **kwargs):
    sequence=list(statuses or [status()]);f=frames or frame()
    def read():return deepcopy(sequence.pop(0) if len(sequence)>1 else sequence[0])
    return capture_frame_state(c,lambda:deepcopy(f),status_reader=read,**kwargs)


class SDKSession:
    session_id='session'
    def __init__(self, before=None, probe=None, after=None):
        self.before=before or {'state':'stopped','session_id':'session','state_revision':9}
        self.after=after or deepcopy(self.before)
        self.probe=probe or {'session_id':'session','state_revision':9,'frame_id':4,'mode_id':5,'captured_ticks':123}
        self.calls=[]
    def call(self, method):
        assert method=='session.status'
        self.calls.append('status')
        item=self.before if len(self.calls)%3==1 else self.after
        if isinstance(item,Exception):raise item
        return deepcopy(item)
    def frame_probe(self, points):
        assert points==[];self.calls.append('frame_probe')
        if isinstance(self.probe,Exception):raise self.probe
        return deepcopy(self.probe)


def test_default_sdk_status_adapter_brackets_probe_without_guest_execution():
    c=Fake();c.session=SDKSession()
    out=capture_frame_state(c,frame)
    assert out['complete'] and out['atomic'] is False and out['frame_state_equivalence'] is None
    assert c.calls==[] and c.session.calls==['status','frame_probe','status']*2
    assert [item['kind'] for item in c.journal]==['frame-capture','frame-status-probe','frame-status-probe']
    assert len(out['status_brackets'])==2 and all(item['complete'] for item in out['status_brackets'])
    assert out['status_brackets'][0]['frame_probe']['captured_ticks']==123


def test_default_adapter_fresh_poll_uses_bounded_owner_progress():
    c=Fake();c.session=SDKSession()
    def advance(ms):
        c.guest_elapsed+=ms
        c.session.before['state_revision']=10;c.session.after['state_revision']=10
        c.session.probe.update(state_revision=10,frame_id=5)
    c.on_advance=advance
    out=capture_frame_state(c,lambda:frame(status(frame=5,revision=10)),
                            require_fresh=True,guest_ms=50,slice_ms=20)
    assert out['complete'] and out['freshness']=='confirmed' and c.calls==[20]
    assert len(out['status_brackets'])==3 and c.guest_elapsed==20


@pytest.mark.parametrize('which,change', [
    ('before',{'state':'running'}), ('after',{'state':'running'}),
    ('before',{'state_revision':8}), ('after',{'state_revision':10}),
    ('before',{'session_id':'foreign'}), ('after',{'session_id':'foreign'}),
    ('probe',{'session_id':'foreign'}), ('probe',{'state_revision':10}),
    ('probe',{'frame_id':None}),
])
def test_default_adapter_disagreement_never_invents_stopped_or_advances(which,change):
    c=Fake();c.session=SDKSession();getattr(c.session,which).update(change)
    out=capture_frame_state(c,frame,require_fresh=True,baseline_frame_id=3)
    assert not out['complete'] and out['last_status']['state'] is None and not c.calls
    bracket=out['status_brackets'][0]
    assert bracket['issues'] and not bracket['complete']
    assert all(k in bracket for k in ('session_before','frame_probe','session_after'))


def test_default_adapter_preserves_prior_parts_when_last_status_read_fails():
    c=Fake();error=OSError('authored status failure');c.session=SDKSession();c.session.after=error
    with pytest.raises(OSError) as caught:capture_frame_state(c,frame)
    assert caught.value is error and c.blocked_reason and c.calls==[]
    bracket=c.frame_captures[0]['status_brackets'][0]
    assert bracket['session_before']['state']=='stopped' and bracket['frame_probe']['frame_id']==4
    assert 'session_after' not in bracket and c.frame_captures[0]['error']['message']=='authored status failure'


def test_default_adapter_cannot_borrow_a_consistent_foreign_session():
    c=Fake();c.session=SDKSession()
    c.session.before['session_id']='foreign';c.session.after['session_id']='foreign'
    c.session.probe['session_id']='foreign'
    out=capture_frame_state(c,frame,require_fresh=True,baseline_frame_id=3)
    assert not out['complete'] and out['issues']==['status session differs from controller session']
    assert out['status_brackets'][0]['complete'] and not c.calls and 'frame' not in out


def test_stable_bracket_is_not_atomic_or_frame_cpu_equivalence():
    c=Fake();out=run(c)
    assert out['complete'] is True and out['freshness']=='not_requested' and not c.calls
    assert out['atomic'] is False and out['frame_state_equivalence'] is None
    assert out['state_before']==out['state_after']=={'score':1}
    assert c.frame_captures==[out] and c.journal[0]['record'] is out
    assert out['frame']['metadata']['captured_ticks']==123


def test_already_new_frame_does_not_advance():
    c=Fake();out=run(c,require_fresh=True,baseline_frame_id=3)
    assert out['complete'] and out['freshness']=='confirmed' and c.calls==[]
    assert out['baseline_source']=='caller_asserted_ordinal'


def test_session_bound_baseline_validates_context_before_wait():
    c=Fake();baseline={'session_id':'session','mode_id':5,'frame_id':3}
    out=run(c,require_fresh=True,baseline_frame=baseline)
    assert out['complete'] and out['baseline_source']=='session_bound' and out['baseline_frame']==baseline
    baseline['frame_id']=100
    assert out['baseline_frame']['frame_id']==3


@pytest.mark.parametrize('baseline', [
    {'session_id':'other','mode_id':5,'frame_id':3},
    {'session_id':'session','mode_id':6,'frame_id':3},
])
def test_wrong_baseline_context_refuses_freshness_execution(baseline):
    c=Fake();out=run(c,require_fresh=True,baseline_frame=baseline)
    assert not out['complete'] and out['freshness']=='unqualified' and c.calls==[]
    assert 'baseline session or mode differs from current status' in out['issues']


def test_foreign_status_is_refused_before_freshness_execution():
    c=Fake();out=run(c,statuses=[status(session='other')],require_fresh=True,baseline_frame_id=3)
    assert not out['complete'] and out['freshness']=='unqualified' and c.calls==[]
    assert out['issues']==['status session differs from controller session']


def test_opaque_adapter_requires_explicit_session_binding():
    c=Fake();c.session=None;out=run(c)
    assert not out['complete'] and out['issues']==['controller session identity is unknown'] and c.calls==[]
    c=Fake();c.session=None;out=run(c,expected_session_id='session')
    assert out['complete'] and out['expected_session_id']=='session'


def test_explicit_identity_cannot_override_known_controller_session():
    c=Fake();out=run(c,expected_session_id='other',require_fresh=True)
    assert not out['complete'] and out['issues']==['controller session identity conflicts with expected session']
    assert out['polls']==0 and c.calls==[]


def test_poll_wait_uses_measured_bounded_progress_then_brackets():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    newer=status(frame=5,revision=10)
    out=run(c,statuses=[status(),newer,newer],frames=frame(newer),require_fresh=True,guest_ms=50,slice_ms=20)
    assert c.calls==[20] and out['guest_elapsed_ms']==20 and out['polls']==2
    assert out['complete'] and out['freshness']=='confirmed'


def test_freshness_uses_owner_advance_adapter_when_provided():
    c=Fake();owner={'elapsed':0};calls=[]
    def advance(ms):
        calls.append(ms);owner['elapsed']+=ms;c.guest_elapsed=owner['elapsed']
    c.input_advance=advance
    newer=status(frame=5,revision=10)
    out=run(c,statuses=[status(),newer,newer],frames=frame(newer),require_fresh=True)
    assert out['complete'] and calls==[20] and c.calls==[]
    assert owner['elapsed']==c.guest_elapsed==20


def test_real_controller_records_its_bounded_guest_run():
    current={'value':status()}
    class Session:
        session_id='session'
        def run(self, *, guest_ms, timeout_ms, fast_forward, stop_on_hook):
            current['value']=status(frame=5,revision=10)
            return {'outcome':'guest_time','guest_elapsed_ms':guest_ms,'hook_hits':[]}
    c=BoundedNativeController(Session(),read_state=lambda:{'score':1},
                              total_guest_ms=100,total_timeout_ms=1000,clock=lambda:0)
    c.frame_captures=[]
    out=capture_frame_state(c,lambda:frame(current['value']),status_reader=lambda:deepcopy(current['value']),
                            require_fresh=True,guest_ms=50,slice_ms=20)
    assert out['complete'] and out['guest_elapsed_ms']==c.guest_elapsed==20
    assert [item['kind'] for item in c.journal]==['frame-capture','run']


def test_read_only_bracket_is_allowed_exactly_at_global_guest_cap():
    current={'value':status()}
    class Session:
        session_id='session'
        def run(self, *, guest_ms, timeout_ms, fast_forward, stop_on_hook):
            current['value']=status(frame=5,revision=10)
            return {'outcome':'guest_time','guest_elapsed_ms':guest_ms,'hook_hits':[]}
    c=BoundedNativeController(Session(),read_state=lambda:{'score':1},
                              total_guest_ms=20,total_timeout_ms=1000,clock=lambda:0)
    c.frame_captures=[]
    out=capture_frame_state(c,lambda:frame(current['value']),status_reader=lambda:deepcopy(current['value']),
                            require_fresh=True,guest_ms=50,slice_ms=20)
    assert out['complete'] and out['freshness']=='confirmed' and c.guest_elapsed==20
    assert [item['kind'] for item in c.journal]==['frame-capture','run'] and c.blocked_reason is None


def test_stale_frame_at_global_cap_does_not_start_another_run():
    c=Fake();c.guest_budget_ms=20;c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    out=run(c,require_fresh=True,guest_ms=50,slice_ms=20,max_polls=8)
    assert not out['complete'] and out['freshness']=='not_observed' and c.calls==[20]


def test_freshness_rejects_zero_measured_progress_without_replay():
    c=Fake()
    with pytest.raises(NativeControlError,match='no measured guest progress'):
        run(c,require_fresh=True)
    assert c.calls==[20] and c.blocked_reason


def test_stale_poll_cap_retains_last_status_without_diagnostic_execution():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    out=run(c,require_fresh=True,max_polls=2,guest_ms=50,slice_ms=20)
    assert out['complete'] is False and out['freshness']=='not_observed'
    assert out['last_status']==status() and len(out['status_polls'])==2 and c.calls==[20]
    assert 'frame' not in out and c.blocked_reason is None


def test_stale_local_guest_budget_stops_after_one_slice():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    out=run(c,require_fresh=True,guest_ms=20,slice_ms=20,max_polls=8)
    assert not out['complete'] and out['freshness']=='not_observed' and c.calls==[20]


def test_frame_id_regression_is_incomplete_without_another_slice():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    out=run(c,statuses=[status(frame=4),status(frame=3)],require_fresh=True)
    assert not out['complete'] and out['issues']==['frame id regressed during freshness wait']
    assert out['freshness']=='unqualified' and c.calls==[20]


@pytest.mark.parametrize('changed', [status(frame=5,session='other'),status(frame=5,mode=6)])
def test_freshness_session_or_mode_change_stops_without_second_advance(changed):
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    out=run(c,statuses=[status(),changed],require_fresh=True)
    assert not out['complete'] and c.calls==[20] and 'frame' not in out


@pytest.mark.parametrize('changed', [status(revision=10),status(frame=5),status(mode=6),status(session='other')])
def test_bracket_status_identity_mismatch_is_incomplete_without_retry(changed):
    c=Fake();out=run(c,statuses=[status(),changed])
    assert not out['complete'] and out['issues'] and not c.calls
    assert out['state_after']=={'score':1} and out['status_after']==changed


def test_state_mismatch_and_explicit_projection():
    c=Fake();c.states=[{'score':1,'counter':1},{'score':1,'counter':2}]
    assert not run(c)['complete']
    c=Fake();c.states=[{'score':1,'counter':1},{'score':1,'counter':2}]
    out=run(c,state_projector=lambda s:{'score':s['score']})
    assert out['complete'] and out['projected_before']==out['projected_after']=={'score':1}
    assert out['state_before']!=out['state_after'] and out['atomic'] is False


def test_post_read_failure_preserves_successful_frame_and_primary_error():
    c=Fake();error=OSError('authored post-state failure');c.states=[{'score':1},error]
    with pytest.raises(OSError) as caught:run(c)
    assert caught.value is error
    out=c.frame_captures[0];assert out['state_before']=={'score':1} and out['frame']==frame()
    assert 'state_after' not in out and out['error']['message']=='authored post-state failure'
    assert c.blocked_reason and not c.calls


def test_foreign_stop_propagates_and_is_not_resumed():
    c=Fake();error=NativeControlError('foreign stop')
    def stop(ms):raise error
    c.on_advance=stop
    with pytest.raises(NativeControlError) as caught:run(c,require_fresh=True)
    assert caught.value is error and c.calls==[20] and c.frame_captures[0]['last_status']==status()
    assert c.blocked_reason=='foreign stop'


def test_measured_local_overshoot_is_retained_and_blocks():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms+1)
    with pytest.raises(NativeControlError,match='exceeded measured guest budget'):
        run(c,require_fresh=True,guest_ms=20,slice_ms=20)
    assert c.calls==[20] and c.frame_captures[0]['guest_elapsed_ms']==21 and c.blocked_reason


def test_wall_expiration_after_frame_retains_returned_frame():
    c=Fake()
    def read_frame():c.now=10;return frame()
    with pytest.raises(NativeControlError):capture_frame_state(c,read_frame,status_reader=status)
    assert c.frame_captures[0]['frame']==frame() and c.frame_captures[0]['state_before']=={'score':1}
    assert 'state_after' not in c.frame_captures[0] and c.blocked_reason


def test_admission_that_exhausts_wall_prevents_next_observation():
    c=Fake();calls=[]
    c.admission_check=lambda:setattr(c,'now',10)
    with pytest.raises(NativeControlError,match='wall budget'):
        capture_frame_state(c,frame,status_reader=lambda:calls.append('status') or status())
    assert calls==[] and c.blocked_reason and c.frame_captures[0]['complete'] is False


def test_initial_controller_admission_that_exhausts_wall_prevents_status():
    c=Fake();calls=[]
    c._active=lambda:setattr(c,'now',10)
    with pytest.raises(NativeControlError,match='wall budget'):
        capture_frame_state(c,frame,status_reader=lambda:calls.append('status') or status())
    assert calls==[] and c.blocked_reason and c.frame_captures[0]['complete'] is False


def test_slow_final_comparison_cannot_complete_after_wall_deadline(monkeypatch):
    c=Fake();original=frame_coherence.json.dumps
    def slow(value, **kwargs):
        result=original(value, **kwargs)
        if kwargs.get('sort_keys') is True:c.now=10
        return result
    monkeypatch.setattr(frame_coherence.json,'dumps',slow)
    with pytest.raises(NativeControlError,match='wall budget'):
        run(c)
    out=c.frame_captures[0]
    assert out['complete'] is False and out['status_after']==status()
    assert out['frame']==frame() and out['state_before']==out['state_after']=={'score':1}
    assert c.blocked_reason


@pytest.mark.parametrize('bad', [{'frame_id':None}, {'session_id':''}, {'mode_id':True}, {'state':'running'}])
def test_unknown_status_is_incomplete_without_input(bad):
    c=Fake();x=status();x.update(bad);out=run(c,statuses=[x])
    assert not out['complete'] and out['last_status']==x and not c.calls and 'frame' not in out


def test_bad_frame_identity_is_incomplete_but_bracket_is_retained():
    c=Fake();f=frame();f['metadata']['state_revision']=8;out=run(c,frames=f)
    assert not out['complete'] and 'frame state_revision differs from bracket' in out['issues']
    assert out['state_after']=={'score':1} and not c.calls


def test_fresh_status_does_not_qualify_mismatched_frame():
    c=Fake();f=frame();f['metadata']['frame_id']=3
    out=run(c,frames=f,require_fresh=True,baseline_frame_id=3)
    assert not out['complete'] and out['freshness']=='unqualified' and not c.calls


def test_failed_final_status_preserves_every_prior_success():
    c=Fake();error=OSError('status read lost');calls=[]
    def read():
        calls.append(1)
        if len(calls)==2:raise error
        return status()
    with pytest.raises(OSError) as caught:
        capture_frame_state(c,frame,status_reader=read)
    out=c.frame_captures[0]
    assert caught.value is error and out['frame']==frame()
    assert out['state_before']==out['state_after']=={'score':1}
    assert 'status_after' not in out and c.blocked_reason


def test_frame_callback_exception_preserves_before_state_and_is_not_retried():
    c=Fake();error=OSError('frame read lost');calls=[]
    def read_frame():calls.append(1);raise error
    with pytest.raises(OSError) as caught:
        capture_frame_state(c,read_frame,status_reader=status)
    assert caught.value is error and calls==[1] and c.frame_captures[0]['state_before']=={'score':1}
    assert 'frame' not in c.frame_captures[0] and c.blocked_reason


def test_aggregate_poll_evidence_is_bounded_and_last_status_is_retained():
    c=Fake();c.on_advance=lambda ms:setattr(c,'guest_elapsed',c.guest_elapsed+ms)
    large=status();large['authored_padding']='x'*600000
    with pytest.raises(ValueError,match='evidence exceeds size limit'):
        run(c,statuses=[large],require_fresh=True,guest_ms=500,max_polls=30)
    assert c.frame_captures[0]['last_status']==large and c.blocked_reason
    assert c.frame_captures[0]['evidence_bytes'] > 4*1024*1024


@pytest.mark.parametrize('options', [{'require_fresh':1},{'baseline_frame_id':True},{'guest_ms':0},
    {'slice_ms':float('nan')},{'max_polls':0},{'max_polls':True},{'state_projector':3},
    {'expected_session_id':True}, {'baseline_frame':{'session_id':'session','mode_id':True,'frame_id':2}},
    {'baseline_frame':{'session_id':'session','mode_id':5,'frame_id':2},'baseline_frame_id':2}])
def test_invalid_arguments_never_create_attempt_or_do_io(options):
    c=Fake()
    with pytest.raises(ValueError):run(c,**options)
    assert c.frame_captures==[] and c.journal==[] and c.calls==[]
