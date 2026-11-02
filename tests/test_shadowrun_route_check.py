"""Negative tests for captured route comparison evidence bindings."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH=Path(__file__).resolve().parents[1]/'scripts/check_shadowrun_opening_route.py'
spec=importlib.util.spec_from_file_location('shadowrun_route_review',PATH)
route=importlib.util.module_from_spec(spec);spec.loader.exec_module(route)


def receipt(trace):
    return {'system':'nes','core_sha256':route.NES_CORE_SHA,'rom_sha256':'a'*64,
            'patches':[],'patch_trace':[],'memory_injection_mode':'no memory patches',
            'frames':len(trace['frames']),'ram_trace_sha256':route.digest(json.dumps(trace).encode())}


def frame(i,tick,seq=0):
    state=bytearray(24);state[22]=seq;state[23]=tick
    return {'frame':i,'input_mask':0,'raw':{'state':state.hex()}}


def test_target_receipt_refuses_wrong_rom_and_hidden_patches():
    r=receipt({'frames':[frame(0,1)]})
    with pytest.raises(ValueError):route.checked_receipt(r,system='nes',core_sha=route.NES_CORE_SHA,rom_sha='b'*64)
    for key,value in [('patches',[{'frame':7}]),('patch_trace',[{'frame':7}]),('memory_injection_mode','assisted')]:
        changed=dict(r);changed[key]=value
        with pytest.raises(ValueError):route.checked_receipt(changed,system='nes',core_sha=route.NES_CORE_SHA,rom_sha='a'*64)


def test_trace_binding_rejects_tamper_duplicate_and_missing_frames():
    trace={'frames':[frame(0,1),frame(1,2)]};r=receipt(trace);raw=json.dumps(trace).encode()
    assert len(route.indexed_frames(raw,r))==2
    with pytest.raises(ValueError,match='differs'):route.indexed_frames(raw+b' ',r)
    for rows in ([frame(0,1),frame(0,2)],[frame(0,1),frame(2,2)]):
        altered={'frames':rows};rr=receipt(altered)
        with pytest.raises(ValueError,match='frame'):route.indexed_frames(json.dumps(altered).encode(),rr)
    r['frames']=3
    with pytest.raises(ValueError,match='Incomplete'):route.indexed_frames(raw,r)


def test_source_capture_rejects_changed_and_missing_ram(tmp_path):
    path=tmp_path/'native'/'scene-000001'/'ram.bin';path.parent.mkdir(parents=True);path.write_bytes(b'captured')
    key='native/scene-000001/ram.bin';capture={'files':{key:{'size':8,'sha256':route.digest(b'captured')}}}
    assert route.captured_file(tmp_path,capture,key)==b'captured'
    path.write_bytes(b'changed!')
    with pytest.raises(ValueError,match='Changed'):route.captured_file(tmp_path,capture,key)
    path.unlink()
    with pytest.raises(ValueError,match='Missing'):route.captured_file(tmp_path,capture,key)


def test_completed_tick_selection_rejects_gaps_and_torn_states():
    frames={0:frame(0,254),1:frame(1,254),2:frame(2,255,1),3:frame(3,255),4:frame(4,0)}
    assert route.select_completed(frames,0,3)==[0,3,4]
    with pytest.raises(ValueError,match='not observed'):route.select_completed({0:frame(0,1),1:frame(1,3)},0,2)
    with pytest.raises(ValueError,match='Insufficient'):route.select_completed({0:frame(0,1),1:frame(1,2,1)},0,2)


def test_receipt_schedule_is_validated_and_merged():
    r={'frames':10,'inputs':[{'start':2,'end':5,'buttons':['UP']},
                            {'start':3,'end':4,'buttons':['RIGHT']}],
       'input_map':{'UP':4,'RIGHT':7}}
    assert route.scheduled_mask(r,1)==0
    assert route.scheduled_mask(r,2)==16
    assert route.scheduled_mask(r,3)==144
    r['inputs'][0]['end']=11
    with pytest.raises(ValueError,match='schedule'):route.scheduled_mask(r,2)
