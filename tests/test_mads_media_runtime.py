"""Authored format/model fixtures. No original game payloads or fonts."""
from dataclasses import replace
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import wave
import zlib

import pytest
from tests.test_mads_processor import pack, literal_fab, hag, cnv, cnd, expr
from fdisbull.codec_dcl import decode_dcl, _codes, _LITERAL_RUNS, _LENGTH_RUNS
from fdisbull.codec_fab import decode_fab
from fdisbull.mads_media import (IndexedImage, AudioSample, decode_sprite_pixels,
    decode_sprites, decode_tiles, decode_background, decode_font, decode_dsr,
    decode_mask, decode_animation)
from fdisbull.mads_media_adapters import NAMES, prepare
from fdisbull.mads_resources import MadsPack
from fdisbull.mads_runtime import ConversationRuntime, evaluate, signed16
from fdisbull.media import inspect_media, extract_media


def colors(values=((63,0,0),(0,63,0)), fixed=False):
    return struct.pack('<H',len(values))+b''.join(bytes((*v,0,0,0)) for v in values)+bytes(6*(256-len(values)) if fixed else 0)


def sprite(mode=0, empty=False):
    h=bytearray(40);h[0]=mode;struct.pack_into('<H',h,38,1)
    data=b'\xfc' if empty else b'\x00\x00\x01\xff\xfd\x01\x01\x01\xfd\xff\xfc'
    encoded=data if mode==0 else literal_fab(data)
    d=struct.pack('<IIhhHH',0,len(data),-2,3,0 if empty else 2,0 if empty else 2)
    return pack([bytes(h),d,colors(),encoded])


def tiles(depth=False, empty=False):
    h=bytearray(20);struct.pack_into('<4H',h,0,0 if empty else 1,2,2,1)
    parts=[bytes(h)]
    if not empty:parts.append(struct.pack('<I',0))
    if not depth:parts += [colors(fixed=True), bytes(34)]
    return pack(parts)+(b'' if empty else literal_fab(b'\x12\x34' if depth else b'\x00\x01\x01\x00'))


def tile_map(indexes=(0,0)):
    h=bytearray(52);struct.pack_into('<8H',h,0,0,0,len(indexes),1,2,2,2*len(indexes),2)
    return pack([bytes(h),struct.pack('<'+'H'*len(indexes),*indexes)])


def dsr():
    raw=b'\x00\x80\xff';compressed=literal_fab(raw)
    return struct.pack('<HHIIII',1,11025,1,len(compressed),len(raw),20)+compressed


def font():
    d=bytearray(388);d[0:2]=bytes((2,3));d[66]=3  # character 65
    struct.pack_into('<H',d,130+2*64,386);d[386:]=b'\x6c\xe4'
    return pack([bytes(d)])


def animation(ui=False):
    h=bytearray(752);struct.pack_into('<4H',h,0,1,1,1,0);struct.pack_into('<H',h,12,4 if ui else 1)
    h[49:55]=b'OWN.SS'
    frame=struct.pack('<HBBHhh',0,0,0,1,2,3)+(b'' if ui else struct.pack('<bb',1,100))
    return pack([bytes(h),frame,bytes(20 if ui else 10)])


def dcl_literals(raw, coded=False, dictionary=4):
    bits=[]
    def write(value,n):bits.extend((value>>i)&1 for i in range(n))
    def symbol(value,table):
        (width,code)=next(k for k,v in table.items() if v==value)
        bits.extend(1-((code>>i)&1) for i in reversed(range(width)))
    for value in raw:
        write(0,1)
        if coded:symbol(value,_codes(_LITERAL_RUNS))
        else:write(value,8)
    write(1,1);symbol(15,_codes(_LENGTH_RUNS));write(255,8)
    out=bytearray((int(coded),dictionary))
    for i in range(0,len(bits),8):out.append(sum(b<<j for j,b in enumerate(bits[i:i+8])))
    return bytes(out)


@pytest.mark.parametrize('coded',[False,True])
@pytest.mark.parametrize('dictionary',[4,5,6])
@pytest.mark.parametrize('raw',[b'',b'authored',bytes(range(256))])
def test_dcl_literals_and_consumed_extent(coded,dictionary,raw):
    encoded=dcl_literals(raw,coded,dictionary)
    decoded,used=decode_dcl(encoded+b'tail',len(raw))
    assert decoded==raw and used==len(encoded)


def test_dcl_independent_published_vector_and_limits():
    encoded=bytes.fromhex('00048224258f807f')
    assert decode_dcl(encoded,13)==(b'AIAIAIAIAIAIA',8)
    for data,size in [(encoded[:-1],13),(encoded,12),(b'\x02'+encoded[1:],13),(b'\x00\x03'+encoded[2:],13)]:
        with pytest.raises(ValueError):decode_dcl(data,size)
    for limit in (True,-1,33554433):
        with pytest.raises(ValueError):decode_dcl(encoded,max_output_bytes=limit)


def test_legacy_pack_dcl_and_resolved_codec():
    raw=b'authored legacy';encoded=dcl_literals(raw)
    h=bytearray(176);h[:14]=b'MADSPACK 1.0\x1a\0';struct.pack_into('<HBBII',h,14,1,1,0,len(raw),len(encoded))
    p=MadsPack.read(bytes(h)+encoded)
    assert p.sections[0].data==raw and p.version=='1.0'
    assert p.metadata()['sections'][0]['codec']=='pkware-dcl'


@pytest.mark.parametrize('mode',[0,1])
@pytest.mark.parametrize('empty',[False,True])
def test_sprite_modes_local_colors_transparency_and_empty(mode,empty):
    images,report=decode_sprites(sprite(mode,empty))
    image=images[0];assert image.origin==(-2,3)
    if empty:
        assert image.pixels==b''
        with pytest.raises(ValueError):image.png()
    else:
        assert image.pixels==b'\0\1\1\xff'
        assert image.rgba()==b'\xff\0\0\xff\0\xff\0\xff\0\xff\0\xff\0\0\0\0'
        assert report['frames'][0]['command_tail_bytes']==0


@pytest.mark.parametrize('stream',[b'',b'\x00',b'\xfd\x03\x01\xff\xfc',b'\xff\xff\xff\xfc',b'\x00\xfe\x02'])
def test_sprite_malformed_stream_refused(stream):
    with pytest.raises(ValueError):decode_sprite_pixels(stream,2,2)


@pytest.mark.parametrize('depth',[False,True])
def test_tile_canvas_repeats_and_depth_nibbles(depth):
    raw=tiles(depth);images,report=decode_tiles(raw,depth=depth)
    assert images[0].pixels==(b'\1\2\3\4' if depth else b'\0\1\1\0')
    image,meta=decode_background(raw,tile_map(),depth=depth)
    assert (image.width,image.height)==(4,2) and meta['map_cells']==2
    assert image.pixels==(b'\1\2\1\2\3\4\3\4' if depth else b'\0\1\0\1\1\0\1\0')
    with pytest.raises(ValueError):decode_background(raw,tile_map((1,)),depth=depth)
    assert decode_tiles(tiles(depth,empty=True),depth=depth)[0]==()
    with pytest.raises(ValueError,match='Empty'):decode_background(tiles(depth,empty=True),tile_map(),depth=depth)


def test_masks_and_fonts_are_indices_without_guessed_colors():
    image,_=decode_mask(pack([b'\x80\x40']),width=2,height=2)
    assert image.pixels==b'\1\0\0\1'
    with pytest.raises(ValueError):image.png()
    glyphs,_=decode_font(font())
    assert glyphs[64].pixels==bytes((1,2,3,3,2,1))
    assert all(not g.pixels for i,g in enumerate(glyphs) if i!=64)
    with pytest.raises(ValueError):decode_mask(pack([b'\0']),width=True,height=1)


def test_dsr_unsigned_pcm_lossless_wav():
    samples,report=decode_dsr(dsr());sample=samples[0]
    assert sample.pcm==b'\0\x80\xff' and sample.rate==11025
    with wave.open(io.BytesIO(sample.wav()),'rb') as r:
        assert (r.getnchannels(),r.getsampwidth(),r.getframerate())==(1,1,11025)
        assert r.readframes(3)==sample.pcm
    with pytest.raises(ValueError):AudioSample(11025,b'x',True)


@pytest.mark.parametrize('ui',[False,True])
def test_aa_records_are_not_playback(ui):
    r=decode_animation(animation(ui))
    assert len(r['frames'])==len(r['timing'])==1 and r['sprite_names']==['OWN.SS']
    assert r['playback'] is False and r['frames'][0]['position']==[2,3]


@pytest.mark.parametrize('factory,decoder',[(sprite,decode_sprites),(tiles,decode_tiles),(dsr,decode_dsr),(font,decode_font),(animation,decode_animation)])
def test_truncated_assets_refuse(factory,decoder):
    raw=factory()
    for cut in (0,1,len(raw)//2,len(raw)-1):
        with pytest.raises(ValueError):decoder(raw[:cut])


def test_media_json_export_and_privacy(tmp_path):
    from fdisbull.cli import respond
    raw=sprite();p=tmp_path/'source';p.write_bytes(raw)
    q={'method':'media-inspect','params':{'path':str(p),'adapter':'mads-sprite'}}
    response=respond(q,default_project='/not-created.fdb');assert response['ok'],response
    assert response['result']['members'][0]['name']=='indices'
    out=tmp_path/'out';out.parent.chmod(0o700)
    receipt=extract_media(p,out,adapter='mads-sprite',member='preview-png')
    assert (out/'payload.bin').read_bytes()==decode_sprites(raw)[0][0].png()
    assert p.read_bytes()==raw and receipt['input_executed'] is False
    assert (out/'payload.bin').stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):extract_media(p,out,adapter='mads-sprite',member='indices')
    with pytest.raises(ValueError):extract_media(p,tmp_path/'budget',adapter='mads-sprite',member='indices',max_output_bytes=1)
    assert not (tmp_path/'budget').exists()
    with pytest.raises(ValueError):inspect_media(p,adapter='mads-sprite',map_path='not-read')
    with pytest.raises(ValueError):inspect_media(p,adapter='mz-envelope',expected_size=1)


def test_archive_occurrence_and_companion_hashes(tmp_path):
    p=tmp_path/'one.hag';p.write_bytes(hag([('A.TT',tiles()),('A.MM',tile_map())]))
    r,_=prepare(p,'mads-background',source_member='A.TT',map_path=p,map_member='A.MM')
    assert len(r['inputs'])==4 and r['members'][0]['derived']
    r,payload=prepare(p,'mads-hag',number=0)
    assert payload['resource']==tiles() and r['members'][0]['offset'] is not None


def test_fresh_process_codecs_and_media_do_not_import_engine(tmp_path):
    p=tmp_path/'authored';p.write_bytes(sprite())
    program="""import sys
from fdisbull.media import inspect_media, media_modules
r=inspect_media(sys.argv[1],adapter='mads-sprite')
assert r['members'] and len(media_modules()['modules']) >= 13
assert not any(x.startswith(('fdisbull.mads_processor','fdisbull.mads_runtime','fdisbull.scummvm')) for x in sys.modules)
print('independent')
"""
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    result=subprocess.run([sys.executable,'-S','-c',program,str(p)],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='independent'


def test_standalone_cli_uses_shared_api(tmp_path):
    p=tmp_path/'authored';p.write_bytes(sprite())
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    r=subprocess.run([sys.executable,'-S','-m','fdisbull.mads_media_adapters','inspect',str(p),'--adapter','mads-sprite'],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)['result']['adapter']=='mads-sprite'


def operation(code,a=0,b=0,flag=0):
    return dict(operation=code,operands=[] if code==255 else
                [dict(value=a,encoded_flag=flag)] + ([] if code==0 else [dict(value=b,encoded_flag=0)]))


@pytest.mark.parametrize('code,a,b,expected',[(0,-7,0,-7),(1,32767,1,-32768),(2,-32768,1,32767),(3,256,256,0),
    (4,-7,3,-2),(5,-7,3,-1),(4,1,0,0),(5,1,0,0),(6,-1,1,0),(7,-1,1,1),(8,2,1,1),(9,2,1,0),
    (10,1,2,1),(11,2,2,1),(12,2,-3,1),(13,0,4,1),(255,0,0,-1)])
def test_expression_contract(code,a,b,expected):
    assert evaluate(operation(code,a,b),lambda i:9)==expected


def test_operand_inversion_and_passive_reads():
    calls=[]
    assert evaluate(operation(0,3,flag=2),lambda i:calls.append(i) or 0)==1
    assert calls==[3]


def assignment(value=42,target=2):
    return b'\x09'+expr()+expr(0,value)+struct.pack('<H',target)


def model(script=None,**kw):
    return ConversationRuntime(cnv([assignment() if script is None else script]),cnd(),**kw)


def test_unbound_import_is_transactional_and_explicit():
    m=model();m.start_dialog(0);before=m.snapshot()
    with pytest.raises(ValueError,match='Unbound'):m.step()
    assert m.snapshot()==before and m.revision==1
    m=model(external_values={2:0});m.start_dialog(0)
    assert m.run()['stop_reason']=='done' and m.variables==[-1,0,42]


def test_breakpoint_resume_checkpoint_source_and_revision():
    m=model(assignment()+assignment(7),external_values={2:0},trace_capacity=1)
    m.start_dialog(0);m.breakpoint(0,0)
    assert m.run()['stop_reason']=='breakpoint'
    before=m.snapshot();rev=m.revision
    assert m.run()['stop_reason']=='done' and m.variables[2]==7
    end=m.snapshot();assert m.trace()['dropped']==1
    m.restore(before);assert m.trace()['events']==[]
    assert m.run()['stop_reason']=='breakpoint';m.run();assert m.snapshot()==end
    with pytest.raises(ValueError,match='Stale'):m.restore(before,expected_revision=rev)
    changed=deepcopy(before);changed['binding']['cnv_sha256']='0'*64
    with pytest.raises(ValueError):m.restore(changed)
    changed=deepcopy(before);changed['variables']=[0]
    with pytest.raises(ValueError):m.restore(changed)
    assert m.snapshot()==end


def test_loop_budgets_refuse_bool_and_external_jump():
    script=b'\x08'+expr()+b'\0\0'
    m=model(script,external_values={2:0});m.start_dialog(0)
    assert m.run(7)['completed_dispatches']==7
    assert m.phase=='paused'
    with pytest.raises(ValueError):m.run(True)
    m=model(b'\x08'+expr()+b'\1\0',external_values={2:0});m.start_dialog(0)
    before=m.snapshot()
    with pytest.raises(ValueError):m.step()
    assert m.snapshot()==before


def test_conflicting_old_opcodes_are_not_invented():
    m=model(b'\0'+expr(),external_values={2:0});m.start_dialog(0)
    with pytest.raises(ValueError,match='conflicting'):m.step()


def test_flag_updates_and_node_exit():
    script=b'\x01'+expr()+b'\1\0\0'+b'\x03'+expr()+b'\1\0\0'+b'\x07'+expr()+expr(0,-1)+expr(0,0)
    m=model(script,external_values={2:0});m.start_dialog(0);m.run()
    assert m.flags==[0x4000] and m.variables[:2]==[-1,0]


def test_png_decodes_with_independent_reader():
    from PIL import Image
    image=decode_sprites(sprite())[0][0]
    with Image.open(io.BytesIO(image.png())) as decoded:
        assert decoded.convert('RGBA').tobytes()==image.rgba()


def message_cnv(script):
    parts=[s.data for s in MadsPack.read(cnv([script])).sections]
    h=bytearray(parts[0]);struct.pack_into('<H',h,4,2);parts[0]=bytes(h);parts[3]=bytes(8)
    return pack(parts)


def test_weighted_message_draw_checkpoint_and_no_replay_on_refusal():
    script=b'\x04'+expr()+bytes((2,2,2,3))+struct.pack('<4H',0,1,31,32)
    m=ConversationRuntime(message_cnv(script),cnd(),external_values={2:0},random_tape=[3])
    m.start_dialog(0);before=m.snapshot();m.run();end=m.snapshot()
    assert m.messages=={'player':[1],'npc':[]} and m.speech['player']==[32]
    m.restore(before);m.run();assert m.snapshot()==end
    for tape in ([],[6]):
        m=ConversationRuntime(message_cnv(script),cnd(),external_values={2:0},random_tape=tape)
        m.start_dialog(0);before=m.snapshot()
        with pytest.raises(ValueError):m.step()
        assert m.snapshot()==before


def test_false_condition_does_not_draw_random_or_read_assignment_value():
    script=b'\x04'+expr(0,0)+bytes((1,0,1))+struct.pack('<H',0)
    m=ConversationRuntime(message_cnv(script),cnd());m.start_dialog(0);m.run()
    assert m.rng_position==0 and m.messages['player']==[]
    script=b'\x09'+expr(0,0)+expr(0,2,variable=True)+b'\2\0'
    m=model(script);m.start_dialog(0);m.run();assert m.variables[2] is None


@pytest.mark.parametrize('same', [True, False])
def test_corpus_harness_records_identical_duplicates_and_refuses_conflicts(same):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'examples/mads/validate_corpus.py'
    spec = importlib.util.spec_from_file_location('authored_mads_acceptance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from fdisbull.mads_resources import HagArchive
    from tests.test_mads_processor import hag
    archive = HagArchive.read(hag([('X.MM', b'abc'), ('X.MM', b'abc' if same else b'xyz')]))
    records = []
    if same:
        assert module.companion(archive, 'X.MM', records) == b'abc'
        assert records[0]['indices'] == [0, 1]
        assert records[0]['comparison'] == 'full-byte-equality'
        module.companion(archive, 'X.MM', records)
        assert len(records) == 1
    else:
        with pytest.raises(ValueError, match='conflicting'):
            module.companion(archive, 'X.MM', records)
        assert not records
