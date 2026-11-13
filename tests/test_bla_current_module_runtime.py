"""Original/reduced tree probes preserve native paths, exits and evidence limits."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which('node')
ORACLE = Path(__file__).resolve().parents[1] / 'scripts/bla_current_module_runtime.cjs'
pytestmark = pytest.mark.skipif(NODE is None, reason='Node is required for native CJS checks')
KEY = 'authored-current-edition-key'
OUTPUT = 'FLAG{authored-current-native-output}'
KEY_SHA = hashlib.sha256(KEY.encode()).hexdigest()
OUTPUT_SHA = hashlib.sha256(OUTPUT.encode()).hexdigest()


def write_tree(root, files):
    root.mkdir()
    for name, source in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    return {'root': str(root), 'pins': [{'path': name, 'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest()}
                                      for name in sorted(files)]}


def config(tmp_path, edition, files, reduced_files=None):
    witness = tmp_path / 'private-key.json'
    witness.write_text(json.dumps({'key': KEY}))
    return {'edition': edition, 'original': write_tree(tmp_path / 'original', files),
            'reduced': write_tree(tmp_path / 'reduced', reduced_files or files),
            'commitment': {'keySha256': KEY_SHA, 'outputSha256': OUTPUT_SHA},
            'witnessPath': str(witness)}


def invoke(request, check=True):
    result = subprocess.run([NODE, '--max-old-space-size=256', str(ORACLE)],
                            input=json.dumps(request), text=True, capture_output=True, timeout=90,
                            env={'PATH': str(Path(NODE).parent)})
    if check:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    return result


V6 = ''''use strict';
const {createHash}=require('node:crypto');
async function main(){
 const key=process.argv[2]||'';
 if(key.length!==%d){console.log('authored usage');process.exit(2);}
 await WebAssembly.instantiate(Buffer.from('0061736d01000000','hex'));
 if(createHash('sha256').update(key).digest('hex')!==%s){console.log('authored rejection');process.exit(1);}
 console.log(Buffer.from(%s,'hex').toString('utf8'));
}
main().catch(error=>{console.error(error.message);process.exit(1);});
''' % (len(KEY), json.dumps(KEY_SHA), json.dumps(OUTPUT.encode().hex()))
GETTER = "Object.defineProperty(globalThis,'authored-private-initializer',{configurable:true,get(){return Object.freeze({active:true});}});\n"


def v7_files():
    expr = "exports.evaluate=value=>value==='2+3*4'?14:0;exports.format=String;\n"
    license_source = ''''use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function activate(key){
 if(typeof key!=='string'||key.length<12)return {ok:false,format:true};
 if(sha(key)!==%s||sha(fs.readFileSync(path.join(__dirname,'expr.cjs')))!==%s)return {ok:false};
 return {ok:true,certificate:Buffer.from(%s,'hex').toString('utf8')};
}
exports.activate=activate;
''' % (json.dumps(KEY_SHA), json.dumps(hashlib.sha256(expr.encode()).hexdigest()), json.dumps(OUTPUT.encode().hex()))
    cli = ''''use strict';
const license=require('../core/license.cjs');
const args=process.argv.slice(2);
if(args[0]==='license'&&args[1]==='activate'&&args.length===3){
 const value=license.activate(args[2]);
 if(value.ok)console.log('Certificate: '+value.certificate);
 else {console.error('authored license denied');process.exitCode=value.format?2:1;}
}else if(args.length===0){console.log('authored usage');}
else if(args[0]==='version'){console.log('authored version');}
else if(args[0]==='calc'){console.log(require('../core/expr.cjs').evaluate(args[1]));}
else{console.error('authored other command');process.exitCode=2;}
'''
    return {'cli/meridian.cjs': cli, 'core/license.cjs': license_source, 'core/expr.cjs': expr,
            'core/units.cjs': 'exports.catalog=()=>({revision:1});\n',
            'core/stats.cjs': 'exports.describe=values=>({n:values.length});\n'}


def exit_observation(row):
    return next(control for control in row['controls'] if control['phase'] == 'native_exit_observed')


def test_async_v6_stream_equivalence_does_not_erase_initialization_difference(tmp_path):
    request = config(tmp_path, 'v6', {'vault.cjs': V6 + GETTER}, {'vault.cjs': V6})
    receipt = invoke(request)
    assert receipt['status'] == 'finite_observations_differ'
    assert receipt['original_real_acceptance_verified'] is True
    assert receipt['reduced_real_acceptance_verified'] is True
    assert receipt['all_cli_observations_equal'] is True
    assert receipt['all_measured_cli_observations_equal'] is False
    assert receipt['all_module_observations_equal'] is False
    original = {row['input_class']: row for row in receipt['original']['measured_cli']}
    valid = exit_observation(original['valid_key'])
    missing = exit_observation(original['missing'])
    assert valid['synchronous_compile_returned'] is True
    assert missing['synchronous_compile_returned'] is False
    assert missing['exit_code'] == 2
    name_hash = hashlib.sha256(b'authored-private-initializer').hexdigest()
    assert any(row['key']['name_sha256'] == name_hash for row in valid['final']['global_descriptor_delta'])
    assert not missing['final']['global_descriptor_delta']
    assert receipt['observation_context']['plain_cli']['exit_listener_installed'] is False
    assert receipt['observation_context']['measured_cli_and_modules']['exit_listener_installed'] is True
    serialized = json.dumps(receipt)
    for secret in (KEY, OUTPUT, OUTPUT.encode().hex(), str(tmp_path), 'authored-private-initializer'):
        assert secret not in serialized


def test_identical_v7_tree_copies_match_and_call_actual_exports(tmp_path):
    request = config(tmp_path, 'v7', v7_files())
    for tree in ('original', 'reduced'):
        request[tree]['moduleEntries'] = [
            {'label': 'expr', 'path': 'core/expr.cjs',
             'calls': [{'export': 'evaluate', 'inputClass': 'arithmetic', 'args': ['2+3*4']}]},
            {'label': 'license', 'path': 'core/license.cjs'},
            {'label': 'cli', 'path': 'cli/meridian.cjs'}]
    receipt = invoke(request)
    assert receipt['status'] == 'finite_observations_equal'
    assert receipt['all_cli_observations_equal'] is True
    assert receipt['all_module_observations_equal'] is True
    assert receipt['original_real_acceptance_verified'] is True
    license_row = next(row for row in receipt['original']['modules'] if row['label'] == 'license')
    observed = exit_observation(license_row)
    assert observed['final']['exports']['public_export_names'] == ['activate']
    assert observed['calls'][0]['accepted'] is True
    assert observed['calls'][0]['output_commitment_matches'] is True
    assert observed['calls'][1]['accepted'] is False
    assert receipt['filesystem_substitutions'] is False
    assert receipt['provider_substitutions'] is False
    assert receipt['native_exit_replaced'] is False


def test_reduced_self_integrity_reads_its_own_tree_and_valid_key_rejects(tmp_path):
    original = v7_files()
    reduced = {**original, 'core/expr.cjs': original['core/expr.cjs'] + '// same expression behavior, changed original bytes\n'}
    receipt = invoke(config(tmp_path, 'v7', original, reduced))
    assert receipt['original_real_acceptance_verified'] is True
    assert receipt['reduced_real_acceptance_verified'] is False
    assert receipt['all_cli_observations_equal'] is False
    valid = next(row for row in receipt['reduced']['cli'] if row['input_class'] == 'valid_key')
    assert valid['exit_status'] == 1
    assert valid['output_commitment_matches'] is False
    license_row = next(row for row in receipt['reduced']['modules'] if row['label'] == 'license')
    call = exit_observation(license_row)['calls'][0]
    assert call['accepted'] is False
    assert call['output_commitment_matches'] is False


def test_native_process_event_registration_is_retained_in_effect_receipt(tmp_path):
    tail = "process.on('beforeExit',function authoredPrivateListener(){});\n"
    receipt = invoke(config(tmp_path, 'v6', {'vault.cjs': V6 + tail}, {'vault.cjs': V6}))
    assert receipt['all_cli_observations_equal'] is True
    valid = next(row for row in receipt['original']['measured_cli'] if row['input_class'] == 'valid_key')
    listeners = exit_observation(valid)['final']['process_event_listener_delta']
    assert any(row['event']['name_sha256'] == hashlib.sha256(b'beforeExit').hexdigest()
               and row['after_count'] == row['before_count'] + 1 for row in listeners)
    assert 'authoredPrivateListener' not in json.dumps(receipt)


def test_changed_pin_or_wrong_witness_fails_closed_without_private_diagnostics(tmp_path):
    request = config(tmp_path, 'v6', {'vault.cjs': V6})
    request['reduced']['pins'][0]['sha256'] = '0' * 64
    result = invoke(request, check=False)
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr == 'Current module comparison failed\n'
    request['reduced']['pins'][0]['sha256'] = hashlib.sha256(V6.encode()).hexdigest()
    Path(request['witnessPath']).write_text(json.dumps({'key': 'wrong-private-authored-key'}))
    result = invoke(request, check=False)
    assert result.returncode == 2
    assert 'wrong-private-authored-key' not in result.stderr


def test_target_native_exception_keeps_exit_one_and_only_hashed_diagnostics(tmp_path):
    files = {'vault.cjs': 'throw new Error("authored-private-native-error");\n'}
    receipt = invoke(config(tmp_path, 'v6', files))
    assert receipt['status'] == 'original_witness_acceptance_failed'
    assert receipt['original']['cli'][0]['exit_status'] == 1
    assert receipt['original']['cli'][0]['stderr_bytes'] > 0
    assert 'authored-private-native-error' not in json.dumps(receipt)


def test_independent_root_and_entry_pins_cannot_be_bypassed(tmp_path):
    request = config(tmp_path, 'v6', {'vault.cjs': V6})
    request['reduced']['root'] = request['original']['root']
    assert invoke(request, check=False).returncode == 2
    request['reduced']['root'] = str(tmp_path / 'reduced')
    request['reduced']['cliEntry'] = '../original/vault.cjs'
    assert invoke(request, check=False).returncode == 2


@pytest.mark.parametrize('artifact_kind', ['unpinned_file', 'symlink', 'shared_inode'])
def test_unpinned_or_aliased_files_are_rejected_before_execution(tmp_path, artifact_kind):
    request = config(tmp_path, 'v6', {'vault.cjs': V6})
    reduced = Path(request['reduced']['root'])
    if artifact_kind == 'unpinned_file':
        (reduced / 'unlisted.json').write_text('{}')
    elif artifact_kind == 'symlink':
        (reduced / 'unlisted-link').symlink_to(Path(request['original']['root']) / 'vault.cjs')
    else:
        # Test fixture replacement is reversible and contains authored source.
        original = Path(request['original']['root']) / 'vault.cjs'
        (reduced / 'vault.cjs').unlink()
        (reduced / 'vault.cjs').hardlink_to(original)
    result = invoke(request, check=False)
    assert result.returncode == 2
    assert result.stdout == ''
