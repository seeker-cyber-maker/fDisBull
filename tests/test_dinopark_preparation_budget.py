"""Park preparation must progress by readiness, without long blind guest runs."""
from types import SimpleNamespace
import pytest

from fdisbull import dinopark_scenes as scenes
from fdisbull.dinopark_purchase import bounded_preparation


class GuideWorld:
    """Recorded five-input route, with delayed native presentation/commit."""
    def __init__(self, *, guides_after=1, fail_final_view=False):
        self.view='employment';self.guides=0;self.pending=0;self.queued=None
        self.clicks=[];self.runs=[];self.guides_after=guides_after
        self.fail_final_view=fail_final_view;self.run_id='guide-native'

    def scene_assert(self, scene, **kw):
        if scene=='street' and self.fail_final_view:raise RuntimeError('Final witness missing')
        assert self.view==('shop_street' if scene=='street' else scene)

    def click(self,x,y,**kw):
        transitions={('employment',0,(55,140)):'guide_posters',
                     ('guide_posters',0,(55,160)):'guide_detail',
                     ('guide_detail',0,(226,148)):'guide_staged',
                     ('guide_staged',1,(201,187)):'employment',
                     ('employment',1,(201,187)):'shop_street'}
        assert self.queued is None
        next_view=transitions[(self.view,self.pending,(x,y))]
        self.clicks.append((x,y));self.queued=[next_view,350]
        return {'accepted':True,'delivery':'queued','ticket':len(self.clicks)}

    def run(self,*,guest_ms,**kw):
        # Deliberately reject the old 1,000..7,000 ms settling sleeps.
        assert guest_ms<=500,'Blind settling run exceeded the readiness quantum'
        assert self._rpc_deadline is not None
        self.runs.append(guest_ms)
        if self.queued:
            self.queued[1]-=guest_ms
            if self.queued[1]<=0:
                self.view=self.queued[0];self.queued=None
                if self.view=='guide_staged':self.pending=1
                if self.view=='shop_street':self.guides=self.guides_after
        return {'outcome':'guest_time','guest_elapsed_ms':guest_ms}


@pytest.fixture
def guide(monkeypatch):
    def make(**kw):
        world=GuideWorld(**kw)
        text=object.__new__(scenes.TextScene)
        text.current='employment';text.fence_bought=True;text.guide_hired=False
        text.debug=world;text.project=None;text.street='street';text.locations={'employment':'employment'}
        text.patterns={x:x for x in ['employment','guide_posters','guide_detail','guide_staged','shop_street']}
        text.events=[];text.event=text.events.append
        return text,world
    monkeypatch.setattr(scenes,'balances',lambda d:dict(cash=2250,working_cash=2250,loan=5000))
    monkeypatch.setattr(scenes,'park_resources',lambda d:dict(guides=d.guides,small_feeders=0))
    monkeypatch.setattr(scenes,'pending_guide',lambda d:d.pending)
    monkeypatch.setattr(scenes,'take_frame',lambda p,d,name:({},d.view))
    monkeypatch.setattr(scenes,'matches',lambda image,pattern:image==pattern)
    return make


def test_guide_waits_for_each_native_transition_without_repeating_input(guide):
    text,world=guide();result=text.hire_guide()
    assert world.clicks==[(55,140),(55,160),(226,148),(201,187),(201,187)]
    assert world.guides==1 and text.guide_hired and text.current=='street'
    assert '$900 per month' in result and world._rpc_deadline is None
    proof=[e for e in text.events if e['phase']=='guide_hire_confirmed']
    assert len(proof)==1 and proof[0]['input']['ticket']==5
    assert proof[0]['guides_before']==0 and proof[0]['guides_after']==1


def test_guide_commit_is_recorded_before_a_missing_final_witness(guide):
    text,world=guide(fail_final_view=True)
    with pytest.raises(RuntimeError,match='Final witness'):text.hire_guide()
    assert len(world.clicks)==5 and world.guides==1 and not text.guide_hired
    assert any(e['phase']=='guide_hire_confirmed' for e in text.events)
    assert world._rpc_deadline is None


def test_wrong_native_roster_does_not_claim_guide_commit(guide):
    text,world=guide(guides_after=2)
    with pytest.raises(RuntimeError,match='unexpected committed resources'):text.hire_guide()
    assert len(world.clicks)==5 and not any(e['phase']=='guide_hire_confirmed' for e in text.events)


def test_first_committed_frame_failure_keeps_native_hire_proof(guide,monkeypatch):
    text,world=guide();original=scenes.take_frame
    def frame(project,debug,name):
        if name=='guide-committed':
            assert world.guides==1
            raise RuntimeError('First committed frame unavailable')
        return original(project,debug,name)
    monkeypatch.setattr(scenes,'take_frame',frame)
    with pytest.raises(RuntimeError,match='First committed frame'):text.hire_guide()
    assert len(world.clicks)==5
    proof=[e for e in text.events if e['phase']=='guide_hire_confirmed']
    assert len(proof)==1 and proof[0]['input']['ticket']==5


def test_preparation_deadline_intersects_and_restores_an_outer_scope():
    debug=SimpleNamespace(_rpc_deadline=7,_rpc_timeout_cap_ms=1000,
                          _rpc_admission_ms=1000,_rpc_cleanup_grace_ms=3000)
    text=SimpleNamespace(debug=debug)
    @bounded_preparation
    def operation(text):
        assert text.debug._rpc_deadline==7
        raise ValueError('probe')
    with pytest.raises(ValueError,match='probe'):operation(text)
    assert (debug._rpc_deadline,debug._rpc_timeout_cap_ms,debug._rpc_admission_ms,
            debug._rpc_cleanup_grace_ms)==(7,1000,1000,3000)
