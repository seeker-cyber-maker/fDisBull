"""Bounded notification semantics and model-level equivalence."""
import shutil

import pytest

# Source examples are deliberately omitted from release distributions.
pytest.importorskip("examples", reason="source-checkout examples are not packaged")

from examples.udc.game_variants.tic_tac_toe import contract, variants
from fdisbull.interaction_il import execute_il
from fdisbull.udc_c import compile_c
from fdisbull.udc_qualify import qualify_uil


@pytest.mark.parametrize('name', ['clean', 'compact', 'verbose'])
def test_messages_and_invalid_combinations(name):
    program = variants()[name]
    cases = {(0, 0): 0, (1, 1): 1, (1, 2): 2, (2, 0): 3,
             (0, 1): 65535, (1, 0): 65535, (1, 3): 65535,
             (2, 1): 65535, (3, 0): 65535, (255, 255): 65535}
    for (status, player), expected in cases.items():
        result = execute_il(program, state={'$status': status, '$player': player, '$message': 0})
        assert result['complete'] and result['state']['$message'] == expected


def test_variants_are_distinct_and_qualified_over_full_typed_domain():
    pytest.importorskip('z3')
    programs = variants()
    assert len({str(program['body']) for program in programs.values()}) == 3

    def node_count(body):
        return sum(1 + (node_count(node['then']) + node_count(node['else'])
                        if node['op'] == 'if' else 0) for node in body)

    counts = {name: node_count(program['body']) for name, program in programs.items()}
    assert counts['compact'] < counts['clean'] < counts['verbose']
    for name, program in programs.items():
        result = qualify_uil(contract(), {'backend': 'uil', 'program': program})
        assert result['status'] == 'equivalent_under_contract'
        if name != 'clean':
            assert result['method'] == 'bounded-scalar-z3'
            assert result['reference_completion_possible'] is True


@pytest.mark.parametrize('name', ['clean', 'compact', 'verbose'])
def test_c_compiler_accepts_scalar_program(name):
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('clang unavailable')
    module = {'backend': 'c-uil', 'program': variants()[name], 'return': '$message',
              'state_adapter': {'inputs': ['$status', '$player'], 'outputs': ['$message']}}
    result = compile_c(module, compiler)
    assert result['code_hex'] and result['inputs'] == ['$status', '$player']
    assert result['outputs'] == ['$message']
