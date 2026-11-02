"""Behavioral examples qualify only the declared source/model/output edges."""
from copy import deepcopy
import hashlib
import shutil

import pytest

from fixtures_common_uil import (
    food_bundle, food_expected, food_vectors,
    memory_bundle, mini_expected, mini_initial, mini_snake_program,
    orchestration, run_emitted, synthetic_bundle,
)
from fdisbull.common_uil import digest, validate_orchestration, validate_presentation, validate_program
from fdisbull.uil_catalog import build_catalog, import_udl
from fdisbull.uil_codegen import compile_program
from fdisbull.uil_runtime import execute_program

EMPTY = {'format': 'fdisbull-uil-catalog-1', 'groups': [], 'rejected': []}


def test_mixed_source_list_groups_explicit_u16_projections_then_builds_new_program():
    program, view, catalog, group = synthetic_bundle()
    assert len(catalog['groups']) == 2
    assert not catalog['rejected']
    assert {i['language'] for i in group['implementations']} == {'c-u16', 'python-u16', 'x86-16'}
    assert validate_program(program) and validate_presentation(program, view)
    frozen = (digest(program), digest(view))
    for impl in group['implementations']:
        plan = orchestration(program, impl['id'])
        qualified = validate_orchestration(program, catalog, plan)
        assert qualified['shims'][0]['inputs'][0]['ownership'] == 'copy'
        for x in (0, 1, 65527, 65528, 65535):
            result = execute_program(program, view, plan, catalog, inputs=[x])
            assert result['status'] == 'complete'
            assert result['outputs'] == [(x + 8) & 65535]
            # The helper mutates its own frame; the caller's original port survives.
            assert result['state'] == [x, (x + 8) & 65535]
            assert result['calls'][0]['implementation'] == impl['id']
            assert result['calls'][0]['outputs'] == [(x + 1) & 65535]
        assert frozen == (digest(program), digest(view))


def test_changed_logic_cannot_be_selected_as_an_equivalent_implementation():
    program, view, catalog, group = synthetic_bundle()
    variant = next(g for g in catalog['groups'] if g['semantic_id'] != group['semantic_id'])
    with pytest.raises(ValueError, match='different semantic contract'):
        execute_program(program, view, orchestration(program, variant['implementations'][0]['id']), catalog, inputs=[12])


def test_unbounded_python_and_observable_assembly_flags_do_not_gain_equivalence():
    specs = [{'language': 'python-u16', 'source_text': 'ax += 1', 'inputs': ['ax'], 'outputs': ['ax']}]
    result = build_catalog(specs)
    assert not result['groups'] and len(result['rejected']) == 1
    program, _, _, group = synthetic_bundle()
    imported = import_udl({'language': 'x86-16', 'code': '40'})
    assert len(imported['function']['outputs']) > len(program['imports'][0]['outputs'])
    assert group['semantic_id'].startswith('semantic:')


def test_host_effect_is_a_deferred_plan_and_keeps_original_state():
    program, view, catalog, group = synthetic_bundle(host_effect=True)
    plan = orchestration(program, group['implementations'][0]['id'])
    result = execute_program(program, view, plan, catalog, inputs=[65535])
    assert result['status'] == 'pending_host'
    assert result['outputs'] == []
    assert result['state'] == [65535, 0]
    assert result['proposed_state'] == [65535, 7]
    assert result['events'][0]['service'] == 'text.show'
    assert result['events'][0]['resource'] == view['resources'][0]


def test_real_food_semantics_over_the_public_2018_vector_matrix():
    program, view = food_bundle()
    cases = food_vectors()
    assert len(cases) == 2018
    for inputs in cases:
        result = execute_program(program, view, inputs=inputs)
        assert result['status'] == 'complete', inputs
        assert result['outputs'] == [food_expected(inputs)], inputs
    # In particular, signed byte widening happens before multiplication.
    assert food_expected([10, 12, -128, 3, 2]) == 272
    assert food_expected([32767, 1, 0, 0, 1]) == -32768


@pytest.mark.parametrize('cost', [0, 3, -1, 32767])
def test_food_domain_guard_refuses_atomically(cost):
    program, view = food_bundle()
    inputs = [123, 456, -128, 42, cost]
    result = execute_program(program, view, inputs=inputs)
    assert result['status'] == 'refused' and result['outputs'] == [] and result['events'] == []
    for slot, value in zip(program['functions'][0]['inputs'], inputs):
        assert result['state'][slot] == value
    assert result['state'][program['functions'][0]['outputs'][0]] == 0


def test_authored_movement_and_raster_are_independently_predicted_at_every_cell():
    legacy = mini_snake_program()
    step, step_view = memory_bundle(legacy, 'step')
    render, render_view = memory_bundle(legacy, 'render')
    for x in range(5):
        for y in range(4):
            for direction in range(4):
                for alive in (0, 1):
                    words = mini_initial()
                    words[:5] = [x, y, direction, alive, 0xffffffff]
                    words[5:7] = [(x + 1) % 5, y]
                    saved = list(words)
                    expected = mini_expected(words, 'step')
                    actual = execute_program(step, step_view, inputs=[words])
                    assert actual['status'] == 'complete' and actual['outputs'] == [expected]
                    assert words == saved
                    rendered = execute_program(render, render_view, inputs=[expected])
                    assert rendered['status'] == 'complete'
                    assert rendered['outputs'] == [mini_expected(expected, 'render')]
                    assert rendered['outputs'][0][63] == 0xdeadbeef
                    assert rendered['outputs'][0][32:52].count(1) == int(bool(expected[3]))
                    rendered['outputs'][0][63] = 0
                    assert words[63] == 0xdeadbeef


def test_imported_memory_preserves_masked_shifts_numeric_booleans_and_initial_locals():
    legacy = {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 70000},
              'variables': {'$a': {'type': 'u32', 'initial': 0xffffffff}},
              'functions': {'edge': {'max_steps': 10, 'body': [
                  {'op': 'store', 'index': 69999, 'value': {'op': 'add', 'left': {'var': '$a'}, 'right': 1}},
                  {'op': 'store', 'index': 65536, 'value': {'op': 'shl', 'left': 1, 'right': 32}},
                  {'op': 'store', 'index': 8192, 'value': {'op': 'eq', 'left': 7, 'right': 7}}]}}}
    program, view = memory_bundle(legacy, 'edge')
    arena = [0] * 70000
    result = execute_program(program, view, inputs=[arena])
    assert result['status'] == 'complete'
    assert (result['outputs'][0][69999], result['outputs'][0][65536], result['outputs'][0][8192]) == (0, 1, 1)
    assert arena == [0] * 70000


def test_memory_failure_discards_earlier_writes_and_returns_owned_original():
    legacy = mini_snake_program()
    legacy['functions']['step']['body'].append({'op': 'store', 'index': 64, 'value': 123})
    program, view = memory_bundle(legacy, 'step')
    words = mini_initial()
    saved = list(words)
    result = execute_program(program, view, inputs=[words])
    assert result['status'] == 'refused'
    assert result['outputs'] == [] and result['events'] == [] and result['state'][0] == saved
    result['state'][0][0] = 99
    assert words == saved


@pytest.mark.parametrize('target', ['python', 'javascript'])
def test_standalone_outputs_recompose_all_three_source_implementations(tmp_path, target):
    if target == 'javascript' and shutil.which('node') is None:
        pytest.skip('local Node runtime is unavailable; JavaScript edge is unqualified')
    program, view, catalog, group = synthetic_bundle()
    vectors = [[x] for x in (0, 1, 65527, 65528, 65535)]
    for i, impl in enumerate(group['implementations']):
        directory = tmp_path / str(i)
        plan = orchestration(program, impl['id'])
        manifest = compile_program(program, view, catalog, plan, directory, target=target)
        assert manifest['selected_implementations'][0]['language'] == impl['language']
        assert manifest['shims'][0]['outputs'][0]['ownership'] == 'copy'
        for filename, expected_hash in manifest['artifacts'].items():
            source = (directory / filename).read_bytes()
            assert hashlib.sha256(source).hexdigest() == expected_hash
            assert b'from fdisbull' not in source and b'import fdisbull' not in source
        actual = run_emitted(directory, target, vectors)
        expected = [execute_program(program, view, plan, catalog, inputs=x) for x in vectors]
        for a, e in zip(actual, expected):
            assert {k: a[k] for k in ('status', 'outputs', 'state', 'events', 'calls', 'steps')} == {k: e[k] for k in ('status', 'outputs', 'state', 'events', 'calls', 'steps')}


@pytest.mark.parametrize('target', ['python', 'javascript'])
def test_standalone_food_matches_independent_arithmetic_for_all_2018_cases(tmp_path, target):
    if target == 'javascript' and shutil.which('node') is None:
        pytest.skip('local Node runtime is unavailable; JavaScript edge is unqualified')
    program, view = food_bundle()
    compile_program(program, view, EMPTY, orchestration(program), tmp_path / 'food', target=target)
    vectors = food_vectors()
    actual = run_emitted(tmp_path / 'food', target, vectors)
    assert all(r['status'] == 'complete' for r in actual)
    assert [r['outputs'][0] for r in actual] == [food_expected(v) for v in vectors]


@pytest.mark.parametrize('target', ['python', 'javascript'])
def test_standalone_arena_raster_and_deferred_effect(tmp_path, target):
    if target == 'javascript' and shutil.which('node') is None:
        pytest.skip('local Node runtime is unavailable; JavaScript edge is unqualified')
    program, view = memory_bundle(mini_snake_program(), 'render')
    compile_program(program, view, EMPTY, orchestration(program), tmp_path / 'raster', target=target)
    words = mini_initial()
    result = run_emitted(tmp_path / 'raster', target, [[words]])[0]
    assert result['status'] == 'complete' and result['outputs'] == [mini_expected(words, 'render')]
    program, view, catalog, group = synthetic_bundle(host_effect=True)
    plan = orchestration(program, group['implementations'][0]['id'])
    compile_program(program, view, catalog, plan, tmp_path / 'effect', target=target)
    result = run_emitted(tmp_path / 'effect', target, [[65535]])[0]
    assert result['status'] == 'pending_host' and result['state'] == [65535, 0]
    assert result['outputs'] == [] and result['proposed_state'] == [65535, 7]
    assert result['events'][0]['service'] == 'text.show'


def test_unused_zero_local_cannot_extend_the_legacy_memory_budget():
    legacy = {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 2},
              'variables': {'$unused': {'type': 'u32', 'initial': 0}},
              'functions': {'bounded': {'max_steps': 1, 'body': [
                  {'op': 'store', 'index': 0, 'value': 1},
                  {'op': 'store', 'index': 1, 'value': 2}]}}}
    program, view = memory_bundle(legacy, 'bounded')
    result = execute_program(program, view, inputs=[[0, 0]])
    assert result['status'] == 'refused'
    assert result['state'][0] == [0, 0] and result['outputs'] == []


def test_presentation_constant_change_has_a_distinct_identity_under_the_same_uil():
    program, view, catalog, group = synthetic_bundle()
    changed = deepcopy(view)
    changed['functions'][1]['constants'][0] = '9'
    assert view['program_sha256'] == changed['program_sha256'] == digest(program)
    assert digest(view) != digest(changed)
    plan = orchestration(program, group['implementations'][0]['id'])
    assert execute_program(program, view, plan, catalog, inputs=[100])['outputs'] == [108]
    assert execute_program(program, changed, plan, catalog, inputs=[100])['outputs'] == [110]
