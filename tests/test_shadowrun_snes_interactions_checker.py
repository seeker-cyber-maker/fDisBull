"""Controller poll ordering in the interaction route verifier."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from test_shadowrun_snes_opening_checker import Reader,empty_source,put

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('interaction_checker',ROOT/'scripts/check_shadowrun_snes_interactions.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def sample(kind,frame,held,previous=0,edge=0,pc=None,actor=None):
    value={'kind':kind,'serial':1,'video_frame':frame,'held':held,'previous':previous,'edge':edge,'actor':actor}
    if pc is not None:value['pc']=pc
    return value


def test_modal_chain_explains_player_input_change_without_extra_main_pass():
    samples=[sample('main',10,0x8000),sample('modal',11,0,pc=0x80a67d),
             sample('modal',12,0,pc=0x80c03a),sample('player',12,0,actor=2)]
    journal={'format':'snes-main-loop-controller-journal-1','dropped':0,'samples':samples,
             'duplicate_serials':[],'conflicting_serials':[],'consumer_disagreements':[1]}
    groups=checker.prepare_journal(journal,[(10,{}),(13,{})])
    assert [x['kind'] for x in groups[1]]==['main','modal','modal','player']
    samples[2]['pc']=0x80a7b2
    with pytest.raises(ValueError,match='unexplained main/player disagreement'):
        checker.prepare_journal(journal,[(10,{}),(13,{})])


def test_journal_rejects_missing_main_and_duplicate_consumer():
    journal={'format':'snes-main-loop-controller-journal-1','dropped':0,'samples':[],
             'duplicate_serials':[],'conflicting_serials':[],'consumer_disagreements':[]}
    with pytest.raises(ValueError,match='missing or duplicate main'):
        checker.prepare_journal(journal,[(1,{}),(2,{})])


def test_conversation_context_uses_stack_return_and_its_own_exit_poll():
    primary=sample('conversation',11,0,pc=0x80a67d)|{'context':'primary','source_return':0x91ac}
    exit_poll=sample('conversation',12,0,pc=0x8092b9)|{'context':'exit'}
    journal={'format':'snes-main-loop-controller-journal-1','dropped':0,
             'samples':[sample('main',10,0x8000),primary,exit_poll,sample('player',12,0,actor=2)],
             'duplicate_serials':[],'conflicting_serials':[],'consumer_disagreements':[1]}
    assert len(checker.prepare_journal(journal,[(10,{}),(13,{})])[1])==4
    primary['source_return']=0x922f
    with pytest.raises(ValueError,match='selector context'):
        checker.prepare_journal(journal,[(10,{}),(13,{})])


def test_shared_poll_pc_cannot_substitute_primary_for_keyword_menu():
    class Model:
        def get(self,name):
            assert name=='conversation_ui_mode'
            return 0
    source={'kind':'conversation','pc':0x80a67d,'context':'keyword'}
    with pytest.raises(checker.Mismatch) as exc:checker.poll_phase(Model(),source)
    assert exc.value.detail['field']=='conversation.selector_context'
    source['context']='primary'
    assert checker.poll_phase(Model(),source)==4


def test_stale_dynamic_exclusion_requires_source_primer_and_model_guard():
    source=empty_source()
    for at,value in ((0x26c,65535),(0xcde,65535),(0x1f6,65535),(0x1d05,65535),(0x2de2,3)):
        put(source,at,value)
    class Model(Reader):
        state={'task_dynamic_stale':1,'opening_phase':0,'task_vm_pending':0}
        def get(self,name,index=0):
            if name in self.state:return self.state[name]
            return super().get(name,index)
    model=Model(source)
    assert checker.dynamic_grid_ready(model,source,1,None) is False
    put(source,0x1f4,1)
    with pytest.raises(ValueError,match='guarded source primer'):
        checker.dynamic_grid_ready(model,source,1,None)
    put(source,0x1f4,0)
    with pytest.raises(checker.Mismatch):checker.dynamic_grid_ready(model,source,2,3)
    model.state['task_dynamic_stale']=0
    assert checker.dynamic_grid_ready(model,source,2,3) is True


def test_neutrality_checks_distinct_checkpoint_and_unmodified_evidence(monkeypatch):
    monkeypatch.setattr(checker,'CHECKPOINT_CORE','checkpoint')
    monkeypatch.setattr(checker,'UNPATCHED_CORE','unpatched')
    capture={'serial':1,'size':131072,'sha256':'hash','registers':{'pc':0x80962e}}
    c={'pc':0x80962e,'phase':'entry','frames':[{'video_frame':4,'dropped':0,'captures':[capture]}]}
    common={'rom_sha256':'rom','inputs':[],'frames':5,'patches':[],
            'memory_injection_mode':'no memory patches','system_ram_sha256':'ram','state_sha256':'state',
            'frame_rgb_sha256':'rgb','frame_png_sha256':'png','save_ram_sha256':'save',
            'snes_checkpoints':c,'frame_ram':[{'frame':4,'size':2,'sha256':'data'}],
            'frame_images':[{'frame':4,'width':1,'height':1,'rgb_sha256':'r','png_sha256':'p'}]}
    source=common|{'core_sha256':'observer'}
    reference=common|{'core_sha256':'checkpoint'};baseline=common|{'core_sha256':'unpatched'}
    value=checker.validate_neutrality(source,json.dumps(reference).encode(),json.dumps(baseline).encode())
    assert value['matching_checkpoint_digests']==1 and value['ram_frames']==1
    baseline=baseline|{'state_sha256':'changed'}
    with pytest.raises(ValueError,match='final-state mismatch'):
        checker.validate_neutrality(source,json.dumps(reference).encode(),json.dumps(baseline).encode())


def test_both_item_records_and_camera_are_compared_but_display_handshake_is_excluded():
    source=empty_source();model=bytearray(source);model[0x0204]=1
    counts=checker.compare_interaction(Reader(model),source)
    assert counts['item_bytes']==10 and counts['camera_words']==4
    model[0x2e80]=1
    with pytest.raises(checker.Mismatch) as exc:checker.compare_interaction(Reader(model),source)
    assert exc.value.detail['field']=='item.2e80'


def test_progression_compares_persistent_world_and_sorted_keyword_termination():
    source=bytearray(empty_source());source[0x3ca3:0x3ca6]=bytes((2,9,255))
    model=bytearray(source)
    counts=checker.compare_progression(Reader(model),source)
    assert counts['keyword_bytes']==3 and counts['persistent_world_bytes']==3761
    model[0x2e00]=1
    with pytest.raises(checker.Mismatch) as exc:checker.compare_progression(Reader(model),source)
    assert exc.value.detail['field']=='world.2e00'
    model=bytearray(source);model[0x3ca4]=8
    with pytest.raises(checker.Mismatch) as exc:checker.compare_progression(Reader(model),source)
    assert exc.value.detail['field']=='keyword.001'
    source[0x3ca4]=2
    with pytest.raises(ValueError,match='sorted and unique'):checker.compare_progression(Reader(source),source)
