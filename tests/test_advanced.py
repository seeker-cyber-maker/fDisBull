"""Public persistent orchestration over real native bytes, never execution."""
import struct

import pytest

from fdisbull.project import Project
from fixtures_formats import pe64


def x86_dispatch(base=0x1000, guarded=True, recursive=True):
    data=bytearray(b'\xcc'*0x200)
    prefix=b'\x48\xb8'+struct.pack('<Q',base+0x100)
    code=prefix+(bytes.fromhex('4883f9027703') if guarded else b'')+bytes.fromhex('ff24c8c3')
    data[:len(code)]=code
    for offset in (0x40,0x50,0x60,0x70):data[offset]=0xc3
    if recursive:
        body=b'\x48\xb8'+struct.pack('<Q',base+0x70)+bytes.fromhex('ffd0c3')
        data[0x40:0x40+len(body)]=body
    struct.pack_into('<3Q',data,0x100,base+0x40,base+0x50,base+0x60)
    return bytes(data)


def arm_dispatch():
    data=bytearray(bytes.fromhex('000020d4')*128)  # BRK padding.
    mov=lambda register,value:struct.pack('<I',0xd2800000|(value<<5)|register)
    code=mov(1,0x1100)+mov(3,0x1040)+bytes.fromhex('5f0800f1880000542078a2b86000008b00001fd6c0035fd6')
    data[:len(code)]=code
    for offset in (0x40,0x50,0x60):data[offset:offset+4]=bytes.fromhex('c0035fd6')
    struct.pack_into('<3i',data,0x100,0,16,32)
    return bytes(data)


def create(tmp_path, payload, *, arch='x86', bits=64, container='raw', name='case'):
    source=tmp_path/(name+('.exe' if container=='PE' else '.bin'))
    if container=='PE':
        native=bytearray(pe64())
        struct.pack_into('<II',native,0x98+112,0,0)  # Remove fixture's export directory.
        native[0x200:0x400]=payload
        source.write_bytes(native)
        return Project.create(tmp_path/(name+'.fdb'),source)
    source.write_bytes(payload)
    return Project.create(tmp_path/(name+'.fdb'),source,arch=arch,bits=bits,base=0x1000)


def decoded(project,address):
    return project.db.execute('SELECT 1 FROM instructions WHERE version=? AND address=?',
                              (project.version()['id'],f'{address:016x}')).fetchone() is not None


@pytest.mark.parametrize('container,base',[('raw',0x1000),('PE',0x140001000)])
def test_public_recursive_admission_reaches_fixed_point_across_containers(tmp_path,container,base):
    with create(tmp_path,x86_dispatch(base),container=container) as project:
        project.analyze()
        assert not decoded(project,base+0x40)
        receipt=project.auto_analyze(max_rounds=20)
        assert receipt['stable'] and not receipt['budget_exhausted'] and receipt['rounds']>1
        assert all(decoded(project,base+offset) for offset in (0x40,0x50,0x60,0x70))
        edges={(int(r['source'],16),int(r['target'],16),r['kind']) for r in project.db.execute("SELECT source,target,kind FROM xrefs WHERE kind LIKE 'resolved_%'")}
        assert {(base+0x10,base+offset,'resolved_branch') for offset in (0x40,0x50,0x60)} <= edges
        assert (base+0x4a,base+0x70,'resolved_call') in edges
        document=project.function_analysis(base)
        assert document['state']=='done' and not document['stale']
        assert len(document['result']['indirect']['candidates'])==4
        assert all(c['admitted'] for c in document['result']['indirect']['candidates'])
        generation=document['generation']
        repeated=project.auto_analyze(max_rounds=20)
        assert repeated['stable'] and repeated['processed_jobs']==0
        assert project.function_analysis(base)['generation']==generation


def test_arm_guarded_signed_table_uses_same_persistent_passes(tmp_path):
    with create(tmp_path,arm_dispatch(),arch='arm64') as project:
        project.analyze()
        assert not decoded(project,0x1040)
        assert project.auto_analyze(abi='aarch64_aapcs64',max_rounds=20)['stable']
        result=project.function_analysis(0x1000)['result']
        candidates=result['indirect']['candidates']
        assert {c['target'] for c in candidates}=={0x1040,0x1050,0x1060}
        assert all(c['admitted'] and c['loads'][0]['signed'] for c in candidates)
        assert all(decoded(project,address) for address in (0x1040,0x1050,0x1060))


def test_unbounded_index_remains_proposal_and_does_not_admit_pointer_looking_bytes(tmp_path):
    with create(tmp_path,x86_dispatch(guarded=False,recursive=False)) as project:
        receipt=project.auto_analyze(max_rounds=20)
        assert receipt['stable']  # Fixed point of implemented rules, not coverage.
        result=project.function_analysis(0x1000)['result']['indirect']
        assert result['proposals'] and not result['candidates']
        assert all(not decoded(project,address) for address in (0x1040,0x1050,0x1060))
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE kind='resolved_branch'").fetchone()


def test_explicit_unexplored_pointer_table_is_not_read_for_target_admission(tmp_path):
    with create(tmp_path,x86_dispatch(recursive=False)) as project:
        project.represent(0x1100,'unexplored',size=24,defer=True)
        assert project.auto_analyze(max_rounds=20)['stable']
        result=project.function_analysis(0x1000)['result']['indirect']
        assert not result['candidates'] and result['rejections']
        assert all(not decoded(project,address) for address in (0x1040,0x1050,0x1060))


def test_partial_budget_persists_restart_and_resumes_without_byte_changes(tmp_path):
    project=create(tmp_path,x86_dispatch())
    project.analyze()
    digest=project.version()['sha256'];path=project.path
    partial=project.auto_analyze(max_steps=1,max_rounds=1)
    assert partial['budget_exhausted'] and not partial['stable']
    assert project.function_analysis(0x1000)['state']=='partial'
    project.db.close()
    with Project(path) as reopened:
        saved=reopened.function_analysis(0x1000)
        assert saved['stale'] and saved['result']['budget_exhausted']
        assert reopened.auto_analyze(max_rounds=20)['stable']
        assert reopened.version()['sha256']==digest
        assert reopened.function_analysis(0x1000)['state']=='done'


def caller_payload(arch='x86',count=8):
    data=bytearray(b'\xcc'*0x200 if arch=='x86' else bytes.fromhex('000020d4')*128)
    if arch=='x86':
        code=bytes.fromhex('bf00110000be34120000')+b'\xba'+struct.pack('<I',count)+bytes.fromhex('e86c000000c3')
        data[0x80]=0xc3
    else:
        mov=lambda register,value:struct.pack('<I',0xd2800000|(value<<5)|register)
        code=mov(0,0x1100)+mov(1,0x1234)+mov(2,count)+bytes.fromhex('1d000094c0035fd6')
        data[0x80:0x84]=bytes.fromhex('c0035fd6')
    data[:len(code)]=code
    return bytes(data)


@pytest.mark.parametrize('arch,abi',[('x86','x86_64_sysv'),('arm64','aarch64_aapcs64')])
def test_explicit_per_callee_abi_qualifies_public_call_effects_and_survives_restart(tmp_path,arch,abi):
    project=create(tmp_path,caller_payload(arch),arch=arch)
    registered=project.set_summary(0x1080,'memset',abi=abi,author='reviewed contract')
    assert registered['summary']['source']['kind']=='user_confirmed'
    assert project.auto_analyze(max_rounds=20)['stable']
    effects=project.call_effects(0x1107,access='write',include_unresolved=False)
    effect,=effects['items']
    assert (effect['address'],effect['size'],effect['end_exclusive'],effect['fill_byte'])==(0x1100,8,0x1108,0x34)
    assert effect['abi']==abi and not effect['runtime_observed']
    assert project.call_effects(0x1108,access='write',include_unresolved=False)['total']==0
    path=project.path;document=project.function_analysis(0x1000)
    project.db.close()
    with Project(path) as reopened:
        assert reopened.function_analysis(0x1000)==document
        assert reopened.call_effects(0x1107,access='write')['items']==effects['items']


def test_summary_change_invalidates_caller_and_excludes_stale_effects(tmp_path):
    with create(tmp_path,caller_payload()) as project:
        project.set_summary(0x1080,'memset',abi='x86_64_sysv')
        assert project.auto_analyze(max_rounds=20)['stable']
        assert project.call_effects(0x1100,access='write',include_unresolved=False)['total']==1
        receipt=project.set_summary(0x1080,'memset',abi='x86_64_win64')
        assert receipt['invalidated_tasks'] and project.function_analysis(0x1000)['stale']
        assert project.call_effects(0x1100,access='write',include_unresolved=False)['total']==0
        assert project.auto_analyze(max_rounds=20)['stable']
        effects=project.call_effects(0x1100,access='write')
        assert any(not x.get('resolved') for x in effects['items'])


def test_qualified_per_call_abi_preserves_stack_arguments_across_an_earlier_call(tmp_path):
    data=bytearray(b'\xcc'*0x200)
    code=bytes.fromhex('6a07e87900000083c4046a086a006800110000e87800000083c40cc3')
    data[:len(code)]=code;data[0x80]=data[0x90]=0xc3
    with create(tmp_path,bytes(data),bits=32) as project:
        project.set_summary(0x1080,'observe',prototype={'arguments':[dict(name='code',type='int')]},
                            summary={'effects':[]},abi='x86_32_cdecl')
        project.set_summary(0x1090,'memset',abi='x86_32_cdecl')
        assert project.auto_analyze(max_rounds=20)['stable']
        effect,=project.call_effects(0x1100,access='write',include_unresolved=False)['items']
        assert effect['address']==0x1100 and effect['size']==8
        assert effect['abi']=='x86_32_cdecl'


def test_zero_byte_contract_does_not_overlap_any_writer_query(tmp_path):
    with create(tmp_path,caller_payload(count=0)) as project:
        project.set_summary(0x1080,'memset',abi='x86_64_sysv')
        assert project.auto_analyze(max_rounds=20)['stable']
        assert project.call_effects(0x10f0,size=32,access='write')['total']==0
        assert project.call_effects(access='write')['total']==0


def test_signature_identity_is_requalified_after_patch_and_parent_is_immutable(tmp_path):
    body=bytes.fromhex('4889f84889d1fcf3a4c3')
    with create(tmp_path,body) as project:
        assert project.auto_analyze(max_rounds=20)['stable']
        original=project.function_analysis(0x1000,version=1)
        assert original['result']['summary']['name']=='memcpy'
        child=project.patch(0x1007,'9090')
        version=child['version']
        assert project.auto_analyze(version=version,max_rounds=20)['stable']
        changed=project.function_analysis(0x1000,version=version)['result']
        assert changed['signature_matches']==[] and changed['summary'] is None
        assert project.summaries(version=version)['items']==[]
        assert project.function_analysis(0x1000,version=1)==original


def test_registered_masked_signature_preserves_qualified_confidence_and_match_kind(tmp_path):
    with create(tmp_path,bytes.fromhex('48b81122334455667788c3')) as project:
        project.add_signature(dict(id='reviewed.masked.memset',name='memset',arch='x86',bits=64,
                                   bytes='48b80000000000000000c3',mask='ffff0000000000000000ff',
                                   relocations=[dict(offset=2,size=8,kind='absolute64')],
                                   source='explicit reviewed signature fixture',confidence=0,abi='x86_64_sysv'))
        assert project.auto_analyze()['stable']
        summary=project.function_analysis(0x1000)['result']['summary']
        assert summary['confidence']==0 and summary['source']['match']=='masked_bytes'
        assert len(summary['source']['input_sha256'])==64
        assert summary['source']['masked_offsets']==list(range(2,10))
        for invalid in (float('nan'),float('inf'),[],True,''):
            with pytest.raises(ValueError,match='confidence'):
                project.add_signature(dict(id='bad',name='memset',arch='x86',bits=64,bytes='c3',
                                           source='test invalid registration',confidence=invalid))


def test_automatic_helper_contract_reaches_callers_and_retracts_in_patched_child(tmp_path):
    data=bytearray(caller_payload())
    helper=bytes.fromhex('4989f84889d189f0fcf3aa4c89c0c3')
    data[0x80:0x80+len(helper)]=helper
    with create(tmp_path,bytes(data)) as project:
        assert project.auto_analyze(max_rounds=20)['stable']
        effect,=project.call_effects(0x1100,access='write',include_unresolved=False)['items']
        assert effect['size']==8 and effect['evidence_source']=='exact_signature'
        assert effect['summary_source']['kind']=='exact_signature' and effect['conditions']
        parent=project.function_analysis(0x1000,version=1)
        child=project.patch(0x1089,'9090')['version']
        assert project.auto_analyze(version=child,max_rounds=20)['stable']
        assert project.function_analysis(0x1080,version=child)['result']['summary'] is None
        assert project.call_effects(0x1100,access='write',include_unresolved=False,version=child)['total']==0
        assert project.function_analysis(0x1000,version=1)==parent


def test_signature_body_start_must_equal_candidate_entry_even_when_cfg_branches_back(tmp_path):
    source=tmp_path/'back.bin';source.write_bytes(bytes.fromhex('c3ebfd'))
    with Project.create(tmp_path/'back.fdb',source,arch='x86',bits=64,base=0x1000,entry=0x1001) as project:
        project.add_signature(dict(id='reviewed.backward.fixture',name='memset',arch='x86',bits=64,
                                   bytes='c3ebfd',source='whole supplied byte fixture'))
        assert project.auto_analyze()['stable']
        result=project.function_analysis(0x1001)['result']
        assert result['graph']['instructions']==2
        assert not result['signature_matches'] and result['summary'] is None


def test_dos_near_call_effect_keeps_offsets_separate_from_physical_ranges(tmp_path):
    module=bytearray(b'\xcc'*0x100)
    module[:14]=bytes.fromhex('6a086a00688000e8060083c406c3')
    module[0x10]=0xc3
    header=bytearray(64)
    struct.pack_into('<14H',header,0,0x5a4d,320,1,0,4,0,0xffff,0,0x80,0,0,0,28,0)
    source=tmp_path/'near.exe';source.write_bytes(bytes(header)+module)
    with Project.create(tmp_path/'near.fdb',source) as project:
        project.set_summary('1000:0010','memset',abi='x86_16_cdecl_near')
        assert project.auto_analyze(abi='x86_16_cdecl_near',max_rounds=20)['stable']
        effect,=project.call_effects('1000:0080',access='write')['items']
        assert not effect['resolved'] and effect['address'] is effect['end_exclusive'] is None
        assert effect['address_space']=='near_offset_unresolved_segment'
        assert 'possible_range' not in effect and 'address_range' not in effect
        assert effect['offset_possible_range']['start']==0x80
        assert effect['offset_possible_range']['end_exclusive']==0x88


def test_dos_legacy_file_pointer_edge_is_retracted_after_unknown_slot_write(tmp_path):
    module=bytearray(b'\xcc'*0x100)
    module[:8]=bytes.fromhex('890e3000ff263000')  # MOV [0030],CX; JMP word [0030].
    struct.pack_into('<H',module,0x30,0x40);module[0x40]=0xc3
    header=bytearray(64)
    struct.pack_into('<14H',header,0,0x5a4d,320,1,0,4,0,0xffff,0,0x80,0,0,0,28,0)
    source=tmp_path/'legacy.exe';source.write_bytes(bytes(header)+module)
    with Project.create(tmp_path/'legacy.fdb',source) as project:
        project.analyze(start='1000:0000',ds=0x1000)
        old=project.db.execute("SELECT 1 FROM dos_edges WHERE source='0000000000010004' AND target='0000000000010040' AND kind='branch'").fetchone()
        assert old is not None
        receipt=project.auto_analyze(max_rounds=20)
        assert receipt['stable'] and receipt['legacy_snapshot_edges_retracted']>=1
        assert not project.db.execute("SELECT 1 FROM dos_edges WHERE source='0000000000010004' AND target='0000000000010040' AND kind IN ('branch','resolved_branch')").fetchone()
        assert decoded(project,0x10040)  # Prior byte observations stay available.


def test_explicit_summary_is_preserved_as_an_assumption_across_patch(tmp_path):
    with create(tmp_path,b'\x90\xc3') as project:
        project.set_summary(0x1000,'memcpy',abi='x86_64_sysv',author='reviewer')
        assert project.auto_analyze()['stable']
        child=project.patch(0x1000,'90')
        assert project.auto_analyze(version=child['version'])['stable']
        summary=project.function_analysis(0x1000,version=child['version'])['result']['summary']
        assert summary['source']=={'kind':'user_confirmed','author':'reviewer'}


def test_mutated_pointer_slot_does_not_recover_original_file_target(tmp_path):
    data=bytearray(b'\xcc'*0x80)
    data[:14]=bytes.fromhex('48890519000000ff2513000000')
    struct.pack_into('<Q',data,0x20,0x1040);data[0x40]=0xc3
    with create(tmp_path,bytes(data)) as project:
        project.analyze()  # A preexisting project can carry legacy pointer facts.
        assert project.auto_analyze(max_rounds=20)['stable']
        candidates=project.function_analysis(0x1000)['result']['indirect']['candidates']
        assert candidates==[]
        assert not project.db.execute("SELECT 1 FROM advanced_edges WHERE target='0000000000001040'").fetchone()
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE source='0000000000001007' AND target='0000000000001040' AND kind='resolved_branch'").fetchone()


def test_invalidated_indirect_call_candidate_is_revived_after_readmission(tmp_path):
    with create(tmp_path,x86_dispatch()) as project:
        assert project.auto_analyze(max_rounds=20)['stable']
        assert project.function_analysis(0x1070)['state']=='done'
        assert project.auto_analyze(abi='x86_64_sysv',max_rounds=20)['stable']
        assert project.function_analysis(0x1070)['state']=='done'
        assert decoded(project,0x1070)


def test_raw_code_at_zero_is_a_valid_indirect_destination(tmp_path):
    source=tmp_path/'zero.bin'
    source.write_bytes(bytes.fromhex('c3b800000000ffe0'))
    with Project.create(tmp_path/'zero.fdb',source,arch='x86',bits=32,base=0,entry=1) as project:
        receipt=project.auto_analyze()
        assert receipt['stable']
        assert project.db.execute("SELECT 1 FROM instructions WHERE address='0000000000000000'").fetchone()
        assert any(row['target']=='0x0' and row['kind']=='resolved_branch' for row in project.xrefs(6,direction='from'))
