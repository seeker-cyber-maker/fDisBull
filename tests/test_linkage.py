"""Declared import identities join generic call expressions without execution."""
import pytest
from fdisbull.linkage import import_call_bindings,metadata_symbols,canonical_library_name


def node(flow='indirect_call'):
    return dict(id='cpu:64@0x1000',address='0x1000',context='cpu:64',flow=flow)


def test_direct_stub_is_joined_to_slot_without_a_runtime_pointer_value():
    n=node('call');imports=[dict(name='copy',module='libcopy',address=0x3000,stub_addresses=[0x2000])]
    graph=dict(nodes=[n],calls=[dict(source=n['id'],target_address='0x2000')])
    bindings=import_call_bindings(graph,{},dict(stable=False),imports,8)
    assert len(bindings)==1
    assert (bindings[0]['slot'],bindings[0]['stub'],bindings[0]['external_target'])==(0x3000,0x2000,None)
    assert bindings[0]['source_address']=='0x1000' and not bindings[0]['runtime_observed']


def test_register_loaded_from_declared_slot_is_recognized_in_generic_state():
    n=node();expr=dict(op='load',address=dict(op='const',value=0x3000),width=8,signed=False)
    sem={n['id']:dict(indirect_target=dict(op='reg',name='callee'))}
    flow=dict(stable=True,in_states={n['id']:dict(registers=dict(callee=expr))})
    result=import_call_bindings(dict(nodes=[n]),sem,flow,[dict(name='copy',address=0x3000)],8)
    assert len(result)==1 and result[0]['slot']==0x3000 and result[0]['stub'] is None


@pytest.mark.parametrize('mutation',['incomplete','width','signed','address_of_slot','unknown'])
def test_incomplete_or_nonpointer_evidence_does_not_identify_an_import(mutation):
    n=node();expr=dict(op='load',address=dict(op='const',value=0x3000),width=8,signed=False)
    flow=dict(stable=True,in_states={n['id']:dict(registers=dict(callee=expr))})
    if mutation=='incomplete':flow['stable']=False
    elif mutation=='width':expr['width']=4
    elif mutation=='signed':expr['signed']=True
    elif mutation=='address_of_slot':flow['in_states'][n['id']]['registers']['callee']=dict(op='const',value=0x3000)
    else:flow['in_states'][n['id']]['registers'].clear()
    assert import_call_bindings(dict(nodes=[n]),{n['id']:dict(indirect_target=dict(op='reg',name='callee'))},flow,[dict(name='copy',address=0x3000)],8)==[]


def test_zero_slot_is_preserved_and_stub_identity_stays_separate():
    rows=list(metadata_symbols(dict(imports=[dict(name='_copy',address=0,stub_addresses=[0x2000])],exports=[])))
    assert [(a,k) for a,k,_ in rows]==[(0,'imports'),(0x2000,'import_stubs')]
    assert rows[1][2]['slot_address']==0 and rows[1][2]['address_kind']=='code_stub'
    assert canonical_library_name('_memcpy','Mach-O')=='memcpy'
    assert canonical_library_name('memcpy@GLIBC_2.14','ELF')=='memcpy'
    assert canonical_library_name('_memcpy','raw')=='_memcpy'


def test_data_imports_do_not_become_callable_identities():
    n=node();expression=dict(op='load',address=dict(op='const',value=0x3000),width=8)
    flow=dict(stable=True,in_states={n['id']:dict(registers=dict(callee=expression))})
    imports=[dict(name='object',address=0x3000,stub_addresses=[0x2000],callable=False)]
    assert import_call_bindings(dict(nodes=[n]),{n['id']:dict(indirect_target=dict(op='reg',name='callee'))},flow,imports,8)==[]
