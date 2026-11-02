"""Immutable table reads preserve types, bounds and atomic execution."""
import copy
import pytest
from fdisbull.interaction_il import ILInvalid, execute_il, validate_il


def program():
    return {'format':'fdisbull-il-1','role':'uil','resources':{},
        'variables':{'$index':{'type':'u8','initial':1},'$out':{'type':'u16','initial':7}},
        'tables':{'samples':{'type':'u16','values':[0,65535]}},
        'body':[{'id':'read','op':'lookup','var':'$out','table':'samples','index':{'var':'$index'}}]}


def test_typed_lookup_returns_data_without_effects_or_mutating_source():
    p=program();before=copy.deepcopy(p)
    r=execute_il(p)
    assert r['complete'] and r['state']=={'$index':1,'$out':65535}
    assert r['events']==[] and p==before


def test_dynamic_bounds_failure_rolls_back_preceding_work():
    p=program();p['body'].insert(0,{'id':'increment','op':'add','var':'$out','value':1})
    initial={'$index':2,'$out':7};r=execute_il(p,initial)
    assert not r['complete'] and r['state']==initial and r['events']==[]
    assert 'index out of range' in r['error']


@pytest.mark.parametrize('mutate',[
    lambda p:p['tables']['samples'].update(values=[]),
    lambda p:p['tables']['samples'].update(values=[-1]),
    lambda p:p['tables']['samples'].update(type='i16'),
    lambda p:p['body'][0].update(table='missing'),
    lambda p:p['body'][0].update(index=True),
    lambda p:p['body'][0].update(index=2),
    lambda p:p['variables']['$out'].update(type='u8'),
])
def test_invalid_table_contracts_are_refused(mutate):
    p=program();mutate(p)
    with pytest.raises(ILInvalid):validate_il(p)
