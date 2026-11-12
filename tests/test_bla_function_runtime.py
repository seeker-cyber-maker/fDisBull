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
const {makeRealm, sanitizedCall, run} = require(process.argv[1]);
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
