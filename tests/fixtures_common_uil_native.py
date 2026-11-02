"""Public native-UIL fixtures; original data and large media stay external.

Each kernel is an actual selected closed import. Arithmetic provider selection
can change without changing the common program, catalog or orchestration.
"""
from __future__ import annotations

from copy import deepcopy

from fixtures_common_uil import food_bundle, memory_bundle, mini_snake_program, package
from fdisbull.common_uil import digest, presentation_value
from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_runtime import execute_program


def selected_import_bundle(program, presentation, *, label):
    """Wrap one closed function, preserving exact formal input/output aliases."""
    function = deepcopy(program['functions'][program['entry']])
    binding = presentation['functions'][program['entry']]
    constants = [presentation_value(v, t) for v, t in zip(binding['constants'], function['constants'])]
    catalog = build_catalog([{'language': 'common', 'function': function,
                              'constants': constants, 'source': {'fixture': label}}])
    if catalog['rejected'] or len(catalog['groups']) != 1:
        raise ValueError('native fixture requires one admitted closed kernel')
    group = catalog['groups'][0]
    implementation = group['implementations'][0]
    # A memory kernel's arena is both input and output. Copy shims preserve that
    # interface while the callee still gets an owned copy of its input frame.
    original_to_entry = {}
    variables = []
    inputs = []
    outputs = []
    for side, ports in ((inputs, function['inputs']), (outputs, function['outputs'])):
        for slot in ports:
            if slot not in original_to_entry:
                original_to_entry[slot] = len(variables)
                variables.append(deepcopy(function['variables'][slot]))
            side.append(original_to_entry[slot])
    entry = {'variables': variables, 'constants': [], 'inputs': inputs, 'outputs': outputs,
             'max_steps': 4000000, 'body': [
                 {'op': 'invoke', 'block': 0, 'inputs': [{'var': i} for i in inputs], 'outputs': outputs}]}
    imported = {'semantic_id': group['semantic_id'],
                'inputs': [deepcopy(function['variables'][i]) for i in function['inputs']],
                'outputs': [deepcopy(function['variables'][i]) for i in function['outputs']], 'effects': group['effects']}
    wrapper, view = package([entry], [[]], imports=[imported], resources=presentation['resources'])
    plan = {'format': 'fdisbull-uil-orchestration-1', 'program_sha256': digest(wrapper),
            'bindings': [{'import': 0, 'implementation': implementation['id']}],
            'ownership': 'copy-in-copy-out', 'max_call_depth': 8}
    return {'program': wrapper, 'presentation': view, 'catalog': catalog, 'orchestration': plan,
            'semantic_id': group['semantic_id'], 'implementation': implementation['id'],
            'kernel_sha256': digest(function), 'label': label}


def selected_food_bundle():
    program, presentation = food_bundle()
    return selected_import_bundle(program, presentation, label='public-stock-maintenance-word16')


def selected_memory_bundle(legacy, function):
    program, presentation = memory_bundle(legacy, function)
    return selected_import_bundle(program, presentation, label='memory-' + function)


def selected_mini_snake_bundle(function='step'):
    return selected_memory_bundle(mini_snake_program(), function)


def reference_result(bundle, inputs):
    return execute_program(bundle['program'], bundle['presentation'], bundle['orchestration'],
                           bundle['catalog'], inputs=inputs)


def check_native_result(actual, expected, bundle, *, arithmetic, require_arithmetic=False):
    """Verify native values and actual selected-import/provider observations.

    Native call receipts intentionally expose identities/counts, not argument
    copies. The complete returned frame/output arrays are compared separately.
    A path with no executed arithmetic may legitimately have no arithmetic
    counters; use require_arithmetic for active arithmetic paths or aggregate
    the returned count over a corpus.
    """
    for key in ('status', 'outputs', 'state', 'events', 'steps'):
        if actual[key] != expected[key]:
            raise AssertionError('native ' + key + ' differs from common reference')
    if actual.get('proposed_state') != expected.get('proposed_state'):
        raise AssertionError('native proposed state differs')
    return check_native_selection(actual, bundle, arithmetic=arithmetic,
                                  status='complete' if expected['status'] == 'pending_host' else expected['status'],
                                  require_arithmetic=require_arithmetic)


def check_native_selection(actual, bundle, *, arithmetic, status='complete', require_arithmetic=False):
    """Check observations independently of a value oracle or model."""
    calls = actual.get('calls', [])
    if len(calls) != 1:
        raise AssertionError('entry did not observe exactly one selected import')
    call = calls[0]
    wanted = {'block': 0, 'semantic_id': bundle['semantic_id'],
              'implementation': bundle['implementation'], 'status': status}
    for key, value in wanted.items():
        if call.get(key) != value:
            raise AssertionError('selected native call identity/status differs: ' + key)
    if call.get('observation') != 'identity-and-counts-only':
        raise AssertionError('native call observation scope is missing')
    signature = bundle['program']['imports'][0]
    if (call.get('input_count'), call.get('output_count')) != (len(signature['inputs']), len(signature['outputs'])):
        raise AssertionError('selected native call port counts differ')
    count = 0
    for row in actual.get('arithmetic_calls', []):
        if row.get('kind') == 'imports' and row.get('index') == 0:
            if row.get('provider') != arithmetic:
                raise AssertionError('selected import used a different arithmetic provider')
            if type(row.get('calls')) is not int or row['calls'] <= 0:
                raise AssertionError('native arithmetic counter is invalid')
            count += row['calls']
    if require_arithmetic and count <= 0:
        raise AssertionError('no actual arithmetic backing invocation was observed')
    return count


def batches(records, size=4):
    """Bound full-arena protocol materialization; no raw files are written here."""
    if type(size) is not int or not 1 <= size <= 4:
        raise ValueError('native conformance batches must contain one to four records')
    for start in range(0, len(records), size):
        yield records[start:start + size]


def snake_action_cases(initial, state, inputs):
    """31 authored normalized events; caller supplies model layout and arena.

    These are logical key/pointer/clock records. No physical device behavior is
    implied. Every record owns its arena so later preparation cannot alter it.
    """
    records = []
    def add(label, event, changes=None):
        words = list(initial)
        for index in inputs.values():
            words[index] = 0
        for key, value in event.items():
            words[inputs[key]] = value
        for key, value in (changes or {}).items():
            words[state[key]] = value
        records.append({'id': label, 'inputs': [words]})
    for name, ascii_code, scan in [
        ('escape',27,0),('space',32,0),('uppercase-pause',80,0),('single-step',110,0),
        ('reset',114,0),('wasd-up',119,0),('wasd-right',100,0),('wasd-down',115,0),
        ('wasd-left',97,0),('scan-up',0,72),('scan-right',0,77),('scan-down',0,80),
        ('scan-left',0,75),('contradictory-escape-up',27,72),('ignored',120,0)]:
        add('key-' + name, {'kind':1,'ascii':ascii_code,'scan':scan,'clock':9})
    for name, x, y in [('up',290,50),('left',265,75),('right',300,75),('down',290,98),
                       ('pause',270,130),('step',270,150),('reset',270,180),('outside',5,5)]:
        add('pointer-' + name, {'kind':2,'x':x,'y':y,'buttons':1,'clock':9})
    add('pointer-held', {'kind':2,'x':270,'y':130,'buttons':1,'clock':9}, {'mouse_buttons':1})
    add('pointer-release', {'kind':2,'x':270,'y':130,'buttons':0,'clock':9}, {'mouse_buttons':1})
    add('pointer-absent', {'kind':2,'x':270,'y':130,'buttons':1,'clock':9}, {'mouse_present':0})
    add('clock-paused', {'kind':0,'clock':4})
    add('clock-before-boundary', {'kind':0,'clock':3}, {'paused':0,'last_tick':0})
    add('clock-at-boundary', {'kind':0,'clock':4}, {'paused':0,'last_tick':0})
    add('clock-wrap', {'kind':0,'clock':2}, {'paused':0,'last_tick':65534})
    add('clock-eats-food', {'kind':0,'clock':4}, {'paused':0,'last_tick':0,'food_cell':309})
    return records


def snake_kernel_inputs(initial, state, layout):
    """Explicit prepared-state adapter for the 600-cell/14-field CPU oracle."""
    words = list(initial)
    cells = state['all_cells'] if 'all_cells' in state else state['cells']
    if len(cells) > 600:
        raise ValueError('Snake kernel adapter admits at most 600 cells')
    words[:600] = list(cells) + [0] * (600 - len(cells))
    for name, index in layout.items():
        value = state[name]
        if type(value) is not int or not 0 <= value <= 65535:
            raise ValueError('original Snake scalar is outside u16')
        words[index] = value
    return words


def snake_kernel_projection(words, layout):
    result = {name: words[index] for name, index in layout.items()}
    result['all_cells'] = list(words[:600])
    result['cells'] = list(words[:result['snake_length']])
    return result
