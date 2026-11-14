"""Contract composition checks independent of a live guest."""
from copy import deepcopy

import pytest
z = pytest.importorskip('z3')

from fdisbull.pe_dll_contracts import validate_dll_callback
from fdisbull.pe_loader_module_recovery import (
    ENVIRONMENT, _cells, _instantiate_dll_transfer, expand_loader_module_contraction,
    recover_loader_module, _require_owned_poststate, _admit_call_binding,
)
from fdisbull.pe_region_equivalence import _digest
from test_pe_dll_contracts import _path, DATA, STACK


def test_composition_does_not_silently_assume_loader_or_exit_contracts():
    for key in ENVIRONMENT:
        missing = dict(ENVIRONMENT); del missing[key]
        result = recover_loader_module(None, None, {}, environment_contract=missing)
        assert result['status'] == 'unknown' and result['whole_module_recovery'] is None
        assert 'Explicit loader' in result['reason']


def test_generic_report_transfer_is_instantiated_with_the_callers_actual_state():
    observation, contract = _path('report', data=(2).to_bytes(4, 'little') + bytes(60))
    proof = validate_dll_callback(observation, contract=contract)
    assert proof['status'] == 'proved_for_authored_dll_callback', proof
    names = proof['transfer']['registers']
    registers = {n: z.BitVec('caller_' + n, 64) for n in names}
    registers['rsp'] = z.BitVecVal(STACK, 64)
    flags = z.BitVec('caller_flags', 32)
    initial = _cells(contract['entry_memory'])
    memory = {a: z.BitVecVal(b, 8) for a,b in initial.items()}
    transfer = _instantiate_dll_transfer(z, proof, registers, flags, memory)
    assert z.simplify(transfer['registers']['rsp']).as_long() == STACK + 8
    assert z.simplify(transfer['registers']['rax']).as_long() == 1
    assert transfer['registers']['rbx'].eq(registers['rbx'])
    assert z.simplify(transfer['memory'][DATA]).as_long() == 3
    assert z.simplify(transfer['memory'][DATA + 32 + 2*4]).as_long() == 0x33
    assert transfer['accesses'][-1]['kind'] == 'read'
    assert transfer['accesses'][-1]['width'] == 8


def test_a_callback_cannot_read_an_omitted_caller_return_word():
    observation, contract = _path('report')
    proof = validate_dll_callback(observation, contract=contract)
    registers = {n:z.BitVec('caller_'+n,64) for n in proof['transfer']['registers']}
    memory = {a:z.BitVecVal(b,8) for a,b in _cells(contract['entry_memory']).items() if a != STACK}
    with pytest.raises(ValueError, match='undeclared main RAM'):
        _instantiate_dll_transfer(z,proof,registers,z.BitVec('caller_flags',32),memory)


def test_contraction_retains_exact_source_reference_bundle_and_contracts():
    evidence = {'run': 'source', 'callback': 'immutable-artifact'}
    body = {'format':'fdisbull-loader-module-contraction-1','evidence_sha256':_digest(evidence),
            'environment_contract':dict(ENVIRONMENT)}
    contraction = body | {'sha256':_digest(body)}
    assert expand_loader_module_contraction(contraction,evidence)==evidence
    for changed in (evidence | {'run':'foreign'}, evidence | {'callback':'replacement'}):
        with pytest.raises(ValueError):expand_loader_module_contraction(contraction,changed)
    forged=deepcopy(contraction);forged['environment_contract']['termination']='assumed_return'
    with pytest.raises(ValueError):expand_loader_module_contraction(forged,evidence)


def test_sample_equal_store_cannot_establish_a_universal_teardown_precondition():
    rbx=z.BitVec('application_entry_rbx',64)
    memory={0x1000:z.Extract(7,0,rbx)}
    # This hostile store preserves the observed zero byte at RBX=0, while it
    # changes the DLL state for other admitted entry registers.
    assert z.simplify(z.substitute(memory[0x1000],(rbx,z.BitVecVal(0,64)))).as_long()==0
    def prove(claim):
        solver=z.Solver();solver.add(z.Not(claim))
        if solver.check()!=z.unsat:raise ValueError('not universal')
    with pytest.raises(ValueError,match='universal DLL/code state'):
        _require_owned_poststate(z,memory,{0x1000:0},prove)
    _require_owned_poststate(z,{0x1000:z.BitVecVal(0,8)},{0x1000:0},prove)


def _call_binding():
    call={'name':'SetLastError','callsite':'0x1000','return_address':'0x1006',
          'iat_address':'0x3000','target':'0x2000','entry':None}
    imported={'name':call['name'],'callsite':call['callsite'],'return_address':call['return_address'],
              'runtime_iat_address':call['iat_address'],'target':call['target']}
    bound={'exe':{'imports':{'SetLastError':{'iat_address':'0x3000'},'GetLastError':{'iat_address':'0x3008'}}},
        'report':{'recovery':{'entry':'entry','bindings':'bindings'}},
        'documents':{'entry':{'memory':[{'address':'0x3000','hex':(0x2000).to_bytes(8,'little').hex()}]},
                     'bindings':{'imports':[{'name':'SetLastError','iat_address':'0x3000','target':'0x2000'}]}}}
    return bound,call,{'import':imported}


@pytest.mark.parametrize('field,value',[('name','GetLastError'),('runtime_iat_address','0x3008'),
    ('target','0x2010'),('callsite','0x1010'),('return_address','0x1016')])
def test_equal_state_api_cannot_borrow_another_name_slot_target_or_frame(field,value):
    bound,call,document=_call_binding();_admit_call_binding(bound,call,document)
    document['import'][field]=value
    with pytest.raises(ValueError,match='verified implementation'):
        _admit_call_binding(bound,call,document)


def test_import_resolution_ledger_cannot_replace_the_actual_entry_iat_snapshot():
    bound,call,document=_call_binding()
    bound['documents']['entry']['memory'][0]['hex']=(0x2010).to_bytes(8,'little').hex()
    with pytest.raises(ValueError,match='Entry snapshot IAT'):
        _admit_call_binding(bound,call,document)
