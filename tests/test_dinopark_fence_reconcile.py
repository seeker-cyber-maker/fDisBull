"""Original fence intent: finite phases, retained effects and no replay."""
import io
import json
import struct
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes,dinopark_z as bridge
from test_dinopark_land_reconcile import NativeLand

POINTS=[(205,105),(263,165),(160,54),(110,109),(60,85),(160,54),
        (160,188),(42,50),(216,187),(160,188),(188,187),(216,187)]
VIEWS=['general_store','general_store','fence_tab','fence_tab','fence_selected',
       'fence_selected','fence_map','fence_staged','fence_selected',
       'fence_reopened','fence_selected','shop_street']


class NativeFence(NativeLand):
    def __init__(self):
        super().__init__()
        self.view='general_store'
        self.money=dict(cash=3250,loan=5000,working_cash=3250)
        struct.pack_into('<h',self.pens,190,-1)
        struct.pack_into('<hh',self.pens,194,4,1)
        self.draft[:]=self.pens
        self.require_budget=False

    def run(self,*,guest_ms,**kw):
        self.runs.append(guest_ms)
        if self.motion is not None:self.hover,self.motion=self.motion,None
        if self.queued is not None:
            point,self.queued=self.queued,None
            index=len(self.clicks)-1
            assert point==POINTS[index]
            self.view=VIEWS[index]
            if index==7:
                self.money['working_cash']=2250
                struct.pack_into('<h',self.draft,190,0)
            if index==8:
                self.money['cash']=2250
                self.pens[:]=self.draft
            self.hover=point
        return {'outcome':'guest_time','guest_elapsed_ms':guest_ms}

    def scene_assert(self,*a,**kw):
        assert self.view in ('general_store','fence_tab','fence_selected','shop_street')
        return {'status':'matched','observation':'fresh-context','frame':{'mode_id':5,'frame_id':1}}

    def registers(self):
        if self.require_budget:
            assert getattr(self,'_rpc_deadline',None) is not None,'Fence observation started without shared deadline'
        return super().registers()


def fixture(monkeypatch):
    native=NativeFence();events=[]
    views=set(VIEWS)|{'general_store'}
    patterns={v:{'name':v,'samples':[{'x':0,'y':0,'rgb':[0,0,0]}],
                 'min_matches':1,'tolerance':0} for v in views}
    project=SimpleNamespace(debug_scene_info=lambda *a,**k:{'definition':{'match':{'constant':True}}})
    text=scenes.TextScene(native,None,None,project=project,patterns=patterns,event=events.append)
    text.current,text.street='general_store','street-source'
    text.locations={'general_store':'store-source'}
    text.land_bought=text.dinosaur_bought=True
    monkeypatch.setattr(scenes,'take_frame',lambda *a,**k:({'artifact':'stored-frame'},native.view))
    monkeypatch.setattr(scenes,'matches',lambda image,p:image==p['name'])
    return text,native,events


def provider(tmp_path,text,events):
    service=bridge.ZService(tmp_path,io.StringIO(),io.StringIO());service.ready(text)
    text.event=lambda x:(events.append(deepcopy(x)),service.event(x))
    service.pending={'command':'buy wood fence','session_token':service.session_token,
                     'action':{'verb':'buy','target':'wood-fence','item':None,'context_token':'original'},
                     'messages':[],'events':[]}
    return service


def continue_order(service):
    observed=service.observe();assert observed['complete']
    service.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'continue','target':'fence-order',
        'item':None,'context_token':observed['context']['token']}})+'\n')
    return service.command()


def test_fence_keeps_twelve_original_inputs_and_prepares_each_pointer(monkeypatch):
    text,native,events=fixture(monkeypatch)
    result=text.buy_fence()
    assert native.clicks==POINTS and native.moves==POINTS
    assert native.money==dict(cash=2250,loan=5000,working_cash=2250)
    assert struct.unpack_from('<h',native.pens,190)[0]==0
    assert text.fence_bought and text.current=='street' and '$2,250' in result
    assert any(e['phase']=='fence_purchase_confirmed' for e in events)


def test_public_fence_admission_binds_deadline_before_observation(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    service.pending=None
    observed=service.observe();native.require_budget=True
    service.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'buy','target':'wood-fence',
        'item':None,'context_token':observed['context']['token']}})+'\n')
    assert service.command()=='buy wood fence'
    assert native._rpc_deadline is not None
    service._end_action_budget()


def test_postcommit_display_error_retains_provider_then_continues_without_confirm_replay(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    original=scenes.take_frame
    def unavailable(*a,**kw):
        if native.money['cash']==2250:raise RuntimeError('first postcommit frame unavailable')
        return original(*a,**kw)
    monkeypatch.setattr(scenes,'take_frame',unavailable)
    with pytest.raises(RuntimeError) as caught:text.buy_fence()
    assert service.action_error(caught.value)
    assert service.held_action['effects']=='applied-confirmed' and len(native.clicks)==9
    root=service.held_action['id'];diagnostic=(tmp_path/'z-failure.json').read_bytes()
    before=list(native.runs),list(native.clicks)
    assert not service.reconcile(root)['complete']
    assert before==(native.runs,native.clicks)
    monkeypatch.setattr(scenes,'take_frame',original)
    command=continue_order(service);assert command=='continue fence order'
    service.output(scenes.dispatch_local_action(text,command));service.finish()
    assert service.held_action['id']==root and native.clicks==POINTS
    before=list(native.runs),list(native.clicks)
    result=service.reconcile(root)
    assert result['complete'] and result['read_only'] and result['effects']=='applied-confirmed'
    assert result['action']=={'verb':'buy','target':'wood-fence','item':None}
    assert result['witness']['context_id']=='street'
    assert before==(native.runs,native.clicks)
    assert (tmp_path/'z-failure.json').read_bytes()==diagnostic


def test_missing_final_witness_does_not_report_fence_success(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    text.buy_fence();native.registers=lambda:(_ for _ in ()).throw(RuntimeError('last witness unavailable'))
    service.finish();reply=json.loads(service.writer.getvalue().splitlines()[-1])
    assert not reply['complete'] and reply['effects']=='applied-confirmed' and service.held_action


def test_reservation_is_not_fence_commit(tmp_path,monkeypatch):
    from fdisbull import dinopark_fence as fence
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    press=fence._press
    def stop(text,budget,phase,*a):
        if phase=='confirm':raise RuntimeError('confirmation withheld')
        return press(text,budget,phase,*a)
    monkeypatch.setattr(fence,'_press',stop)
    with pytest.raises(RuntimeError) as caught:text.buy_fence()
    service.action_error(caught.value);before=list(native.runs),list(native.clicks)
    assert not service.reconcile()['complete'] and not text.fence_bought
    assert native.money['cash']==3250 and before==(native.runs,native.clicks)


@pytest.mark.parametrize('field,value',[('run','foreign'),('source_revision','foreign'),('id','foreign')])
def test_fence_reconciliation_rejects_foreign_binding(tmp_path,monkeypatch,field,value):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    text.buy_fence();assert service.action_error(RuntimeError('final followup'))
    text.fence_order[field]=value;before=list(native.runs),list(native.clicks),list(native.reads)
    assert not service.reconcile()['complete']
    assert before==(native.runs,native.clicks,native.reads)


def test_repeated_read_only_failure_preserves_root_and_proof(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    text.buy_fence();service.action_error(RuntimeError('host followup'));root=service.held_action['id']
    diagnostic=(tmp_path/'z-failure.json').read_bytes();before=list(native.clicks),list(native.runs)
    witness=service.witness;monkeypatch.setattr(service,'witness',lambda observation:None)
    assert not service.reconcile(root)['complete'] and text.fence_order['proof']
    monkeypatch.setattr(service,'witness',witness)
    assert service.reconcile(root)['complete'] and before==(native.clicks,native.runs)
    assert (tmp_path/'z-failure.json').read_bytes()==diagnostic


def held_map(tmp_path,monkeypatch):
    from fdisbull import dinopark_purchase as purchase
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    clock=[0];monkeypatch.setattr(purchase,'_clock',lambda:clock[0])
    event=text.event
    def expire(item):
        event(item)
        if item.get('phase')=='fence_input_sent' and item['purchase_phase']=='map':clock[0]=40
    text.event=expire
    with pytest.raises(TimeoutError) as caught:text.buy_fence()
    assert service.action_error(caught.value)
    return text,native,service


def test_map_deadline_continuation_does_not_replay_seven_delivered_inputs(tmp_path,monkeypatch):
    text,native,service=held_map(tmp_path,monkeypatch);root=service.held_action['id']
    assert native.clicks==POINTS[:7] and not text.fence_order['execution_unknown']
    command=continue_order(service)
    service.output(scenes.dispatch_local_action(text,command));service.finish()
    assert service.held_action['id']==root and native.clicks==POINTS
    assert service.reconcile(root)['complete']


def test_repeated_guest_exhaustion_does_not_renew_allowance_or_add_inputs(tmp_path,monkeypatch):
    from fdisbull import dinopark_fence as fence
    text,native,service=held_map(tmp_path,monkeypatch)
    text.fence_order['guest_requested_ms']['map']=fence.PHASE_GUEST_MS
    root=service.held_action['id'];before=list(native.clicks),list(native.moves),list(native.runs)
    for _ in range(2):
        command=continue_order(service)
        with pytest.raises(TimeoutError,match='guest budget') as caught:scenes.dispatch_local_action(text,command)
        assert service.action_error(caught.value) and service.held_action['id']==root
    assert before==(native.clicks,native.moves,native.runs)


def test_ready_source_preparation_refuses_before_pointer_when_only_100ms_left(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    event=text.event
    def exhaust(item):
        event(item)
        if item.get('phase')=='fence_observation' and item.get('view')=='fence_tab' and item['ready']:
            text.fence_order.setdefault('guest_requested_ms',{})[text.fence_order['phase']]=15900
    text.event=exhaust
    with pytest.raises(TimeoutError,match='guest budget') as caught:text.buy_fence()
    assert service.action_error(caught.value)
    assert native.clicks==POINTS[:3] and native.moves==POINTS[:3]


def test_unknown_input_delivery_does_not_authorize_replay(tmp_path,monkeypatch):
    text,native,events=fixture(monkeypatch);service=provider(tmp_path,text,events)
    click=native.click
    def lost(x,y,**kw):
        result=click(x,y,**kw)
        if len(native.clicks)==7:raise TimeoutError('input reply lost')
        return result
    native.click=lost
    with pytest.raises(TimeoutError) as caught:text.buy_fence()
    assert service.action_error(caught.value)
    before=list(native.clicks),list(native.runs),list(native.reads)
    assert not service.reconcile()['complete']
    assert before==(native.clicks,native.runs,native.reads)


def test_different_fence_marker_does_not_certify_wood(monkeypatch):
    text,native,_=fixture(monkeypatch);run=native.run
    def wrong(**kw):
        result=run(**kw)
        if native.money['cash']==2250:struct.pack_into('<h',native.pens,190,1)
        return result
    native.run=wrong
    with pytest.raises(ValueError,match='outside its qualified phase'):text.buy_fence()
    assert text.fence_order['proof'] is None and not text.fence_bought


@pytest.mark.parametrize('view',['general_store','fence_tab','fence_selected','fence_map','fence_staged','fence_reopened'])
def test_fence_cursor_predicates_require_every_remaining_sample(view):
    from PIL import Image
    from fdisbull import dinopark_fence as fence
    patterns=json.loads(scenes.SHOP_PATTERNS.read_text())['scenes'];original=deepcopy(patterns[view])
    clean=fence.observation_pattern(SimpleNamespace(patterns=patterns),view)
    assert patterns[view]==original and clean['min_matches']==len(clean['samples'])>=16
    image=Image.new('RGB',(320,200),(255,0,255))
    for sample in clean['samples']:image.putpixel((sample['x'],sample['y']),tuple(sample['rgb']))
    assert scenes.matches(image,clean)
    sample=clean['samples'][0];image.putpixel((sample['x'],sample['y']),(255,0,255))
    assert not scenes.matches(image,clean)


def test_fence_helper_is_bound_to_source_provenance():
    from pathlib import Path
    import hashlib
    from fdisbull import dinopark_fence as fence
    data=json.loads((Path(bridge.__file__).parent/'data/dinopark-e55-source-provenance.json').read_text())
    assert data['bounded_fence_helper_source_sha256']==hashlib.sha256(Path(fence.__file__).read_bytes()).hexdigest()
