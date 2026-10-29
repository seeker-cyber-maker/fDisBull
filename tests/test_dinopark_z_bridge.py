"""Protocol-only tests; native and compiler parity are separate acceptance runs."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
from fdisbull import dinopark_z as bridge


class ReadOnlyDebug:
    def registers(self): return {'state_revision': 1}


def service(tmp_path, requests=(), scene='office'):
    reader = io.StringIO(''.join(json.dumps(r)+'\n' for r in requests)); writer = io.StringIO()
    backend = bridge.ZService(tmp_path,reader,writer)
    text = SimpleNamespace(current=scene,debug=ReadOnlyDebug(),vegasaurus_extinct=False,
                           describe=lambda:'Original observed description.\nCommands: legacy bare verbs')
    backend.ready(text)
    return backend,writer


def test_native_projection_uses_public_names_and_opaque_freshness(tmp_path):
    backend,_ = service(tmp_path,scene='bank')
    obs = backend.observe()
    assert obs['complete'] and obs['coverage']['partial']
    assert 'Commands:' not in obs['context']['description']
    assert any(o['label']=='loan' and o['verbs']==['borrow','repay'] for o in obs['objects'])
    assert len(obs['context']['token'])==64
    assert not any(k in json.dumps(obs) for k in ('$cash','working_cash','4020:','compiler'))
    assert backend.observe()['context']['token']==obs['context']['token']


def test_cold_dinosaur_listing_has_no_undiscovered_outcome(tmp_path):
    backend,_ = service(tmp_path,scene='dinomart')
    listing=next(o for o in backend.observe()['objects'] if o['id']=='vegasaurus')
    assert listing['verbs']==['buy','read']
    assert not any(s in json.dumps(listing).lower() for s in ('refund','fake','joke','extinct'))
    backend.text.vegasaurus_extinct=True
    listing=next(o for o in backend.observe()['objects'] if o['id']=='vegasaurus')
    assert listing['verbs']==[] and 'EXTINCT' in listing['description']


def test_resolved_z_action_maps_only_to_existing_native_command(tmp_path):
    backend,writer = service(tmp_path,scene='bank')
    token=backend.observe()['context']['token']
    backend.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'repay','target':'loan','item':None,'context_token':token}})+'\n')
    assert backend.command()=='repay'
    assert backend.pending['command']=='repay' and writer.getvalue()==''


def test_stale_or_unknown_commands_send_no_native_command(tmp_path):
    requests=[{'op':'act','action':{'verb':'repay','target':'loan','item':None,'context_token':'stale'}},
              {'op':'execute_code','code':'untrusted'}]
    backend,writer=service(tmp_path,requests,scene='bank')
    with pytest.raises(EOFError): backend.command()
    replies=[json.loads(line) for line in writer.getvalue().splitlines()]
    assert [r['status'] for r in replies]==['rejected','incomplete']
    assert backend.pending is None


def test_legacy_messages_do_not_advertise_wrong_grammar_or_private_paths(tmp_path):
    backend,_=service(tmp_path)
    text=backend.public_message('Saved park. Evidence: /Users/operator/private/result\nCommands: bare legacy grammar')
    assert '/Users/' not in text and 'Commands:' not in text and 'legacy grammar' not in text


def test_confirmed_purchase_is_preserved_if_followup_fails(tmp_path):
    backend,writer=service(tmp_path)
    backend.pending={'command':'buy 20 small feeders','messages':[],
                     'events':[{'phase':'food_purchase_committed','result':{'quantity':20,'price':500}}]}
    backend.failure(RuntimeError('private failure'))
    reply=json.loads(writer.getvalue())
    assert reply['status']=='incomplete' and reply['effects']=='applied-confirmed'
    assert 'purchase is confirmed' in reply['message'] and 'private failure' not in writer.getvalue()


def test_missing_evidence_is_not_success_from_a_sentence(tmp_path):
    backend,writer=service(tmp_path)
    backend.pending={'command':'hire tour guide','messages':['A plausible completion sentence.'],'events':[]}
    backend.finish()
    assert json.loads(writer.getvalue())['status']=='incomplete'


def test_refusal_after_a_completed_hop_retains_partial_effects(tmp_path):
    backend,writer=service(tmp_path)
    backend.pending={'command':'save park zpark','messages':['No input was sent.'],
                     'events':[{'phase':'result','command':'go office'},
                               {'phase':'refused','command':'save park zpark','input':'not_sent'}]}
    backend.finish()
    reply=json.loads(writer.getvalue())
    assert reply['status']=='incomplete' and reply['effects']=='partial'


def test_known_modal_exposes_handler_without_background_or_hidden_routes(tmp_path,monkeypatch):
    backend,writer=service(tmp_path,scene='park')
    def obscured(): raise ValueError('background does not match under modal')
    backend.text.describe=obscured
    backend.text.park_opened=True;backend.text.notice_outcome_unknown=False
    backend.text.project=object();backend.text.patterns={'quarter_popup':'known','parking_hint':'other'}
    profile=SimpleNamespace(take_frame=lambda *args:({},object()), matches=lambda image,p:p=='known')
    monkeypatch.setattr(bridge,'load_scenes',lambda:profile)
    obs=backend.observe()
    assert obs['complete'] and obs['context']['id']=='park.quarter-notice'
    assert [o['id'] for o in obs['objects']]==['notice']
    backend.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'go','target':'route-bank','item':None,'context_token':obs['context']['token']}})+'\n')
    with pytest.raises(EOFError): backend.command()
    assert json.loads(writer.getvalue())['status']=='rejected'
    backend.reader=io.StringIO(json.dumps({'op':'act','action':{'verb':'acknowledge','target':'notice','item':None,'context_token':obs['context']['token']}})+'\n')
    assert backend.command()=='acknowledge notice'


def test_promoted_profiles_and_native_business_methods_keep_provenance():
    import ast,hashlib
    from fdisbull import dinopark_scenes
    data=Path(dinopark_scenes.__file__).parent/'data'
    provenance=json.loads((data/'dinopark-e55-source-provenance.json').read_text())
    names={'newgame-pixel-patterns.json':'newgame','shop_patterns.json':'shop','save_patterns.json':'save',
           'street_patterns.json':'street','mart_patterns.json':'mart'}
    for name,target in names.items():
        assert hashlib.sha256((data/('dinopark-e55-'+target+'.json')).read_bytes()).hexdigest()==provenance['source_files_sha256'][name]
    source=Path(dinopark_scenes.__file__).read_text()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='TextScene')
    # ast.dump changes its empty-field formatting between Python 3.12 and 3.13.
    # The exact unchanged class source provides a version-independent identity.
    original_class=ast.get_source_segment(source,node)
    assert hashlib.sha256(original_class.encode()).hexdigest()==provenance['native_text_scene_class_source_sha256']


def test_no_udc_means_no_game_copy_or_implicit_legacy_fallback(tmp_path,monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,'fdisbull.udc',None)
    with pytest.raises(ValueError,match='UDC is required'):
        bridge.build_game(tmp_path,tmp_path/'never-created')
    assert not (tmp_path/'never-created').exists()


def test_running_inventory_uses_qualified_operating_report_without_replaying_ui(tmp_path):
    backend,_=service(tmp_path,scene='street')
    backend.text.park_opened=True
    objects,bindings=backend.objects()
    matches=[o for o in objects if 'inventory' in [o['label'],*o['aliases']]]
    assert len(matches)==1 and matches[0]['id']=='park-status'
    assert bindings[('check','park-status')]=='status'
    assert bindings[('check','inventory')]=='check inventory'
    backend.text.current='park'
    objects,bindings=backend.objects()
    assert any('inventory' in o['aliases'] and o['id']=='park-status' for o in objects)


@pytest.mark.parametrize('interrupt', [False,True])
def test_native_launch_failure_or_interrupt_always_finalizes_receipt(tmp_path,monkeypatch,interrupt):
    import hashlib
    from fdisbull import dinopark_scenes as scenes
    game=tmp_path/'game';game.mkdir()
    for name in ('DINOPARK.EXE','VARS.DAT'):
        (game/name).write_bytes(b'authored setup failure fixture')
    value=hashlib.sha256((game/'DINOPARK.EXE').read_bytes()).hexdigest()
    monkeypatch.setattr(scenes,'EXPECTED_EXE',value)
    monkeypatch.setattr(scenes,'EXPECTED_VARS',value)
    backend=tmp_path/'not-launched';backend.write_bytes(b'not an emulator')
    error=scenes.SceneInterrupted if interrupt else RuntimeError
    class FailBeforeLaunch:
        @staticmethod
        def create(*args,**kwargs): raise error('injected setup boundary failure')
    monkeypatch.setattr(scenes,'Project',FailBeforeLaunch)
    work=tmp_path/'run'
    with pytest.raises(error):
        scenes.run_session(['--game-dir',str(game),'--backend',str(backend),'--work-dir',str(work)])
    receipt=json.loads((work/'receipt.json').read_text())
    assert receipt['status']==('interrupted' if interrupt else 'failed')
    assert receipt['complete'] is False and receipt['ok'] is False
    assert receipt['source_unchanged'] is True


def test_interrupted_receipt_preserves_known_purchase_and_unknown_followup(tmp_path):
    backend,_=service(tmp_path)
    backend.pending={'command':'buy 20 small feeders','events':[{'phase':'food_purchase_committed'}]}
    backend.stop_reason='SIGTERM'
    backend.receipt('interrupted')
    receipt=json.loads((tmp_path/'z-session.json').read_text())
    assert receipt['complete'] is False
    assert receipt['pending_effects']=='applied-confirmed'
    assert receipt['pending_command']=='buy 20 small feeders'


def test_bank_preparation_runs_move_in_guest_then_rechecks_before_any_press():
    from fdisbull import dinopark_scenes as scenes
    calls=[];events=[]
    mouse={'buttons':0,'release_pending':False,'x':350,'y':140}
    class Mouse:
        def scene_assert(self,*args,**kwargs):
            calls.append('observe');return {'frame':{'mode_id':5,'frame_id':42},'observation':'fresh'}
        def call(self,method,params=None):
            calls.append(method)
            if method=='input.mouse.move':
                assert params=={'x':51,'y':26,'mode_id':5,'frame_id':42}
                mouse.update(x=102,y=26)
            return {'mouse':dict(mouse)}
        def run(self,**kwargs):
            calls.append('guest-consumes-move');return {'outcome':'guest_time'}
    scenes.prepare_bank_pointer(Mouse(),'office',events.append)
    assert calls==['observe','input.mouse.state','input.mouse.move','guest-consumes-move','input.mouse.state','observe']
    assert events[0]['bank_press']=='not_sent'
    assert events[0]['mouse_after']['x']==102


def test_held_pointer_never_sends_bank_move_or_press():
    from fdisbull import dinopark_scenes as scenes
    calls=[]
    class Held:
        def scene_assert(self,*args,**kwargs): return {'frame':{'mode_id':5,'frame_id':1}}
        def call(self,method,params=None):
            calls.append(method);return {'mouse':{'buttons':1,'release_pending':True}}
    with pytest.raises(ValueError,match='withheld'):
        scenes.prepare_bank_pointer(Held(),'office',lambda e:None)
    assert calls==['input.mouse.state']
