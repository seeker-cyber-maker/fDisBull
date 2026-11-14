"""Native CJS module/CLI observations distinguish missing evidence and effects."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which('node')
MODULE = Path(__file__).resolve().parents[1] / 'scripts/bla_module_runtime.cjs'
pytestmark = pytest.mark.skipif(NODE is None, reason='Node is required for native CJS checks')
# Authored fixtures only. No original crackme key, flag or ciphertext belongs here.
KEY = 'authored-native-witness-2026'
FLAG = 'FLAG{authored-finite-runtime-fixture}'
KEY_SHA = hashlib.sha256(KEY.encode()).hexdigest()
FLAG_SHA = hashlib.sha256(FLAG.encode()).hexdigest()
MASK = hashlib.sha256(('authored|' + KEY).encode()).digest()
CIPHER = bytes(value ^ MASK[index % len(MASK)] for index, value in enumerate(FLAG.encode())).hex()
SOURCE = ''''use strict';
const {createHash}=require('node:crypto');
const keySha=%s,flagSha=%s,cipher=%s;
function tryUnlock(value){
 if(typeof value!=='string'||value.length<12||value.length>96)return null;
 const hash=x=>createHash('sha256').update(x,'utf8').digest('hex');
 if(hash(value)!==keySha)return null;
 const mask=createHash('sha256').update('authored|'+value).digest();
 const data=Buffer.from(cipher,'hex'),plain=Buffer.alloc(data.length);
 for(let i=0;i<data.length;i++)plain[i]=data[i]^mask[i%%mask.length];
 const flag=plain.toString('utf8');return hash(flag)===flagSha?flag:null;
}
module.exports={tryUnlock,settings:{scope:'authored'}};
if(require.main===module){
 const key=process.argv[2]||'';
 if(!key){console.log('authored usage');process.exit(1);}
 const flag=tryUnlock(key);
 if(flag){console.log('[+] Access Granted! Flag: '+flag);process.exit(0);}
 console.error('authored rejection');process.exit(1);
}
''' % (json.dumps(KEY_SHA), json.dumps(FLAG_SHA), json.dumps(CIPHER))


def config(source=SOURCE, witness_path=None):
    return {'reference': {'source': SOURCE, 'filename': '/authored/reference.cjs'},
            'targets': [{'tier': 'L1', 'source': source, 'filename': '/authored/target.cjs'}],
            'commitment': {'keySha256': KEY_SHA, 'flagSha256': FLAG_SHA},
            'witnessPath': str(witness_path) if witness_path else None}


def invoke(request, check=True):
    result = subprocess.run([NODE, '--max-old-space-size=256', str(MODULE)],
                            input=json.dumps(request), text=True, capture_output=True, timeout=60,
                            env={'PATH': str(Path(NODE).parent)})
    if check:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    return result


def witness(tmp_path, key=KEY):
    target = tmp_path / 'external-witness.json'
    target.write_text(json.dumps({'key': key}))
    return target


def test_real_native_key_and_flag_are_verified_and_never_returned(tmp_path):
    key_file = witness(tmp_path)
    receipt = invoke(config(witness_path=key_file))
    assert receipt['real_valid_key_acceptance_verified'] is True
    assert receipt['rejection_paths_verified'] is True
    assert receipt['all_cli_observations_equal'] is True
    assert receipt['all_module_observations_equal'] is True
    assert receipt['cases_per_cli'] == 12
    assert receipt['witness']['file_sha256'] == hashlib.sha256(key_file.read_bytes()).hexdigest()
    assert receipt['witness']['path_sha256'] == hashlib.sha256(str(key_file).encode()).hexdigest()
    assert receipt['provider_substitutions'] is False
    assert receipt['function_bodies_rewritten'] is False
    assert receipt['target_observer_suffix'] is False
    serialized = json.dumps(receipt)
    for private in (KEY, FLAG, CIPHER, '/authored/', str(tmp_path)):
        assert private not in serialized
    valid = next(row for row in receipt['targets'][0]['cli'] if row['input_class'] == 'valid_key')
    assert valid['exit_status'] == 0
    assert valid['flag_commitment_matches'] is True
    assert valid['native_cli_dispatch_returned'] is False


def test_absent_witness_does_not_promote_rejections_to_acceptance():
    receipt = invoke(config())
    assert receipt['status'] == 'verified_finite_rejections_real_acceptance_pending'
    assert receipt['witness']['status'] == 'missing'
    assert receipt['real_valid_key_acceptance_verified'] is False
    assert receipt['rejection_paths_verified'] is True
    assert receipt['all_module_observations_equal'] is True
    assert receipt['cases_per_cli'] == 9
    assert all(row['input_class'] != 'valid_key' for row in receipt['reference']['cli'])


def test_global_getter_effect_and_function_reflection_are_not_erased(tmp_path):
    tail = "\nObject.defineProperty(globalThis,'authored-private-global',{configurable:true,get(){return 7;}});\n"
    altered = SOURCE.replace('function tryUnlock(value)', 'function differentName(value)').replace(
        'tryUnlock,settings', 'tryUnlock:differentName,settings').replace(
        'const flag=tryUnlock(key)', 'const flag=differentName(key)') + tail
    receipt = invoke(config(altered, witness(tmp_path)))
    target = receipt['targets'][0]
    assert receipt['real_valid_key_acceptance_verified'] is True
    assert target['function_results_equal'] is True
    assert target['export_reflection_equal'] is False
    assert target['initialization_global_effects_equal'] is False
    assert target['module_observations_equal'] is False
    assert target['cli_observations_equal'] is True
    delta = target['module']['observation']['initialization_global_descriptor_delta']
    getters = [row for row in delta if row['key']['name_sha256'] ==
               hashlib.sha256(b'authored-private-global').hexdigest()]
    assert len(getters) == 1
    assert getters[0]['after']['kind'] == 'accessor'
    assert getters[0]['after']['set'] is None
    assert 'authored-private-global' not in json.dumps(receipt)


def test_actual_native_exit_prevents_cli_postlude_from_running():
    altered = SOURCE + "\nprocess.stdout.write('authored-private-postlude');\n"
    receipt = invoke(config(altered))
    target = receipt['targets'][0]
    assert target['module']['stdout_bytes'] == len('authored-private-postlude')
    assert target['module_observations_equal'] is False
    assert target['cli_observations_equal'] is True
    assert all(not row['native_cli_dispatch_returned'] for row in target['cli'])
    assert 'authored-private-postlude' not in json.dumps(receipt)


def test_rejection_difference_is_visible_even_when_both_exit_one():
    altered = SOURCE.replace("console.error('authored rejection')", "console.error('changed authored rejection')")
    receipt = invoke(config(altered))
    target = receipt['targets'][0]
    assert target['function_results_equal'] is True
    assert target['cli_observations_equal'] is False
    short = next(row for row in target['cli'] if row['input_class'] == 'short')
    assert short['exit_status'] == 1
    assert short['equal_to_reference'] is False


def test_wrong_private_witness_is_rejected_without_relaying_value(tmp_path):
    private = 'wrong-authored-private-key'
    result = invoke(config(witness_path=witness(tmp_path, private)), check=False)
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr == 'Native module/CLI verification failed\n'
    assert private not in result.stderr


def test_changed_source_pin_and_private_initialization_failure_fail_closed():
    request = config()
    request['targets'][0]['source_sha256'] = '0' * 64
    result = invoke(request, check=False)
    assert result.returncode == 2
    assert result.stdout == ''
    result = invoke(config('throw new Error("authored-private-initialization");'), check=False)
    assert result.returncode == 2
    assert 'authored-private-initialization' not in result.stderr


def test_matching_key_does_not_validate_an_invented_native_acceptance(tmp_path):
    altered = SOURCE.replace('return hash(flag)===flagSha?flag:null', 'return null')
    receipt = invoke(config(altered, witness(tmp_path)))
    assert receipt['witness']['status'] == 'native_acceptance_failed'
    assert receipt['real_valid_key_acceptance_verified'] is False
    assert receipt['targets'][0]['real_valid_key_acceptance_verified'] is False
    assert receipt['all_cli_observations_equal'] is False


@pytest.mark.parametrize('with_witness', [False, True])
def test_bad_rejection_paths_cannot_receive_a_verified_rejection_status(tmp_path, with_witness):
    altered = SOURCE.replace("if(typeof value!=='string'||value.length<12||value.length>96)return null",
                             "if(typeof value!=='string'||value.length<12||value.length>96)return 'authored-invalid-acceptance'")
    receipt = invoke(config(altered, witness(tmp_path) if with_witness else None))
    assert receipt['status'] == 'native_rejection_validation_failed'
    assert receipt['rejection_paths_verified'] is False
    assert receipt['targets'][0]['rejection_paths_verified'] is False
    assert receipt['all_cli_observations_equal'] is False
    assert receipt['real_valid_key_acceptance_verified'] is with_witness
