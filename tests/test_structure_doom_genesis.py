"""Authored format and CPU fixtures; no original game payloads."""
import struct
from hashlib import sha256
import pytest
from fdisbull.structure_68000 import probe
from fdisbull.structure_console import inspect_console,profiles
from fdisbull.structure_patterns import match_graph,RULES
from fdisbull.structure_events import SELECTOR_RULE
from fdisbull.structure_wad import inspect_wad,ORDER
from fdisbull.structure_discovery import scan_directory
from fdisbull.structure_native import embedded_le_views,native_views,le_source_views
from test_le_loader import le_file


def walk(hexcode, **kw):
    data=bytes.fromhex(hexcode)
    return probe(data,[{'cpu_start':0x200,'file_start':0,'size':len(data)}],[0x200],mapping_id='authored',budget=100,**kw)


def matches(r,name):
    return [x for x in match_graph(r['nodes'],r['edges'],rules=RULES+(SELECTOR_RULE,))['matches'] if x['pattern']==name]


def genesis(code):
    d=bytearray(4096);d[0x100:0x110]=b'SEGA MEGA DRIVE '
    struct.pack_into('>II',d,0,0xffff00,0x200)
    struct.pack_into('>IIII',d,0x1a0,0,len(d)-1,0xff0000,0xffffff)
    d[0x200:0x200+len(code)]=code
    struct.pack_into('>H',d,0x18e,sum(struct.unpack('>'+str((len(d)-512)//2)+'H',d[512:]))&65535)
    return bytes(d)


def wad(lumps):
    d=bytearray(12);directory=[]
    for name,body in lumps:
        directory.append((len(d),len(body),name.encode().ljust(8,b'\0')));d+=body
    offset=len(d)
    for row in directory:d+=struct.pack('<ii8s',*row)
    struct.pack_into('<4sii',d,0,b'PWAD',len(directory),offset)
    return bytes(d)


def map_lumps():
    p={
        'THINGS':struct.pack('<5h',-20,30,90,1,7),
        'LINEDEFS':struct.pack('<7H',0,1,4,7,9,0,1),
        'SIDEDEFS':b''.join(struct.pack('<hh8s8s8sH',0,0,b'A',b'B',b'C',s) for s in (0,1)),
        'VERTEXES':struct.pack('<4h',-40,0,40,0),
        'SEGS':struct.pack('<6H',0,1,0,0,0,0),
        'SSECTORS':struct.pack('<2H',1,0), 'NODES':b'',
        'SECTORS':b''.join(struct.pack('<hh8s8shhh',0,128,b'F',b'C',160,0,t) for t in (0,9)),
        'REJECT':b'\0','BLOCKMAP':b'\0'*8}
    return [('MAP01',b'')]+[(n,p[n]) for n in ORDER]


def test_genesis_header_routing():
    d=genesis(bytes.fromhex('4e75'));h,v,n=profiles(d)
    assert h['platform']=='Sega Genesis / Mega Drive' and len(v)==1
    assert v[0]['entries']==[0x200]
    assert inspect_console(d)['views'][0]['coverage']['decoded_candidate_instructions']==1


def test_genesis_truncated_refuses_code():
    d=genesis(b'\x4e\x75')[:-1]
    assert not inspect_console(d)['views']


def test_byteswapped_sega_not_snes():
    d=bytearray(genesis(b'\x4e\x75'));d[0x100:0x104]=b'ESAG'
    h,v,notes=profiles(bytes(d));assert h['platform']=='Sega Genesis / Mega Drive' and not v


def test_32x_not_assumed_68000_only():
    d=bytearray(genesis(b'\x4e\x75'));d[0x100:0x110]=b'SEGA 32X        '
    assert not inspect_console(bytes(d))['views']


@pytest.mark.parametrize('gate',['6702','6602'])
def test_loaded_mask_uses_adjacent_value_and_flags(gate):
    r=walk('103900ff0000 02000004 '+gate+' 4e71 4e75')
    mm=matches(r,'loaded-mask-controls-branch');assert len(mm)==1
    assert mm[0]['bindings']['mask']['value']==4
    assert mm[0]['bindings']['read']['expression']['absolute']==0xff0000


def test_clobbered_flags_do_not_match():
    assert not matches(walk('103900ff0000 02000004 4a01 6702 4e71 4e75'),'loaded-mask-controls-branch')


def test_different_register_no_value_edge():
    assert not matches(walk('103900ff0000 02010004 6702 4e71 4e75'),'loaded-mask-controls-branch')


def test_different_operand_width_no_value_edge():
    assert not matches(walk('103900ff0000 02400004 6702 4e71 4e75'),'loaded-mask-controls-branch')


@pytest.mark.parametrize('mask',['0000','00ff'])
def test_zero_and_all_bits_are_not_selective_masks(mask):
    assert not matches(walk('103900ff0000 0200'+mask+' 6702 4e71 4e75'),'loaded-mask-controls-branch')


def test_absolute_memory_bit_test_and_modulo():
    r=walk('0839000b00ff0010 6702 4e71 4e75')
    mm=matches(r,'loaded-mask-controls-branch');assert len(mm)==1 and mm[0]['bindings']['mask']['value']==8


@pytest.mark.parametrize('branch,write_equality',[('660a',True),('670a',False)])
def test_selector_arm_polarity(branch,write_equality):
    r=walk('0c000001 '+branch+' 13fc000200ff0010 4e75 4e75')
    found=matches(r,'selector-controls-operation');assert len(found)==2
    effect=next(x['bindings']['effect'] for x in found if x['bindings']['effect']['kind']=='memory_write')
    assert effect['equality'] is write_equality


def test_indirect_jump_is_frontier():
    r=walk('4ed0 0c000001 6702 4e75 4e75')
    assert r['decoded_candidate_instructions']==1 and r['unresolved'][0]['reason']=='indirect transfer unresolved'


def test_pc_relative_branch_base_is_after_opcode_word():
    r=walk('60000004 4afc 4e75')
    assert r['decoded_candidate_instructions']==2 and not r['unresolved']


def test_pc_relative_effective_address():
    r=walk('103a000e 02000004 6702 4e71 4e75 0000')
    mm=matches(r,'loaded-mask-controls-branch');assert mm[0]['bindings']['read']['expression']['absolute']==0x210


def test_absolute_short_sign_extension_uses_24bit_bus():
    r=walk('1038ff00 02000004 6702 4e71 4e75')
    assert matches(r,'loaded-mask-controls-branch')[0]['bindings']['read']['expression']['absolute']==0xffff00


def test_stop_is_wait_not_fallthrough():
    r=walk('4e722000 0c000001 6702 4e75 4e75')
    assert r['decoded_candidate_instructions']==1 and r['accesses'][0]['kind']=='wait'


def test_known_mapping_write_stops():
    r=walk('13fc000100a130f1 4e71 4e75')
    assert r['decoded_candidate_instructions']==1 and 'mapping' in r['unresolved'][0]['reason']


def test_unknown_indirect_store_not_aliased_to_ram():
    r=walk('1080 4e75')
    assert r['unresolved_indirect_stores']==1 and not r['accesses']


@pytest.mark.parametrize('kw',[{'budget':0},{'budget':True},{'max_arm':0},{'mapping_id':''}])
def test_probe_budgets(kw):
    args={'mapping_id':'test','budget':5};args.update(kw)
    with pytest.raises(ValueError):probe(b'\x4e\x75',[{'cpu_start':512,'file_start':0,'size':2}],[512],**args)


def test_odd_entry_refused():
    with pytest.raises(ValueError):probe(b'\0'*8,[{'cpu_start':512,'file_start':0,'size':8}],[513],mapping_id='odd')


def test_work_budget_is_exposed():
    r=probe(bytes.fromhex('4e714e714e75'),[{'cpu_start':512,'file_start':0,'size':6}],[512],mapping_id='limited',budget=1)
    assert r['budget_exhausted'] and r['pending_roots']==1


def test_wad_links_and_scene_semantic_limits():
    r=inspect_wad(wad(map_lumps()));s=r['maps'][0]
    assert s['selected_reference_checks_pass'] and s['counts']['SECTORS']==2
    assert s['entity_definitions'][0]['x']==-20 and s['entity_definitions'][0]['active'] is None
    assert s['event_candidates'][0]['nonzero_tag_sector_candidates']==[1]
    assert s['event_candidates'][0]['effect'] is None and s['sector_adjacency_candidates'][0]['walkable'] is None


def test_duplicate_map_names_keep_identity():
    r=inspect_wad(wad(map_lumps()+map_lumps()))
    assert len(r['maps'])==2 and r['maps'][0]['id']!=r['maps'][1]['id'] and r['duplicate_names']['MAP01']==2


@pytest.mark.parametrize('extended',['BEHAVIOR','TEXTMAP'])
def test_extended_map_is_not_classic(extended):
    r=inspect_wad(wad(map_lumps()+[(extended,b'\0'*8)]))
    assert not r['maps'] and 'separate layout' in r['unresolved'][0]['reason']


def test_record_partial_retained_as_unresolved():
    l=map_lumps();l[1]=('THINGS',b'\0'*9)
    assert not inspect_wad(wad(l))['maps']


def test_reference_error_does_not_become_valid_scene():
    l=map_lumps();l[2]=('LINEDEFS',struct.pack('<7H',0,300,4,7,9,0,1))
    r=inspect_wad(wad(l));assert r['maps'][0]['selected_reference_checks_pass'] is False


@pytest.mark.parametrize('field,value',[(4,-1),(8,-1),(4,100001),(8,999999)])
def test_directory_bounds(field,value):
    d=bytearray(wad([]));struct.pack_into('<i',d,field,value)
    with pytest.raises(ValueError):inspect_wad(bytes(d))


def test_lump_extent_is_checked():
    d=bytearray(wad([('X',b'hi')]))
    pos=struct.unpack_from('<i',d,8)[0];struct.pack_into('<i',d,pos+4,99999)
    with pytest.raises(ValueError):inspect_wad(bytes(d))


def test_empty_wad_valid_directory_no_world():
    assert inspect_wad(wad([]))['maps']==[]


def test_non_wad_ignored():
    assert inspect_wad(b'not a wad') is None


def test_map_budget_explicit():
    r=inspect_wad(wad(map_lumps()*2),max_maps=1)
    assert len(r['maps'])==1 and r['unresolved'][0]['reason']=='map budget'


def test_record_budget_explicit():
    r=inspect_wad(wad(map_lumps()),max_records=1)
    assert not r['maps'] and r['unresolved'][0]['reason']=='record budget'


def test_public_scan_discovers_wad_and_genesis_without_names(tmp_path):
    (tmp_path/'unknown.dat').write_bytes(wad(map_lumps()))
    (tmp_path/'other.dat').write_bytes(genesis(bytes.fromhex('103900ff00000200000467024e714e75')))
    r=scan_directory(tmp_path,max_instructions=100)
    assert r['pattern_counts']['linked-scene-records']==1
    assert r['pattern_counts']['loaded-mask-controls-branch']==1
    assert scan_directory(tmp_path,max_instructions=100)==r


def outer(child):
    d=bytearray(128);struct.pack_into('<14H',d,0,0x5a4d,128,1,0,4,0,0xffff,0,0,0,0,0,64,0)
    d[64]=0xc3
    return bytes(d)+child


def test_nested_mz_le_source_offsets_are_parent_relative():
    original=le_file();v,notes=embedded_le_views(outer(original))
    direct=le_source_views(original)
    assert len(v)==len(direct)==1 and v[0]['bytes']==direct[0]['bytes']
    assert v[0]['file_mapping'][0]['file_offset']==128+direct[0]['file_mapping'][0]['file_offset']
    assert v[0]['source_envelope_offset']==128
    assert len(native_views(outer(original))[0])==2


def test_mz_magic_without_valid_header_is_not_code():
    v,n=embedded_le_views(outer(b'MZ'+b'\xff'*100+b'LE'+b'\0'*196));assert not v


def test_mixed_width_le_code_does_not_invent_real_mode_entry():
    d=le_file(object_flags=(0x1045,0x2045));v=le_source_views(d)
    assert v[0]['bits']==16 and v[0]['entry'] is None and v[0]['declared_entry']==0
    assert v[1]['bits']==32 and v[1]['entry'] is None


def test_checksum_advisory_not_authenticity():
    d=bytearray(genesis(b'\x4e\x75'));d[-1]^=1
    h,v,notes=profiles(bytes(d));assert v and any('checksum' in n.lower() for n in notes)


def test_genesis_archive_fast_path_without_extension_knowledge(tmp_path):
    import zipfile
    path=tmp_path/'samples.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('unlabelled.dat',genesis(b'\x4e\x75'))
        z.writestr('truncated.bin',genesis(b'\x4e\x75')[:-1])
    r=scan_directory(path,max_instructions=100)
    assert r['coverage']['files_read']==2
    assert len(r['producers'][0]['views'])==0 or len(r['producers'][1]['views'])==0
    assert not r['skipped']


def test_default_budget_admits_larger_resource_package(tmp_path):
    data=wad([('PADDING',bytes(3*1024*1024))])
    p=tmp_path/'data.bin';p.write_bytes(data)
    r=scan_directory(p,max_instructions=100)
    assert r['pattern_counts']['indexed-resource-directory']==1
    assert r['limits']['max_file_bytes']==32*1024*1024
    assert scan_directory(p,max_file_bytes=1024)['coverage']['files_read']==0


def test_map_payload_work_budget_counts_aliases():
    r=inspect_wad(wad(map_lumps()*2),max_map_bytes=220)
    assert len(r['maps'])==1 and r['unresolved'][0]['reason']=='map payload work budget'
