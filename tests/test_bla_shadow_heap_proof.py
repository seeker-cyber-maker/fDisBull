"""Authored source fixtures challenge the heap induction/ranking checker.

No archived challenge implementation, ciphertext, key or flag is embedded.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BABEL = Path(os.environ.get('FDISBULL_BABEL_ROOT',
    '/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules'))


def heap_literal():
    return {'cursor': 0, 'tick': 1, 'rollingMask': 2,
            'slots': [{'slotId': i, 'kind': 'authored metadata', 'epoch': 0,
                       'words': [0, 0, 0, 0], 'hmacTag': 0} for i in range(8)],
            'splitShareA': [0, 1, 2], 'splitShareB': [3, 4, 5],
            'diffEnvelope': {'state_diff_frontier_0': 0, 'state_diff_frontier_1': 0}}


FUNCTION = '''
function advance(delta) {
  if (!heap) return 0;
  const mixed = Math.imul(delta | 0, 13) ^ heap.rollingMask >>> 4;
  heap.tick = (heap.tick + 1) & 2147483647;
  heap.rollingMask = mixed & 2147483647;
  const count = heap.slots.length;
  for (let i = 0; i < 8; i++) {
    const at = (heap.cursor + i) % count;
    const slot = heap.slots[at];
    const data = slot.words;
    data[0] = (data[0] ^ mixed) & 2147483647;
    slot.epoch = (slot.epoch + 1) & 2147483647;
  }
  heap.cursor = (heap.cursor + 8) % count;
  const first = heap.splitShareA;
  const second = heap.splitShareB;
  const roll = (mixed & 32767) | 1;
  for (let k = 0; k < first.length; k++) {
    first[k] = first[k] ^ roll;
    second[k] = second[k] ^ roll;
  }
  const e = heap.diffEnvelope;
  e.state_diff_frontier_0 = (e.state_diff_frontier_0 ^ (mixed + 7)) & 2147483647;
  return heap.rollingMask;
}
'''


@pytest.fixture(scope='module')
def prove():
    node = shutil.which('node')
    if not node or not (BABEL / '@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required for the optional heap proof')
    driver = r'''
const fs=require('node:fs');
const parser=require(process.argv[1]+'/@babel/parser');
const {proveShadowHeap,checkHeapInvariant}=require(process.argv[2]);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source='const heap='+JSON.stringify(input.heap)+';\n'+input.function;
let ast;
try {ast=parser.parse(source).program;}
catch (_) {console.log(JSON.stringify({certificate:{status:'unknown',reason:'source_syntax_rejected'}}));process.exit(0);}
if(input.astMutation==='function') ast.body[1].body.body.pop();
if(input.astMutation==='initializer') ast.body[0].declarations[0].init.properties.pop();
const cert=proveShadowHeap({functionNode:ast.body[1],heapInitializerNode:ast.body[0].declarations[0].init,
                          heapName:'heap',source,babelRoot:process.argv[1]});
let invariant=null;
if(cert.status==='proved') {
  const h=input.observedHeap ?? input.heap;
  if(input.runtimeMutation==='alias') h.splitShareB=h.splitShareA;
  if(input.runtimeMutation==='hole') delete h.slots[0].words[0];
  if(input.runtimeMutation==='accessor') Object.defineProperty(h,'tick',{get(){return 0;},enumerable:true});
  if(input.runtimeMutation==='readonly') Object.defineProperty(h,'tick',{value:0,writable:false});
  invariant=checkHeapInvariant(h,cert);
}
console.log(JSON.stringify({certificate:cert,invariant}));
'''

    def invoke(function=FUNCTION, heap=None, observed=None, mutation=None, ast_mutation=None):
        config = {'function': function, 'heap': heap if heap is not None else heap_literal(),
                  'runtimeMutation': mutation, 'astMutation': ast_mutation}
        if observed is not None:
            config['observedHeap'] = observed
        result = subprocess.run([node, '--max-old-space-size=256', '-e', driver, str(BABEL),
                                 str(ROOT / 'scripts/bla_shadow_heap_proof.cjs')],
                                input=json.dumps(config), text=True, capture_output=True, timeout=15,
                                env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS', 'NODE_PATH')})
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    return invoke


def test_all_invariant_states_and_loop_ranks_have_source_bound_certificate(prove):
    result=prove()
    c=result['certificate']
    assert c['status']=='proved' and result['invariant'] is True
    assert c['invariant']['preserved'] is True
    assert c['invariant']['ordinary_disjoint_own_data_graph'] is True
    assert c['invariant']['arrays_and_object_schema_unchanged'] is True
    assert c['termination']['max_loop_iterations']==11
    assert [l['iterations'] for l in c['termination']['loops']]==[8,3]
    assert all(l['decrease']==1 and l['exit_rank']==0 for l in c['termination']['loops'])
    assert c['mutation']['max_numeric_writes']==26
    kinds={o['kind'] for o in c['obligations']}
    assert {'bounded_array_access','nonnegative_remainder','invariant_preserving_numeric_write',
            'exact_integer_arithmetic','loop_induction_and_rank'} <= kinds
    assert len(c['source']['mutator_sha256'])==64
    serialized=json.dumps(c)
    assert 'authored metadata' not in serialized
    assert 'function advance' not in serialized
    assert c['source']['ast_identity_verified'] is True


@pytest.mark.parametrize('before,after', [
    ('i++', 'i--'),
    ('i < 8', 'i <= 8'),
    ('i < 8', 'i < delta'),
    ('i < 8', 'i < heap.tick'),
    ('const at =', 'i = 0; const at ='),
    ('const at =', 'heap.slots.length = 0; const at ='),
    ('const at =', 'heap.slots = heap.splitShareA; const at ='),
    ('const at =', 'heap.slots.push(0); const at ='),
    ('(heap.cursor + i) % count', 'heap.cursor + i'),
    ('(heap.cursor + i) % count', '(heap.cursor - i) % count'),
    ('(heap.cursor + i) % count', '(heap.cursor + i) % 0'),
    ('data[0] = (data[0] ^ mixed) & 2147483647;', 'data[0] = mixed;'),
    ('const roll = (mixed & 32767) | 1;', 'const roll = mixed;'),
    ('first[k] = first[k] ^ roll;', 'first[k + 1] = first[k] ^ roll;'),
    ('heap.tick = (heap.tick + 1) & 2147483647;', 'heap.tick = heap.tick + 1;'),
    ('(heap.tick + 1)', '(heap.tick + 9007199254740991)'),
    ('return heap.rollingMask;', 'return heap;'),
    ('const count = heap.slots.length;', 'const count = heap.slots.push;'),
    ('const count = heap.slots.length;', 'const count = heap.constructor;'),
    ('Math.imul(delta | 0, 13)', 'Math.random()'),
    ('Math.imul(delta | 0, 13)', 'Math.imul(heap, 13)'),
    ('if (!heap) return 0;', 'if (!heap) { var Math; return 0; }'),
    ('const count = heap.slots.length;', 'const Math = 0; const count = heap.slots.length;'),
    ('return heap.rollingMask;', 'while (true) {} return heap.rollingMask;'),
    ('return heap.rollingMask;', 'return advance(delta);'),
    ('const data = slot.words;', 'const data = slot.kind;'),
    ('data[0] = (data[0] ^ mixed) & 2147483647;', 'data.length = 0;'),
    ('function advance(delta)', 'function Math(delta)'),
    ('function advance(delta)', 'function heap(delta)'),
])
def test_unproved_accesses_writes_and_control_fail_closed(prove, before, after):
    result=prove(FUNCTION.replace(before,after))
    assert result['certificate']['status']=='unknown'
    assert 'certificate_sha256' not in result['certificate']


@pytest.mark.parametrize('mutation', ['alias','hole','accessor','readonly'])
def test_runtime_invariant_checks_own_data_shape_and_disjoint_graph(prove,mutation):
    result=prove(mutation=mutation)
    assert result['certificate']['status']=='proved'
    assert result['invariant'] is False


@pytest.mark.parametrize('field,value', [('cursor',8),('cursor',-1),('tick',2147483648)])
def test_invalid_initial_shape_does_not_receive_a_proof(prove,field,value):
    heap=heap_literal();heap[field]=value
    assert prove(heap=heap)['certificate']['status']=='unknown'


def test_numeric_boundary_poststates_satisfy_the_inductive_shape(prove):
    heap=heap_literal()
    for slot in heap['slots']:
        slot.update(slotId=2147483647,epoch=2147483647,hmacTag=2147483647,words=[2147483647]*4)
    heap.update(cursor=7,tick=2147483647,rollingMask=2147483647,splitShareA=[2147483647]*3,splitShareB=[2147483647]*3)
    heap['diffEnvelope']={k:2147483647 for k in heap['diffEnvelope']}
    result=prove(observed=heap)
    assert result['certificate']['status']=='proved' and result['invariant'] is True


@pytest.mark.parametrize('mutation', ['function','initializer'])
def test_supplied_ast_cannot_claim_a_different_source(prove,mutation):
    result=prove(ast_mutation=mutation)
    assert result['certificate']['status']=='unknown'
    assert result['certificate']['reason'] in ('source_ast_identity','source_heap_identity')


def test_owning_source_cannot_shadow_the_assumed_math_intrinsic(prove):
    result=prove(FUNCTION+'\nconst Math = {imul(a,b) {return 0;}};\n')
    assert result['certificate']['status']=='unknown'
    assert result['certificate']['reason']=='source_binding_identity'
