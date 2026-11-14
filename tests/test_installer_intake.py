"""Authored fixtures; no commercial payloads or prior-run result inheritance."""
from dataclasses import replace
import io
import json
from pathlib import Path
import stat
import struct
import zipfile
import pytest
from fdisbull.archive_layers import safe_name,zip_segments,zip_payload
from fdisbull.exepack import mz_info,unpack_exepack,rebuild_mz
from fdisbull.image_intake import disc_plan,disc_payload
from fdisbull.unpack import Limits,Provider,register_provider,inspect_path,unpack_layers
from fdisbull.installer_probe import TraceObserver,interrupt_request
from test_iso9660 import image
from test_disc import raw


def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,payload in files:z.writestr(name,payload)
    return out.getvalue()


@pytest.mark.parametrize('name',['../escape','/root','a/../../b','C:foo','a\\..\\b',
    'x\x00y','a//b','CON.txt','a/NUL','tail.','tail ','a:<b','x/./y',''])
def test_unsafe_names(name):
    with pytest.raises(ValueError):safe_name(name)


def test_concat_and_sfx_complete_accounting(tmp_path):
    segments=[archive([('ONE.BIN',b'one')]),archive([('TWO.BIN',b'two')]),archive([('THREE.BIN',b'three')])]
    data=b''.join(segments)
    assert zipfile.ZipFile(io.BytesIO(data)).namelist()==['THREE.BIN']
    report=zip_segments(data)
    assert report['entries']==3 and report['complete_byte_accounting']
    assert [s['start'] for s in report['segments']]==[0,len(segments[0]),sum(map(len,segments[:2]))]
    for s,expected in zip(report['segments'],[b'one',b'two',b'three']):
        assert zip_payload(data,s,s['entries'][0],limit=100)==expected
    p=tmp_path/'sfx.exe';p.write_bytes(b'MZ'+bytes(62)+data)
    r=inspect_path(p)
    assert r['provider']=='zip' and r['status']=='partial'
    assert r['metadata']['opaque_ranges']==[{'offset':0,'bytes':64}]


@pytest.mark.parametrize('files',[[('a',b'1'),('A',b'2')],[('../x',b'3')]])
def test_bad_zip_names_refuse(files):
    with pytest.raises(ValueError):zip_segments(archive(files))


def test_zip_symlink_refused():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        i=zipfile.ZipInfo('link');i.create_system=3;i.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(i,'outside')
    with pytest.raises(ValueError,match='nonregular'):zip_segments(out.getvalue())


def test_zip_crc_and_size_budget(tmp_path):
    data=bytearray(archive([('X',b'abcdef')]))
    r=zip_segments(bytes(data));s=r['segments'][0];e=s['entries'][0]
    with pytest.raises(ValueError,match='budget'):zip_payload(bytes(data),s,e,limit=2)
    data[e['data_offset']]^=255
    with pytest.raises(Exception):zip_payload(bytes(data),s,e,limit=100)
    p=tmp_path/'bad.zip';p.write_bytes(data);dest=tmp_path/'out'
    with pytest.raises(Exception):unpack_layers(p,dest)
    assert not dest.exists() and p.read_bytes()==data


def test_recursive_zip_provenance_and_no_overwrite(tmp_path):
    p=tmp_path/'outer.zip';p.write_bytes(archive([('inner.zip',archive([('file.txt',b'value')]))]))
    d=tmp_path/'out';r=unpack_layers(p,d,recursive=True)
    assert r['complete'] and len(r['files'])==2
    assert r['layers'][1]['parent']==0 and r['layers'][2]['parent']==1
    assert (d/'layer-0001/archive-000/file.txt').read_bytes()==b'value'
    with pytest.raises(FileExistsError):unpack_layers(p,d)
    assert (d/'layers.json').is_file()


def test_depth_and_global_limits(tmp_path):
    p=tmp_path/'a.zip';p.write_bytes(archive([('b.zip',archive([('c',b'123')]))]))
    r=unpack_layers(p,tmp_path/'depth',recursive=True,limits=Limits(max_depth=0))
    assert not r['complete'] and r['layers'][-1]['status']=='depth-limit'
    with pytest.raises(ValueError,match='global'):unpack_layers(p,tmp_path/'count',recursive=True,limits=Limits(max_files=1))
    assert not (tmp_path/'count').exists()
    with pytest.raises(ValueError):unpack_layers(p,tmp_path/'bytes',limits=Limits(max_total=1))
    assert not (tmp_path/'bytes').exists()


def test_prefix_collision_and_symlink_input(tmp_path):
    p=tmp_path/'conflict.zip';p.write_bytes(archive([('a',b'x'),('a/b',b'y')]))
    with pytest.raises(ValueError,match='prefix'):unpack_layers(p,tmp_path/'out')
    link=tmp_path/'alias.zip';link.symlink_to(p)
    with pytest.raises(ValueError,match='nonsymlink'):inspect_path(link)


def test_iso_cue_gog_single_digits_and_audio_omissions(tmp_path):
    blocks=image();blocks[25][:4]=b'TEST'
    gog=tmp_path/'GAME.GOG';gog.write_bytes(raw(blocks))
    cue=tmp_path/'GAME.INS';cue.write_text('FILE "GAME.GOG" BINARY\nTRACK 1 MODE1/2352\nINDEX 1 00:00:00\n')
    plan=disc_plan(gog)
    assert plan['descriptor']==str(cue)
    e=next(e for e in plan['filesystem']['entries'] if e['output_name']=='ONE.BIN')
    payload=disc_payload(plan,e,limit=4096)
    assert payload[:4]==b'TEST' and len(payload)==e['size']
    (tmp_path/'AUDIO.BIN').write_bytes(bytes(2352*3))
    cue.write_text(cue.read_text()+'FILE "AUDIO.BIN" BINARY\nTRACK 2 AUDIO\nINDEX 1 00:00:00\n')
    plan=disc_plan(cue)
    assert plan['omissions']==[{'track':2,'mode':'AUDIO','program_sectors':3}]
    assert not unpack_layers(cue,tmp_path/'out')['complete']
    with pytest.raises(ValueError):disc_plan(cue,track_number=2)


def test_descriptor_ambiguity_duplicate_index_and_escape(tmp_path):
    (tmp_path/'GAME.GOG').write_bytes(raw(image()))
    text='FILE "GAME.GOG" BINARY\nTRACK 1 MODE1/2352\nINDEX 1 00:00:00\n'
    for ext in ('INS','CUE'):(tmp_path/f'GAME.{ext}').write_text(text)
    with pytest.raises(ValueError,match='ambiguous'):disc_plan(tmp_path/'GAME.GOG')
    (tmp_path/'GAME.CUE').unlink()
    (tmp_path/'GAME.INS').write_text(text+'INDEX 01 00:00:00\n')
    with pytest.raises(ValueError):disc_plan(tmp_path/'GAME.INS')
    (tmp_path/'GAME.INS').write_text(text.replace('GAME.GOG','../outside.bin'))
    with pytest.raises(ValueError):disc_plan(tmp_path/'GAME.INS')


def test_exotic_and_plain_files_are_not_guessed(tmp_path):
    p=tmp_path/'disc.nrg';p.write_bytes(b''.join(image()))
    assert inspect_path(p)['status']=='unsupported'
    p=tmp_path/'unknown.dat';p.write_bytes(b'ordinary data')
    assert inspect_path(p)['status']=='leaf'


def packed_fixture(header_bytes=18):
    # 16 literal bytes followed by a 48-byte fill, decoded in reverse.
    packed=b'abcdefghijklmnop'+struct.pack('<HB',16,0xb3)+b'Z'+struct.pack('<HB',48,0xb0)
    packed+=bytes([255])*((-len(packed))%16)
    marker=b'Packed file is corrupt'
    table=struct.pack('<HH',1,2)+bytes(30)
    size=header_bytes+len(marker)+len(table)
    fields=[0,0,0,size,64,0,4]+([1] if header_bytes==18 else [])+[0x4252]
    header=struct.pack('<'+'H'*len(fields),*fields)
    total=32+len(packed)+len(header)+len(marker)+len(table)
    mz=bytearray(32)
    struct.pack_into('<14H',mz,0,0x5a4d,total%512,(total+511)//512,0,2,10,65535,0,0,0,header_bytes,len(packed)//16,28,0)
    return bytes(mz)+packed+header+marker+table


@pytest.mark.parametrize('h',[16,18])
def test_exepack_relocations_and_rebuilt_envelope(h):
    data=packed_fixture(h)
    image,report=unpack_exepack(data)
    assert image==b'abcdefghijklmnop'+b'Z'*48
    assert report['relocations']==[(2,0)] and report['runs']==2
    rebuilt=rebuild_mz(image,report);m=mz_info(rebuilt)
    assert m['relocations']==[(2,0)] and rebuilt[m['header_bytes']:]==image
    assert not report['runnable_verified']


@pytest.mark.parametrize('which',['truncate','run','relocation','signature','limit'])
def test_exepack_bad_inputs(which):
    b=bytearray(packed_fixture())
    if which=='truncate':b=b[:-1]
    elif which=='run':b[50]=0xaf
    elif which=='relocation':b[-32:-30]=b'\xff\xff'
    elif which=='signature':b[64+16:64+18]=b'NO'
    with pytest.raises(ValueError):unpack_exepack(bytes(b),max_output=16 if which=='limit' else 1024)


def event(ip,code,regs=None):
    return {'cpu_mode':'real','code_bits':16,'address':{'space':'segmented','segment':'0x1000','offset':hex(ip)},
            'execution_bytes':code.hex(),'register_changes':regs or {}}


def test_passive_probe_peek_comparison_and_return_boundary():
    base=b'\xcd\x21\x90'+bytes(4093)
    o=TraceObserver(base,0x10000)
    o.feed(event(0,b'\xcd\x21\x91',{'eax':'0x3000'}))
    assert not o.candidates # preview's third byte differs, but instruction does not
    assert o.queries[0]['completion']=='not_observed'
    o.feed(event(100,b'\x90',{'eax':'0x5'}))
    assert o.queries[0]['completion']=='not_observed'
    o.feed(event(2,b'\x90',{'eax':'0x5'}))
    assert o.queries[0]['outputs']['eax']==5
    assert o.queries[0]['completion']=='caller-successor-observed'
    assert o.candidates[0]['original_entry_established'] is False


@pytest.mark.parametrize('vector,ax,name',[(0x11,0,'bios-equipment-list'),(0x12,0,'bios-conventional-memory'),
 (0x10,0xf00,'video-state'),(0x21,0x3600,'disk-free-space'),(0x2f,0x1500,'mscdex-installation'),
 (0x33,0,'mouse-reset-and-detect'),(0x67,0x4000,'ems-service')])
def test_hardware_query_labels(vector,ax,name):
    assert interrupt_request(vector,{'eax':ax})['name']==name


def test_trusted_provider_registration_and_budget(tmp_path):
    import fdisbull.unpack as m
    p=tmp_path/'other.img';p.write_bytes(b'x')
    provider=Provider('authored_test',lambda p,l:{'entries':[{'name':'FILE','size':1}]},lambda p,m,e,l:b'x')
    try:
        register_provider(provider)
        with pytest.raises(ValueError):register_provider(provider)
        r=unpack_layers(p,tmp_path/'out',provider=provider.name)
        assert r['files'][0]['bytes']==1
    finally:m._PROVIDERS.pop(provider.name,None)


@pytest.mark.parametrize('field,value',[('max_depth',True),('max_files',0),('max_seconds',-1),('max_input',2**40)])
def test_budget_validation(field,value):
    with pytest.raises(ValueError):replace(Limits(),**{field:value})


def test_stored_nested_zip_is_not_a_concatenated_sibling(tmp_path):
    out=io.BytesIO();inner=archive([('X',b'y')])
    with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as z:z.writestr('inside.zip',inner)
    report=zip_segments(out.getvalue())
    assert len(report['segments'])==1 and report['entries']==1 and report['nested_candidates']
    p=tmp_path/'outer.zip';p.write_bytes(out.getvalue())
    assert len(unpack_layers(p,tmp_path/'out',recursive=True)['files'])==2


def test_cooked_iso_boot_descriptor_is_automatically_recognized(tmp_path):
    p=tmp_path/'disc.img';p.write_bytes(b''.join(image()))
    r=inspect_path(p)
    assert r['provider']=='disc'


def test_absolute_offset_sfx_prefix_is_retained(tmp_path):
    out=io.BytesIO(b'MZ'+bytes(62));out.seek(64)
    with zipfile.ZipFile(out,'w') as z:z.writestr('X',b'x')
    r=zip_segments(out.getvalue())
    assert not r['complete_byte_accounting']
    assert r['segments'][0]['opaque_ranges']==[{'offset':0,'bytes':64}]


def test_static_extraction_never_launches_a_process(tmp_path,monkeypatch):
    import subprocess
    def forbid(*a,**k):raise AssertionError('target/process launch during static extraction')
    monkeypatch.setattr(subprocess,'Popen',forbid)
    p=tmp_path/'input.zip';p.write_bytes(archive([('SETUP.EXE',b'MZ'+bytes(40))]))
    report=unpack_layers(p,tmp_path/'out',recursive=True)
    assert report['executes_targets'] is False
    assert report['layers'][-1]['status']=='opaque-executable'
