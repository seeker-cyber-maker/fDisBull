"""Movement contracts at the paused session boundary."""
from types import SimpleNamespace
import pytest
import fdisbull.movement as movement


class Session(movement.MovementSessionMixin):
    def __init__(self, samples, *, runs=None, stop_ok=True, scene=None):
        self.samples=iter(samples);self.runs=iter(runs or []);self.stop_ok=stop_ok;self.nav=scene
        self.calls=[];self.closed=False;self.run_id='run';self.version={'id':1}
        self.rpc=SimpleNamespace(capabilities={'timing':{'fast_forward':True}})
    def _macro_plan(self,*args):return ({'id':'macros','sha256':'hash'}, {'script':{'steps':[]}})
    def macro(self,macro_set,name,**kwargs):
        self.calls.append(('macro',name))
        return {'ok':self.stop_ok if name=='stop' else True}
    def run(self,**kwargs):
        self.calls.append(('run',kwargs));return next(self.runs,{'outcome':'guest_time','guest_elapsed_ms':10,'hook_hits':[]})
    def keyboard_state(self):return {'keyboard':{'pending_events':0,'owned_keys':0}}
    def screenshot(self,name,*,hooks=True):
        self.calls.append(('screenshot',hooks));return {'artifact':'diagnostic','metadata':{}}
    def close(self):self.calls.append(('close',));self.closed=True
    def _event(self,*args):pass
    def _artifact(self,*args):return {'artifact':'receipt'}
    def scene(self,name):return self.nav


def sample(x, *, complete=True, stopped=True):
    return {'values':{'x':x,'y':1,'stopped':stopped},'captures':[], 'complete':complete,'errors':{} if complete else {'x':'missing capture'},'context':{}}


def invoke(monkeypatch,session,*,destination=3,**kwargs):
    monkeypatch.setattr(movement,'capture_observations',lambda s,specs:next(s.samples))
    fields={k:{'register':'general.ax'} for k in ('x','y','stopped')}
    return session.move('macros',start={'name':'start'},stop={'name':'stop'},observations=fields,
        until={'field':'x','op':'eq','value':destination},progress={'fields':['x'],'samples':2},
        settle={'field':'stopped','op':'eq','value':True},slice_ms=10,guest_ms=100,timeout_ms=10000,**kwargs)


def test_initial_arrival_does_not_execute(monkeypatch):
    s=Session([sample(3)])
    result=invoke(monkeypatch,s)
    assert result['ok'] and result['outcome']=='already_arrived' and not s.calls


def test_arrival_wins_over_final_stall_sample(monkeypatch):
    # The first poll has stalled; arrival on the next poll must win.
    s=Session([sample(1),sample(1),sample(3),sample(3)])
    result=invoke(monkeypatch,s)
    assert result['outcome']=='arrived' and result['ok'] and result['cleanup']['settled']
    assert result['cleanup']['already_settled']
    assert [c[1] for c in s.calls if c[0]=='macro']==['start']


def test_blocked_captures_diagnostic_before_stop(monkeypatch):
    s=Session([sample(1),sample(1),sample(1),sample(1,stopped=False),sample(1)])
    result=invoke(monkeypatch,s)
    assert result['outcome']=='blocked' and result['classification']=='blocked_unknown'
    assert s.calls.index(('screenshot',False)) < s.calls.index(('macro','stop'))
    assert result['cleanup']['settled']


def test_missing_capture_cannot_start(monkeypatch):
    s=Session([sample(1,complete=False)])
    result=invoke(monkeypatch,s)
    assert result['outcome']=='observation_error' and not result['ok']
    assert not any(c[0] in ('macro','run') for c in s.calls)


def test_debugger_stop_closes_without_resuming(monkeypatch):
    s=Session([sample(1)],runs=[{'outcome':'breakpoint','guest_elapsed_ms':3,'hook_hits':[]}])
    result=invoke(monkeypatch,s)
    assert result['outcome']=='stopped' and result['stop_result']['outcome']=='breakpoint'
    assert s.closed and len([c for c in s.calls if c[0]=='run'])==1
    assert ('macro','stop') not in s.calls and s.calls.index(('screenshot',False))<s.calls.index(('close',))


def test_failed_stop_closes_session(monkeypatch):
    s=Session([sample(1),sample(3),sample(3,stopped=False)],stop_ok=False)
    result=invoke(monkeypatch,s)
    assert result['outcome']=='arrived' and not result['ok'] and s.closed
    assert 'Stop macro failed' in result['cleanup']['error']


class Navigation:
    def __init__(self, condition=True, contradiction=False):
        self.condition=condition;self.contradiction=contradiction
        self.info={'definition':{'navigation':{'space':'room','width':8,'height':8,
          'actor':{'width':1,'height':1,'anchor':[0,0]},'walkable':{'rect':[0,0,8,8]},
          'colliders':[{'id':'wall','area':{'rect':[2,0,3,8]},'when':{'constant':True}}],
          'provenance':{'extraction_rule':'fixture','source_facts':['fixture'],'evidence_status':'inferred'}}}}
    def navigation_check(self,point):
        return {'classification':'blocked' if self.contradiction and point==[1,1] else 'clear',
                'conditions':{'wall':self.condition},'manifest_sha256':'manifest'}


@pytest.mark.parametrize('condition,expected',[(True,'blocked_known_boundary'),(None,'blocked_unknown')])
def test_stall_boundary_requires_known_condition(monkeypatch,condition,expected):
    s=Session([sample(1),sample(1),sample(1),sample(1)],scene=Navigation(condition))
    result=invoke(monkeypatch,s,scene='room',position={'x':'x','y':'y'},target=[3,1])
    assert result['outcome']=='blocked' and result['classification']==expected


def test_observed_geometry_contradiction_is_not_success(monkeypatch):
    s=Session([sample(0),sample(1),sample(1)],scene=Navigation(contradiction=True))
    result=invoke(monkeypatch,s,scene='room',position={'x':'x','y':'y'},target=[3,1])
    assert result['outcome']=='geometry_disagreement' and not result['ok']
    assert result['geometry_counterexample']['classification']=='blocked'


def test_native_authored_key_event_and_cleanup(keyboard_game,emulator):
    from fdisbull.project import Project
    path,binary=keyboard_game
    with Project(path) as project, project.debugger(emulator,binary.parent) as session:
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        macros=project.debug_define_macros({'format':'fdisbull-macro-set-1','name':'fixture', 'macros':{
            'start':{'steps':[{'op':'keyboard.press','key':'a','hold_ms':20,'gap_ms':20}]},
            'stop':{'steps':[{'op':'keyboard.press','key':'b','hold_ms':20,'gap_ms':20}]}}})
        result=session.move(macros['id'],start={'name':'start'},stop={'name':'stop'},
            observations={'x':{'memory':{'address':'1000:0100','type':'u8'}}},
            until={'field':'x','op':'eq','value':97},progress={'fields':['x'],'samples':10},
            settle={'field':'x','op':'in_range','value':[0,255]},slice_ms=100,guest_ms=1000,timeout_ms=5000)
        assert result['ok'] and result['outcome']=='arrived' and result['cleanup']['settled'],result
        assert session.memory('1000:0100',length=1)['hex']=='61'
        assert not session.closed


from test_keyboard import keyboard_game
from test_debugger import emulator


def test_initial_unknown_geometry_refuses_input(monkeypatch):
    nav=Navigation();nav.navigation_check=lambda point:{'classification':'unknown' if point==[1,1] else 'clear','conditions':{},'manifest_sha256':'manifest'}
    s=Session([sample(1)],scene=nav)
    result=invoke(monkeypatch,s,scene='room',position={'x':'x','y':'y'},target=[3,1])
    assert result['outcome']=='geometry_disagreement' and not result['ok']
    assert result['geometry_counterexample']['classification']=='unknown'
    assert not any(c[0] in ('run','macro') for c in s.calls)


def test_arrival_checks_geometry_first(monkeypatch):
    nav=Navigation();nav.navigation_check=lambda point:{'classification':'blocked' if point==[2,1] else 'clear','conditions':{},'manifest_sha256':'manifest'}
    s=Session([sample(1),sample(2),sample(2)],scene=nav)
    result=invoke(monkeypatch,s,destination=2,scene='room',position={'x':'x','y':'y'},target=[2,1])
    assert result['outcome']=='destination_blocked' and not result['ok']
    # A dynamic collider may change after target preflight.
    calls=[]
    def dynamic(point):
        calls.append(point)
        return {'classification':'blocked' if point==[2,1] and len(calls)>3 else 'clear','conditions':{},'manifest_sha256':'manifest'}
    nav.navigation_check=dynamic
    s=Session([sample(1),sample(2),sample(2)],scene=nav)
    result=invoke(monkeypatch,s,destination=2,scene='room',position={'x':'x','y':'y'},target=[2,1])
    assert result['outcome']=='geometry_disagreement' and not result['ok']


def test_arrival_must_match_explicit_target(monkeypatch):
    s=Session([sample(1),sample(2),sample(2)],scene=Navigation())
    result=invoke(monkeypatch,s,destination=2,scene='room',position={'x':'x','y':'y'},target=[3,1])
    assert result['outcome']=='destination_predicate_disagreement' and not result['ok']


def test_control_macro_cannot_consume_guest_budget(monkeypatch):
    s=Session([sample(1)])
    s._macro_plan=lambda *args:({'id':'macros','sha256':'hash'},{'script':{'steps':[{'op':'run','guest_ms':100}]}})
    with pytest.raises(ValueError,match='physical input only'):invoke(monkeypatch,s)
    assert not s.calls


def test_native_move_preserves_caller_owned_key(keyboard_game,emulator):
    from fdisbull.project import Project
    path,binary=keyboard_game
    with Project(path) as project, project.debugger(emulator,binary.parent) as session:
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        macros=project.debug_define_macros({'format':'fdisbull-macro-set-1','name':'fixture', 'macros':{
            'start':{'steps':[{'op':'keyboard.press','key':'a','hold_ms':20,'gap_ms':20}]},
            'stop':{'steps':[{'op':'keyboard.press','key':'b','hold_ms':20,'gap_ms':20}]}}})
        lease=session.keyboard_key_down('left')['lease']
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        before=session.keyboard_state()['keyboard']
        assert before['owned_keys']==1 and not before['pending_events']
        result=session.move(macros['id'],start={'name':'start'},stop={'name':'stop'},
            observations={'x':{'memory':{'address':'1000:0100','type':'u8'}}},
            until={'field':'x','op':'eq','value':97},progress={'fields':['x'],'samples':10},
            settle={'field':'x','op':'in_range','value':[0,255]},slice_ms=100,guest_ms=1000,timeout_ms=5000)
        assert result['outcome']=='initial_input_not_clear' and not result['ok']
        assert not result['cleanup']['attempted'] and not session.closed
        assert session.keyboard_state()['keyboard']==before and lease in session._keyboard_leases
        session.keyboard_key_up(lease)
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        assert session.keyboard_state()['keyboard']['owned_keys']==0


def test_owned_key_is_released_even_if_guest_reports_settled(monkeypatch):
    s=Session([sample(1),sample(3),sample(3),sample(3)])
    owned=[0]
    def plan(macro_set,name,args):
        if name=='start':
            return ({'id':'macros','sha256':'hash'}, {'script':{'steps':[{'op':'keyboard.key-down','as':'down'}]}, 'outputs':{'held':'$down.lease'}})
        return ({'id':'macros','sha256':'hash'}, {'script':{'steps':[{'op':'keyboard.key-up'}]}})
    def macro(macro_set,name,**kwargs):
        s.calls.append(('macro',name,kwargs.get('args')))
        if name=='start':
            owned[0]=1
            return {'ok':True,'outputs':{'held':'lease-1'}}
        assert kwargs['args']=={'lease':'lease-1'}
        owned[0]=0
        return {'ok':True}
    s._macro_plan=plan;s.macro=macro
    s.keyboard_state=lambda:{'keyboard':{'pending_events':0,'owned_keys':owned[0]}}
    monkeypatch.setattr(movement,'capture_observations',lambda session,specs:next(session.samples))
    fields={k:{'register':'general.ax'} for k in ('x','y','stopped')}
    result=s.move('macros', start={'name':'start'},stop={'name':'stop','args':{'lease':'$start.outputs.held'}},
                  observations=fields,until={'field':'x','op':'eq','value':3},
                  progress={'fields':['x'],'samples':2},settle={'field':'stopped','op':'eq','value':True},
                  slice_ms=10,guest_ms=100,timeout_ms=10000)
    assert result['ok'] and not result['cleanup']['already_settled']
    assert result['cleanup']['pre_stop_keyboard']['owned_keys']==1
    assert [c[1] for c in s.calls if c[0]=='macro']==['start','stop']
    assert owned[0]==0 and result['cleanup']['settled']


def test_autoneutral_arrival_keeps_destination_without_toggle(monkeypatch):
    s=Session([sample(1),sample(3),sample(3)])
    result=invoke(monkeypatch,s)
    assert result['ok'] and result['cleanup']['already_settled']
    assert result['cleanup']['pre_stop_observation']['values']['x']==3
    assert result['cleanup']['pre_stop_keyboard']=={'pending_events':0,'owned_keys':0}
    assert [c[1] for c in s.calls if c[0]=='macro']==['start']
    assert result['cleanup']['last_observation']['values']['x']==3


class SpatialAdapter:
    def __init__(self,target_class='clear', *, unknown_after=None):
        self.target_class=target_class;self.points=[];self.unknown_after=unknown_after;self.boundaries=[]
    def navigation_check(self,point):
        self.points.append(point)
        classification=self.target_class if point==[3,1] else 'clear'
        if self.unknown_after is not None and len(self.points)>=self.unknown_after: classification='unknown'
        return {'classification':classification,'conditions':{'wall':True},'manifest_sha256':'map-hash'}
    def first_boundary(self,point,target,*,conditions):
        self.boundaries.append((point,target,conditions))
        return {'result':{'classification':'blocked','point':[2,1]}}


def map_invoke(monkeypatch,s,**kwargs):
    monkeypatch.setattr(movement,'capture_observations',lambda session,specs:next(session.samples))
    fields={k:{'register':'general.ax'} for k in ('x','y','stopped','room')}
    return s.move('macros',start={'name':'start'},stop={'name':'stop'},observations=fields,
        until={'field':'x','op':'eq','value':3},progress={'fields':['x'],'samples':2},
        settle={'field':'stopped','op':'eq','value':True},slice_ms=10,guest_ms=100,timeout_ms=10000,
        spatial_map='map-revision',position={'x':'x','y':'y'},target=[3,1],**kwargs)


@pytest.mark.parametrize('classification',['blocked','unknown'])
def test_spatial_map_refuses_unqualified_destination_before_input(monkeypatch,classification):
    adapter=SpatialAdapter(classification);s=Session([sample(1)])
    s.spatial_navigation=lambda name,**kwargs:adapter
    result=map_invoke(monkeypatch,s)
    assert result['outcome']=='destination_'+classification and not result['ok']
    assert not any(c[0] in ('macro','run') for c in s.calls)


def test_spatial_map_boundary_uses_adapter_and_refreshes_cleanup(monkeypatch):
    adapter=SpatialAdapter();s=Session([sample(1),sample(1),sample(1),sample(1)])
    s.spatial_navigation=lambda name,**kwargs:adapter
    result=map_invoke(monkeypatch,s,map_conditions={'wall':{'field':'stopped','op':'eq','value':True}})
    assert result['classification']=='blocked_known_boundary'
    assert adapter.boundaries==[([1,1],[3,1],{'wall':True})]
    assert result['cleanup']['last_navigation']['classification']=='clear'


def test_spatial_map_dynamic_unknown_stops_movement(monkeypatch):
    adapter=SpatialAdapter(unknown_after=4);s=Session([sample(1),sample(2),sample(2)])
    s.spatial_navigation=lambda name,**kwargs:adapter
    result=map_invoke(monkeypatch,s)
    assert result['outcome']=='geometry_disagreement' and not result['ok']
    assert result['geometry_counterexample']['classification']=='unknown'


def test_spatial_map_rejects_scene_and_bad_condition(monkeypatch):
    s=Session([]);s.spatial_navigation=lambda name,**kwargs:SpatialAdapter()
    with pytest.raises(ValueError,match='either scene'):
        map_invoke(monkeypatch,s,scene='scene')
    with pytest.raises(ValueError,match='known field'):
        map_invoke(monkeypatch,s,map_conditions={'wall':{'field':'missing','op':'eq','value':1}})


def test_target_tolerance_preserves_observed_arrival_and_map(monkeypatch):
    adapter=SpatialAdapter();s=Session([sample(1),sample(2),sample(2)])
    s.spatial_navigation=lambda name,**kwargs:adapter
    monkeypatch.setattr(movement,'capture_observations',lambda session,specs:next(session.samples))
    fields={k:{'register':'general.ax'} for k in ('x','y','stopped','room')}
    result=s.move('macros',start={'name':'start'},stop={'name':'stop'},observations=fields,
        until={'field':'x','op':'in_range','value':[2,4]},progress={'fields':['x'],'samples':2},
        settle={'field':'stopped','op':'eq','value':True},slice_ms=10,guest_ms=100,timeout_ms=10000,
        spatial_map='map-revision',position={'x':'x','y':'y'},target=[3,1],target_tolerance=2)
    assert result['ok'] and [2,1] in adapter.points


def test_target_tolerance_refuses_outside_range(monkeypatch):
    s=Session([sample(1),sample(2),sample(2)],scene=Navigation())
    result=invoke(monkeypatch,s,destination=2,scene='room',position={'x':'x','y':'y'},target=[5,1],target_tolerance=2)
    assert not result['ok'] and result['outcome']=='destination_predicate_disagreement'


@pytest.mark.parametrize('tolerance',[-1,True,65])
def test_target_tolerance_invalid(monkeypatch,tolerance):
    with pytest.raises(ValueError,match='target_tolerance'):
        invoke(monkeypatch,Session([]),target_tolerance=tolerance)


def test_target_tolerance_checks_final_settled_position(monkeypatch):
    adapter=SpatialAdapter();s=Session([sample(1),sample(3),sample(4)])
    s.spatial_navigation=lambda name,**kwargs:adapter
    monkeypatch.setattr(movement,'capture_observations',lambda session,specs:next(session.samples))
    fields={k:{'register':'general.ax'} for k in ('x','y','stopped','room')}
    result=s.move('macros',start={'name':'start'},stop={'name':'stop'},observations=fields,
        until={'field':'x','op':'in_range','value':[3,4]},progress={'fields':['x'],'samples':2},
        settle={'field':'stopped','op':'eq','value':True},slice_ms=10,guest_ms=100,timeout_ms=10000,
        spatial_map='map-revision',position={'x':'x','y':'y'},target=[3,1],target_tolerance=2)
    assert result['ok'] and result['cleanup']['last_observation']['values']['x']==4
    assert [4,1] in adapter.points
