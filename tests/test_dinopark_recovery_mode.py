"""Original-frame regression and provider/native lifetime recovery contracts."""
import io
import json
from types import SimpleNamespace

import pytest
from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge
from fixtures_dinopark_food_return import PROBES, IMAGE_SHA256, FRAME_ID


def retained_frame():
    values = {(p['x'], p['y']):tuple(p['rgb']) for p in PROBES}
    return SimpleNamespace(getpixel=lambda point:values[point])


def patterns():
    values = {}
    for path in (scenes.PATTERNS, scenes.SHOP_PATTERNS, scenes.OPERATING_PATTERNS, scenes.SAVE_PATTERNS):
        values.update(json.loads(path.read_text())['scenes'])
    street = json.loads(scenes.STREET_PATTERNS.read_text())['scenes']['street']
    values['shop_street'] = {**street, 'reject':[values[n] for n in
        ('quarter_popup','parking_hint','game_menu','save_dialog','load_dialog')]}
    return values


def original_return(monkeypatch):
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.current, text.pending_food_return = 'dino_diner', False
    text.project, text.debug, text.patterns = object(), object(), patterns()
    events = []
    text.event = events.append
    frame = {'artifact':'retained-original', 'sha256':IMAGE_SHA256, 'metadata':{'frame_id':FRAME_ID}}
    monkeypatch.setattr(scenes, 'take_frame', lambda *a:(frame, retained_frame()))
    monkeypatch.setattr(scenes, 'balances', lambda debug:{'cash':26364,'loan':4290,'working_cash':26364})
    monkeypatch.setattr(scenes, 'run_guest', lambda *a:None)
    return text, events


def test_actual_funded26k_frame_is_a_known_quarter_and_must_not_match_clear_street():
    p = patterns(); image = retained_frame()
    assert scenes.matches(image, p['quarter_popup'])
    assert not scenes.matches(image, p['parking_hint'])
    assert not scenes.matches(image, p['shop_street'])
    with pytest.raises(KeyError): image.getpixel((319,199))  # Missing evidence stays missing.


def test_postcommit_observer_exposes_explicitly_requested_quarter(monkeypatch):
    text, _ = original_return(monkeypatch)
    with pytest.raises(scenes.KnownSceneNotice) as notice:
        text.shop_observe('shop_street', {}, 'food-committed', wait_slices=0,
                          interrupts=('quarter_popup','parking_hint'))
    assert notice.value.notice == 'quarter_popup'


def test_funded26k_return_preserves_commit_and_exposes_notice_without_another_buy(monkeypatch):
    text, events = original_return(monkeypatch)
    proof = {'quantity':20,'price':500,'stock_at_commit':30}
    result = text.finish_food_return(proof, {'cash':26864}, 10)
    assert 'purchase is confirmed' in result and 'Acknowledge' in result
    assert text.pending_food_return is True and text.current == 'street'
    paused = next(e for e in events if e['phase']=='food_return_interrupted')
    assert paused['commit'] == proof and paused['notices'] == ['quarter_popup']
    assert paused['following_input'] == 'not_sent'


def test_public_food_continuation_is_accepted_with_confirmed_effect(tmp_path):
    writer = io.StringIO(); service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.text = SimpleNamespace(current='street')
    service.observe = lambda:{'complete':True,'context':{'id':'food-return.quarter-notice'}}
    service.pending = {'command':'buy 20 small feeders','messages':['Purchase confirmed. Acknowledge the notice.'],
        'events':[{'phase':'food_purchase_committed'},
                  {'phase':'food_return_interrupted','purchase_outcome':'confirmed'}]}
    service.finish(); response = json.loads(writer.getvalue())
    assert response['status']=='accepted' and response['complete'] is True
    assert response['effects']=='applied-confirmed'
    assert response['continuation']['context']=='food-return.quarter-notice'


def test_food_return_acknowledgment_is_one_new_notice_input_and_no_purchase(monkeypatch):
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.current, text.street = 'street', 'qualified-street'
    text.park_opened, text.pending_park_entry = True, False
    text.pending_food_return, text.pending_food_notice = True, False
    text.notice_outcome_unknown = False
    text.patterns = {x:x for x in ('quarter_popup','parking_hint','street_view','shop_street')}
    text.project = object(); inputs, events = [], []
    text.event, text.format_status = events.append, lambda x:'status'
    text.debug = SimpleNamespace(keyboard_press=lambda key:(inputs.append(key) or
        {'accepted':True,'delivery':'queued'}), scene_assert=lambda *a,**k:None)
    frames = iter(['quarter_popup','quarter_popup','street_view'])
    monkeypatch.setattr(scenes, 'take_frame', lambda *a:({'artifact':'retained'},next(frames)))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern:image==pattern)
    monkeypatch.setattr(scenes, 'run_guest', lambda *a:None)
    monkeypatch.setattr(scenes, 'park_snapshot', lambda *a:{})
    assert 'purchase was already confirmed' in text.acknowledge_notice()
    assert inputs==['enter'] and text.pending_food_return is False
    assert events[-1]['food_return_outcome']=='completed'


def recoverable_service(tmp_path, reader=None, status='stopped'):
    writer = io.StringIO(); service = bridge.ZService(tmp_path, reader or io.StringIO(), writer)
    calls = []
    service.text = SimpleNamespace(debug=SimpleNamespace(call=lambda op:(calls.append(op) or {'state':status})))
    service.pending = {'command':'buy 20 small feeders', 'messages':[],
                       'events':[{'phase':'food_purchase_committed','result':{'price':500,'quantity':20}}]}
    return service, writer, calls


def test_paused_provider_failure_is_durable_and_replies_once_without_finishing_again(tmp_path):
    service, writer, calls = recoverable_service(tmp_path, io.StringIO('{"op":"observe"}\n'))
    assert service.action_error(RuntimeError('postcommit view unavailable')) is True
    assert service.pending is None and service.recovery_required is True
    receipt = json.loads((tmp_path/'z-session.json').read_text())
    assert receipt['status']=='recovery-required' and receipt['complete'] is False
    assert receipt['action_failures'][0]['effects']=='applied-confirmed'
    with pytest.raises(EOFError):service.command()
    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(replies)==2 and replies[0]['effects']=='applied-confirmed'
    assert replies[1]['complete'] is False and replies[1]['recovery_required'] is True
    assert calls == ['session.status']


def test_recovery_only_mode_refuses_actions_and_checkpoint_creation_without_game_calls(tmp_path):
    service, writer, calls = recoverable_service(tmp_path)
    assert service.action_error(RuntimeError('unqualified return'))
    before = list(calls)
    assert service.checkpoint({'op':'save','slot':'unsafe'})['complete'] is False
    service.reader = io.StringIO(json.dumps({'op':'act','action':{
        'verb':'buy','target':'feeders','item':None,'context_token':'stale'}})+'\n')
    with pytest.raises(EOFError):service.command()
    assert calls==before
    assert json.loads(writer.getvalue().splitlines()[-1])['status']=='rejected'


def test_running_or_unreachable_guest_is_not_claimed_recoverable(tmp_path):
    service, writer, _ = recoverable_service(tmp_path, status='running')
    assert service.action_error(RuntimeError('bad state')) is False
    assert not service.recovery_required and writer.getvalue()==''
    def disconnected(op):raise EOFError('native transport gone')
    service.text.debug.call = disconnected
    assert service.action_error(RuntimeError('bad transport')) is False
