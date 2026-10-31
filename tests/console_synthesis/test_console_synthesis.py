"""Authored contract tests. No original console CPU is implied by these tests."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from fdisbull.interaction_il import execute_il
from fdisbull.console_synthesis import *


def block(code,ram=((0x10,'result'),),bank='A'):
    return recover(NativeBacking('authored-fixtures',bank,0x8000,bytes.fromhex(code)),Bindings(ram))


def evaluated(b,**inputs):
    r=execute_il(b.document(),b.state(**inputs))
    assert r['status']=='complete',r
    return b.project(r['state'])


def test_saved_value_is_not_deleted():
    b=block('A9 01 48 A9 02 68 85 10')
    s=evaluated(b)
    assert s['$result']==1 and s['$value']==1
    assert b.maximum_saved_values==1
    assert b.backing.code.hex()=='a90148a902688510'
    assert b.document('udl')['body']==b.document()['body']
    assert '32768' not in json.dumps(b.document())


def test_nested_values_and_final_flag_dependency():
    b=block('A9 80 48 A9 00 48 A9 01 68 AA 68 85 10')
    s=evaluated(b)
    assert s['$result']==128 and s['$index_x']==0
    assert s['$negative'] is True and s['$zero'] is False


@pytest.mark.parametrize('a,rhs,carry',[(0,0,False),(255,0,True),(127,1,False),
                                      (128,128,False),(2,255,True),(23,67,True)])
@pytest.mark.parametrize('opcode', ['65','E5'])
def test_arithmetic_small_cases(opcode,a,rhs,carry):
    b=block(opcode+' 10')
    s=evaluated(b,value=a,result=rhs,carry=carry)
    if opcode=='65':
        total=a+rhs+int(carry);result=total&255
        c=total>255;v=bool((~(a^rhs)&(a^result))&128)
    else:
        total=a-rhs-(not carry);result=total&255
        c=total>=0;v=bool(((a^rhs)&(a^result))&128)
    assert (s['$value'],s['$carry'],s['$overflow'],s['$negative'],s['$zero']) == (result,c,v,bool(result&128),result==0)


def test_store_preserves_live_carry_and_zero():
    b=block('38 A9 00 85 10 69 00')
    s=evaluated(b)
    assert s['$value']==1 and s['$result']==0


def test_source_mirrors_share_one_bound_value():
    b=block('A9 07 8D 10 08 A5 10')
    assert evaluated(b)['$value']==7


@pytest.mark.parametrize('index',[0,1,127,128,255])
def test_zero_page_index_is_unsigned_and_wraps(index):
    target=(0xff+index)&255
    b=block(f'A2 {index:02x} A9 2A 95 FF',ram=((target,'cell'),))
    assert evaluated(b)['$cell']==42


def test_absolute_index_crosses_page_without_zero_page_wrap():
    b=block('A2 FF A9 2A 9D 10 02',ram=((0x30f,'cell'),))
    assert evaluated(b)['$cell']==42


@pytest.mark.parametrize('value',[0,1,128,255])
def test_forward_branch(value):
    b=block('A5 10 F0 04 A9 07 85 11',ram=((0x10,'source'),(0x11,'destination')))
    s=evaluated(b,source=value,destination=19)
    assert s['$destination']==(19 if value==0 else 7)


def test_cmp_preserves_accumulator_and_overflow():
    b=block('C5 10')
    s=evaluated(b,value=2,result=3,overflow=True)
    assert s['$value']==2 and not s['$carry'] and s['$negative'] and s['$overflow']


def test_known_index_does_not_leak_from_other_branch():
    with pytest.raises(Refused,match='dynamic index'):
        block('F0 02 A2 01 B5 10',ram=((0x11,'cell'),))


@pytest.mark.parametrize('code',[
    '68','48','A9','02','20 00 90','60','D0 FE','6C 00 80',
    'AD 02 20','8D 00 20','8D 00 01','B5 10','F0 01 A9 00','F8',
    '4C 00 80','4C 00 90','A5 20',
])
def test_unsupported_source_refuses(code):
    with pytest.raises(Refused): block(code)


@pytest.mark.parametrize('admission',[Admission(decimal_enabled=True),Admission(asynchronous_observers=True),
                                   Admission(observe_stack_bytes=True),Admission(mapping_stable_during_block=False)])
def test_unsupported_environment_refuses(admission):
    with pytest.raises(Refused):
        recover(NativeBacking('fixture','A',0x8000,b'\xea'),Bindings(),admission)


def test_same_logical_label_cannot_merge_distinct_state():
    with pytest.raises(Refused): Bindings(((0x10,'same'),(0x11,'same')))
    with pytest.raises(Refused): Bindings(((0x10,'cell'),(0x10,'other')))


def test_role_does_not_invent_original_execution():
    with pytest.raises(Refused,match='original-CPU'):
        block('EA').execute_original(None,{})


def test_mapped_code_switch_and_original_retained():
    m=CodeMap();a=NativeBacking('image','A',0x8000,bytes.fromhex('A9 01 85 10'))
    other=NativeBacking('image','B',0x8000,bytes.fromhex('A9 02 85 10'))
    bindings=Bindings(((0x10,'result'),))
    m.map('main',a);old,b=m.select('main',bindings)
    assert m.dispatch(old,lambda q:evaluated(q))['$result']==1
    m.map('main',other)
    with pytest.raises(StaleSelection): m.dispatch(old,lambda q:evaluated(q))
    new,b=m.select('main',bindings)
    assert m.dispatch(new,lambda q:evaluated(q))['$result']==2
    assert a.code==bytes.fromhex('A9 01 85 10')


def test_dependency_invalidation_is_selective():
    m=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');b=NativeBacking('image','B',0x8000,b'\xea')
    m.map('a',a);m.map('b',b)
    alone,_=m.select('a',Bindings());dependent,_=m.select('a',Bindings(),dependencies=('b',))
    m.patch('b',b.identity,0,b'\x18')
    assert m.validate(alone)
    with pytest.raises(StaleSelection): m.validate(dependent)


def test_restore_invalidates_leases_but_reuses_derivation():
    m=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');m.map('main',a)
    lease,b=m.select('main',Bindings());snapshot=m.snapshot()
    m.patch('main',a.identity,0,b'\x18');m.restore(snapshot)
    with pytest.raises(StaleSelection): m.validate(lease)
    fresh,c=m.select('main',Bindings())
    assert c.identity==b.identity and m.cache_hits==1 and m.recoveries==1
    assert m.validate(fresh)


def test_stale_expected_patch_does_not_modify_mapping():
    m=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');m.map('main',a)
    lease,_=m.select('main',Bindings())
    with pytest.raises(StaleSelection):m.patch('main','wrong',0,b'\x18')
    assert m.validate(lease)


def test_context_and_forged_lease_refuse():
    m=CodeMap();n=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');m.map('main',a)
    lease,_=m.select('main',Bindings())
    with pytest.raises(StaleSelection):n.validate(lease)
    with pytest.raises(StaleSelection):m.validate(replace(lease,block_identity='wrong'))
    with pytest.raises(Refused):n.restore(m.snapshot())


def test_mapping_mutation_inside_dispatch_refuses_before_write():
    m=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');m.map('main',a)
    lease,_=m.select('main',Bindings())
    with pytest.raises(Refused,match='during'):
        m.dispatch(lease,lambda b:m.patch('main',a.identity,0,b'\x18'))
    assert m.validate(lease).backing.identity==a.identity


def test_reentrant_dispatch_refuses():
    m=CodeMap();a=NativeBacking('image','A',0x8000,b'\xea');m.map('main',a)
    lease,_=m.select('main',Bindings())
    with pytest.raises(Refused,match='reentrant'):
        m.dispatch(lease,lambda b:m.dispatch(lease,lambda c:None))


def test_editable_uil_controls_output_and_does_not_mutate_backing(tmp_path):
    b=block('A9 01 48 A9 02 68 85 10')
    doc=b.document();doc['body'][0]['value']=3
    compiler=Path(shutil.which('gcc'))
    native=compile_c(doc,tmp_path/'native',compiler)
    assert native.run(b.state())['$result']==3
    assert evaluated(b)['$result']==1
    assert b.backing.code[1]==1


def test_source_backing_not_executed_by_c_target(tmp_path):
    b=block('A9 01 48 A9 02 68 85 10')
    text=emit_c(b.document())
    assert '6502' not in text and 'interpreter' not in text
    native=compile_c(b.document(),tmp_path/'native',Path(shutil.which('gcc')))
    assert native.run(b.state())['$result']==1
    assert not any(n in text for n in ('system(', 'fopen(', 'dlopen('))


def test_cpp_or_host_effect_is_not_silently_stubbed():
    doc=block('EA').document()
    doc['body']=[{'id':'click','op':'click','target':'door'}]
    with pytest.raises(Refused,match='required operation'):emit_c(doc)
    with pytest.raises(Refused,match='required operation'):emit_javascript(doc)


def test_generated_javascript_is_standalone(tmp_path):
    b=block('38 A9 FF 69 00 85 10')
    module=tmp_path/'generated.mjs';module.write_text(emit_javascript(b.document()))
    runner=tmp_path/'run.mjs';runner.write_text("import {run} from './generated.mjs';\nconsole.log(JSON.stringify(run("+json.dumps(b.state())+")));\n")
    result=subprocess.run([shutil.which('node'),str(runner)],check=True,capture_output=True,text=True)
    actual=json.loads(result.stdout)
    expected=execute_il(b.document(),b.state())['state']
    assert actual==expected and actual['$result']==0 and actual['$carry'] is True


def test_native_rejection_preserves_output(tmp_path):
    import ctypes
    b=block('EA');native=compile_c(b.document(),tmp_path/'native',Path(shutil.which('gcc')))
    length=len(native.names);array=ctypes.c_uint32*length
    input=array(*[0]*length);output=array(*[12345]*length)
    input[native.names.index('$carry')]=2
    assert native.function(input,length,output,length)==2
    assert list(output)==[12345]*length


def test_private_temp_collision_refuses():
    with pytest.raises(Refused):block('EA',ram=((0x10,'tmp_0'),))


def test_edited_return_dict_cannot_mutate_immutable_document():
    b=block('A9 01');doc=b.document();doc['body'][0]['value']=2
    assert evaluated(b)['$value']==1


def test_first_divergence_reports_earliest_observed_difference():
    d=first_difference([{'x':1},{'x':2},{'x':3}],[{'x':1},{'x':4},{'x':5}],('x',))
    assert (d.event,d.field,d.expected,d.actual)==(1,'x',2,4)


def test_boolean_is_not_silently_numeric():
    assert first_difference([{'x':True}],[{'x':1}],('x',)).reason=='type or value'


def test_missing_is_not_equal_to_absent_on_both_sides():
    d=first_difference([{}],[{}],('x',))
    assert d.reason=='missing observation' and not d.expected_present and not d.actual_present


def test_comparison_budget_exhaustion_is_not_success():
    with pytest.raises(Refused,match='budget'):
        first_difference([{'x':1}]*3,[{'x':1}]*3,('x',),max_events=2)
    assert first_difference([{'x':1}]*2,[{'x':1}]*2,('x',),max_events=2) is None


def test_dropped_event_is_detected():
    d=first_difference([{'x':1}],[{'x':1},{'x':2}],('x',))
    assert d.reason=='event count' and d.event==1


def test_c_range_checked_assignment_does_not_silently_wrap(tmp_path):
    doc={'format':'fdisbull-il-1','role':'uil','variables':{
        '$wide':{'type':'u16','initial':256},'$small':{'type':'u8','initial':99}},
        'resources':{},'body':[{'id':'narrow','op':'set','var':'$small','value':{'var':'$wide'}}]}
    assert execute_il(doc)['status']=='refused'
    native=compile_c(doc,tmp_path/'native',Path(shutil.which('gcc')))
    with pytest.raises(Refused,match='rejected'):
        native.run({'$wide':256,'$small':99})


def test_branch_can_skip_pop_only_when_all_exits_are_balanced():
    with pytest.raises(Refused,match='restore'):
        block('48 F0 01 68')


def test_same_bytes_different_binding_cannot_reuse_old_derivation():
    m=CodeMap();source=NativeBacking('image','A',0x8000,bytes.fromhex('A9 01 85 10'))
    m.map('main',source)
    first,a=m.select('main',Bindings(((0x10,'left'),)))
    second,b=m.select('main',Bindings(((0x10,'right'),)))
    assert a.identity!=b.identity and m.recoveries==2
    assert '$left' in a.public_names and '$right' in b.public_names


def test_patch_updates_semantics_and_invalidates_old_selection():
    m=CodeMap();source=NativeBacking('image','A',0x8000,bytes.fromhex('A9 01 85 10'))
    m.map('main',source);old,a=m.select('main',Bindings(((0x10,'result'),)))
    changed=m.patch('main',source.identity,1,b'\x05')
    new,b=m.select('main',Bindings(((0x10,'result'),)))
    assert evaluated(a)['$result']==1 and evaluated(b)['$result']==5
    assert source.identity!=changed.identity
    with pytest.raises(StaleSelection):m.validate(old)
    assert m.validate(new)


def test_source_lease_rejects_wrong_target_semantics(tmp_path):
    m=CodeMap();source=NativeBacking('image','A',0x8000,bytes.fromhex('A9 01 85 10'))
    m.map('main',source);lease,b=m.select('main',Bindings(((0x10,'result'),)))
    edited=b.document();edited['body'][0]['value']=2
    native=compile_c(edited,tmp_path/'wrong',Path(shutil.which('gcc')))
    with pytest.raises(Refused,match='semantic revision'):
        m.execute(lease,native,b.state())


def test_modified_checkpoint_refuses_without_changing_live_authority():
    m=CodeMap();source=NativeBacking('image','A',0x8000,b'\xea');m.map('main',source)
    lease,_=m.select('main',Bindings());checkpoint=m.snapshot()
    with pytest.raises(Refused,match='modified'):
        m.restore(replace(checkpoint,bindings=()))
    assert m.validate(lease)


def test_modified_native_metadata_refuses(tmp_path):
    b=block('A9 01')
    native=compile_c(b.document(),tmp_path/'native',Path(shutil.which('gcc')))
    native.document['body'][0]['value']=2
    with pytest.raises(Refused,match='metadata'):
        native.run(b.state())


def test_retained_output_is_exact_for_either_role():
    b=block('A9 01 48 A9 02 68 85 10')
    assert emit_retained(b,b.document())==b.backing.code
    assert emit_retained(b,b.document('udl'))==b.backing.code


def test_retained_output_does_not_ignore_a_semantic_edit():
    b=block('A9 01');edited=b.document();edited['body'][0]['value']=2
    with pytest.raises(Refused,match='edited UIL'):
        emit_retained(b,edited)


def test_supported_decoder_entries_match_packaged_capstone():
    capstone=pytest.importorskip('capstone')
    from fdisbull.console_synthesis.recover import OPS
    decoder=capstone.Cs(capstone.CS_ARCH_MOS65XX,capstone.CS_MODE_MOS65XX_6502)
    for opcode,(name,mode,size) in OPS.items():
        raw=bytes([opcode])+bytes([0x10,0x80])[:size-1]
        decoded=list(decoder.disasm(raw,0x8000))
        assert len(decoded)==1 and decoded[0].mnemonic==name and decoded[0].size==size
