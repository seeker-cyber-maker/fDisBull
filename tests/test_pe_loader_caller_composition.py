"""Caller theorem joins must retain their entry bindings and typed effects."""
from copy import deepcopy
import hashlib
import time

import pytest
z = pytest.importorskip('z3')

from fdisbull.pe_loader_caller_joins import join_caller_contract
from fdisbull.pe_loader_module_recovery import (
    ENVIRONMENT, VERIFIED_LOADER_ENVIRONMENT, VERIFIED_CALLER_ENVIRONMENT,
    _bind_loader_source, recover_loader_module,
)
from fdisbull.runtime_loader_analysis import _require_loader_boundary_overlap, load_loader_evidence


def test_caller_profile_retains_the_unchanged_loader_assumptions():
    assert set(VERIFIED_CALLER_ENVIRONMENT) == set(ENVIRONMENT)
    for key in ('initial_iat_binding', 'wine_api_frame', 'termination', 'segment_binding'):
        assert VERIFIED_CALLER_ENVIRONMENT[key] == ENVIRONMENT[key] == VERIFIED_LOADER_ENVIRONMENT[key]


@pytest.mark.parametrize('key', list(ENVIRONMENT))
def test_missing_caller_environment_requirement_cannot_qualify(key):
    incomplete = dict(VERIFIED_CALLER_ENVIRONMENT); del incomplete[key]
    result = recover_loader_module(None, None, {}, environment_contract=incomplete, loader_source=b'bytes')
    assert result['status'] == 'unknown' and 'Explicit loader' in result['reason']


def test_caller_intervals_cannot_substitute_for_dispatcher_proofs():
    with pytest.raises(ValueError, match='also requires verified dispatcher'):
        load_loader_evidence(None, None, {}, require_loader_intervals=True)


def test_caller_source_identity_cannot_borrow_a_valid_dispatcher_source_hash():
    source = b'original source identity'
    sha = hashlib.sha256(source).hexdigest()
    bound = {'report': {'loader_selection': {'source': {'source_sha256': sha}}},
             'loader_capsules': [{'capsule': {'loader_module': {'source_sha256': sha}}}],
             'loader_intervals': [{'interval': {'loader_module': {'source_sha256': '0' * 64}}}]}
    with pytest.raises(ValueError, match='native selected source identity'):
        _bind_loader_source(bound, source)


@pytest.mark.parametrize('address', [0x2068, 0x2fb0])
def test_equal_registers_and_application_bytes_cannot_hide_changed_metadata_or_return_word(address):
    left = [{'address': '0x1000', 'hex': '01020304'}, {'address': hex(address), 'hex': '1122334455667788'}]
    right = deepcopy(left)
    assert _require_loader_boundary_overlap(left, right) == 12
    right[1]['hex'] = '9922334455667788'
    with pytest.raises(ValueError, match='metadata or stack'):
        _require_loader_boundary_overlap(left, right)


def _tail():
    symbols = {'interval_entry_rsp': 64, 'interval_entry_r12': 64,
               'interval_entry_rax': 64, 'interval_entry_flags': 32}
    a, b, c, f = (z.BitVec(n, symbols[n]) for n in symbols)
    guard = z.And(a == 0x3008, b == 0x20a0, z.Extract(31, 0, c) == 0, f & 2 == 2)
    caller = {'symbols': symbols, 'transfer': {'entry_guard': guard.sexpr()}}
    module = {'symbols': {'loader_entry_rsp': 64, 'loader_entry_r12': 64, 'loader_entry_flags': 32},
              'transfer': {'registers': {'rsp': '(bvadd loader_entry_rsp #x0000000000000008)',
                                         'r12': 'loader_entry_r12', 'rax': '#x0000000000000000'},
                           'flags': 'loader_entry_flags'}}
    capsule = {'selection': {'modref': '0x2000'}, 'entry': {'general': {'rsp': '0x3000'}}}
    return {'role': 'attach_success_tail', 'interval': {}}, caller, {'addresses': {'modref': '0x2000'}}, {'capsule': capsule, 'proof': module}


def _join(inputs):
    return join_caller_contract(z, *inputs, deadline=time.monotonic() + 10)


def test_tail_join_reports_the_layout_requirement_instead_of_inventing_a_caller_entry_proof():
    result = _join(_tail())
    assert result['status'] == 'proved_under_explicit_caller_layout'
    assert result['required_outer_entry_bindings'] == {'module_entry_r12': '0x20a0'}


@pytest.mark.parametrize('field,expression', [('rax', '#x0000000000000001'),
    ('r12', '#x0000000000002000'), ('rsp', '(bvadd loader_entry_rsp #x0000000000000010)')])
def test_tail_cannot_borrow_bool_success_wrong_layout_or_an_unbalanced_frame(field, expression):
    inputs = _tail(); inputs[-1]['proof']['transfer']['registers'][field] = expression
    with pytest.raises(ValueError, match='precondition'):
        _join(inputs)


def test_tail_cannot_hide_an_extra_sample_only_guard():
    inputs = _tail(); proof = inputs[1]
    proof['symbols']['interval_entry_r14'] = 64
    proof['transfer']['entry_guard'] = '(and ' + proof['transfer']['entry_guard'] + ' (= interval_entry_r14 #x0000000000000000))'
    with pytest.raises(ValueError, match='precondition'):
        _join(inputs)


def _prefix(flags=0x80004):
    names = {f'interval_entry_ram_{a:x}': 8 for a in range(0x2068, 0x206c)}
    names.update(interval_entry_rsp=64, interval_entry_flags=32)
    parts = [z.BitVec(f'interval_entry_ram_{a:x}', 8) for a in reversed(range(0x2068, 0x206c))]
    incoming = z.Concat(*parts); outgoing = incoming & 0xfff7ffff
    stack = z.BitVec('interval_entry_rsp', 64); cpu_flags = z.BitVec('interval_entry_flags', 32)
    transfer = {'entry_guard': z.And(stack == 0x3000, cpu_flags & 2 == 2, incoming & 0x80000 != 0).sexpr(),
        'registers': {'rcx': '#x0000000000002000', 'rdx': '#x0000000000000000',
                      'r8': '#x0000000000000001', 'rsp': (stack - 0x50).sexpr()},
        'metadata_memory': {hex(0x2068 + k): z.Extract(8 * k + 7, 8 * k, outgoing).sexpr() for k in range(4)},
        'pending_call': {'target': '#x0000000000006000', 'return_address': '0x6060'},
        'defined_flags_mask': 0xffffffef, 'flags': cpu_flags.sexpr()}
    interval = {'entry_memory': [{'address': '0x2068', 'hex': flags.to_bytes(4, 'little').hex()}]}
    capsule = {'selection': {'modref': '0x2000'}, 'entry': {'rip': '0x6000',
        'general': {'rcx': '0x2000', 'rdx': '0x0', 'r8': '0x1', 'rsp': '0x2fb0'}},
        'entry_memory': [{'address': '0x2068', 'hex': '04000000'}], 'return_address': '0x6060'}
    return {'role': 'detach_selection_prefix', 'interval': interval}, {'symbols': names, 'transfer': transfer}, \
           {'addresses': {'modref': '0x2000'}}, {'capsule': capsule, 'proof': {}}


def test_generic_selector_requires_explicit_metadata_specialization_to_join_a_fixed_module_path():
    result = _join(_prefix())
    assert result['status'] == 'proved_under_explicit_metadata_specialization'
    assert result['required_outer_metadata_bindings'] == [{'address': '0x2068', 'hex': '04000800'}]


@pytest.mark.parametrize('flags', [0x40080004, 4])
def test_attached_predicate_alone_does_not_establish_module_metadata_or_a_feasible_guard(flags):
    with pytest.raises(ValueError, match='precondition'):
        _join(_prefix(flags))


@pytest.mark.parametrize('field,value', [('rcx', '#x0000000000002100'), ('r8', '#x0000000000000002')])
def test_selector_must_establish_actual_wm_and_reserved_argument(field, value):
    inputs = _prefix(); inputs[1]['transfer']['registers'][field] = value
    with pytest.raises(ValueError, match='precondition'):
        _join(inputs)
