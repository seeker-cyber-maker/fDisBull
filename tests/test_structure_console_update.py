"""Authored fixtures for console discovery; no commercial ROM bytes."""
import io
import json
import zipfile
from hashlib import sha256
from pathlib import Path
import pytest

from fdisbull.structure_65816 import DecodeState,advance_state,probe as snes_probe
from fdisbull.structure_console import profiles,inspect_console
from fdisbull.structure_discovery import scan_directory,scan_to_directory
from fdisbull.structure_handoffs import inspect_handoffs
from fdisbull.structure_patterns import match_graph,RULES
from fdisbull.structure_events import SELECTOR_RULE


def nes(mapper=0,size=32768):
    data=bytearray(b'NES\x1a'+bytes([size//16384,0,(mapper&15)<<4,mapper&0xf0])+bytes(8)+bytes([0xea])*size)
    for k in range(size//16384):
        base=16+k*16384
        data[base:base+10]=bytes.fromhex('a5102901f00160851060')
        for v in (0x3ffa,0x3ffc,0x3ffe):data[base+v:base+v+2]=b'\x00\x80'
    return bytes(data)


def snes(code=b'\xea\x60',copier=0):
    d=bytearray(32768)
    d[:len(code)]=code
    at=0x7fc0;d[at:at+21]=b'AUTHORED CONSOLE TEST '[:21]
    d[at+21]=0x20;d[at+22]=0;d[at+23]=5
    d[at+28:at+32]=bytes.fromhex('cbed3412')
    d[at+0x3c:at+0x3e]=bytes.fromhex('0080')
    return bytes(copier)+d


def walk(code, state=None):
    return snes_probe(bytes(code),[{'cpu_start':0x8000,'file_start':0,'size':len(code)}],
                      [{'cpu_address':0x8000,'state':state or {'e':False,'m8':False,'x8':False,'dbr':0,'dp':0}}],
                      mapping_id='authored',budget=400)


def matches(r,p):
    return [m for m in match_graph(r['nodes'],r['edges'],rules=RULES+(SELECTOR_RULE,))['matches'] if m['pattern']==p]


@pytest.mark.parametrize('mapper,size,expected',[(0,16384,1),(0,32768,1),(66,65536,2),(227,524288,8)])
def test_content_routing(mapper,size,expected):
    h,views,issues=profiles(nes(mapper,size))
    assert h['platform']=='NES' and len(views)==expected
    assert all(v['mapper']==mapper for v in views)
    if mapper==227:assert any('budget' in x for x in issues)


@pytest.mark.parametrize('copier',[0,512])
def test_snes_header_and_reset(copier):
    h,v,issues=profiles(snes(copier=copier))
    assert h['metadata']['copier_header_size']==copier
    assert v[0]['entries'][0]['state']['e'] is True
    assert len(v[0]['windows'])==2


def test_unknown_mapper_is_frontier():
    r=inspect_console(nes(4))
    assert not r['views'] and r['diagnostics']


def test_special_chip_not_assumed_ordinary_lorom():
    d=bytearray(snes());d[0x7fd6]=0x13
    h,v,issues=profiles(bytes(d))
    assert not v and 'coprocessor' in issues[0]


@pytest.mark.parametrize('m8,x8,size',[(True,True,2),(True,False,2),(False,True,3),(False,False,3)])
def test_accumulator_width(m8,x8,size):
    raw=b'\xa9\x34'+(b'\x12' if not m8 else b'')+b'\x60'
    r=walk(raw,{'e':False,'m8':m8,'x8':x8})
    assert r['decoded_candidate_instructions']==2 and not r['issues']


@pytest.mark.parametrize('m8,x8',[(True,True),(True,False),(False,True),(False,False)])
def test_index_width(m8,x8):
    raw=b'\xa2\x34'+(b'\x12' if not x8 else b'')+b'\x60'
    assert walk(raw,{'e':False,'m8':m8,'x8':x8})['decoded_candidate_instructions']==2


def test_reset_xce_rep_state():
    s=DecodeState.parse({'e':True})
    s=advance_state(s,b'\x18','clc');s=advance_state(s,b'\xfb','xce')
    assert s.e is False and s.c is True
    s=advance_state(s,b'\xc2\x30','rep')
    assert s.m8 is False and s.x8 is False
    s=advance_state(s,b'\xe2\x20','sep')
    assert s.m8 is True and s.x8 is False


def test_rep_in_emulation_cannot_longify():
    s=advance_state(DecodeState.parse({'e':True}),b'\xc2\x30','rep')
    assert s.m8 is True and s.x8 is True


def test_unknown_carry_xce_is_not_guessed():
    s=advance_state(DecodeState(e=False,m8=False,x8=False),b'\xfb','xce')
    assert s.e is None and s.m8 is None and s.x8 is None


def test_unknown_width_stops_before_immediate():
    r=walk(b'\xa9\x01\x60',{'e':False})
    assert r['decoded_candidate_instructions']==0
    assert r['issues'][0]['reason']=='unknown immediate width'


def test_status_is_not_presumed_across_call():
    r=walk(bytes.fromhex('200780a934126060'))
    assert any(x['reason']=='unknown immediate width' and x['address']==0x8003 for x in r['issues'])
    assert r['decoded_candidate_instructions']==2


def test_sep_reestablishes_width_after_opaque_call():
    r=walk(bytes.fromhex('200880e220a9016060'))
    assert r['decoded_candidate_instructions']==5
    assert not any(x['reason']=='unknown immediate width' for x in r['issues'])


def test_plp_invalidates_width_not_e():
    r=walk(bytes.fromhex('28a90160'))
    assert any(x['reason']=='unknown immediate width' for x in r['issues'])


def test_snes_mask_reuses_shared_rule():
    r=walk(bytes.fromhex('ad1000290400f0016060'))
    assert len(matches(r,'loaded-mask-controls-branch'))==1
    assert matches(r,'loaded-mask-controls-branch')[0]['bindings']['read']['storage']['width']==16


def test_snes_selector_two_arms():
    r=walk(bytes.fromhex('c90300f0048d1000608d120060'))
    found=matches(r,'selector-controls-operation')
    assert len(found)==2
    assert {x['bindings']['effect']['selector_relation'] for x in found}=={'equal','not_equal'}


def test_wait_has_explicit_frontier():
    r=walk(b'\xcb\x60')
    assert r['decoded_candidate_instructions']==1 and r['accesses'][0]['kind']=='wait'
    assert inspect_handoffs(r['accesses'])['findings'][0]['pattern']=='wait-continuation'


def test_indirect_jump_not_guessed():
    r=walk(bytes.fromhex('6c0080'))
    assert r['issues'][0]['reason']=='indirect transfer unresolved'


def test_direct_page_unknown_does_not_make_alias():
    r=walk(bytes.fromhex('a510851060'),{'e':False,'m8':True,'x8':True})
    assert r['accesses']==[]


def test_ram_mirror_identity():
    r=walk(bytes.fromhex('ad10008f10007e60'))
    findings=inspect_handoffs(r['accesses'])['findings']
    assert len(findings)==1 and findings[0]['pattern']=='storage-producer-consumer'


def test_handoffs_do_not_cross_width_or_scope():
    r=walk(bytes.fromhex('ad10008d100060'))
    a,b=r['accesses']; b=dict(b,storage={**b['storage'],'width':8})
    assert inspect_handoffs([a,b])['findings']==[]
    b['storage']={**b['storage'],'width':16,'scope':'foreign'}
    with pytest.raises(ValueError):inspect_handoffs([a,b])


def test_device_is_not_plain_variable():
    r=walk(bytes.fromhex('ad16408d164060'))
    findings=inspect_handoffs(r['accesses'])['findings']
    assert len(findings)==1 and findings[0]['pattern']=='device-service-boundary'


@pytest.mark.parametrize('state',[{'e':True,'m8':False},{'m8':1},{'dbr':256},{'dp':-1},{'wat':True}])
def test_invalid_state_rejected(state):
    with pytest.raises(ValueError):DecodeState.parse(state)


def test_mapping_identity_affects_ids():
    data=bytes.fromhex('c901f0016060');w=[{'cpu_start':0x8000,'file_start':0,'size':len(data)}]
    e=[{'cpu_address':0x8000,'state':{'e':True}}]
    a=snes_probe(data,w,e,mapping_id='one');b=snes_probe(data,w,e,mapping_id='two')
    assert a['nodes'][0]['id']!=b['nodes'][0]['id']


def test_file_and_zip_same_finding_ids(tmp_path):
    p=tmp_path/'arbitrary.bin';p.write_bytes(nes())
    z=tmp_path/'arbitrary.zip'
    with zipfile.ZipFile(z,'w') as f:f.writestr('unknown-title.bin',nes())
    a=scan_directory(p,max_instructions=100);b=scan_directory(z,max_instructions=100)
    assert a['pattern_counts']==b['pattern_counts']
    assert [x['id'] for x in a['findings']]==[x['id'] for x in b['findings']]
    assert b['inputs'][0]['container_sha256']==sha256(z.read_bytes()).hexdigest()


@pytest.mark.parametrize('name',['../bad.nes','/bad.nes','C:bad.nes','foo\\bad.nes'])
def test_zip_paths_refused(tmp_path,name):
    z=tmp_path/'bad.zip'
    with zipfile.ZipFile(z,'w') as f:f.writestr(name,nes())
    with pytest.raises(ValueError):scan_directory(z)


def test_zip_duplicate_refused(tmp_path):
    z=tmp_path/'bad.zip'
    with zipfile.ZipFile(z,'w') as f:
        f.writestr('x.nes',nes())
        with pytest.warns(UserWarning,match='Duplicate'):f.writestr('x.nes',nes())
    with pytest.raises(ValueError):scan_directory(z)


def test_zip_expanded_budget(tmp_path):
    z=tmp_path/'small.zip'
    with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as f:f.writestr('x.nes',nes())
    r=scan_directory(z,max_total_bytes=1000)
    assert not r['inputs'] and r['skipped']


def test_profile_hash_mismatch(tmp_path):
    p=tmp_path/'x.nes';p.write_bytes(nes());profile=tmp_path/'profile.json'
    profile.write_text(json.dumps({'sources':{'0'*64:{'source_sha256':'0'*64,'views':[]}}}))
    with pytest.raises(ValueError):scan_directory(p,console_profile=profile)


def test_deterministic_scan_and_private_output(tmp_path):
    p=tmp_path/'x.nes';p.write_bytes(nes())
    a=scan_directory(p);b=scan_directory(p)
    assert a==b
    out=tmp_path/'result';result=scan_to_directory(p,out)
    assert Path(result['report']).exists() and result['execution_authorized'] is False
    with pytest.raises(ValueError):scan_to_directory(p,out)


def test_combined_value_rule_crosses_six_connected_roles():
    from fdisbull.structure_6502 import probe
    code=bytes.fromhex('a5100511c910f0016060')
    r=probe(code,[{'cpu_start':0x8000,'file_start':0,'size':len(code)}],[0x8000],mapping_id='authored',mapper=0)
    found=matches(r,'combined-values-control-operation')
    assert len(found)==2
    assert all(len(x['bindings'])==6 for x in found)
    assert found[0]['bindings']['selector']['value']==16
    assert found[0]['bindings']['combine']['operation']=='ora'


def test_lo_rom_last_banks_keep_high_alias_without_wram_alias():
    d=bytearray(snes());d.extend(bytes(4*1024*1024-len(d)))
    h,views,_=profiles(bytes(d))
    windows=views[0]['windows']
    assert any(w['cpu_start']==0xff8000 for w in windows)
    assert not any(w['cpu_start'] in (0x7e8000,0x7f8000) for w in windows)
