"""Bounded authored Five-Dice UIL variants; no private-source fidelity claim."""
import pytest

# Source examples are deliberately omitted from release distributions.
pytest.importorskip("examples", reason="source-checkout examples are not packaged")

from examples.udc.game_variants.five_dice import contract, turn_program, variants
from fdisbull.interaction_il import execute_il
from fdisbull.udc_qualify import qualify_uil
from fdisbull.project import Project
from fdisbull.udc_layers import register_contract, register_layer, select_layers
from fdisbull.udc_blueprint import execute_module_uil


def test_three_distinct_uil_programs_match_for_every_u16_seed():
    c = contract()
    impls = variants()
    assert len({str(p['body']) for p in impls.values()}) == 3
    counts = {name: len(program['body']) for name, program in impls.items()}
    assert counts['compact'] < counts['clean'] < counts['verbose']
    for program in impls.values():
        result = qualify_uil(c, {'backend': 'uil', 'program': program})
        # Solver-backed proof is optional in lightweight installs; exhaustive
        # execution below remains the independent full-u16 check.
        assert result['status'] in ('equivalent_under_contract', 'unknown')
        if result['status'] == 'unknown':
            assert 'solver is unavailable' in result['reason']
    for seed in range(65536):
        observed = [execute_il(p, {'$seed': seed, '$next': 0, '$scratch': 0}) for p in impls.values()]
        expected = (5 * seed + 1) % 65536
        assert all(r['complete'] and r['state']['$next'] == expected for r in observed)


def test_turn_program_invokes_selected_implementation_for_five_faces(tmp_path):
    raw = tmp_path / 'five-dice.bin'
    raw.write_bytes(b'\xc3' + bytes(31))
    with Project.create(tmp_path / 'five-dice.fdb', raw, arch='x86', bits=16, base=0x1000) as p:
        c = register_contract(p, contract())
        layer_ids = {}
        for name, implementation in variants().items():
            layer = register_layer(p, {
                'format': 'fdisbull-udl-layer-1', 'name': 'authored-' + name,
                'contract': c['id'], 'implementation': {'backend': 'uil', 'program': implementation},
            })
            layer_ids[name] = layer['id']
        chosen = ('clean', 'compact', 'verbose', 'clean', 'compact')
        program = turn_program(c['id'], chosen)
        selection = select_layers(p, 'five-dice-example',
                                  {name: layer_ids[name] for name in variants()}, program=program)
        result = execute_module_uil(p, program, selection['id'])
        assert result['status'] == 'complete'
        assert [result['state'][f'$face{i}'] for i in range(1, 6)] == [1, 2, 1, 2, 1]
