"""Authored media headers and bounded-read admission, without licensed assets."""
import io
import json
import struct
from pathlib import Path
import pytest
from fdisbull.format_registry import (identify_file, format_catalog, resource_profile_hints,
                                     _Reader, ReadBudgetExceeded)


def found(tmp_path, raw, name='file'):
    p=tmp_path/name;p.write_bytes(raw)
    return identify_file(p)['identification']


@pytest.mark.parametrize('raw,ident',[
    (b'FORM'+struct.pack('>I',4)+b'ILBM','iff'),
    (b'CAT '+struct.pack('>I',4)+b'XMID','iff'),
    (b'MThd'+struct.pack('>I3H',6,0,1,96),'midi'),
    (b'MADSPACK 2.0\x1a\0','madspack'),
    (b'Creative Voice File\x1a'+struct.pack('<3H',26,0x114,(~0x114+0x1234)&65535),'voc'),
])
def test_strong_header_profiles_do_not_claim_decoding(tmp_path,raw,ident):
    r=found(tmp_path,raw)
    assert r['format_id']==ident and r['header_valid']
    assert not r['full_decode'] and not r['native_runtime_tested']


@pytest.mark.parametrize('raw',[
    b'FORM'+struct.pack('>I',999)+b'ILBM',
    b'MThd'+struct.pack('>I3H',6,0,2,96),
    b'Creative Voice File\x1a'+struct.pack('<3H',26,0x114,0),
])
def test_known_headers_with_contradictory_extents_or_fields_refuse(tmp_path,raw):
    assert found(tmp_path,raw)['status']=='recognized-invalid'


def test_compound_pcx_header_and_not_just_one_magic_byte(tmp_path):
    header=bytearray(128);header[:4]=bytes([10,5,1,8])
    struct.pack_into('<4H',header,4,0,0,3,1);header[65]=1
    struct.pack_into('<H',header,66,4)
    r=found(tmp_path,header)
    assert r['format_id']=='pcx' and r['metadata']['width']==4 and r['metadata']['height']==2
    assert any(m['decoder_role']=='pixel-reader' for m in r['decoder_modules'])
    assert found(tmp_path,b'\x0a'+bytes(127))['status']=='unknown'


def uncp():
    frame=struct.pack('<I2H',776,2,1)+bytes(768)+struct.pack('<H',2)+bytes([1,2])
    return b'UNCP'+struct.pack('<I',8)+frame


def test_dinopark_picture_directory_and_raw_frame_extent(tmp_path):
    r=found(tmp_path,uncp(),'arbitrary.bin')
    assert r['format_id']=='dinopark-picture' and r['header_valid']
    assert r['metadata']['width']==2 and r['metadata']['first_frame_extent_checked']
    assert not r['full_decode']
    assert found(tmp_path,uncp()[:-1])['status']=='recognized-invalid'
    assert found(tmp_path,b'UNCP'+struct.pack('<I',100000))['status']=='recognized-invalid'


def test_dinopark_actor_envelope_is_distinct_from_flic(tmp_path):
    # One 1x1 transparent authored sprite, no sequences, exact trailing directory.
    sprite=struct.pack('<8H',1,1,0,0,0,0,1,0)+b'\0'
    raw=b'UNC2'+struct.pack('<HI2H',1,14+len(sprite),0,0)+sprite+struct.pack('<I',14)
    r=found(tmp_path,raw)
    assert r['format_id']=='dinopark-actor' and r['metadata']['sprites']==1
    assert r['header_valid'] and not r['full_decode']
    assert found(tmp_path,raw[:-1])['status']=='recognized-invalid'


def test_context_candidates_never_turn_suffix_into_recognition(tmp_path):
    folder=tmp_path/'dinopark';folder.mkdir();p=folder/'noise.ABT';p.write_bytes(b'context only')
    assert identify_file(p)['identification']['status']=='unknown'
    hints=resource_profile_hints(p,format_catalog())
    assert hints and all(h['qualification']=='context-candidate-only' for h in hints)
    # Keep the negative context independent of caller-selected test workspace names.
    assert not resource_profile_hints(Path('/unrelated/inputs/noise.ABT'),format_catalog())
    assert identify_file(folder/'noise.ABT')['identification']['full_decode'] is False


def test_catalog_contains_context_candidates_without_unsupported_decoder_claims():
    c=format_catalog();context=[r for r in c['formats'] if r.get('detection')=='consumer-context-only']
    assert len(context)==97 and all(not r['signatures'] for r in context)
    assert all(r['limitations'] and r['context_hints']['filename_patterns'] for r in context)
    assert c['contains_file_payloads'] is False


def test_budget_gate_precedes_source_read_and_retains_accounting():
    class Counted(io.BytesIO):
        def read(self,n=-1):
            self.calls=getattr(self,'calls',0)+1
            return super().read(n)
    stream=Counted(b'abcdefgh');r=_Reader(stream,8,max_read_bytes=4)
    assert r.read(0,4)==b'abcd'
    with pytest.raises(ReadBudgetExceeded) as error:r.read(4,1)
    assert stream.calls==1 and error.value.bytes_read==4 and len(error.value.sampled_regions)==1


def test_identification_budget_error_and_opened_descriptor_identity(tmp_path):
    p=tmp_path/'input';p.write_bytes(b'ordinary data')
    with pytest.raises(ReadBudgetExceeded) as e:identify_file(p,max_read_bytes=1)
    assert e.value.bytes_read==0 and e.value.sampled_regions==[]
    r=identify_file(p);st=p.stat();opened=r['source']['opened_identity']
    assert (opened['device'],opened['inode'])==(st.st_dev,st.st_ino)
    assert p.read_bytes()==b'ordinary data'


@pytest.mark.parametrize('magic',[0xaf11,0xaf12])
def test_standard_flic_rate_cannot_alias_compact_frame_magic(tmp_path,magic):
    header=bytearray(128);struct.pack_into('<I5H',header,0,144,magic,1,4,4,8)
    struct.pack_into('<I',header,16,0xf1fa)
    frame=struct.pack('<IHH8s',16,0xf1fa,0,bytes(8))
    r=found(tmp_path,header+frame)
    assert r['format_id']=='flic' and r['header_valid']
    assert r['metadata']['depth']==8


def test_custom_context_hint_without_optional_limitations_is_inert(tmp_path):
    c=format_catalog();c['formats'].append(dict(format_id='custom',revision=1,name='Custom',category='resource-profile',context_hints=dict(filename_patterns=['*.foo'],game_markers=[])))
    hints=resource_profile_hints(tmp_path/'x.foo',c)
    assert hints[-1]['format_id']=='custom' and hints[-1]['recovery']==[]
