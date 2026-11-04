"""Typed engine scene reads retain byte semantics, stop identity and provenance."""
import pytest

from fdisbull.scene_values import ObservationReads, before_refs, comparison, evaluate_comparison
from fdisbull.scenes import video_signature
from fdisbull.debug_script import validate_script


class Arena:
    def __init__(self):
        self.data=bytearray(bytes.fromhex('ff800000'))
        self.revision=1
        self.calls=0
    def read_variable(self,offset,*,width=1,signed=False,endian='little'):
        self.calls+=1
        raw=bytes(self.data[offset:offset+width])
        return {'run':'gob-one','state_revision':self.revision,'hex':raw.hex(),
                'value':int.from_bytes(raw,endian,signed=signed)}


def test_typed_aliases_and_before_share_observation_identity():
    arena=Arena();reads=ObservationReads(arena)
    signed={'engine_variable':{'offset':0,'type':'i8'}}
    rule={'left':signed,'op':'eq','right':-1}
    comparison(rule)
    assert evaluate_comparison(rule,reads,None)==(True,-1,-1)
    assert evaluate_comparison(rule,reads,None)[0] and arena.calls==1
    assert reads.engine_variable_scalar({'offset':0,'type':'u16'})==33023
    future={'left':signed,'op':'eq','right':{'before':signed}}
    comparison(future,allow_before=True)
    baseline=reads.freeze(list(before_refs(future)),{'run':'gob-one'})
    arena.data[0]=0;arena.revision+=1
    assert evaluate_comparison(future,ObservationReads(arena),baseline)==(False,0,-1)


def test_changed_revision_and_missing_fields_remain_unavailable():
    arena=Arena();reads=ObservationReads(arena)
    assert reads.engine_variable_scalar({'offset':0,'type':'u8'})==255
    arena.revision+=1
    with pytest.raises(ValueError,match='changed during'):
        reads.engine_variable_scalar({'offset':1,'type':'u8'})
    with pytest.raises(ValueError):reads.engine_variable_scalar({'offset':10,'type':'i32'})


@pytest.mark.parametrize('ref',[{'offset':True,'type':'i8'}, {'offset':-1,'type':'i8'},
    {'offset':0,'type':[]}, {'offset':0,'type':'u64'}, {'offset':0,'type':'u8','endian':'middle'}])
def test_invalid_typed_engine_reference_refuses(ref):
    with pytest.raises(ValueError):comparison({'left':{'engine_variable':ref},'op':'eq','right':0})


def test_gob_scene_binds_runtime_and_loaded_source_but_allows_fresh_generation():
    meta=dict(width=320,height=200,source_bpp=24,double_width=False,double_height=False,
              backend='scummvm-gob',resource_manifest_sha256='a'*64,resource_layers_sha256='b'*64,
              script='EMAM1017.TOT',script_generation=1,script_loaded_sha256='c'*64,
              script_decompressed_sha256='d'*64,scummvm_sha256='e'*64)
    assert video_signature(meta)==video_signature(dict(meta,script_generation=2))
    assert video_signature(meta)!=video_signature(dict(meta,scummvm_sha256='f'*64))
    assert video_signature(meta)!=video_signature(dict(meta,script_loaded_sha256='f'*64))
    with pytest.raises(ValueError,match='identities'):
        video_signature({k:v for k,v in meta.items() if k!='script_loaded_sha256'})


def test_gob_saved_script_validates_its_actual_api_before_execution():
    doc={'format':'fdisbull-script-1','backend':'scummvm-gob','steps':[
        {'op':'run','max_instructions':20,'guest_ms':100,'expect':'budget'},
        {'op':'engine-read-variable','offset':12637,'width':1,'signed':True}]}
    assert validate_script(doc)==doc['steps']
