from copy import deepcopy

from fdisbull.common_uil import FORMAT, digest
from fdisbull.uil_dataflow import scalar_value_plan
from fdisbull.uil_runtime import execute_program


def shuffled_function():
    return {'variables': [{'type': 'u32'}] * 4 + [{'type': 'bool'}],
            'constants': [{'type': 'u32'}], 'inputs': [0, 1, 4], 'outputs': [3, 4],
            'max_steps': 20, 'body': [
                {'op': 'set', 'dst': 2, 'value': {'var': 0}},
                {'op': 'set', 'dst': 0, 'value': {'const': 0}},
                {'op': 'set', 'dst': 3, 'value': {'var': 2}},
                {'op': 'set', 'dst': 3, 'value': {'op': 'add', 'type': 'u32',
                    'args': [{'var': 3}, {'var': 1}]}},
                {'op': 'return'}]}


def test_copy_values_survive_source_overwrite_and_preserve_flags_and_charges():
    fn = shuffled_function(); before = digest(fn)
    plan = scalar_value_plan(fn)
    assert len(plan['eliminated_copies']) == 2
    assert [v['charge'] for v in plan['body']] == [1] * 5
    # Original slot0 is value0; overwriting it defines value5. Both aliases
    # still refer to value0. The arithmetic must consume the snapshot.
    assert plan['body'][1]['value'] == 5
    assert plan['body'][3]['expression']['args'] == [{'ssa': 0}, {'ssa': 1}]
    assert plan['final_values'] == [5, 1, 0, 6, 4]
    assert digest(fn) == before
    p = {'format': FORMAT, 'capabilities': ['core.scalar@1'], 'imports': [], 'functions': [fn], 'entry': 0}
    b = {'format': 'fdisbull-uil-presentation-1', 'program_sha256': digest(p),
         'functions': [{'initial': ['0', '0', '0', '0', False], 'constants': ['99']}], 'resources': []}
    result = execute_program(p, b, inputs=[4294967295, 2, True])
    assert result['state'] == [99, 2, 4294967295, 1, True]
    assert result['outputs'] == [1, True] and result['steps'] == 5
    p['functions'][0]['max_steps'] = 4; b['program_sha256'] = digest(p)
    refused = execute_program(p, b, inputs=[4294967295, 2, True])
    assert refused['status'] == 'refused' and refused['state'] == [4294967295, 2, 0, 0, True]


def test_group_paths_are_recoverable_and_early_return_does_not_run_late_copy():
    fn = shuffled_function()
    fn['body'] = [{'op': 'group', 'semantic_id': 'semantic:' + '0' * 64, 'body': fn['body']}]
    fn['body'].append({'op': 'set', 'dst': 4, 'value': {'var': 4}})
    plan = scalar_value_plan(fn)
    assert plan['body'][0]['path'] == [0, 'body', 0]
    assert len(plan['body']) == 5
    assert len(plan['eliminated_copies']) == 2
    assert plan['function_sha256'] == digest(fn)


def test_control_and_memory_keep_normal_lowering():
    fn = shuffled_function()
    fn['body'].append({'op': 'if', 'condition': {'var': 4}, 'then': [], 'else': []})
    assert scalar_value_plan(fn) is None
    fn = deepcopy(shuffled_function())
    fn['variables'].append({'type': 'u32-array', 'length': 2})
    assert scalar_value_plan(fn) is None
