from copy import deepcopy
from fdisbull.scenes import SceneHandle
from test_scenes import mouse_game
from test_debugger import emulator


class Project:
    def __init__(self, doc): self.doc=doc
    def debug_scene_info(self, scene, version=None):
        return {'id':'rev','scene':'scene','sha256':'hash','definition':self.doc}
    def debug_scenes(self, version=None): return {'scenes':[]}


class Session:
    version={'id':1};run_id='run'
    def __init__(self, doc): self.project=Project(doc);self.rgb=[0,0,0];self.fail=False
    def status(self): return {'state':'stopped'}
    def frame_probe(self, coordinates):
        if self.fail: raise ValueError('missing frame')
        return {'width':2,'height':2,'source_bpp':8,'double_width':False,'double_height':False,
                'frame_id':1,'mode_id':1,'state_revision':1,
                'samples':[{'x':x,'y':y,'rgb':self.rgb} for x,y in coordinates]}


def pix(rgb): return {'pixels':{'samples':[{'x':0,'y':0,'rgb':rgb}]}}


def fixture():
    yes={'constant':True}
    return {'width':2,'height':2,'video':{'width':2,'height':2,'source_bpp':8,'double_width':False,'double_height':False},
            'exclusive_group':'main','match':yes,'content':{'requested':yes,'displayed':pix([1,0,0]),'ready':yes},
            'objects':[{'id':'button','name':'button','aliases':[],'visible':yes,'ready':yes,'enabled':yes,
                        'outcome':{'constant':False},'area':{'rect':[0,0,1,1]},'point':[0,0]}], 'handlers':[]}


def test_content_transitions_and_missing_frame():
    doc=fixture();session=Session(doc);handle=SceneHandle(session,'scene')
    old=handle._observe('button')
    assert old['scene_matched'] is True and old['content']['displayed'] is False and old['status']=='mismatch'
    session.rgb=[1,0,0];doc['content']['ready']={'constant':False}
    assert handle._observe('button')['status']=='mismatch'
    doc['content']['ready']={'constant':True}
    assert handle._observe('button')['status']=='matched'
    session.rgb=[2,0,0]
    assert handle._observe('button')['content']['displayed'] is False
    session.fail=True
    assert handle._observe('button')['status']=='unavailable'
    session.fail=False;session.rgb=[1,0,0]
    assert handle._observe('button')['status']=='matched'
    doc['content']['requested']={'constant':False}
    assert handle._observe('button')['status']=='mismatch'


def test_legacy_scene_has_no_content_gate():
    doc=fixture();del doc['content'];session=Session(doc)
    assert SceneHandle(session,'scene')._observe('button')['status']=='matched'


def test_matching_state_does_not_finish_an_action_while_a_known_popup_blocks():
    import pytest
    from fdisbull.scenes import SceneError
    session=Session(fixture());handle=SceneHandle(session,'scene')
    handle._observe=lambda **kwargs:{'status':'blocked','predicate_matched':True,'handlers':['message']}
    handle._store=lambda result,diagnostic=False:result
    session.run=lambda **kwargs:pytest.fail('A known blocked outcome must not replay input or advance')
    with pytest.raises(SceneError) as error:
        handle._wait_outcome({'constant':True},guest_ms=100,timeout_ms=1000)
    assert error.value.result['status']=='blocked'
    assert error.value.result['complete'] is False


def test_unknown_content_and_frame_revision_never_authorize():
    doc=fixture();doc['content']['displayed']={'memory':{'address':'1234:0000','length':1,'hex':'01'}}
    session=Session(doc);handle=SceneHandle(session,'scene')
    unknown=handle._observe('button')
    assert unknown['content']['displayed'] is None and unknown['status']=='unavailable' and not unknown['complete']
    doc['content']['displayed']={'constant':True}
    original=session.frame_probe;calls=[0]
    def changing(points):
        calls[0]+=1;value=original(points);value['state_revision']=calls[0];return value
    session.frame_probe=changing
    changed=handle._observe('button')
    assert changed['status']=='unavailable' and 'different frame' in changed['error']


def test_ambiguous_family_is_not_success():
    doc=fixture();doc['content']['displayed']={'constant':True};session=Session(doc)
    session.project.debug_scenes=lambda version=None:{'scenes':[{'id':'other','scene':'other','definition':deepcopy(doc)}]}
    result=SceneHandle(session,'scene')._observe('button')
    assert result['scene_matched'] is True and result['status']=='ambiguous' and not result['complete']


def test_interrupted_wait_preserves_stop_without_retry():
    import pytest
    from fdisbull.scenes import SceneError
    doc=fixture();session=Session(doc);handle=SceneHandle(session,'scene');calls=[]
    session.run=lambda **kwargs: calls.append(kwargs) or {'outcome':'breakpoint','guest_elapsed_ms':5,'hook_hits':[]}
    handle._store=lambda result,diagnostic=False:dict(result,diagnostic=diagnostic)
    with pytest.raises(SceneError) as error:handle._wait('button',None,guest_ms=100,timeout_ms=1000,slice_ms=10)
    result=error.value.result
    assert result['status']=='stopped' and result['stop']['outcome']=='breakpoint' and result['diagnostic']
    assert len(calls)==1


def test_animation_family_and_object_control_are_separate_from_content():
    doc=fixture();doc['content']['displayed']={'constant':True}
    doc['match']={'pixels':{'samples':[{'x':0,'y':0,'rgb':[0,0,0]}, {'x':1,'y':0,'rgb':[0,0,0]}], 'min_matches':1}}
    session=Session(doc);handle=SceneHandle(session,'scene')
    def phase(points):
        frame=Session.frame_probe(session,points)
        for sample in frame['samples']:
            sample['rgb']=[0,0,0] if sample['x']==0 else [1,1,1]
        return frame
    session.frame_probe=phase
    assert handle._observe('button')['status']=='matched'
    doc['objects'][0]['enabled']={'constant':False}
    result=handle._observe('button')
    assert result['content']['displayed'] is True and result['availability']['enabled'] is False and result['status']=='mismatch'
    doc['content']['displayed']={'constant':False}
    result=handle._observe('button')
    assert result['scene_matched'] is True and result['content']['displayed'] is False


def test_native_content_readiness_and_runtime_restore(mouse_game, emulator):
    from fdisbull.project import Project
    from test_scenes import definition, pixel
    path,binary=mouse_game
    with Project(path) as project, project.debugger(emulator,binary.parent) as session:
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        original=session.memory('1000:0000',length=4)['hex']
        binding=session.bind_runtime_memory('entry',session.runtime_base,length=4,expected_hex=original,
                                            provenance={'source':'native fixture runtime entry'})
        assert session.runtime_memory(binding['id'],length=4)['hex']==original
        checkpoint=session.save_state('readiness-before.sav')
        doc=definition(session.screenshot())
        doc['objects'][0]['ready']={'constant':True}
        doc['content']={'requested':{'constant':True},'displayed':pixel([170,0,0]),'ready':{'constant':True}}
        scene=project.debug_save_scene('readiness',doc)
        handle=session.scene(scene['id'])
        first=handle.check('test.button')
        assert first['scene_matched'] is True and first['content']=={'requested':True,'displayed':False,'ready':True}
        assert first['status']=='mismatch'
        changed=deepcopy(scene['definition']);changed['content']['displayed']=pixel([0,0,0]);changed['content']['ready']={'constant':False}
        second=project.debug_save_scene('readiness',changed,parent=scene['id'])
        result=session.scene(second['id']).check('test.button')
        assert result['content']['displayed'] is True and result['content']['ready'] is False and result['status']=='mismatch'
        changed=deepcopy(second['definition']);changed['content']['ready']={'runtime_memory':{'binding':'missing','offset':0,'length':1,'hex':'00'}}
        third=project.debug_save_scene('readiness',changed,parent=second['id'])
        result=session.scene(third['id']).check('test.button')
        assert result['content']['ready'] is None and result['status']=='unavailable' and not result['complete']
        changed=deepcopy(third['definition']);changed['content']['ready']={'runtime_memory':{'binding':'entry','offset':0,'length':1,'hex':original[:2]}}
        fourth=project.debug_save_scene('readiness',changed,parent=third['id'])
        assert session.scene(fourth['id']).check('test.button')['status']=='matched'
        session.load_state(checkpoint['artifact'])
        import pytest
        with pytest.raises(ValueError,match='invalidated'):session.runtime_memory(binding['id'],length=4)
        session.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        after_restore=session.scene(fourth['id']).check('test.button')
        assert after_restore['content']['ready'] is None and after_restore['status']=='unavailable'
        rebound=session.bind_runtime_memory('entry',session.runtime_base,length=4,expected_hex=original,provenance={'source':'fixture after restore'})
        assert rebound['id']!=binding['id'] and rebound['identity']['epoch']!=binding['identity']['epoch']
    with Project(path) as project, project.debugger(emulator,binary.parent) as restarted:
        with pytest.raises(ValueError,match='invalidated'):
            restarted.runtime_memory(binding['id'],length=4)


def test_session_navigation_wrapper_forwards_footprint():
    from fdisbull.scenes import SceneSessionMixin
    class FakeSession(SceneSessionMixin):
        def scene(self,name):
            assert name=='room'
            class Handle:
                def navigation_check(self,point,*,footprint=None):return {'point':point,'footprint':footprint}
            return Handle()
    footprint={'width':1,'height':1,'anchor':[0,0]}
    assert FakeSession().scene_navigation('room',[2,3],footprint=footprint)=={'point':[2,3],'footprint':footprint}
