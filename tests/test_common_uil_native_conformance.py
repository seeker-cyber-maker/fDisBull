"""Real native selected-import conformance; original-code oracles are private."""
from copy import deepcopy
import platform
import shutil

import pytest

from fixtures_common_uil import food_expected, food_vectors, mini_expected, mini_initial, package
from fixtures_common_uil_native import (
    batches, check_native_result, reference_result, selected_food_bundle,
    selected_import_bundle, selected_memory_bundle, selected_mini_snake_bundle,
    snake_action_cases, snake_kernel_inputs, snake_kernel_projection,
)
from fdisbull.common_uil import digest, validate_orchestration


def native_target():
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Darwin' and machine in ('arm64', 'aarch64'):
        if not shutil.which('clang'):
            pytest.skip('macOS native compiler unavailable; execution edge unqualified')
        return 'macos-arm64'
    if system == 'Linux' and machine in ('x86_64', 'amd64'):
        if not shutil.which('gcc'):
            pytest.skip('Linux native compiler unavailable; execution edge unqualified')
        return 'linux-x64'
    pytest.skip('native conformance requires an admitted ARM64 macOS or x86-64 Linux host')


def build_and_run(bundle, directory, records, arithmetic, *, module_requirements=None):
    from fdisbull.uil_native import build_native_program
    from fdisbull.uil_native_codegen import run_native_records
    target = native_target()
    manifest = build_native_program(bundle['program'], bundle['presentation'], bundle['catalog'],
        bundle['orchestration'], directory, target=target, arithmetic=arithmetic,
        module_requirements=module_requirements)
    command = [str(directory / manifest['executable'])]
    results = []
    chunks = batches(records) if any(isinstance(v, list) for row in records for v in row) else [records]
    for batch in chunks:
        results.extend(run_native_records(command, manifest, batch, cwd=directory, timeout=120))
    return manifest, results


def test_closed_kernels_are_selected_imports_with_copy_shims():
    for bundle in (selected_food_bundle(), selected_mini_snake_bundle()):
        program = bundle['program']
        assert program['functions'][0]['body'][0]['op'] == 'invoke'
        assert len(program['imports']) == 1 and len(bundle['catalog']['groups']) == 1
        qualified = validate_orchestration(program, bundle['catalog'], bundle['orchestration'])
        assert qualified['resolved'][0]['id'] == bundle['implementation']
        assert all(p['ownership'] == 'copy' for p in qualified['shims'][0]['inputs'])
    memory = selected_mini_snake_bundle()['program']['functions'][0]
    assert memory['inputs'] == memory['outputs'] == [0]


@pytest.mark.parametrize('arithmetic', ['portable-c', 'native-asm'])
def test_real_native_food_selected_kernel_matches_all_2018_independent_answers(tmp_path, arithmetic):
    bundle = selected_food_bundle()
    frozen = [digest(bundle[k]) for k in ('program', 'presentation', 'catalog', 'orchestration')]
    vectors = food_vectors()
    manifest, actual = build_and_run(bundle, tmp_path / arithmetic, vectors, arithmetic)
    assert manifest['program_sha256'] == frozen[0]
    assert len(actual) == 2018
    invocation_count = 0
    for inputs, result in zip(vectors, actual):
        expected = reference_result(bundle, inputs)
        assert expected['outputs'] == [food_expected(inputs)]
        invocation_count += check_native_result(result, expected, bundle, arithmetic=arithmetic, require_arithmetic=True)
    assert invocation_count > 0
    assert frozen == [digest(bundle[k]) for k in ('program', 'presentation', 'catalog', 'orchestration')]


@pytest.mark.parametrize('arithmetic', ['portable-c', 'native-asm'])
def test_real_native_memory_step_and_raster_use_selected_backing_without_input_aliases(tmp_path, arithmetic):
    for name in ('step', 'render'):
        bundle = selected_mini_snake_bundle(name)
        records = []
        for direction in range(4):
            for x, y in ((0, 0), (1, 1), (4, 3)):
                words = mini_initial()
                words[:4] = [x, y, direction, 1]
                records.append([words])
        saved = deepcopy(records)
        _, rows = build_and_run(bundle, tmp_path / (arithmetic + '-' + name), records, arithmetic)
        count = 0
        for inputs, row in zip(records, rows):
            expected = reference_result(bundle, inputs)
            assert expected['outputs'] == [mini_expected(inputs[0], name)]
            count += check_native_result(row, expected, bundle, arithmetic=arithmetic)
        assert count > 0 and records == saved


@pytest.mark.parametrize('arithmetic', ['portable-c', 'native-asm'])
def test_real_native_selected_food_refusal_is_atomic_and_observable(tmp_path, arithmetic):
    bundle = selected_food_bundle()
    records = [[123, 456, -128, 42, cost] for cost in (0, 3, -1, 32767)]
    _, rows = build_and_run(bundle, tmp_path / arithmetic, records, arithmetic)
    for inputs, row in zip(records, rows):
        expected = reference_result(bundle, inputs)
        assert expected['status'] == 'refused'
        check_native_result(row, expected, bundle, arithmetic=arithmetic)
        assert row['state'][-1] == 0 and row['outputs'] == []


def test_real_native_mixed_component_providers_are_actually_called(tmp_path):
    u32 = {'type': 'u32'}
    function = {'variables': [u32], 'constants': [u32, u32], 'inputs': [0], 'outputs': [0],
                'max_steps': 100, 'body': [
                    {'op': 'set', 'dst': 0, 'value': {'op': 'add', 'type': 'u32', 'args': [{'var': 0}, {'const': 0}]}},
                    {'op': 'set', 'dst': 0, 'value': {'op': 'mul', 'type': 'u32', 'args': [{'var': 0}, {'const': 1}]}}]}
    program, view = package([function], [[1, 2]])
    bundle = selected_import_bundle(program, view, label='authored-add-then-multiply')
    requirements = {'implementations': {bundle['implementation']: {
        'arithmetic': 'portable-c', 'components': {'add': 'portable-c', 'mul': 'native-asm'}}}}
    _, rows = build_and_run(bundle, tmp_path / 'mixed', [[0], [0xffffffff]], 'portable-c', module_requirements=requirements)
    for x, row in zip((0, 0xffffffff), rows):
        assert row['status'] == 'complete' and row['outputs'] == [((x + 1) * 2) & 0xffffffff]
        counters = {r['operation']: r for r in row['arithmetic_calls'] if r['kind'] == 'imports' and r['index'] == 0}
        assert counters['add']['provider'] == 'portable-c' and counters['add']['calls'] > 0
        assert counters['mul']['provider'] == 'native-asm' and counters['mul']['calls'] > 0


def test_native_observation_check_rejects_a_forged_provider_or_selected_identity():
    bundle = selected_food_bundle()
    expected = reference_result(bundle, [10, 12, 1, 3, 2])
    actual = {**deepcopy(expected), 'calls': [{
        'block': 0, 'semantic_id': bundle['semantic_id'], 'implementation': bundle['implementation'],
        'status': 'complete', 'observation': 'identity-and-counts-only', 'input_count': 5, 'output_count': 1}],
        'arithmetic_calls': [{'kind': 'imports', 'index': 0, 'operation': 'add', 'provider': 'native-asm', 'calls': 1}]}
    check_native_result(actual, expected, bundle, arithmetic='native-asm', require_arithmetic=True)
    with pytest.raises(AssertionError, match='different arithmetic provider'):
        check_native_result(actual, expected, bundle, arithmetic='portable-c', require_arithmetic=True)
    actual['calls'][0]['implementation'] = 'implementation:' + '0' * 64
    with pytest.raises(AssertionError, match='identity/status'):
        check_native_result(actual, expected, bundle, arithmetic='native-asm')


def test_prepared_snake_inputs_and_projected_route_records_are_owned():
    names = ('snake_length','direction','pending_direction','paused','game_status','score',
             'rng_seed','tick_count','key_events','mouse_events','frame_count','mouse_present','food_cell','turn_queued')
    layout = {name:600+i for i,name in enumerate(names)}
    prepared = {name:0 for name in names}
    prepared.update(snake_length=3,pending_direction=1,cells=[308,307,306])
    initial = [0]*70000
    initial[69999] = 0xdeadbeef
    words = snake_kernel_inputs(initial,prepared,layout)
    saved = snake_kernel_projection(words,layout)
    words[layout['pending_direction']] = 2
    words[0] = 309
    prepared['cells'][0] = 99
    assert saved['pending_direction'] == 1 and saved['all_cells'][0] == 308
    assert saved['cells'] == [308,307,306] and initial[0] == 0
    assert words[69999] == 0xdeadbeef


def test_normalized_action_records_do_not_alias_each_other_or_initial_state():
    states = {name:600+i for i,name in enumerate(('paused','last_tick','mouse_buttons','mouse_present','food_cell'))}
    inputs = {name:630+i for i,name in enumerate(('kind','ascii','scan','x','y','buttons','clock'))}
    initial = [0]*70000
    records = snake_action_cases(initial,states,inputs)
    assert len(records) == 31
    first = list(records[0]['inputs'][0])
    records[1]['inputs'][0][0] = 42
    initial[inputs['ascii']] = 65
    assert records[0]['inputs'][0] == first
    wrap = next(x['inputs'][0] for x in records if x['id'] == 'clock-wrap')
    assert wrap[inputs['clock']] == 2 and wrap[states['last_tick']] == 65534
