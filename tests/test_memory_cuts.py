"""Exact cut admission, lexical resumption and real compiled phase behavior."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.udc_memory_cuts import lower_memory_cuts
from fdisbull.udc_web_memory import (MAX_STEPS, build_memory_block, digest,
                                    execute_memory_uil, validate_memory_uil)


def _store(index, value, ident=None):
    node = {'op': 'store', 'index': index, 'value': value}
    if ident is not None:
        node['id'] = ident
    return node


def _set(name, value, ident=None):
    node = {'op': 'set', 'var': name, 'value': value}
    if ident is not None:
        node['id'] = ident
    return node


def _if(condition, yes, no=(), ident=None):
    node = {'op': 'if', 'condition': condition, 'then': list(yes), 'else': list(no)}
    if ident is not None:
        node['id'] = ident
    return node


def _expr(op, a, b):
    return {'op': op, 'left': a, 'right': b}


def _program(caller=None, callee=None):
    if callee is None:
        callee = [_store(0, 7, 'callee.1')]
    if caller is None:
        caller = deepcopy(callee)
        for number, node in enumerate(caller):
            node['id'] = 'caller.' + str(number + 1)
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil',
            'memory': {'words': 6},
            'variables': {'$scratch': {'type': 'u32', 'initial': 0}},
            'functions': {'caller': {'max_steps': 100, 'body': caller},
                          'callee': {'max_steps': 100, 'body': callee}}}


def _document(program, cuts=None):
    return {'format': 'fdisbull-memory-cuts-1', 'module_uil_sha256': digest(program),
            'cuts': cuts if cuts is not None else [
                {'caller': 'caller', 'entry': 'caller.1', 'callee': 'callee'}]}


def _nested():
    callee = [_set('$scratch', {'load': 0}, 'callee.1'),
              _store(0, _expr('add', {'var': '$scratch'}, 1), 'callee.2')]
    first, second = deepcopy(callee), deepcopy(callee)
    for number, node in enumerate(first, 1):
        node['id'] = 'first.' + str(number)
    for number, node in enumerate(second, 1):
        node['id'] = 'second.' + str(number)
    caller = [_store(1, 10, 'before'),
              _if({'load': 5}, [
                  _if(_expr('eq', {'load': 0}, 1), first,
                      [_store(2, 99, 'inner.other')], 'inner'),
                  _store(2, 20, 'inner.tail'), *second,
                  _store(3, 25, 'outer.then.tail')],
                  [_store(2, 88, 'outer.other')], 'outer'),
              _store(4, 30, 'outer.tail')]
    p = _program(caller, callee)
    d = _document(p, [{'caller': 'caller', 'entry': entry, 'callee': 'callee'}
                      for entry in ('first.1', 'second.1')])
    return p, d


def test_exact_identity_deep_ownership_and_unchanged_canonical_document():
    p, d = _nested()
    before, cut_before = deepcopy(p), deepcopy(d)
    result = lower_memory_cuts(p, d)
    assert p == before and d == cut_before
    assert result['format'] == 'fdisbull-memory-cut-lowering-1'
    assert result['module_uil_sha256'] == digest(before)
    assert result['cut_plan_sha256'] == digest(cut_before)
    assert result['document'] == cut_before
    function = result['functions']['caller']
    assert function['max_steps'] == 100
    assert function['yields'] == {
        '1': {'callee': 'callee', 'resume': 'resume_1', 'adapter_steps': 2},
        '2': {'callee': 'callee', 'resume': 'resume_2', 'adapter_steps': 2}}
    for phase in function['phases'].values():
        validate_memory_uil(phase['program'])
        assert list(phase['program']['functions']) == ['caller']
        assert phase['program']['memory'] == p['memory']
        assert phase['program']['functions']['caller']['max_steps'] == MAX_STEPS
    result['document']['cuts'][0]['callee'] = 'changed'
    function['phases']['entry']['program']['variables']['$scratch']['initial'] = 77
    assert p == before and d == cut_before
    assert function['phases']['resume_1']['program']['variables']['$scratch']['initial'] == 0


def test_multiple_lexical_tails_are_flattened_and_later_cuts_reapplied():
    p, d = _nested()
    function = lower_memory_cuts(p, d)['functions']['caller']
    token = function['token_local']
    one = function['phases']['resume_1']['program']['functions']['caller']['body']
    assert one == [_store(2, 20, 'inner.tail'),
                   _set(token, 2), {'op': 'return'},
                   _store(3, 25, 'outer.then.tail'), _store(4, 30, 'outer.tail')]
    two = function['phases']['resume_2']['program']['functions']['caller']['body']
    assert two == [_store(3, 25, 'outer.then.tail'), _store(4, 30, 'outer.tail')]
    # No ancestor if survives in the resume program: changing word zero in the
    # callee must not retest the old condition or replay its prefix.
    assert not any(node['op'] == 'if' for node in one + two)


@pytest.mark.parametrize('change', [
    lambda d: d.update(unknown=True),
    lambda d: d.pop('cuts'),
    lambda d: d.update(format='other'),
    lambda d: d.update(module_uil_sha256='0' * 64),
    lambda d: d.update(cuts=[]),
    lambda d: d.update(cuts=()),
    lambda d: d.update(cuts=d['cuts'] * 33),
    lambda d: d['cuts'][0].update(unknown=True),
    lambda d: d['cuts'][0].pop('entry'),
    lambda d: d['cuts'][0].update(entry=''),
    lambda d: d['cuts'][0].update(caller=[]),
    lambda d: d['cuts'][0].update(callee='absent'),
])
def test_cut_schema_is_exact_and_nonempty(change):
    p = _program(); d = _document(p); change(d)
    with pytest.raises(ValueError):
        lower_memory_cuts(p, d)


def test_metadata_only_difference_is_allowed_but_changed_behavior_is_not():
    p = _program()
    p['evidence'] = {'a': {'source': 'caller'}, 'b': {'source': 'callee'}}
    p['functions']['caller']['body'][0]['evidence'] = ['a']
    p['functions']['callee']['body'][0]['evidence'] = ['b']
    assert lower_memory_cuts(p, _document(p))['functions']['caller']
    p['functions']['caller']['body'][0]['value'] = 8
    with pytest.raises(ValueError, match='exact callee body'):
        lower_memory_cuts(p, _document(p))


def test_duplicate_node_ids_across_functions_are_refused():
    p = _program(); p['functions']['callee']['body'][0]['id'] = 'caller.1'
    validate_memory_uil(p)  # This profile itself scopes IDs per function.
    with pytest.raises(ValueError, match='duplicate'):
        lower_memory_cuts(p, _document(p))


@pytest.mark.parametrize('body', [
    [_store(0, {'var': '$scratch'})],
    [_if({'load': 0}, [_set('$scratch', 1)]),
     _store(0, {'var': '$scratch'})],
    [{'op': 'while', 'condition': 0, 'limit': 3,
      'body': [_set('$scratch', 1)]}, _store(0, {'var': '$scratch'})],
])
def test_region_must_define_locals_before_every_read(body):
    p = _program(callee=body)
    with pytest.raises(ValueError, match='incoming local reads'):
        lower_memory_cuts(p, _document(p))


def test_both_branches_define_local_and_dead_tail_does_not_need_transfer():
    body = [_if({'load': 0}, [_set('$scratch', 1)], [_set('$scratch', 2)]),
            _store(0, {'var': '$scratch'})]
    p = _program(callee=body)
    p['functions']['caller']['body'] += [
        {'op': 'return'}, _store(0, {'var': '$scratch'})]
    assert lower_memory_cuts(p, _document(p))['functions']['caller']


def test_continuation_local_reads_are_refused_even_from_an_ancestor_tail():
    callee = [_set('$scratch', 1, 'callee.1')]
    p = _program([_if({'load': 0}, [_set('$scratch', 1, 'caller.1')], ident='outer'),
                  _store(0, {'var': '$scratch'}, 'tail')], callee)
    with pytest.raises(ValueError, match='continuation has incoming local reads'):
        lower_memory_cuts(p, _document(p))


def test_loop_ancestor_and_any_return_inside_region_are_refused():
    p = _program()
    p['functions']['caller']['body'] = [
        {'op': 'while', 'limit': 3, 'condition': 0,
         'body': p['functions']['caller']['body']}]
    with pytest.raises(ValueError, match='loop ancestor'):
        lower_memory_cuts(p, _document(p))
    p = _program(callee=[_if(0, [{'op': 'return'}], ident='callee.1')])
    with pytest.raises(ValueError, match='return inside'):
        lower_memory_cuts(p, _document(p))


def test_overlapping_contiguous_ranges_and_duplicate_cut_are_refused():
    p = _program([_store(0, 1, ident) for ident in ('a', 'b', 'c')],
                 [_store(0, 1, ident) for ident in ('x', 'y')])
    for entries in (('a', 'b'), ('a', 'a')):
        d = _document(p, [{'caller': 'caller', 'entry': x, 'callee': 'callee'}
                          for x in entries])
        with pytest.raises(ValueError, match='overlapping'):
            lower_memory_cuts(p, d)


def test_parent_and_descendant_regions_overlap():
    p = _program([_if(1, [_store(0, 1, 'child')], ident='caller.1')],
                 [_if(1, [_store(0, 1, 'source.child')], ident='callee.1')])
    p['functions']['inner'] = {'body': [_store(0, 1, 'inner.1')], 'max_steps': 100}
    d = _document(p, [
        {'caller': 'caller', 'entry': 'caller.1', 'callee': 'callee'},
        {'caller': 'caller', 'entry': 'child', 'callee': 'inner'}])
    with pytest.raises(ValueError, match='overlapping'):
        lower_memory_cuts(p, d)


def _chain(count):
    p = _program()
    p['functions'] = {'f' + str(i): {'body': [_store(0, 1, 'node.' + str(i))],
                                    'max_steps': 100} for i in range(count)}
    d = _document(p, [{'caller': 'f' + str(i), 'entry': 'node.' + str(i),
                       'callee': 'f' + str(i + 1)} for i in range(count - 1)])
    return p, d


def test_cycles_and_seventeen_active_frames_are_refused():
    p, d = _chain(2)
    d['cuts'].append({'caller': 'f1', 'entry': 'node.1', 'callee': 'f0'})
    with pytest.raises(ValueError, match='recursive'):
        lower_memory_cuts(p, d)
    p, d = _chain(16)
    assert len(lower_memory_cuts(p, d)['functions']) == 15
    p, d = _chain(17)
    with pytest.raises(ValueError, match='depth'):
        lower_memory_cuts(p, d)


def test_callee_budget_may_not_add_a_new_refusal():
    p = _program(callee=[_store(0, 1), _store(1, 2)])
    p['functions']['callee']['max_steps'] = 1
    with pytest.raises(ValueError, match='callee budget could narrow source'):
        lower_memory_cuts(p, _document(p))
    p['functions']['callee']['max_steps'] = 2
    assert lower_memory_cuts(p, _document(p))['functions']['caller']
    # A source budget equally small already refuses the same path.
    p['functions']['callee']['max_steps'] = p['functions']['caller']['max_steps'] = 1
    assert lower_memory_cuts(p, _document(p))['functions']['caller']


def test_phase_bound_counts_final_while_condition_and_adapters():
    p = _program()
    p['functions']['caller']['max_steps'] = 10
    p['functions']['caller']['body'][:0] = [
        _set('$scratch', 0), {'op': 'while', 'limit': 3,
         'condition': _expr('lt', {'var': '$scratch'}, 3),
         'body': [_set('$scratch', _expr('add', {'var': '$scratch'}, 1))]}]
    lowered = lower_memory_cuts(p, _document(p))['functions']['caller']
    entry = lowered['phases']['entry']
    assert lowered['max_steps'] == 10
    assert entry['max_steps_bound'] == 11  # set + while + 4 tests + 3 body + 2 adapters
    actual = execute_memory_uil(entry['program'], 'caller', [0] * 6)
    assert actual['status'] == 'complete' and actual['steps'] == 11
    assert lowered['phases']['resume_1']['max_steps_bound'] == 0


def test_phase_static_cap_is_inclusive_and_arithmetic_saturates():
    p = _program()
    first = {'op': 'while', 'limit': 1000000, 'condition': 0,
             'body': [_store(0, 0), _store(1, 0)]}
    last = {'op': 'while', 'limit': 999994, 'condition': 0, 'body': []}
    p['functions']['caller']['body'][:0] = [first, last]
    entry = lower_memory_cuts(p, _document(p))['functions']['caller']['phases']['entry']
    assert entry['max_steps_bound'] == MAX_STEPS
    last['limit'] += 1
    with pytest.raises(ValueError, match='static bound'):
        lower_memory_cuts(p, _document(p))
    # Very large products stay small during admission, rather than building a
    # number proportional to the hypothetical nested execution tree.
    nested = _store(0, 0)
    for _ in range(12):
        nested = {'op': 'while', 'limit': 1000000, 'condition': 0, 'body': [nested]}
    p['functions']['caller']['body'][0] = nested
    with pytest.raises(ValueError, match='static bound'):
        lower_memory_cuts(p, _document(p))


def test_fresh_token_preserves_arena_bounds_and_original_oob_refusal():
    p = _program(callee=[_store(6, 1, 'callee.1')])
    p['variables']['$__fdisbull_cut_token'] = {'type': 'u32', 'initial': 99}
    lowered = lower_memory_cuts(p, _document(p))['functions']['caller']
    assert lowered['token_local'] == '$__fdisbull_cut_token_1'
    for phase in lowered['phases'].values():
        assert phase['program']['memory']['words'] == 6
    result = execute_memory_uil(p, 'callee', [0] * 6)
    assert result['status'] == 'refused' and result['words'] == [0] * 6
    assert result['error'] == 'store outside arena'


@pytest.mark.skipif(not shutil.which('node'), reason='Real Wasm requires Node')
def test_real_wasm_resumption_preserves_outputs_charges_and_private_token(tmp_path):
    p, d = _nested()
    lowered = lower_memory_cuts(p, d)['functions']['caller']
    for name, phase in lowered['phases'].items():
        build_memory_block(phase['program'], 'caller', 'wasm32-memory-1', tmp_path / name,
                           report_steps=True, capture_locals=(lowered['token_local'],))
    for name in ('caller', 'callee'):
        build_memory_block(p, name, 'wasm32-memory-1', tmp_path / name, report_steps=True)
    runtime = (Path(__file__).parents[1] / 'src/fdisbull/web_runtime/memory.mjs').as_uri()
    script = """
import fs from 'node:fs/promises';import assert from 'node:assert/strict';
import {createWasmMemoryProvider} from RUNTIME;
const spec=SPEC,providers={};
for(const name of ['entry','resume_1','resume_2','caller','callee']) {
 const build=JSON.parse(await fs.readFile(name+'/build.json'));
 providers[name]=await createWasmMemoryProvider(build,await fs.readFile(name+'/block.wasm'));
 assert.equal(build.abi.memory_words,6);
}
try {
 for(const flag of [1,0]) {
  const original=[1,0,0,0,0,flag];let words=original.slice(),phase='entry',steps=0,calls=0;
  while(true) {
   const result=await providers[phase].invoke(words);assert.equal(result.status,'complete');
   words=result.words;steps+=result.steps;const token=result.locals[spec.token_local];
   if(token===0)break;
   assert(token===1||token===2);steps-=2;calls++;
   const callee=await providers[spec.yields[String(token)].callee].invoke(words);
   assert.equal(callee.status,'complete');words=callee.words;steps+=callee.steps;
   phase=spec.yields[String(token)].resume;
  }
  const direct=await providers.caller.invoke(original);
  assert.deepEqual(words,direct.words);assert.equal(steps,direct.steps);
  assert.deepEqual(Array.from(words),flag?[3,10,20,25,30,1]:[1,10,88,0,30,0]);
  assert.equal(calls,flag?2:0);assert.equal(words.length,6);
 }
} finally {for(const provider of Object.values(providers))await provider.dispose();}
console.log(JSON.stringify({status:'complete',cases:2}));
""".replace('RUNTIME', json.dumps(runtime)).replace('SPEC', json.dumps(lowered))
    (tmp_path / 'run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'), 'run.mjs'], cwd=tmp_path,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)['cases'] == 2
