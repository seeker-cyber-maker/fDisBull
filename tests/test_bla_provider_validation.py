"""Real native provider checks and independent oracle regressions, no targets."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

import pytest


MODULE = Path(__file__).resolve().parents[1] / 'scripts/bla_provider_validation.cjs'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node is required for real provider validation')


def node_json(body, payload=None):
    prelude = "const fs=require('node:fs');const api=require(process.argv[1]);const input=JSON.parse(fs.readFileSync(0,'utf8'));\n"
    result = subprocess.run([NODE, '--max-old-space-size=256', '-e', prelude + body, str(MODULE)],
                            input=json.dumps(payload), text=True, capture_output=True, timeout=20,
                            env={k: v for k, v in os.environ.items() if k not in ('NODE_OPTIONS', 'NODE_PATH')})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_independent_sha256_matches_python_at_padding_and_chunk_boundaries():
    rng = random.Random(20261112)
    rows = [[rng.randrange(256) for _ in range(length)]
            for length in [0, 1, 2, 31, 32, 55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 1024, 4096]]
    actual = node_json("console.log(JSON.stringify(input.map(a=>Array.from(api.pureSha256(Uint8Array.from(a)),x=>x.toString(16).padStart(2,'0')).join(''))));", rows)
    assert actual == [hashlib.sha256(bytes(row)).hexdigest() for row in rows]


def test_independent_utf8_encoder_handles_surrogates_and_primitive_text():
    rows = ['', 'a\0b', 'λ☃😀', '\ud800', '\udfff', '\ud800x\udc00😀']
    actual = node_json("console.log(JSON.stringify(input.map(a=>Array.from(api.encodeUtf8(a)))));", rows)
    assert actual == [[], [97, 0, 98], list('λ☃😀'.encode()), [239, 191, 189], [239, 191, 189],
                      [239, 191, 189, 120, 239, 191, 189, 240, 159, 152, 128]]


def test_independent_utf8_decoder_matches_replacement_subparts():
    rng = random.Random(73)
    rows = [[], list(range(256)), [0xe1, 0x80, 0x41], [0xf0, 0x90, 0x80], [0xed, 0xa0, 0x80],
            [0xf4, 0x90, 0x80, 0x80], [0xe0, 0x80, 0x80]]
    rows += [[rng.randrange(256) for _ in range(length)] for length in range(1, 130)]
    actual = node_json("console.log(JSON.stringify(input.map(a=>api.decodeUtf8(a))));", rows)
    assert actual == [bytes(row).decode('utf8', errors='replace') for row in rows]


def test_hex_decoder_models_valid_prefix_and_odd_nibble_truncation():
    actual = node_json("console.log(JSON.stringify(input.map(a=>Array.from(api.decodeHexPrefix(a)))));",
                       ['', '00', 'ABCDEF', 'a', 'abc', 'ab cd', 'abzzcd', 'zz', '00λ', '00\0ff'])
    assert actual == [[], [0], [171, 205, 239], [], [171], [171], [171], [], [0], [0]]


def test_byte_view_overlap_uses_offsets_and_empty_extents():
    actual = node_json("""
const b=Buffer.from([1,2,3,4]);
console.log(JSON.stringify([api.byteViewsOverlap(b.subarray(0,2),b.subarray(1,3)),
 api.byteViewsOverlap(b.subarray(0,2),b.subarray(2,4)),api.byteViewsOverlap(b.subarray(2,2),b),
 api.byteViewsOverlap(b,Buffer.from(b))]));
""")
    assert actual == [True, False, False, False]


def test_oracles_refuse_out_of_bound_or_incorrect_input_types():
    actual = node_json("""
const checks=[()=>api.pureSha256([]),()=>api.pureSha256(new Uint8Array(2**21+1)),
 ()=>api.encodeUtf8(17),()=>api.encodeUtf8('x'.repeat(2**20+1))];
console.log(JSON.stringify(checks.map(fn=>{try{fn();return false;}catch(_){return true;}})));
""")
    assert actual == [True] * 4


def test_real_provider_receipt_fingerprints_native_runtime_and_limits_claim():
    receipt = node_json("console.log(JSON.stringify(api.validateProviders()));")
    assert receipt['status'] == 'verified_finite_conformance'
    assert receipt['cases'] == 73
    assert sum(receipt['categories'].values()) == receipt['cases']
    assert receipt['categories']['sha256_known_vector'] == 4
    assert receipt['categories']['native_error_and_recovery'] == 6
    assert receipt['categories']['contract_boundary_counterexample'] == 2
    assert all(row['passed'] and len(row['evidence_sha256']) == 64 for row in receipt['rows'])
    assert receipt['runtime']['node'].startswith('v') and receipt['runtime']['openssl']
    assert type(receipt['runtime']['fips']) is int
    assert len(receipt['runtime']['executable_sha256']) == 64
    assert receipt['runtime']['executable_bytes'] > 0
    assert set(receipt['runtime']['builtin_source_sha256']) == {
        'createHash', 'hash_update', 'hash_digest', 'Buffer_from', 'Buffer_alloc', 'Buffer_toString'}
    assert receipt['buffer_freshness']['logical_byte_views_nonoverlapping'] is True
    assert receipt['buffer_freshness']['distinct_ArrayBuffer_not_required'] is True
    expected_hash = hashlib.sha256(json.dumps({k: v for k, v in receipt.items() if k != 'receipt_sha256'},
                                             sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    assert receipt['receipt_sha256'] == expected_hash
    assert 'metadata mutation is excluded' in receipt['buffer_freshness']['extent_stability']
    assert 'not a universal native-code' in receipt['limitations'][0]
    serialized = json.dumps(receipt)
    assert 'Digest already called' not in serialized and 'authored-left' not in serialized
    assert 'process.env' not in serialized and 'execPath' not in serialized


@pytest.mark.parametrize('provider', ['crypto', 'buffer'])
def test_corrupted_provider_cannot_produce_a_verified_receipt(provider):
    # The mutation is confined to this fresh Node subprocess. It demonstrates
    # that the suite checks actual leaf behavior rather than emitting a label.
    result = node_json("""
const crypto=require('node:crypto');const {Buffer:B}=require('node:buffer');
if(input==='crypto')crypto.createHash=()=>({update(){return this;},digest(){return '0'.repeat(64);}});
else {const alloc=B.alloc;B.alloc=(...args)=>alloc(...args).fill(1);}
try {api.validateProviders();console.log(JSON.stringify({rejected:false}));}
catch(error){console.log(JSON.stringify({rejected:/^provider_case_failed_/.test(error.message)}));}
""", provider)
    assert result['rejected'] is True
