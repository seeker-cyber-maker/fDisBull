"""Scene waits resume only explicitly registered passive observer stops."""
from types import SimpleNamespace

import pytest

from fdisbull.scenes import SceneHandle,SceneError,register_scene_observer,scene_observer_stop


def stop():
    return {'run':'run','outcome':'hook','guest_elapsed_ms':7,
            'hook_hits':[{'observer':'assets'}],
            'session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'bp-1'}}}


def session():return SimpleNamespace(run_id='run',version={'id':1},_runtime_epoch='epoch')


@pytest.mark.parametrize('change',['unregistered','foreign-run','foreign-id','epoch','version','mixed','breakpoint','malformed'])
def test_observer_name_alone_does_not_authorize_resuming_a_stop(change):
    s=session();reply=stop()
    if change!='unregistered':register_scene_observer(s,'assets',breakpoint_ids=['bp-1'])
    if change=='foreign-run':reply['run']='other'
    if change=='foreign-id':reply['session']['stop_reason']['breakpoint_id']='bp-2'
    if change=='epoch':s._runtime_epoch='new'
    if change=='version':s.version={'id':2}
    if change=='mixed':reply['hook_hits'].append({'observer':'deliberate'})
    if change=='breakpoint':reply['outcome']='breakpoint'
    if change=='malformed':reply['hook_hits'][0]['observer']={}
    assert not scene_observer_stop(s,reply)


def handle():
    s=session();register_scene_observer(s,'assets',breakpoint_ids=['bp-1'])
    h=object.__new__(SceneHandle);h.session=s
    ready=[False];calls=[]
    def run(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:return stop()
        ready[0]=True
        return {'run':'run','outcome':'guest_time','guest_elapsed_ms':13,'hook_hits':[]}
    s.run=run
    h._observe=lambda *a,**kw:{'status':'matched' if ready[0] else 'mismatch',
                              'predicate_matched':ready[0],'frame':{'frame_id':len(calls)}}
    h.records=[]
    def store(result,**kw):
        h.records.append(result);return dict(result,observation=str(len(h.records)))
    h._store=store
    return h,calls


@pytest.mark.parametrize('outcome',[False,True])
def test_wait_and_action_outcome_resume_registered_observer_without_new_input(outcome):
    h,calls=handle()
    result=(h._wait_outcome({},guest_ms=100,timeout_ms=1000) if outcome else
            h._wait(None,None,guest_ms=100,timeout_ms=1000,slice_ms=100))
    assert result['status']=='matched' and result['guest_elapsed_ms']==20
    assert result['observer_stops']==[dict(observation='1',observer='assets',breakpoint_id='bp-1',guest_elapsed_ms=7)]
    assert h.records[0]['stop']==stop() and result['observer_stop_count']==1
    assert len(calls)==2 and all(x['stop_on_hook'] is True for x in calls)
    assert calls[1]['guest_ms']==93


@pytest.mark.parametrize('outcome',[False,True])
def test_explicit_debugger_stop_still_stops_scene_wait(outcome):
    h,calls=handle();h.session._scene_observers={}
    with pytest.raises(SceneError) as error:
        if outcome:h._wait_outcome({},guest_ms=100,timeout_ms=1000)
        else:h._wait(None,None,guest_ms=100,timeout_ms=1000,slice_ms=100)
    assert error.value.result['status']=='stopped' and len(calls)==1


def test_passive_stops_do_not_renew_guest_or_host_budget(monkeypatch):
    from fdisbull import scenes
    h,calls=handle();clock=[0];monkeypatch.setattr(scenes.time,'monotonic',lambda:clock[0])
    run=h.session.run
    def slow(**kw):
        reply=run(**kw);clock[0]=2;return reply
    h.session.run=slow
    with pytest.raises(SceneError) as error:h._wait_outcome({},guest_ms=100,timeout_ms=1000)
    assert error.value.result['status']=='timeout' and len(calls)==1
    assert error.value.result['observer_stop_count']==1 and h.records[0]['stop']==stop()


def test_zero_progress_observer_stops_are_still_bounded():
    h,calls=handle()
    def run(**kw):
        calls.append(kw);reply=stop();reply['guest_elapsed_ms']=0;return reply
    h.session.run=run
    with pytest.raises(SceneError) as error:h._wait_outcome({},guest_ms=100,timeout_ms=60000)
    assert error.value.result['status']=='timeout' and len(calls)==999
    assert len(error.value.result['observer_stops'])==16
    assert error.value.result['observer_stop_count']==999
    assert h.records[998]['previous_observer_stop']=='998'


def test_registration_is_explicit_bounded_and_replaceable():
    s=session()
    with pytest.raises(ValueError):register_scene_observer(s,'assets',breakpoint_ids='bp-1')
    register_scene_observer(s,'assets',breakpoint_ids=['bp-1']);assert scene_observer_stop(s,stop())
    register_scene_observer(s,'assets',breakpoint_ids=[]);assert not scene_observer_stop(s,stop())


def test_actual_scene_input_is_not_repeated_after_registered_observer(counter_game,emulator):
    from fdisbull.project import Project
    from test_scene_improvements import counter_definition
    path,binary=counter_game
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        scene=p.debug_save_scene('counter-observed',counter_definition(d.screenshot()))
        bp=d.breakpoint('1000:000b')['breakpoint_id']
        original=d._dispatch_hook
        def observe(result):
            if result.get('stop_reason',{}).get('breakpoint_id')==bp:
                d.delete_breakpoint(bp)
                return {'observer':'counter-assets'}
            return original(result)
        d._dispatch_hook=observe
        register_scene_observer(d,'counter-assets',breakpoint_ids=[bp])
        result=d.scene_act(scene['id'],'test.button')
        assert result['status']=='matched' and len(result['observer_stops'])==1
        assert d.memory('1000:0100',length=2)['hex']=='0100'
        inputs=[e for e in p.debug_events(d.run_id)['events'] if e['operation']=='keyboard.press']
        assert len(inputs)==1


from test_scene_improvements import counter_game
from test_debugger import emulator
