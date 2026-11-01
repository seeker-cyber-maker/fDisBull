"""First land purchase: prepared input, native allocation and retained recovery."""
import io
import json
import struct
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge


class NativeLand:
    run_id = 'land-original-run'

    def __init__(self):
        self.view = 'shop_street'
        self.money = dict(cash=5000, loan=5000, working_cash=5000)
        self.pens = bytearray(200)
        for i in range(10):
            struct.pack_into('<h', self.pens, i * 20 + 10, -2)
            struct.pack_into('<h', self.pens, i * 20 + 14, -1)
        self.draft = bytearray(self.pens)
        self.hover = None
        self.motion = self.queued = None
        self.point = (0, 0)
        self.clicks, self.runs, self.reads = [], [], []
        self.moves = []
        self.cancelled = False

    def memory(self, address, length):
        self.reads.append(address)
        if address == '4020:4384': return {'hex': self.pens.hex()}
        if address == '4020:b91c': return {'hex': self.draft.hex()}
        values = {'4020:5c3a':self.money['cash'], '4020:bfbb':self.money['loan'],
                  '4020:bad4':self.money['working_cash'], '4020:3c5c':65535}
        return {'hex': values[address].to_bytes(length, 'little', signed=False).hex()}

    def mouse(self):
        return {'x':self.point[0], 'y':self.point[1], 'buttons':0, 'release_pending':False}

    def call(self, method, params=None):
        if method == 'session.status': return {'state':'stopped'}
        if method == 'input.mouse.state': return {'mouse':self.mouse()}
        assert method == 'input.mouse.move'
        self.point = self.motion = (params['x'], params['y'])
        self.moves.append(self.point)
        return {'accepted':True, 'mouse':self.mouse()}

    def click(self, x, y, **kw):
        self.point = self.queued = (x, y)
        self.clicks.append(self.queued)
        return {'accepted':True, 'delivery':'queued', 'operation_id':str(len(self.clicks))}

    def run(self, *, guest_ms, **kw):
        self.runs.append(guest_ms)
        if self.motion is not None:
            self.hover, self.motion = self.motion, None
        if self.queued is not None:
            point, self.queued = self.queued, None
            if point == (201, 187):
                # A press using the previous plot hit target toggles selection
                # off. This reproduces the retained reserve-then-cancel result.
                if self.hover != point:
                    self.cancelled = True
                    self.money['working_cash'] = 5000
                    self.draft[:] = self.pens
                    self.view = 'plot'
                else:
                    self.money.update(cash=4500, working_cash=4500)
                    self.pens[:] = self.draft
                    self.view = 'shop_street'
            else:
                self.view = {(60,140):'estate', (60,100):'choice', (145,187):'inventory',
                             (172,187):'plot', (42,52):'plot_staged'}[point]
                if point == (42,52):
                    self.money['working_cash'] = 4500
                    struct.pack_into('<h', self.draft, 190, -1)
            self.hover = point
        return {'outcome':'guest_time', 'guest_elapsed_ms':guest_ms}

    def scene_assert(self, *a, **kw):
        assert self.view == 'shop_street'
        return {'status':'matched', 'observation':'fresh-street', 'frame':{'mode_id':5,'frame_id':1}}

    def registers(self): return {'state_revision':len(self.runs)}


def setup(monkeypatch):
    native = NativeLand()
    events = []
    project = SimpleNamespace(debug_scene_info=lambda *a, **k:{'definition':{'match':{'constant':True}}})
    patterns = {name:{'name':name,'samples':[{'x':0,'y':0,'rgb':[0,0,0]}],
                      'min_matches':1,'tolerance':0}
                for name in ('shop_street','estate','choice','inventory','plot','plot_staged')}
    text = scenes.TextScene(native, None, None, project=project, patterns=patterns, event=events.append)
    text.current, text.street = 'street', 'street-original'
    monkeypatch.setattr(scenes,'take_frame',lambda *a,**kw:(
        {'artifact':'stored-frame','metadata':{'mode_id':5}},native.view))
    monkeypatch.setattr(scenes,'matches',lambda image,pattern:image==pattern['name'])
    return text,native,events


def service_for(tmp_path,text,events):
    service = bridge.ZService(tmp_path,io.StringIO(),io.StringIO())
    service.ready(text)
    text.event = lambda item:(events.append(deepcopy(item)),service.event(item))
    service.pending = {'command':'buy desert plot','session_token':service.session_token,
                       'action':{'verb':'buy','target':'plot','item':None,'context_token':'original'},
                       'messages':[],'events':[]}
    return service


def test_pointer_preparation_prevents_reserved_plot_from_being_toggled_off(monkeypatch):
    text,native,events = setup(monkeypatch)
    text.buy_land()
    assert not native.cancelled and native.money == dict(cash=4500,loan=5000,working_cash=4500)
    assert struct.unpack_from('<h',native.pens,190)[0] == -1
    assert native.clicks == [(60,140),(60,100),(145,187),(172,187),(42,52),(201,187)]
    assert text.land_bought
    assert any(e['phase']=='land_purchase_confirmed' for e in events)


def test_land_commit_survives_first_display_failure_and_read_only_reconciliation(tmp_path,monkeypatch):
    text,native,events = setup(monkeypatch)
    service = service_for(tmp_path,text,events)
    frame = scenes.take_frame
    def fail_after_commit(*a,**kw):
        if native.money['cash']==4500: raise RuntimeError('post-commit frame unavailable')
        return frame(*a,**kw)
    monkeypatch.setattr(scenes,'take_frame',fail_after_commit)
    with pytest.raises(RuntimeError) as caught:text.buy_land()
    assert service.action_error(caught.value)
    assert service.held_action['effects']=='applied-confirmed'
    original = (tmp_path/'z-failure.json').read_bytes()
    clicks,runs = list(native.clicks),list(native.runs)
    monkeypatch.setattr(scenes,'take_frame',frame)
    reply = service.reconcile(service.held_action['id'])
    assert reply['complete'] and reply['read_only'] and reply['effects']=='applied-confirmed'
    assert reply['action']=={'verb':'buy','target':'plot','item':None}
    assert reply['witness']['context_id']=='street'
    assert native.clicks==clicks and native.runs==runs
    assert (tmp_path/'z-failure.json').read_bytes()==original


def test_reservation_alone_is_not_a_land_commit(tmp_path,monkeypatch):
    from fdisbull import dinopark_land as land
    text,native,events = setup(monkeypatch)
    service = service_for(tmp_path,text,events)
    original_press = land._press
    def stop_before_confirm(text,budget,phase,*args):
        if phase=='confirm': raise RuntimeError('readback before confirmation unavailable')
        return original_press(text,budget,phase,*args)
    monkeypatch.setattr(land,'_press',stop_before_confirm)
    with pytest.raises(RuntimeError) as caught:text.buy_land()
    assert service.action_error(caught.value)
    before = len(native.runs),len(native.clicks)
    assert not service.reconcile()['complete']
    assert not text.land_bought and native.money['cash']==5000
    assert before==(len(native.runs),len(native.clicks))


@pytest.mark.parametrize('field,value',[('run','foreign-run'),('source_revision','foreign-street'),('id','foreign-order')])
def test_land_recovery_is_bound_to_original_order(tmp_path,monkeypatch,field,value):
    from fdisbull import dinopark_land as land
    text,native,events = setup(monkeypatch)
    service = service_for(tmp_path,text,events)
    original = land._press
    def hold(text,budget,phase,*args):
        if phase=='confirm':raise RuntimeError('hold')
        return original(text,budget,phase,*args)
    monkeypatch.setattr(land,'_press',hold)
    with pytest.raises(RuntimeError) as caught:text.buy_land()
    service.action_error(caught.value)
    text.land_order[field]=value
    assert not service.reconcile()['complete']


def test_completed_native_land_still_needs_final_witness(tmp_path,monkeypatch):
    text,native,events = setup(monkeypatch)
    service = service_for(tmp_path,text,events)
    text.buy_land()
    native.registers=lambda:(_ for _ in ()).throw(RuntimeError('last witness unavailable'))
    service.finish()
    reply=json.loads(service.writer.getvalue().splitlines()[-1])
    assert not reply['complete'] and reply['effects']=='applied-confirmed'
    assert reply['recovery_required'] and service.held_action is not None


def held_land(tmp_path,monkeypatch):
    from fdisbull import dinopark_purchase as purchase
    text,native,events = setup(monkeypatch)
    service = service_for(tmp_path,text,events)
    clock = [0]
    monkeypatch.setattr(purchase,'_clock',lambda:clock[0])
    event = text.event
    def expire_after_select(item):
        event(item)
        if item.get('phase')=='land_input_sent' and item['purchase_phase']=='select':clock[0]=40
    text.event = expire_after_select
    with pytest.raises(TimeoutError) as caught:text.buy_land()
    assert service.action_error(caught.value)
    return text,native,service


def continue_land(service):
    observation = service.observe()
    assert observation['complete'] and observation['objects'][0]['id']=='land-order'
    service.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'continue','target':'land-order',
        'item':None,'context_token':observation['context']['token']}})+'\n')
    return service.command()


def test_explicit_continuation_skips_delivered_input_and_certifies_original_buy(tmp_path,monkeypatch):
    text,native,service = held_land(tmp_path,monkeypatch)
    ident = service.held_action['id']
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    assert len(native.clicks)==5 and text.land_order['phase']=='select'
    assert not service.reconcile(ident)['complete']
    command = continue_land(service)
    assert command=='continue land purchase'
    service.output(scenes.dispatch_local_action(text,command))
    service.finish()
    assert service.held_action['id']==ident and service.recovery_required
    assert len(native.clicks)==6 and native.clicks[-1]==(201,187)
    assert service.observe()['objects']==[]
    before = list(native.clicks),list(native.runs)
    result = service.reconcile(ident)
    assert result['complete'] and result['action']=={'verb':'buy','target':'plot','item':None}
    assert result['recovery_id']==ident and result['effects']=='applied-confirmed'
    assert before==(native.clicks,native.runs)
    assert (tmp_path/'z-failure.json').read_bytes()==diagnostic


def test_repeated_phase_exhaustion_keeps_original_root_and_cumulative_budget(tmp_path,monkeypatch):
    from fdisbull import dinopark_land as land
    text,native,service = held_land(tmp_path,monkeypatch)
    root = deepcopy(service.held_action)
    text.land_order['guest_requested_ms']['select']=land.PHASE_GUEST_MS
    before = list(native.clicks),list(native.runs)
    for _ in range(2):
        command = continue_land(service)
        with pytest.raises(TimeoutError,match='guest budget') as caught:scenes.dispatch_local_action(text,command)
        assert service.action_error(caught.value)
        assert service.held_action['id']==root['id']
        assert service.held_action['pending']==root['pending']
        assert text.land_order['guest_requested_ms']['select']==land.PHASE_GUEST_MS
    assert before==(native.clicks,native.runs)


def test_wrong_draft_plot_withholds_confirmation(monkeypatch):
    text,native,_ = setup(monkeypatch)
    run=native.run
    def different_plot(**kw):
        result=run(**kw)
        if native.view=='plot_staged':
            struct.pack_into('<h',native.draft,190,-2)
            struct.pack_into('<h',native.draft,10,-1)
        return result
    native.run=different_plot
    with pytest.raises(ValueError,match='draft land allocation'):text.buy_land()
    assert len(native.clicks)==5 and not text.land_bought
    assert text.land_order['proof'] is None


def test_money_change_without_exact_native_allocation_is_not_a_commit(monkeypatch):
    text,native,_=setup(monkeypatch)
    run=native.run
    def changed_other_pen(**kw):
        result=run(**kw)
        if native.money['cash']==4500:native.pens[0]^=1
        return result
    native.run=changed_other_pen
    with pytest.raises(ValueError,match='outside the qualified phase'):text.buy_land()
    assert len(native.clicks)==6 and text.land_order['proof'] is None and not text.land_bought


def test_failed_reconcile_preserves_proof_and_original_diagnostic_for_retry(tmp_path,monkeypatch):
    text,native,events=setup(monkeypatch)
    service=service_for(tmp_path,text,events)
    text.buy_land()
    assert service.action_error(RuntimeError('host follow-up unavailable'))
    root=service.held_action['id']
    before=list(native.runs),list(native.clicks)
    diagnostic=(tmp_path/'z-failure.json').read_bytes()
    witness=service.witness
    monkeypatch.setattr(service,'witness',lambda observation:None)
    assert not service.reconcile(root)['complete']
    assert service.held_action['id']==root and text.land_order['proof']
    monkeypatch.setattr(service,'witness',witness)
    assert service.reconcile(root)['complete']
    assert before==(native.runs,native.clicks)
    assert (tmp_path/'z-failure.json').read_bytes()==diagnostic


def test_wrong_recovery_id_performs_no_native_read_or_execution(tmp_path,monkeypatch):
    text,native,service=held_land(tmp_path,monkeypatch)
    before=list(native.reads),list(native.runs),list(native.clicks)
    assert not service.reconcile('foreign-recovery')['complete']
    assert before==(native.reads,native.runs,native.clicks)


def test_unknown_run_execution_does_not_offer_an_automatic_continuation(tmp_path,monkeypatch):
    text,native,service=held_land(tmp_path,monkeypatch)
    text.land_order['execution_unknown']=True
    observed=service.observe()
    assert observed['complete'] and observed['objects']==[]
    assert not service.reconcile()['complete']


@pytest.mark.parametrize('exhausted',['guest','host'])
def test_ready_source_exhaustion_queues_no_extra_pointer_movement(tmp_path,monkeypatch,exhausted):
    from fdisbull import dinopark_land as land,dinopark_purchase as purchase
    text,native,events=setup(monkeypatch)
    service=service_for(tmp_path,text,events)
    clock=[0]
    monkeypatch.setattr(purchase,'_clock',lambda:clock[0])
    event=text.event
    def exhaust_at_ready_estate(item):
        event(item)
        if item.get('phase')=='land_observation' and item.get('view')=='estate' and item['ready']:
            if exhausted=='guest':text.land_order.setdefault('guest_requested_ms',{})['enter']=15900
            else:clock[0]=40
    text.event=exhaust_at_ready_estate
    with pytest.raises(TimeoutError) as caught:text.buy_land()
    assert service.action_error(caught.value)
    assert native.moves==[(60,140)] and native.clicks==[(60,140)]
    before=list(native.moves),list(native.clicks),list(native.runs)
    if exhausted=='guest':
        root=service.held_action['id']
        for _ in range(2):
            command=continue_land(service)
            with pytest.raises(TimeoutError) as caught:scenes.dispatch_local_action(text,command)
            assert service.action_error(caught.value) and service.held_action['id']==root
        assert before==(native.moves,native.clicks,native.runs)


def test_land_helper_source_is_bound_to_adapter_provenance():
    import hashlib
    from pathlib import Path
    from fdisbull import dinopark_land
    root=Path(bridge.__file__).parent
    data=json.loads((root/'data/dinopark-e55-source-provenance.json').read_text())
    assert data['bounded_land_helper_source_sha256']==hashlib.sha256(Path(dinopark_land.__file__).read_bytes()).hexdigest()
