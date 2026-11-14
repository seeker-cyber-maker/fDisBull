"""Contract composition checks independent of a live guest."""
from copy import deepcopy

import pytest
z = pytest.importorskip('z3')

from fdisbull.pe_dll_contracts import validate_dll_callback
from fdisbull.pe_loader_module_recovery import (
    ENVIRONMENT, _cells, _instantiate_dll_transfer, expand_loader_module_contraction,
    recover_loader_module,
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
