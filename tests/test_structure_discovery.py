"""Authored cross-format fixtures. No original game bytes or dictionaries."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

import pytest
from fdisbull.structure_patterns import match_graph
from fdisbull.structure_native import native_facts,native_views,exepack_candidates
from fdisbull.structure_tables import record_candidates,pointer_string_tables
from fdisbull.structure_vm import agi_facts,z_catalog,z_facts,decode_z_core
from fdisbull.structure_discovery import scan_directory,scan_to_directory
from fdisbull.zmachine import decode_v3


def evidence(offset=0,source='a'*64):
    return {'source_sha256':source,'space':'authored:'+source,'offset':offset,'size':1}


def graph(subject='object:7'):
    nodes=[{'id':'r','role':'read','evidence':evidence(0),'subject':subject},
           {'id':'m','role':'mask','evidence':evidence(1),'subject':subject},
           {'id':'b','role':'branch','evidence':evidence(2)}]
    return nodes,[('r','m','value'),('m','b','predicate')]


def view(code,bits=16):
    return {'bytes':code,'bits':bits,'base':0,'entry':0,'entry_ip':0,'entry_cs':0,
            'kind':'authored-source','sha256':sha256(code).hexdigest(),
            'qualification':'authored fixture','file_mapping':[]}


def native_matches(code,bits=16,**kwargs):
    n,e,c=native_facts(view(code,bits),{'sha256':sha256(code).hexdigest()},**kwargs)
    return match_graph(n,e),c


def test_connected_pattern_returns_bindings_and_no_execution_authority():
    n,e=graph();r=match_graph(n,e)
    assert len(r['matches'])==1
    assert r['matches'][0]['bindings']['read']['evidence']['offset']==0
    assert r['matches'][0]['execution_authorized'] is False


@pytest.mark.parametrize('removed',[0,1])
def test_disconnected_features_do_not_match(removed):
    n,e=graph();e.pop(removed);assert not match_graph(n,e)['matches']


def test_mixed_sources_cannot_become_a_local_code_slice():
    n,e=graph();n[2]['evidence']=evidence(2,'b'*64)
    assert not match_graph(n,e)['matches']


def test_match_order_is_deterministic():
    n,e=graph();assert match_graph(n,e)==match_graph(list(reversed(n)),list(reversed(e)))


@pytest.mark.parametrize('subject',[None,'object:8'])
def test_unknown_or_different_entity_does_not_unify(subject):
    n=[{'id':'t','role':'entity_test','subject':'object:7','evidence':evidence()},
       {'id':'g','role':'branch','evidence':evidence(1)},
       {'id':'e','role':'effect','subject':subject,'evidence':evidence(2)}]
    assert not match_graph(n,[('t','g','predicate'),('g','e','controls')])['matches']


def test_same_literal_entity_unifies():
    n=[{'id':'t','role':'entity_test','subject':'object:7','evidence':evidence()},
       {'id':'g','role':'branch','evidence':evidence(1)},
       {'id':'e','role':'effect','subject':'object:7','evidence':evidence(2)}]
    assert match_graph(n,[('t','g','predicate'),('g','e','controls')])['matches'][0]['pattern']=='same-entity-test-and-mutation'


def test_bounded_join_records_truncation():
    n,e=graph();r=match_graph(n,e,max_work=1)
    assert r['work_budget_exhausted'] and not r['matches']


@pytest.mark.parametrize('budget',[0,-1,True,100001])
def test_invalid_match_budget(budget):
    n,e=graph()
    with pytest.raises(ValueError):match_graph(n,e,max_matches=budget)


def test_duplicate_node_is_not_silently_overwritten():
    n,e=graph()
    with pytest.raises(ValueError):match_graph(n+[n[0]],e)


def test_dangling_edge_is_rejected():
    n,e=graph()
    with pytest.raises(ValueError):match_graph(n,e+[('missing','r','value')])


@pytest.mark.parametrize('branch,meaning',[(0x74,'zero'),(0x75,'nonzero')])
def test_x86_load_mask_branch_keeps_branch_polarity(branch,meaning):
    code=bytes.fromhex('8a060001a801')+bytes([branch,1,0x90,0xc3])
    r,c=native_matches(code)
    assert len(r['matches'])==1 and r['matches'][0]['bindings']['gate']['test']==meaning
    assert c['mask_sites']==1


@pytest.mark.parametrize('code',[
    '8a060001b002a801740190c3', # overwrite loaded register
    '8a06000184c0740190c3',     # self-test is only a zero test
    '8a060001a8ff740190c3',     # full mask is only a zero test
    '8a060001a800740190c3',     # zero mask is constant
    '8a060001a80140740190c3',   # INC overwrites relevant flags
    '8a060001a80190c3',         # no conditional consumer
])
def test_native_near_misses(code):
    assert not native_matches(bytes.fromhex(code))[0]['matches']


def test_native_mask_then_explicit_zero_compare():
    r,c=native_matches(bytes.fromhex('8a06000124013c00740190c3'))
    assert len(r['matches'])==1
    assert r['matches'][0]['bindings']['mask']['zero_comparison'] is not None


def test_native_memory_rhs_can_supply_the_masked_value():
    r,c=native_matches(bytes.fromhex('22070000740190c3')) # AND AL,[BX]; ADD [BX+SI],AL is a flag barrier
    assert not r['matches']
    r,c=native_matches(bytes.fromhex('2207740190c3'))
    assert len(r['matches'])==1


def test_native_instruction_budget_is_not_complete_coverage():
    r,c=native_matches(bytes.fromhex('8a060001a801740190c3'),max_instructions=1)
    assert c['instruction_budget_exhausted'] and not r['matches']


def pack_fixture(skip=1):
    hdr=struct.pack('<14H',0x5a4d,96,1,0,2,0,0xffff,0,0,0,0,0,28,0)+b'\0'*4
    packed=b'\x90\x10\0\xb1'+b'\xff'*12
    control=struct.pack('<9H',0,0,0,32,0,0,1,skip,0x4252)+bytes.fromhex('8cc00510000e1f')
    return hdr+packed+control.ljust(32,b'\0')


def test_exepack_fill_stream_is_a_derived_view_not_executable():
    r=exepack_candidates(pack_fixture())
    assert len(r)==1 and r[0]['bytes']==b'\x90'*16 and r[0]['file_mapping'] is None


def test_exepack_unqualified_skip_profile_is_refused():
    assert not exepack_candidates(pack_fixture(2))
    assert not native_views(pack_fixture(2))[0]


def test_exepack_bad_run_refused():
    b=bytearray(pack_fixture());b[33]=0xff
    assert not exepack_candidates(bytes(b))


def records(stride=37,count=12):
    b=bytearray(stride*count)
    for i in range(count):
        text=f'Pilot {i}'.encode()+b'\0'
        b[stride*i+9:stride*i+9+len(text)]=text
        b[stride*i+31]=i+1
    return bytes(b)


def test_unknown_stride_and_offset_discovered_without_game_profile():
    r=record_candidates(records())
    assert r[0]['stride']==37 and r[0]['label_residue']==9 and r[0]['record_positions']==12


def test_packed_bitmap_like_repetition_is_not_a_named_population():
    assert not record_candidates((b'AAAA\0\0\0\0'*100))


def test_strings_longer_than_candidate_stride_cannot_define_rows():
    assert all(r['stride']>=max(a['length'] for a in r['examples']) for r in record_candidates(records()))


def test_zero_and_random_buffers_have_no_supported_named_records():
    rnd=random.Random(42)
    for b in (b'\0'*10000,rnd.randbytes(10000)):
        assert not record_candidates(b)


def test_pointer_table_infers_an_unknown_base():
    b=bytearray(1024);targets=[];at=600
    for label in ('alpha','bravo','charlie','delta','echoes','foxtrot','golfing','hotel'):
        t=label.encode()+b'\0';targets.append(at);b[at:at+len(t)]=t;at+=len(t)
    for i,target in enumerate(targets):b[200+i*2:202+i*2]=(target-512).to_bytes(2,'little')
    r=pointer_string_tables(bytes(b))
    assert any(t['offset']==200 and t['candidate_base']==512 and t['count']==8 for t in r['tables'])


def ztext(word,version=5):
    chars=[ord(c)-97+6 for c in word];chars=(chars+[5]*9)[:6 if version==3 else 9]
    words=[(chars[i]<<10)|(chars[i+1]<<5)|chars[i+2] for i in range(0,len(chars),3)]
    words[-1]|=32768
    return b''.join(w.to_bytes(2,'big') for w in words)


def story(version=5,code=b'\xba'):
    b=bytearray(1024)
    def w(at,n):b[at:at+2]=n.to_bytes(2,'big')
    b[0]=version;w(4,900);w(6,900);w(8,800);w(10,64);w(12,300);w(14,800);w(26,1024//(2 if version==3 else 4))
    stride=9 if version==3 else 14;first=64+(62 if version==3 else 126)
    for i in range(2):w(first+i*stride+stride-2,first+2*stride+i*2)
    enc=4 if version==3 else 6;b[800]=0;b[801]=enc+3;w(802,3)
    for i,t in enumerate(('alpha','bravo','delta')):b[804+i*(enc+3):804+i*(enc+3)+enc]=ztext(t,version)
    b[900:900+len(code)]=code;w(28,sum(b[64:])&65535)
    return bytes(b)


@pytest.mark.parametrize('version',[3,5])
def test_z_catalogue_is_versioned_and_preserves_opaque_metadata(version):
    r=z_catalog(story(version))
    assert r['dictionary']['count']==3 and r['dictionary']['game_metadata_bytes']==3
    assert r['objects']['count']==2 and r['objects']['status']=='validated_candidate'
    assert r['objects']['stride']==(9 if version==3 else 14)


def test_z_checksum_refusal():
    b=bytearray(story());b[700]^=1
    with pytest.raises(ValueError,match='checksum'):z_catalog(bytes(b))


def test_z_parent_cycle_is_not_a_valid_entity_graph():
    b=bytearray(story());b[196:198]=(1).to_bytes(2,'big');b[28:30]=(sum(b[64:])&65535).to_bytes(2,'big')
    assert 'parent cycle' in z_catalog(bytes(b))['objects']['issues']


def test_z_unsupported_version_refused():
    b=bytearray(story());b[0]=6
    with pytest.raises(ValueError):z_catalog(bytes(b))


def test_z_attribute_guard_uses_the_same_graph_pattern_as_native():
    # test_attr object1 attribute3, return false on true; otherwise clear attr.
    b=story(code=bytes.fromhex('0a0103c00c0103b0'));cat=z_catalog(b)
    n,e,c=z_facts(b,cat);r=match_graph(n,e)
    assert {'loaded-mask-controls-branch','same-entity-test-and-mutation'}<=set(m['pattern'] for m in r['matches'])


def test_z_five_read_stores_but_three_read_does_not():
    code=bytes.fromhex('e45f404110')
    assert decode_z_core(code,0,5)['end']==5
    assert decode_z_core(code,0,3)['end']==4


@pytest.mark.parametrize('code',['b0','0a0103c0','0b0103','15010210','e05f123410','9003c0'])
def test_z3_common_layout_agrees_with_existing_decoder(code):
    b=bytes.fromhex(code)
    a=decode_z_core(b,0,3);other=decode_v3(b,0)
    assert (a['op'],a['operands'],a['end'],a.get('store'))==(other['op'],other['operands'],other['end'],other.get('store'))


def test_z_extended_opcode_stays_explicit():
    with pytest.raises(ValueError,match='extended'):decode_z_core(bytes.fromhex('be00ff'),0,5)


def agi_census(join=False,call=False):
    rows=[{'offset':2,'end_offset':10,'operation':'if','operands':[],
           'conditions':[{'offset':3,'operation':'said','operands':[1,42,0],'word_groups':[42]}],
           'successors':[{'kind':'true','offset':10},{'kind':'false','offset':12}]},
          {'offset':10,'end_offset':12,'operation':'call' if call else 'set','operands':[7],
           'successors':[{'kind':'fallthrough','offset':12}]},
          {'offset':12,'end_offset':13,'operation':'return','operands':[],'successors':[]}]
    if join:rows.append({'offset':20,'end_offset':23,'operation':'goto','operands':[],
                         'successors':[{'kind':'jump','offset':10}]})
    return {'vocabulary':{'groups':[{'number':42,'words':['activate','enable']}]},
            'logics':[{'logic':1,'source':{'sha256':'a'*64,'volume':0,'offset':0},'ir':{'instructions':rows}}]}


def test_agi_dictionary_binds_to_guarded_effect_not_just_text():
    n,e,c=agi_facts(agi_census());r=match_graph(n,e)
    assert len(r['matches'])==1 and r['matches'][0]['pattern']=='dictionary-test-controls-effect'


@pytest.mark.parametrize('arg',[{'join':True},{'call':True}])
def test_agi_join_and_call_are_boundaries(arg):
    n,e,c=agi_facts(agi_census(**arg));assert not match_graph(n,e)['matches']


def test_scan_and_saved_report_are_deterministic_and_private(tmp_path):
    root=tmp_path/'inputs';root.mkdir();(root/'unknown.dat').write_bytes(records())
    a=scan_directory(root);b=scan_directory(root);assert a==b
    result=scan_to_directory(root,tmp_path/'out')
    assert result['status']=='candidates' and result['runtime_observed'] is False
    assert Path(result['report']).stat().st_size>0
    with pytest.raises(ValueError):scan_to_directory(root,tmp_path/'out')


def test_scan_ignores_symlink_and_reports_it(tmp_path):
    root=tmp_path/'input';root.mkdir();outside=tmp_path/'outside';outside.write_bytes(records())
    (root/'link').symlink_to(outside)
    r=scan_directory(root);assert r['coverage']['skipped_count']==1 and not r['findings']


def test_output_inside_input_or_git_is_refused(tmp_path):
    root=tmp_path/'input';root.mkdir()
    with pytest.raises(ValueError):scan_to_directory(root,root/'out')
    repo=tmp_path/'repo';repo.mkdir();(repo/'.git').mkdir()
    with pytest.raises(ValueError):scan_to_directory(root,repo/'out')


def test_file_byte_budget_does_not_claim_complete_input(tmp_path):
    (tmp_path/'test.dat').write_bytes(records())
    r=scan_directory(tmp_path,max_file_bytes=100)
    assert r['coverage']['files_read']==0 and r['coverage']['skipped_count']==1


def test_same_bytes_with_unknown_filename_return_same_pattern(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    (a/'first.bin').write_bytes(records());(b/'unfamiliar.resource').write_bytes(records())
    ra=scan_directory(a);rb=scan_directory(b)
    assert ra['pattern_counts']==rb['pattern_counts']
    assert [x['id'] for x in ra['findings']]==[x['id'] for x in rb['findings']]


def test_projectless_public_json_and_bounded_drilldown(tmp_path):
    from fdisbull.cli import respond
    root=tmp_path/'input';root.mkdir();(root/'unknown.bin').write_bytes(records())
    result=respond({'method':'structure-scan','params':{'game_dir':str(root),'output':str(tmp_path/'output')}},default_project='do-not-open.fdb')
    assert result['ok'],result
    report=result['result']['report']
    page=respond({'method':'structure-info','params':{'report':report,'limit':1}},default_project='do-not-open.fdb')
    assert page['ok'] and len(page['result']['items'])==1
    ident=page['result']['items'][0]['id']
    selected=respond({'method':'structure-info','params':{'report':report,'lead_id':ident}})
    assert selected['ok'] and selected['result']['total']==1
    assert not (tmp_path/'do-not-open.fdb').exists()


def test_public_cli_executes_the_shared_scan(tmp_path):
    import os
    root=tmp_path/'input';root.mkdir();(root/'unknown.bin').write_bytes(records())
    r=subprocess.run([sys.executable,'-m','fdisbull','structure-scan',str(root),'--output',str(tmp_path/'output')],
                     text=True,capture_output=True,timeout=30)
    assert r.returncode==0,r.stderr+r.stdout
    doc=json.loads(r.stdout)
    assert doc['ok'] and doc['result']['venues'][0]['pattern']=='labelled-record-array'


def test_agi_reader_cannot_follow_an_uninventoried_symlink(tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'LOGDIR').write_bytes(b'\0\0\0')
    outside=tmp_path/'payload';outside.write_bytes(b'\0'*32);(root/'VOL.0').symlink_to(outside)
    r=scan_directory(root)
    assert any('outside admitted snapshots' in i.get('error','') for i in r['issues'])
    assert not any(p['producer']=='agi-existing-census' for p in r['producers'])


def test_native_source_refuses_invalid_mz_extents():
    assert not native_views(b'MZ'+b'\0'*30)[0]


def test_legal_graph_does_not_change_input_facts():
    n,e=graph();before=deepcopy((n,e));match_graph(n,e);assert (n,e)==before


def test_le_source_view_preserves_unapplied_fixup_bytes():
    from test_le_loader import le_file
    from fdisbull.le import load_le
    source=le_file()
    views,notes=native_views(source)
    assert len(views)==1 and views[0]['kind']=='le-unrelocated-object'
    assert views[0]['bytes'][:6]==bytes.fromhex('b800000000c3')
    assert load_le(source).regions[0].data[:6]==bytes.fromhex('b802000200c3')
    assert 'fixups unapplied' in views[0]['qualification']
    for mapping in views[0]['file_mapping']:
        offset=mapping['file_offset']; at=mapping['view_offset']; size=mapping['size']
        assert views[0]['bytes'][at:at+size]==source[offset:offset+size]


def test_le_inspection_does_not_relax_the_executable_loader():
    from test_le_loader import le_file
    from fdisbull.le import load_le
    source=le_file(fixups=[struct.pack('<BBhBH',2,0,1,2,2),b''])
    with pytest.raises(ValueError):
        load_le(source)
    views,notes=native_views(source)
    assert views and 'unrelocated' in notes[0]


@pytest.mark.parametrize('kind',['entry','page','header'])
def test_le_bad_source_mapping_is_rejected(kind):
    from test_le_loader import le_file
    source=bytearray(le_file())
    if kind=='entry':struct.pack_into('<I',source,0x80+0x1c,0xffffff)
    elif kind=='page':struct.pack_into('<I',source,0x80+0x80,len(source)+100)
    else:struct.pack_into('<I',source,0x80+0x18,100)
    with pytest.raises(ValueError):native_views(bytes(source))


def test_short_sequential_printable_runs_are_not_labelled_records():
    # Authored binary indices can spell alphabet fragments without being names.
    data=b''.join((name+b'\0'*40)[:32] for name in (b'bcd',b'efg',b'hij',b'klm',b'nop',b'qrs',b'tuv',b'wxy'))
    assert record_candidates(data)==[]


def test_nonregular_input_is_skipped_without_opening(tmp_path):
    import os
    if not hasattr(os,'mkfifo'):pytest.skip('requires POSIX fifo fixture')
    root=tmp_path/'input';root.mkdir();os.mkfifo(root/'pipe')
    report=scan_directory(root)
    assert report['coverage']['files_read']==0
    assert report['skipped']==[{'path':'pipe','reason':'not a regular file'}]
