"""Public decoder routes and private PNG/WAV exports from authored resources."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import wave
import pytest
from PIL import Image
from fdisbull.cli import main, respond
from fdisbull.dinopark_media import decode_media, inspect_dinopark
from fdisbull.format_registry import format_catalog, identify_file
from fdisbull.intake import intake_inventory


def authored_pic():
    palette=bytes([0,0,0,63,0,0])+bytes(762)
    frame=struct.pack('<I2H',776,2,1)+palette+struct.pack('<H',2)+bytes([0,1])
    return b'UNCP'+struct.pack('<I',8)+frame


def authored_act():
    commands=b'\x01\x41\0';colors=b'\x01'
    sprite=struct.pack('<8H',2,1,1,1,0,0,len(commands),len(colors))+commands+colors
    return b'UNC2'+struct.pack('<HI2H',1,14+len(sprite),0,0)+sprite+struct.pack('<I',14)


def authored_abt():
    # Initial0x80, repeat2 then native seven-bit literal0x81<<1 =0x02.
    return struct.pack('<HHB',4,22050,8)+b'xyz'+bytes([128,0x42,0x81])


def resource(tmp_path,name,raw):
    p=tmp_path/name;p.write_bytes(raw);return p


def private_parent(tmp_path):
    p=tmp_path/'exports';p.mkdir(mode=0o700);return p


def test_picture_inspection_and_export_preserve_native_indices_and_policy(tmp_path):
    raw=authored_pic();p=resource(tmp_path,'picture',raw)
    report=inspect_dinopark(p,adapter='dinopark-pic')
    assert report['full_indexed_decode'] and not report['native_runtime_tested']
    assert 'palette6_sha256' in report['frames'][0] and 'palette6' not in report['frames'][0]
    result=decode_media(p,private_parent(tmp_path)/'pic',adapter='dinopark-pic',palette_policy='replicate6')
    with Image.open(Path(result['output'])/'image.png') as image:
        assert image.mode=='P' and image.tobytes()==bytes([0,1])
        assert image.convert('RGB').tobytes()==bytes([0,0,0,255,0,0])
    assert result['selection']['palette_policy']=='replicate6'
    assert not result['selection']['host_RGB_display_qualified']
    assert p.read_bytes()==raw


def test_actor_without_palette_has_exact_diagnostic_planes(tmp_path):
    p=resource(tmp_path,'actor',authored_act());out=private_parent(tmp_path)/'act'
    result=decode_media(p,out,adapter='dinopark-act')
    assert not (out/'image.png').exists()
    with Image.open(out/'indices.png') as im:assert im.tobytes()==bytes([0,1])
    with Image.open(out/'opacity.png') as im:assert im.tobytes()==bytes([0,255])
    assert 'diagnostic' in result['selection']['presentation']


def test_actor_external_palette_binds_both_source_identities_and_alpha(tmp_path):
    p=resource(tmp_path,'actor',authored_act());pal=resource(tmp_path,'palette',authored_pic())
    result=decode_media(p,private_parent(tmp_path)/'act',adapter='dinopark-act',palette_path=pal)
    with Image.open(Path(result['output'])/'image.png') as im:
        assert im.mode=='RGBA' and im.tobytes()==bytes([0,0,0,0,252,0,0,255])
    assert result['selection']['palette_source']['sha256']==hashlib.sha256(pal.read_bytes()).hexdigest()
    assert result['selection']['raw_palette6_sha256']


def test_abt_wav_has_explicit_authored_timing_and_exact_sample_sequence(tmp_path):
    raw=authored_abt();p=resource(tmp_path,'sample',raw)
    result=decode_media(p,private_parent(tmp_path)/'abt',adapter='dinopark-abt',sample_rate=8000,channels=1)
    with wave.open(str(Path(result['output'])/'samples.wav'),'rb') as reader:
        assert (reader.getnchannels(),reader.getsampwidth(),reader.getframerate())==(1,1,8000)
        assert reader.readframes(4)==bytes([128,128,128,2])
    assert result['decoded']['rate_field']==22050 and result['decoded']['rate_hz'] is None
    assert result['selection']['timing_source']=='explicit-caller-adapter'
    assert not result['native_runtime_tested'] and p.read_bytes()==raw


@pytest.mark.parametrize('options',[
    {},{'sample_rate':8000},{'sample_rate':8000,'channels':True},
    {'sample_rate':8000,'channels':1,'index':0},
    {'sample_rate':8000,'channels':1,'palette_policy':'replicate6'},
])
def test_abt_refuses_guessed_or_contradictory_export_adapters(tmp_path,options):
    p=resource(tmp_path,'sample',authored_abt());out=private_parent(tmp_path)/'abt'
    with pytest.raises(ValueError):decode_media(p,out,adapter='dinopark-abt',**options)
    assert not out.exists()


def test_output_budget_includes_manifest_and_refuses_before_directory(tmp_path):
    p=resource(tmp_path,'picture',authored_pic());out=private_parent(tmp_path)/'pic'
    with pytest.raises(ValueError,match='budget'):decode_media(p,out,adapter='dinopark-pic',max_output_bytes=1)
    assert not out.exists()


def test_existing_git_or_linked_outputs_are_refused(tmp_path):
    p=resource(tmp_path,'picture',authored_pic());parent=private_parent(tmp_path);out=parent/'existing';out.mkdir()
    with pytest.raises(FileExistsError):decode_media(p,out,adapter='dinopark-pic')
    (parent/'.git').mkdir()
    with pytest.raises(ValueError):decode_media(p,parent/'new',adapter='dinopark-pic')
    assert not (parent/'new').exists()


def test_catalog_routes_strong_headers_and_context_only_abt_to_real_modules(tmp_path):
    root=tmp_path/'dinopark';root.mkdir()
    act=resource(root,'sprite.ACT',authored_act());pic=resource(root,'room.PIC',authored_pic());abt=resource(root,'sample.ABT',authored_abt())
    catalog=tmp_path/'catalog.sqlite';c=format_catalog(catalog_path=catalog)
    assert {'dinopark-act','dinopark-pic','dinopark-abt'} <= {m['module_id'] for m in c['modules']}
    assert any(m['module_id']=='dinopark-act' and m['decoder_role']=='pixel-reader' for m in identify_file(act,catalog_path=catalog)['identification']['decoder_modules'])
    report=intake_inventory([root],catalog_path=catalog)
    assert report['complete'] and report['summary']['files_reported']==3
    assert any(r['reason']=='context-decoder-validation-needed' for r in report['recovery_queue'])
    assert any(r['reason']=='media-validation-needed' and r['format_id']=='dinopark-picture' for r in report['recovery_queue'])
    assert not any(r['reason']=='media-decoder-recovery' for r in report['recovery_queue'])
    sample=next(f for f in report['files'] if f['member']=='sample.ABT')
    assert sample['identification']['status']=='unknown'
    assert any(m['module_id']=='dinopark-abt' for h in sample['candidate_profiles'] for m in h['decoder_modules'])
    assert b'xyz' not in catalog.read_bytes()


def test_projectless_cli_inspection_and_export(tmp_path,capsys):
    p=resource(tmp_path,'picture',authored_pic());out=private_parent(tmp_path)/'pic'
    assert main(['media-inspect',str(p),'--adapter','dinopark-pic'])==0
    assert json.loads(capsys.readouterr().out)['result']['full_indexed_decode']
    assert main(['media-decode',str(p),str(out),'--adapter','dinopark-pic'])==0
    r=json.loads(capsys.readouterr().out);assert r['ok'] and r['result']['outputs'][0]['path']=='image.png'
    assert respond({'method':'media-inspect','params':dict(path=str(p),adapter='dinopark-pic')},default_project='/nonexistent.fdb')['ok']
