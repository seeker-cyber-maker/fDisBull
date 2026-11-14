"""Authored two-run frame/erasure fixtures; no archived BLA target contents."""
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
            'slots': [{'slotId': i, 'kind': 'authored private metadata', 'epoch': 0,
                       'words': [0, 0, 0, 0], 'hmacTag': 0} for i in range(8)],
            'splitShareA': [0, 1, 2], 'splitShareB': [3, 4, 5],
            'diffEnvelope': {'state_diff_frontier_0': 0}}


FUNCTIONS = '''
function advance(delta) {
  if (!heap) return 0;
  const mixed = Math.imul(delta | 0, 3);
  heap.tick = (heap.tick + mixed) & 2147483647;
  return heap.tick;
}
function first(value) { advance(1); return String(value); }
function second(value) { advance(2); return first(value); }
module.exports = {first,second};
'''


@pytest.fixture(scope='module')
def prove():
    node = shutil.which('node')
    if not node or not (BABEL / '@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required for optional noninterference proofs')
    driver = r'''
const fs=require('node:fs');
const parser=require(process.argv[1]+'/@babel/parser');
const {proveHeapNoninterference}=require(process.argv[2]+'/bla_heap_noninterference.cjs');
const {proveShadowHeap}=require(process.argv[2]+'/bla_shadow_heap_proof.cjs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source='const heap='+JSON.stringify(input.heap)+';\n'+input.functions;
let heapProof;
if(input.certificate) {
  try {
    const ast=parser.parse(source).program;
    heapProof=proveShadowHeap({source,babelRoot:process.argv[1],heapName:'heap',
      functionNode:ast.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='advance'),
      heapInitializerNode:ast.body[0].declarations[0].init});
    if(input.certificate==='tampered') heapProof.mutation.external_effects=true;
    if(input.certificate==='fake') heapProof={status:'proved',source:{sha256:'0'.repeat(64)}};
  } catch (_) {heapProof={status:'unknown'};}
}
const result=proveHeapNoninterference({source,babelRoot:process.argv[1],heapName:input.heapName??'heap',
  heapStepName:input.stepName??'advance',functionNames:input.names??{sha256Hex:'first',tryUnlock:'second'},heapProof});
console.log(JSON.stringify(result));
'''

    def invoke(functions=FUNCTIONS, **kwargs):
        config = {'functions': functions, 'heap': heap_literal(), **kwargs}
        result = subprocess.run([node, '--max-old-space-size=256', '-e', driver, str(BABEL), str(ROOT/'scripts')],
                                input=json.dumps(config), capture_output=True, text=True, timeout=15,
                                env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    return invoke


def test_private_frame_proves_two_run_silent_step_erasure(prove):
    c=prove(certificate='actual')
    assert c['status']=='proved'
    assert c['source']['ast_identity_verified'] is True
    assert c['relation']['private_states_need_not_equal'] is True
    assert c['audit']['heap_references_owned_by_exact_mutator'] is True
    assert c['audit']['source_initial_separation_established'] is True
    assert c['audit']['private_own_data_ownership_preserved'] is True
    assert c['audit']['private_aliases_escape'] is False
    assert c['audit']['observable_mutator_calls']==[]
    assert c['audit']['mutator_language_exceptions'] is False
    assert c['audit']['termination_sensitive'] is True
    assert c['audit']['selected_callsite_count']==2
    assert {x['role'] for x in c['selected_calls']}=={'sha256Hex','tryUnlock'}
    assert all(x['result_discarded'] and x['argument_evaluation']=='pure_literal' for x in c['selected_calls'])
    assert all(x['result']=='proved' for x in c['obligations'])
    serialized=json.dumps(c)
    assert 'authored private metadata' not in serialized and 'function advance' not in serialized
    assert len(c['heap_certificate_sha256'])==64 and len(c['certificate_sha256'])==64


@pytest.mark.parametrize('certificate',['tampered','fake'])
def test_supplied_heap_certificate_is_recomputed_and_compared(prove,certificate):
    c=prove(certificate=certificate)
    assert c['status']=='unknown' and c['reason']=='stale_or_forged_heap_certificate'


@pytest.mark.parametrize('before,after',[
    ('return String(value);','return heap.tick;'),
    ('module.exports = {first,second};','module.exports = {first,second,heap};'),
    ('module.exports = {first,second};','module.exports = {first,second,advance};'),
    ('module.exports = {first,second};','const alias=heap; module.exports = {first,second};'),
    ('module.exports = {first,second};','const alias=advance; module.exports = {first,second};'),
    ('advance(1);','return advance(1);'),
    ('advance(1);','const result=advance(1);'),
    ('advance(1);','advance.call(null,1);'),
    ('advance(1);','advance((console.log("effect"),1));'),
    ('advance(1);','advance(value);'),
    ('advance(1);','advance(9007199254740992);'),
    ('advance(1);','advance(1,2);'),
    ('advance(1);','advance(...[1]);'),
    ('advance(1);','advance?.(1);'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','heap.tick = mixed;'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','console.log(heap.tick);'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','publicState.tick=heap.tick;'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','unbound=heap.tick;'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','throw new Error("private exception");'),
    ('heap.tick = (heap.tick + mixed) & 2147483647;','while(true){}'),
    ('Math.imul(delta | 0, 3)','Math.random()'),
    ('return String(value);','return eval("heap.tick");'),
    ('return String(value);','const e=eval; return e("heap.tick");'),
    ('return String(value);','return Function("return 0")();'),
    ('return String(value);','return first.constructor("return 0")();'),
    ('return String(value);','return first["constructor"]("return 0")();'),
])
def test_leaks_observable_effects_and_unsafe_erasure_fail_closed(prove,before,after):
    c=prove(FUNCTIONS.replace(before,after))
    assert c['status']=='unknown'
    assert 'certificate_sha256' not in c


def test_nested_same_name_is_not_the_private_mutator_owner(prove):
    c=prove(FUNCTIONS+'''
function unrelated() {return function advance() {return heap;};}
''')
    assert c['status']=='unknown' and c['reason']=='private_heap_reference_escapes'


def test_mutable_heap_or_transition_binding_is_not_private(prove):
    c=prove(FUNCTIONS+'\nadvance=first;\n')
    assert c['status']=='unknown' and c['reason']=='mutable_or_missing_private_binding'


def test_outside_calls_are_recorded_and_not_erased(prove):
    c=prove(FUNCTIONS+'\nfunction unrelated(value) {advance(value.length);return value;}\n')
    assert c['status']=='proved'
    assert c['audit']['module_callsite_count']==3
    assert c['audit']['outside_selected_callsite_count']==1
    assert len(c['selected_calls'])==2
    assert 'not erased' in c['scope']


@pytest.mark.parametrize('kwargs',[
    {'heapName':'absent'}, {'stepName':'absent'}, {'heapName':'not valid'},
    {'names':{'sha256Hex':'first','tryUnlock':'first'}},
    {'names':{'sha256Hex':'advance'}}, {'names':{'sha256Hex':'absent'}},
])
def test_ambiguous_or_missing_boundaries_cannot_receive_a_proof(prove,kwargs):
    assert prove(**kwargs)['status']=='unknown'
