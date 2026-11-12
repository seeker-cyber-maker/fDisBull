"""Exercise the observer on authored modules without shipping BLA targets."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


DRIVER = Path(__file__).resolve().parents[1] / 'scripts' / 'bla_function_runtime.cjs'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node is required for the VM observer')


def node_json(body):
    prelude = r'''
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {makeRealm, sanitizedCall, run, referenceShadowHeapStep} = require(process.argv[1]);
const commitment = {keySha256:'1'.repeat(64),flagSha256:'2'.repeat(64)};
const source = (protectedHeap=false, extraCall=false, returned='authored private return') => `
  const FLAG_CIPHER_HEX = '00'.repeat(63);
  const crypto = require('node:crypto');
  let H = {cursor:0,slots:[{value:3}]};
  function sha256Hex(value) {
    ${protectedHeap ? 'H.cursor++;H.slots[0].value=Math.imul(H.slots[0].value,3);' : ''}
    const h=crypto.createHash('sha256').update(String(value),'utf8');
    ${extraCall ? "h.update('authored-extra','utf8');" : ''}
    return h.digest('hex');
  }
  function tryUnlock(value) {return ${JSON.stringify(returned)};}
  module.exports={sha256Hex,tryUnlock,SCOPE:'authored',LICENSE_RPC:'/authored',
    KEY_SHA256:'1'.repeat(64),FLAG_SHA256:'2'.repeat(64)};
`;
const runtime={heapName:'H',cipherName:'FLAG_CIPHER_HEX'};
const realm=(protectedHeap=false, extraCall=false, instrument=false, returned) =>
  makeRealm(source(protectedHeap,extraCall,returned),protectedHeap ? runtime : null,
            0,commitment,'actual_crypto',instrument);
'''
    result = subprocess.run([NODE, '--max-old-space-size=256', '-e', prelude + body, str(DRIVER)],
                            capture_output=True, text=True, timeout=10,
                            env={k: v for k, v in os.environ.items() if k not in ('NODE_OPTIONS', 'NODE_PATH')})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_private_heap_writes_are_separate_from_equal_caller_observations():
    result = node_json(r'''
const clean=realm(),target=realm(true),instrumented=realm(true,false,true);
const a=clean.call('sha256Hex','"authored"'),b=target.call('sha256Hex','"authored"');
const c=instrumented.call('sha256Hex','"authored"');
assert.deepEqual(a.result,b.result); assert.deepEqual(a.events,b.events);
assert.deepEqual(b.result,c.result);assert.deepEqual(b.events,c.events);assert.deepEqual(b.after,c.after);
assert.equal(a.after,null);assert.notDeepEqual(b.before,b.after);assert.equal(c.writes.length,2);
console.log(JSON.stringify({target:sanitizedCall(b),diagnostic:sanitizedCall(c)}));
''')
    assert result['target']['heap_changed_paths'] == 2
    assert result['target']['recorded_writes'] == 0
    assert result['diagnostic']['recorded_writes'] == 2
    assert result['target']['heap_after_sha256'] == result['diagnostic']['heap_after_sha256']


def test_call_contract_changes_are_detected_even_when_event_values_are_private():
    result = node_json(r'''
const a=realm().call('sha256Hex','"authored"');
const b=realm(false,true).call('sha256Hex','"authored"');
console.log(JSON.stringify({a:sanitizedCall(a),b:sanitizedCall(b)}));
''')
    assert result['a']['ordered_calls'] == 3
    assert result['b']['ordered_calls'] == 4
    assert result['a']['ordered_calls_sha256'] != result['b']['ordered_calls_sha256']
    assert result['a']['result_sha256'] != result['b']['result_sha256']


def test_sanitized_observations_do_not_publish_return_or_exception_message():
    result = node_json(r'''
const r=realm(false,false,false,'authored private return');
const a=sanitizedCall(r.call('tryUnlock','null'));
const b=sanitizedCall(r.call('sha256Hex','({toString(){throw new TypeError("authored private failure");}})'));
const text=JSON.stringify({a,b});
assert(!text.includes('authored private return'));assert(!text.includes('authored private failure'));
assert(!text.includes('stack'));
console.log(text);
''')
    assert result['a']['result_type'] == 'string'
    assert result['b']['result_kind'] == 'throw'
    assert result['b']['exception_name'] == 'TypeError'
    assert len(result['b']['exception_message_sha256']) == 64


def test_reproducible_calls_and_source_receipts():
    result = node_json(r'''
const a=realm(true),b=realm(true);
assert.deepEqual(a.call('sha256Hex','"authored"'),b.call('sha256Hex','"authored"'));
assert.deepEqual(a.executionReceipt,b.executionReceipt);
assert.equal(a.executionReceipt.source_sha256,crypto.createHash('sha256').update(source(true)).digest('hex'));
console.log(JSON.stringify(a.executionReceipt));
''')
    assert result['function_bodies_rewritten'] is False
    assert result['private_heap_proxy'] is False
    assert len(result['observer_suffix_sha256']) == 64


def test_wrong_source_pin_is_rejected_before_analyzer_or_execution(tmp_path):
    fixture = tmp_path / 'authored.cjs'
    fixture.write_text('// authored fixture')
    config = {'root': str(tmp_path), 'template': {'path': fixture.name, 'sha256': '0' * 64},
              'targets': [{'tier': 'authored'}],
              'commitment': {'keySha256': '1' * 64, 'flagSha256': '2' * 64}}
    result = node_json('''
try {run(%s);throw new Error('incorrectly accepted');}
catch(error){assert.equal(error.message,'Source hash mismatch');console.log(JSON.stringify({rejected:true}));}
''' % json.dumps(config))
    assert result['rejected'] is True


def test_wrong_export_commitment_is_rejected():
    result = node_json(r'''
assert.throws(()=>makeRealm(source(),null,0,{...commitment,keySha256:'3'.repeat(64)}),
              {message:'Target commitment mismatch'});
console.log(JSON.stringify({rejected:true}));
''')
    assert result['rejected'] is True


def test_function_source_reflection_is_an_explicit_counterexample():
    result = node_json(r'''
const a=realm().call('sha256Hex','__realm.exports.sha256Hex');
const b=realm(true).call('sha256Hex','__realm.exports.sha256Hex');
console.log(JSON.stringify({a:sanitizedCall(a),b:sanitizedCall(b)}));
''')
    assert result['a']['result_kind'] == result['b']['result_kind'] == 'return'
    assert result['a']['result_sha256'] != result['b']['result_sha256']


def test_intrinsic_mutation_breaks_agreement_across_calls():
    result = node_json(r'''
const a=realm(),b=realm(true);
const input='({toString(){Math.imul=()=>{throw new Error("authored intrinsic failure");};return "authored";}})';
assert.deepEqual(a.call('sha256Hex',input).result,b.call('sha256Hex',input).result);
const x=a.call('sha256Hex','"next"'),y=b.call('sha256Hex','"next"');
console.log(JSON.stringify({a:sanitizedCall(x),b:sanitizedCall(y)}));
''')
    assert result['a']['result_kind'] == 'return'
    assert result['b']['result_kind'] == 'throw'
    assert result['b']['exception_name'] == 'Error'


def test_private_step_boundary_uses_original_helper_and_separate_proxy():
    result = node_json(r'''
const s=source().replace('function sha256Hex(value) {',
  'function mutateFixture(delta) {H.cursor+=delta;H.slots[0].value^=delta;return H.cursor;}\nfunction sha256Hex(value) {');
const metadata={...runtime,heapStepName:'mutateFixture'};
const original=makeRealm(s,metadata,0,commitment);
const diagnostic=makeRealm(s,metadata,0,commitment,'actual_crypto',true);
const input={cursor:7,slots:[{value:2147483647}]};
original.installHeap(input);diagnostic.installHeap(input);
const a=original.step(-1),b=diagnostic.step(-1);
assert.deepEqual(a.result,b.result);assert.deepEqual(a.after,b.after);
assert.equal(a.result.value,6);assert.equal(a.after.slots[0].value,-2147483648);
assert.deepEqual(a.exportsBefore,a.exportsAfter);assert.deepEqual(a.events,[]);
assert.equal(input.cursor,7);assert.equal(input.slots[0].value,2147483647);
assert.equal(b.writes.length,2);
console.log(JSON.stringify({original:sanitizedCall(a),diagnostic:sanitizedCall(b)}));
''')
    assert result['original']['recorded_writes'] == 0
    assert result['diagnostic']['recorded_writes'] == 2
    assert result['original']['heap_after_sha256'] == result['diagnostic']['heap_after_sha256']


def test_private_step_rejects_missing_helper_and_non_numeric_delta():
    result = node_json(r'''
assert.throws(()=>realm(true).step(1),{message:'No numeric private-step boundary'});
const s=source().replace('function sha256Hex(value) {','function mutateFixture(delta) {return delta;}\nfunction sha256Hex(value) {');
const r=makeRealm(s,{...runtime,heapStepName:'mutateFixture'},0,commitment);
assert.throws(()=>r.step({valueOf(){throw new Error('must not coerce');}}),
              {message:'No numeric private-step boundary'});
for(const value of [NaN,Infinity,-Infinity,0.5,Number.MAX_SAFE_INTEGER+1])
  assert.throws(()=>r.step(value),{message:'No numeric private-step boundary'});
console.log(JSON.stringify({rejected:true}));
''')
    assert result['rejected'] is True


def test_private_heap_certificate_must_bind_the_executed_source():
    result = node_json(r'''
const metadata={...runtime,shadowHeapProof:{status:'proved',source:{sha256:'0'.repeat(64)}}};
assert.throws(()=>makeRealm(source(),metadata,0,commitment),{message:'Shadow-heap proof source mismatch'});
console.log(JSON.stringify({rejected:true}));
''')
    assert result['rejected'] is True


def test_bigint_oracle_preserves_boundary_shape_without_mutating_input():
    result = node_json(r'''
const heap={tick:2147483647,rollingMask:2147483647,cursor:7,
  slots:Array.from({length:8},(_,slotId)=>({slotId,kind:'fixture',words:[2147483647,0,2147483647,0],epoch:2147483647,hmacTag:0})),
  splitShareA:[0,2147483647,1],splitShareB:[2147483647,0,1],
  diffEnvelope:{state_diff_frontier_0:0,state_diff_frontier_1:2147483647}};
const before=JSON.stringify(heap);
const rows=[];
for(const delta of [0,-1,2147483647,-2147483648,4294967295,Number.MAX_SAFE_INTEGER,Number.MIN_SAFE_INTEGER]) {
  const out=referenceShadowHeapStep(heap,delta);
  assert.equal(JSON.stringify(heap),before);assert.equal(out.heap.tick,0);assert.equal(out.heap.cursor,7);
  assert.equal(out.result,out.heap.rollingMask);assert.equal(out.heap.slots.length,8);
  assert.equal(out.heap.splitShareA.length,3);assert.equal(out.heap.splitShareB.length,3);
  assert.deepEqual(out.heap.slots.map(s=>s.kind),heap.slots.map(s=>s.kind));
  for(const slot of out.heap.slots)for(const value of [...slot.words,slot.epoch,slot.hmacTag])
    assert(Number.isInteger(value)&&value>=0&&value<=2147483647);
  for(const value of [...out.heap.splitShareA,...out.heap.splitShareB,...Object.values(out.heap.diffEnvelope)])
    assert(Number.isInteger(value)&&value>=0&&value<=2147483647);
  rows.push(out.result);
}
assert.throws(()=>referenceShadowHeapStep(heap,0.5),{message:'Unsupported oracle delta'});
assert.throws(()=>referenceShadowHeapStep({...heap,diffEnvelope:{unexpected:0}},0),{message:'Unsupported oracle frontier'});
console.log(JSON.stringify({cases:rows.length,unchanged:JSON.stringify(heap)===before}));
''')
    assert result == {'cases': 7, 'unchanged': True}
