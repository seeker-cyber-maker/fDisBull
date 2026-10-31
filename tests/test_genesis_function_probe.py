"""The native probe's input contract must bound actual execution explicitly."""
import copy
from pathlib import Path
import runpy

import pytest


PROBE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/probe_genesis_function.py'))


def contract():
    return {'entry': 0x200, 'code_ranges': [{'start': 0x200, 'end': 0x210}],
            'registers': {'A0': 0xff1000}, 'ram': [{'address': 0xff1000, 'data': '1b000001'}],
            'watch': [{'name': 'object', 'address': 0xff1000, 'length': 4}],
            'max_instructions': 16, 'max_master_cycles': 10000}


def test_batch_overrides_inputs_without_mutating_common_contract():
    value = contract()
    value['cases'] = [{'name': 'zero', 'registers': {'D0': 7}, 'ram': []},
                      {'name': 'one', 'ram': [{'address': 0xff1003, 'data': '01'}]}]
    original = copy.deepcopy(value)
    cases = PROBE['expand_contracts'](value, 32768)
    assert cases[0]['registers'] == {'A0': 0xff1000, 'D0': 7}
    assert cases[0]['ram'] == []
    assert cases[1]['ram'] == [{'address': 0xff1003, 'data': '01'}]
    assert value == original


def test_explicit_exit_is_distinct_from_return_sentinel():
    value = contract()
    value['stop_pcs'] = [0x210]
    assert PROBE['validate_contract'](value, 32768)
    value['return_address'] = 0xfffd00
    with pytest.raises(ValueError, match='conflicting'):
        PROBE['validate_contract'](value, 32768)


@pytest.mark.parametrize('change', [
    {'entry': True}, {'entry': 0x201}, {'stop_pcs': [0x200]},
    {'code_ranges': [{'start': 0x200, 'end': 0x210}, {'start': 0x20e, 'end': 0x220}]},
    {'code_ranges': [{'start': 0x200, 'end': 0x20200}]},
    {'max_instructions': 0}, {'max_master_cycles': True},
    {'registers': {'PC': 0x200}}, {'registers': {'A7': 0xfffe00}},
    {'ram': [{'address': 0xfffe00, 'data': '00000000'}]},
    {'ram': [{'address': 0xff1000, 'data': 'zz'}]},
    {'watch': [{'name': 'bad', 'address': 0xffffff, 'length': 2}]},
])
def test_refuses_ambiguous_unbounded_or_invalid_native_inputs(change):
    value = {**contract(), **change}
    with pytest.raises(ValueError):
        PROBE['validate_contract'](value, 0x400000)


def test_batch_budget_and_duplicate_names_are_refused():
    value = contract()
    value['max_instructions'] = 100000
    value['cases'] = [{'name': 'a'}, {'name': 'b'}]
    with pytest.raises(ValueError, match='combined'):
        PROBE['expand_contracts'](value, 32768)
    value['max_instructions'] = 16
    value['cases'][1]['name'] = 'a'
    with pytest.raises(ValueError, match='unique'):
        PROBE['expand_contracts'](value, 32768)


def test_private_output_must_be_fresh_outside_git(tmp_path):
    PROBE['_private_output'](tmp_path / 'fresh')
    with pytest.raises(ValueError, match='fresh'):
        PROBE['_private_output'](tmp_path)
    (tmp_path / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='Git'):
        PROBE['_private_output'](tmp_path / 'fresh')
