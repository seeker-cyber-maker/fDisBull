"""Controller poll ordering in the interaction route verifier."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from test_shadowrun_snes_opening_checker import Reader,empty_source

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
