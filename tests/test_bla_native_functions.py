"""Native CJS loader observations use real providers and publish no result bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which('node')
MODULE = Path(__file__).resolve().parents[1] / 'scripts/bla_native_functions.cjs'
pytestmark = pytest.mark.skipif(NODE is None, reason='Node is required for native CJS checks')
SOURCE = r'''#!/usr/bin/env node
'use strict';
const {createHash}=require('node:crypto');
if(typeof Buffer.prototype.subarray!=='function')throw new Error('Not a native Buffer');
function sha256Hex(value){return createHash('sha256').update(String(value),'utf8').digest('hex');}
function tryUnlock(value){if(typeof value!=='string'||value.length<12)return null;
 return Buffer.from('617574686f72656420707269766174652072657475726e','hex').toString('utf8');}
module.exports={sha256Hex,tryUnlock};
if(require.main===module)throw new Error('CLI must not run');
'''


def invoke(body, source=SOURCE):
    script = '''
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const {probeNativeFunctions,execute}=require(process.argv[1]);
const source=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
''' + body
    result = subprocess.run([NODE, '--max-old-space-size=256', '-e', script, str(MODULE)],
                            input=json.dumps(source), text=True, capture_output=True, timeout=15,
                            env={'PATH': str(Path(NODE).parent)})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_native_loader_uses_real_exports_and_sanitizes_result_values():
    receipt = invoke('''
const r=probeNativeFunctions({source,filename:'/authored/native-fixture.cjs'});
assert.equal(r.cases,34);console.log(JSON.stringify(r));
''')
    assert receipt['source_sha256'] == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert receipt['provider_substitutions'] is False
    assert receipt['target_observer_suffix'] is False
    assert receipt['function_bodies_rewritten'] is False
    assert len(receipt['runtime']['executable_sha256']) == 64
    serialized = json.dumps(receipt)
    assert 'authored private return' not in serialized
    assert '/authored/' not in serialized
    row = next(r for r in receipt['rows'] if r['function'] == 'sha256Hex' and r['input_class'] == 'number')
    expected = {'kind': 'return', 'value': hashlib.sha256(b'17').hexdigest(), 'input_effects': []}
    assert row['result_sha256'] == hashlib.sha256(json.dumps(expected, separators=(',', ':')).encode()).hexdigest()
    assert any(r['input_class'] == 'bigint' for r in receipt['rows'])


def test_changed_pin_is_rejected_before_native_compilation():
    assert invoke('''
assert.throws(()=>execute({source,filename:'/authored/fixture.cjs',source_sha256:'0'.repeat(64)}),
 {message:'Invalid native source receipt'});console.log(JSON.stringify({rejected:true}));
''')['rejected'] is True


def test_native_failure_does_not_relay_private_loader_diagnostics():
    assert invoke('''
assert.throws(()=>probeNativeFunctions({source,filename:'/authored/fixture.cjs'}),
 {message:'Bounded native CJS probe failed'});console.log(JSON.stringify({rejected:true}));
''', 'throw new Error("authored private initialization detail");')['rejected'] is True


def test_missing_native_exports_cannot_be_a_verified_probe():
    assert invoke('''
assert.throws(()=>probeNativeFunctions({source,filename:'/authored/fixture.cjs'}),
 {message:'Bounded native CJS probe failed'});console.log(JSON.stringify({rejected:true}));
''', 'module.exports={sha256Hex:value=>value};')['rejected'] is True
