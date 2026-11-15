"""Authored current-module inventories and source-integrity dependency slices."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
BABEL=Path(os.environ.get('FDISBULL_BABEL_ROOT',
    '/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules'))
SOURCE=r'''
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {createHash,timingSafeEqual}=require('node:crypto');
const sourceFiles=['cli/main.cjs','core/license.cjs'];
function fingerprint(){
 const root=join(__dirname,'..');
 const hash=createHash('sha256');
 for(const file of sourceFiles){hash.update(file);hash.update(readFileSync(join(root,file)));}
 return hash.digest('hex');
}
function deriveSeed(commitment){return createHash('sha256').update(commitment).digest();}
function activate(key){
 if(typeof key!=='string')return {ok:false};
 const seed=deriveSeed(fingerprint());
 const alias=seed;
 const answer=Buffer.from(alias);
 const matches=answer.length===1&&timingSafeEqual(answer,Buffer.alloc(1));
 return matches?{ok:true}:{ok:false};
}
module.exports={activate};
'''
CLI=r'''
const license=require('../core/license.cjs');
function main(argv){return license.activate(argv[0]).ok?0:1;}
try{process.exitCode=main(process.argv.slice(2));}catch(error){console.error(error.message);process.exitCode=2;}
Object.defineProperty(globalThis,'authoredDecoration',{configurable:true,get(){return 1;}});
'''


@pytest.fixture(scope='module')
def analyze():
    node=shutil.which('node')
    if not node or not (BABEL/'@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required')
    driver=r'''
const fs=require('node:fs'),path=require('node:path');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const {analyzeCurrentModules,extractCurrentV6RuntimeMetadata}=require(path.join(process.argv[1],'scripts/bla_current_module_analysis.cjs'));
console.log(JSON.stringify(input.privateRuntimeMetadata?extractCurrentV6RuntimeMetadata({source:input.originalModules[0].source,babelRoot:process.argv[2]}):analyzeCurrentModules({...input,babelRoot:process.argv[2]})));
'''
    def invoke(original=None,reduced=None,entry_paths=None,private_metadata=False):
        original=original or [{'path':'core/license.cjs','source':SOURCE},{'path':'cli/main.cjs','source':CLI}]
        reduced=reduced if reduced is not None else [{'path':x['path'],'source':x['source'].replace('authoredDecoration','authoredRenamedDecoration')+'\n// authored change'} for x in original]
        out=subprocess.run([node,'--max-old-space-size=256','-e',driver,str(ROOT),str(BABEL)],
            input=json.dumps({'originalModules':original,'reducedModules':reduced,'entryPaths':entry_paths if entry_paths is not None else [original[0]['path']],'privateRuntimeMetadata':private_metadata}),
            text=True,capture_output=True,timeout=20,
            env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
        assert out.returncode==0,out.stderr
        return json.loads(out.stdout)
    return invoke


def test_source_byte_to_seed_and_acceptance_slice_is_binding_aware(analyze):
    result=analyze()
    assert result['status']=='observational_equivalence_unproved',result
    module=result['modules'][0]['original']
    assert module['inventory_completeness']['effect_inventory_exhaustive'] is False
    slices=module['source_integrity_slices']
    assert len(slices)==1
    sliced=slices[0]
    assert sliced['source_files']==['cli/main.cjs','core/license.cjs']
    assert sliced['source_inputs'][0]['base_relative_to_module_directory']=='..'
    assert sliced['admitted_export_paths'][0]['export']=='activate'
    assert len(sliced['admitted_export_paths'][0]['path'])==2
    site=sliced['consumption_sites'][0]
    assert site['immediate_argument_consumer']['argument_index']==0
    assert site['assigned_binding']['name']=='seed'
    assert {x['name'] for x in site['downstream_definitions']}=={'seed','alias','answer','matches'}
    assert len(site['crypto_acceptance_comparisons'])==1 and len(site['dependent_returns'])==1
    assert len(result['changed_source_integrity_inputs'])==4
    assert all(len(x['original_source_sha256'])==64 for x in result['changed_source_integrity_inputs'])


def test_matching_bytes_and_regions_do_not_establish_whole_js_equivalence(analyze):
    modules=[{'path':'core/license.cjs','source':SOURCE}]
    result=analyze(original=modules,reduced=modules)
    assert result['status']=='observational_equivalence_unproved'
    assert result['modules'][0]['status']=='byte_identical'
    assert result['modules'][0]['comparison']['exact_named_function_asts']
    assert result['changed_source_integrity_inputs']==[]


def test_target_source_is_never_executed_and_data_stays_out_of_report(analyze):
    text="const privateFixture='authored-sensitive-fixture';throw new Error('must never execute');"
    result=analyze(original=[{'path':'entry.cjs','source':text}])
    assert result['status']=='observational_equivalence_unproved'
    assert result['source_execution'] is False
    assert 'authored-sensitive-fixture' not in json.dumps(result)
    assert 'must never execute' not in json.dumps(result)


def test_source_paths_are_resolved_from_actual_checked_base(analyze):
    text=SOURCE.replace("join(__dirname,'..')","join(__dirname,'other')")
    result=analyze(original=[{'path':'core/license.cjs','source':text},{'path':'cli/main.cjs','source':CLI}])
    assert result['changed_source_integrity_inputs']==[]
    assert result['modules'][0]['original']['source_integrity_slices'][0]['source_inputs'][0]['base_relative_to_module_directory']=='other'


def test_unrelated_path_arrays_do_not_create_source_read_dependencies(analyze):
    text=SOURCE.replace('join(root,file)',"join(root,'fixed.bin')")
    result=analyze(original=[{'path':'core/license.cjs','source':text}])
    sliced=result['modules'][0]['original']['source_integrity_slices'][0]
    assert sliced['source_files']==[] and sliced['source_inputs']==[]
    assert result['changed_source_integrity_inputs']==[]


def test_shadowed_filesystem_or_hash_calls_are_not_builtins(analyze):
    text=SOURCE.replace('function fingerprint(){','function fingerprint(readFileSync,createHash){')
    result=analyze(original=[{'path':'core/license.cjs','source':text}])
    module=result['modules'][0]['original']
    assert module['source_integrity_slices']==[]
    assert any(x['kind']=='unresolved_call_target' for x in module['unresolved_boundaries'])


def test_async_top_level_entry_is_distinct_from_settlement(analyze):
    text='async function main(){await Promise.resolve();console.log("after");} main().catch(error=>console.error(error));globalThis.later=1;'
    result=analyze(original=[{'path':'entry.cjs','source':text}])
    model=result['modules'][0]['original']['initialization_execution_model']
    assert len(model['async_entry_calls'])==1 and len(model['first_awaits'])==1
    assert 'before Promise settlement' in model['note']


def test_exit_code_assignment_retains_following_initialization_effects(analyze):
    result=analyze()
    module=result['modules'][1]['original']
    assert module['initialization_execution_model']['async_entry_calls']==[]
    assert 'does not preempt' in module['initialization_execution_model']['note']
    assert any(x['kind']=='property_definition' and x['owner']=='$init' for x in module['effects'])
    assert any(x['target']=={'global':'process','property':'exitCode'} for x in module['writes'])


def test_reflection_and_environment_reads_remain_explicit(analyze):
    text="function check(){return Function.prototype.toString.call(Math.imul)+process.execArgv.join('')+process.env.NODE_OPTIONS;} module.exports={check};"
    result=analyze(original=[{'path':'entry.cjs','source':text}])
    reflection=result['modules'][0]['original']['reflection']
    assert any(x['kind']=='native_function_source_reflection' for x in reflection)
    assert len([x for x in reflection if x['kind']=='process_environment_read'])==2


def test_unknown_receivers_and_callbacks_are_not_declared_pure(analyze):
    text="const object={};object.arbitrary(()=>console.log('callback'));"
    result=analyze(original=[{'path':'entry.cjs','source':text}])
    module=result['modules'][0]['original']
    assert module['unresolved_boundaries']
    assert module['inventory_completeness']['effect_inventory_exhaustive'] is False


@pytest.mark.parametrize('modules,reduced,entry',[
    ([{'path':'../escape.cjs','source':'1;'}],None,None),
    ([{'path':'/absolute.cjs','source':'1;'}],None,None),
    ([{'path':'same.cjs','source':'1;'},{'path':'same.cjs','source':'2;'}],None,None),
    ([{'path':'a.cjs','source':'1;'}],[{'path':'b.cjs','source':'1;'}],None),
    ([{'path':'a.cjs','source':'1;'}],None,['missing.cjs']),
    ([{'path':'a.cjs','source':'function {'}],None,None),
])
def test_invalid_or_unpaired_inputs_fail_closed(analyze,modules,reduced,entry):
    assert analyze(original=modules,reduced=reduced,entry_paths=entry)['status']=='unknown'


def test_discarded_hash_and_unrelated_digest_do_not_get_a_returned_fingerprint_slice(analyze):
    for text in [SOURCE.replace("return hash.digest('hex');",'return 0;'),
                 SOURCE.replace("return hash.digest('hex');","return createHash('sha256').digest('hex');"),
                 SOURCE.replace('hash.update(readFileSync(join(root,file)))','unknown.update(readFileSync(join(root,file)))')]:
        result=analyze(original=[{'path':'core/license.cjs','source':text}])
        assert result['modules'][0]['original']['source_integrity_slices']==[]
        assert result['changed_source_integrity_inputs']==[]


def test_inline_html_script_path_and_await_qualification_are_supported(analyze):
    text='async function main(){if(unknown)await first();await second();}main();'
    result=analyze(original=[{'path':'panel.html#script:0','source':text}])
    assert result['status']=='observational_equivalence_unproved'
    model=result['modules'][0]['original']['initialization_execution_model']
    assert 'Lexically first' in model['await_qualification']
    assert 'not a general control-flow' in model['await_qualification']


def test_retired_input_extractor_is_separate_from_public_inventory(analyze):
    text="""
const retired=Object.freeze(['fixture-input-01','fixture-input-02','fixture-input-03']);
async function main(){const input=process.argv[2]||'';if(retired.includes(input)){console.log('retired');process.exit(0);}await work();}
main();
"""
    module=[{'path':'vault.cjs','source':text}]
    private=analyze(original=module,private_metadata=True)
    assert private['status']=='source_qualified_literal_candidates'
    assert private['honeypotInputs']==['fixture-input-01','fixture-input-02','fixture-input-03']
    public=analyze(original=module)
    assert 'fixture-input-' not in json.dumps(public)
    assert 'honeypotInputs' not in json.dumps(public)
    changed=analyze(original=[{'path':'vault.cjs','source':text+'const alias=retired;'}],private_metadata=True)
    assert changed['status']=='unknown'


def test_project_import_edges_connect_cli_input_to_exported_license_function(analyze):
    result=analyze(entry_paths=['cli/main.cjs'])
    graph=result['project_call_graph']['sides']['original']
    assert any(e['kind']=='commonjs_load' and e['caller_module']=='cli/main.cjs' and e['callee_module']=='core/license.cjs' for e in graph['edges'])
    assert any(e['kind']=='imported_export' and e['export']=='activate' and e['caller_module']=='cli/main.cjs' and e['callee_module']=='core/license.cjs' for e in graph['edges'])
    assert 'core/license.cjs::$init' in graph['may_reach']


def test_discarded_file_read_is_retained_as_effect_but_not_returned_digest_input(analyze):
    text=SOURCE.replace("const sourceFiles=", "const discardedFiles=['core/unrelated.cjs'];const sourceFiles=")
    text=text.replace("return hash.digest('hex');", "for(const ignored of discardedFiles){readFileSync(join(root,ignored));}return hash.digest('hex');")
    modules=[{'path':'core/license.cjs','source':text},
             {'path':'cli/main.cjs','source':CLI},
             {'path':'core/unrelated.cjs','source':'module.exports={};'}]
    result=analyze(original=modules)
    sliced=result['modules'][0]['original']['source_integrity_slices'][0]
    assert len(sliced['filesystem_reads'])==2
    assert len(sliced['hash_updates_with_file_bytes'])==1
    assert sliced['source_files']==['cli/main.cjs','core/license.cjs']
    assert all(x['read_module']!='core/unrelated.cjs' for x in result['changed_source_integrity_inputs'])
    assert len(result['changed_source_integrity_inputs'])==4
