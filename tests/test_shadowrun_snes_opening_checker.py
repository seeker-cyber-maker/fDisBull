"""Tests for the opening checker's coverage and strict comparison rules."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('opening_checker',ROOT/'scripts/check_shadowrun_snes_opening.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def put(b,at,value):b[at:at+2]=value.to_bytes(2,'little')


def empty_source():
    b=bytearray(131072);put(b,0x14cc,0xfffe);put(b,0x268,0xffff);put(b,0x220,0xfffe)
    for i in range(4):put(b,0x232+i*2,0xffff)
    for base in (0xde88,0xe088):
        for i in range(256):put(b,base+i*2,0xffff)
    return b


class Reader:
    def __init__(self,b,messages=0):self.b=b;self.messages=messages
    def byte(self,at):return self.b[at]
    def word(self,at):return checker.word(self.b,at)
    def other_word(self,at):return checker.word(self.b,65536+at)
    def get(self,name,index=0):
        if name=='opening_message_count':return self.messages
        if name in ('task_list_head','task_list_free','task_list_current'):
            return checker.word(self.b,{'task_list_head':0x268,'task_list_free':0x26a,
                                        'task_list_current':0x26c}[name])
        raise AssertionError((name,index))


def test_sprite_pool_and_terminated_text_are_checked_without_exposing_text():
    source=empty_source();source[0x21a0:0x21a4]=b'abc\0'
    model=bytearray(source)
    counts=checker.check(Reader(model,1),source)
    assert counts['sprite_fields']==122 and counts['text_bytes']==4
    model[0x21a1]=ord('x')
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model,1),source)
    assert exc.value.detail=={'field':'text.byte.001','model':'redacted','source':'redacted'}
    model[0x21a1]=source[0x21a1];put(model,0x1584,2)
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model,1),source)
    assert exc.value.detail['field']=='sprite.node.04'


def test_unpatched_baseline_gate_checks_selected_and_final_hashes(monkeypatch):
    monkeypatch.setattr(checker,'JOURNAL_CORE','observer')
    monkeypatch.setattr(checker,'UNPATCHED_CORE','unpatched')
    monkeypatch.setattr(checker,'ROM_SHA256','rom')
    common={'rom_sha256':'rom','inputs':[],'frames':1,'patches':[],
            'memory_injection_mode':'no memory patches','system_ram_sha256':'ram',
            'state_sha256':'state','frame_rgb_sha256':'rgb','frame_png_sha256':'png',
            'save_ram_sha256':'save','frame_ram':[{'frame':0,'size':1,'sha256':'r'}],
            'frame_images':[{'frame':0,'width':1,'height':1,'rgb_sha256':'r','png_sha256':'p'}]}
    observer=common|{'core_sha256':'observer'};baseline=common|{'core_sha256':'unpatched'}
    raw=json.dumps(observer).encode()
    result=checker.check_unpatched_baseline(observer,raw,json.dumps(baseline).encode())
    assert result['selected_ram_frames']==1 and result['selected_image_frames']==1
    bad=baseline|{'state_sha256':'different'}
    with pytest.raises(ValueError,match='final-state mismatch'):
        checker.check_unpatched_baseline(observer,raw,json.dumps(bad).encode())


def test_reachable_collision_nodes_records_and_owners_are_checked():
    source=empty_source();put(source,0xde88,0);put(source,0xef18,0);put(source,0xf778,0xffff)
    for i in range(6):put(source,0xe288+2*i,i+1)
    put(source,65536+0xe214,7)
    model=bytearray(source);counts=checker.check(Reader(model),source)
    assert counts['collision_elements']==523  # 2 allocator words, 512 heads, node, record and owner
    put(model,65536+0xe214,9)
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model),source)
    assert exc.value.detail['field']=='collision.record.000.owner'


def test_actor_order_is_strict_even_when_slot_set_is_the_same():
    source=empty_source();put(source,0x14cc,2);put(source,0x14ce,2);put(source,0x14d0,4)
    model=bytearray(source);put(model,0x14ce,4);put(model,0x14d0,2)
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model),source)
    assert exc.value.detail['field']=='actor_order'


def test_collision_rebuild_flag_is_compared():
    source=empty_source();put(source,0x14cc,0);put(source,0x14ce,0)
    put(source,checker.FIELDS['npc_action'],0xffff)
    model=bytearray(source);put(model,checker.FIELDS['npc_flags'],0x100)
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model),source)
    assert exc.value.detail['field']=='00.physics_flags'


def test_uninitialized_dynamic_heads_are_excluded_only_before_first_rebuild():
    source=empty_source();model=bytearray(source);put(model,0xe088,0)
    counts=checker.check(Reader(model),source,dynamic_ready=False)
    assert counts['collision_elements']==258
    with pytest.raises(checker.Mismatch) as exc:checker.check(Reader(model),source)
    assert exc.value.detail['field']=='collision.dynamic.head.000'


def test_input_epochs_are_translated_without_inventing_unmapped_buttons():
    assert checker.pad_at([{'start':3,'end':5,'buttons':['RIGHT','START']}],3)==24
    assert checker.pad_at([{'start':3,'end':5,'buttons':['RIGHT','START']}],5)==0
    with pytest.raises(ValueError,match='no qualified logical mapping'):
        checker.pad_at([{'start':0,'end':1,'buttons':['A']}],0)


def test_controller_journal_checks_identity_coverage_and_consumer_agreement(tmp_path,monkeypatch):
    monkeypatch.setattr(checker,'JOURNAL_CORE','observer')
    monkeypatch.setattr(checker,'CORE','baseline')
    monkeypatch.setattr(checker,'ROM_SHA256','rom')
    phase='before selected opcode at instruction entry; video frame identifies containing retro_run'
    entries=[];frames=[]
    for serial in (1,2,3):
        frame=9+serial
        capture={'serial':serial,'sha256':str(serial),'size':131072,'registers':{'pc':0x80962e}}
        entries.append((frame,capture));frames.append({'video_frame':frame,'dropped':0,'captures':[capture]})
    checkpoint={'pc':0x80962e,'phase':phase,'frames':frames}
    reference={'frames':20,'inputs':[],'snes_checkpoints':checkpoint,'system_ram_sha256':'ram',
               'core_sha256':'baseline','rom_sha256':'rom','patches':[],
               'memory_injection_mode':'no memory patches',
               'state_sha256':'state','frame_rgb_sha256':'rgb','frame_png_sha256':'png','save_ram_sha256':'save'}
    samples=[{'kind':'main','serial':i,'video_frame':10+i,'held':0,'previous':0,'edge':0,'actor':None}
             for i in (1,2)]
    samples.append({'kind':'player','serial':2,'video_frame':12,'held':0,'previous':0,'edge':0,'actor':0x42})
    journal={'format':'snes-main-loop-controller-journal-1','dropped':0,'samples':samples,
             'duplicate_serials':[],'conflicting_serials':[],'consumer_disagreements':[]}
    path=tmp_path/'controller_journal.json'
    def write():
        raw=json.dumps(journal).encode();path.write_bytes(raw)
        observer=reference|{'core_sha256':'observer','rom_sha256':'rom','patches':[],
          'memory_injection_mode':'no memory patches','snes_controller_journal_sha256':hashlib.sha256(raw).hexdigest()}
        (tmp_path/'receipt.json').write_text(json.dumps(observer))
    write();main,players,info=checker.read_controller_journal(path,reference,entries)
    assert (len(main),len(players),info['required_transition_samples'])==(2,1,2)
    with pytest.raises(ValueError,match='independent pre-journal baseline'):
        checker.read_controller_journal(path,reference|{'core_sha256':'observer'},entries)
    journal['samples']=samples[:1];write()
    with pytest.raises(ValueError,match='missing main controller sample'):
        checker.read_controller_journal(path,reference,entries)
    journal['samples']=samples;journal['samples'][-1]['held']=0x100;write()
    with pytest.raises(ValueError,match='controller samples disagree'):
        checker.read_controller_journal(path,reference,entries)
