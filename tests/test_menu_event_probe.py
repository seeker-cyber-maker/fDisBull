"""Collector controls use an authored stopped-session double."""
from pathlib import Path
import importlib.util
import pytest

spec=importlib.util.spec_from_file_location('menu_probe',Path(__file__).parents[1]/'examples/menu_event_probe/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class Keyboard:
    def state(self):return {'keyboard':{'pending_events':0,'owned_keys':[],'frame_keys':[]}}

class Session:
    metadata={'source_sha256':'a'*64};run_id='authored';_runtime_epoch=None
    def __init__(self):self.tick=0;self.context='main';self.keyboard=Keyboard();self.sent=0;self.fail=False
    def call(self,method):
        if method=='session.status':return {'state':'stopped','last_stop':{'kind':'pause'}}
        if method=='execution.timing':return {'guest_ticks':self.tick}
        raise AssertionError(method)
    def scene_check(self,revision,compact):
        yes=self.context in (revision,'both')
        return {'status':'matched' if yes else 'mismatch','scene_matched':yes,'observation':f'observation:{self.tick}:{revision}'}
    def frame_probe(self,points):assert points==[];return {'frame_id':self.tick,'mode_id':1}
    def run(self,**kwargs):
        self.tick+=kwargs['guest_ms']
        return {'outcome':'breakpoint' if self.fail else 'guest_time'}


def setup(s):
    records=[]
    def record(kind,payload):records.append((kind,payload));return 'record:'+str(len(records))
    def action(before):s.sent+=1;s.context='other';return {'queued':True}
    args=dict(contexts={'main':'main','other':'other'},expected_context='main',record=record,
              action=action,samples=2,idle_samples=2,readiness_evidence={'main':'authored','other':'authored'})
    return args,records


def test_records_intent_before_one_dispatch_and_waits_in_bounded_slices():
    s=Session();args,records=setup(s)
    episode,result=probe.collect_episode(s,**args)
    assert s.sent==1 and result['category']=='dispatch-effect'
    kinds=[x[0] for x in records]
    assert kinds.index('input-intent')<kinds.index('input-receipt')<kinds.index('episode')
    assert len(episode['idle'])==2 and len(episode['after'])==2


@pytest.mark.parametrize('context',['other','both',None])
def test_ambiguous_or_wrong_precheck_never_sends(context):
    s=Session();s.context=context;args,records=setup(s)
    with pytest.raises(ValueError):probe.collect_episode(s,**args)
    assert s.sent==0


def test_exception_after_dispatch_is_retained_not_retried():
    s=Session();args,records=setup(s)
    def action(before):s.sent+=1;raise OSError('uncertain transport')
    args['action']=action
    with pytest.raises(OSError):probe.collect_episode(s,**args)
    assert s.sent==1 and records[-1][0]=='interrupted'
    assert records[-1][1]['retry_authorized'] is False


def test_changed_epoch_during_action_stops_collection():
    s=Session();args,records=setup(s)
    def action(before):s.sent+=1;s._runtime_epoch='restored';return {}
    args['action']=action
    with pytest.raises(ValueError):probe.collect_episode(s,**args)
    assert s.sent==1


def test_unexpected_native_stop_is_not_ignored():
    s=Session();args,records=setup(s)
    def action(before):s.sent+=1;s.fail=True;return {}
    args['action']=action
    with pytest.raises(ValueError):probe.collect_episode(s,**args)
    assert s.sent==1 and records[-1][0]=='interrupted'


def test_missing_retention_refuses_before_dispatch():
    s=Session();args,records=setup(s);args['record']=lambda kind,payload:None
    with pytest.raises(ValueError):probe.collect_episode(s,**args)
    assert s.sent==0


@pytest.mark.parametrize('params',[{'samples':0},{'idle_samples':0},{'samples':129},{'slice_ms':True},{'readiness_evidence':{}}])
def test_invalid_budgets_and_missing_readiness_evidence(params):
    s=Session();args,records=setup(s);args.update(params)
    with pytest.raises(ValueError):probe.collect_episode(s,**args)
    assert s.sent==0
