"""Authored module/CLI boundaries: executed effects must survive contraction.

No original challenge source, commitment, key, ciphertext or flag is retained.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_bla_function_equivalence import TEMPLATE as CORE_TEMPLATE
from test_bla_seed_invariant import source as seed_source
from test_bla_shadow_heap_proof import FUNCTION, heap_literal

ROOT = Path(__file__).resolve().parents[1]
BABEL = Path(os.environ.get('FDISBULL_BABEL_ROOT',
    '/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules'))
CLI = r'''
function printUsage(){console.log('authored usage');console.log('authored instructions');}
function main(){
 const authorization=process.argv[2]||'';
 if(!authorization){printUsage();process.exit(1);}
 const result=tryUnlock(authorization);
 if(result){console.log('authored grant: '+result);process.exit(0);}
 console.error('authored denial');process.exit(1);
}
'''
TEMPLATE = CORE_TEMPLATE.replace('module.exports=', CLI + '\nmodule.exports=') + '\nif(require.main===module){main();}\n'
# Independent authored fixture for the checked environmental decorator profile.
DECORATOR = r'''
(function decorate(){try{
 const host=typeof globalThis!=='undefined'?globalThis:typeof window!=='undefined'?window:{};
 const switches=typeof process!=='undefined'&&Array.isArray(process.execArgv)?process.execArgv.join(' '):'';
 const observed=switches.includes('authored-debug')||switches.includes('authored-break')||Boolean(host&&(host.__playwright||host.__puppeteer_evaluation_script__||host.frida||host._frida_||host.navigator&&host.navigator.webdriver));
 const vault=Object.freeze({classification:'fixture',securityBoundary:'fixture',status:'fixture',enclaveCid:7,transport:'fixture',inspectorObserved:observed,attestationNotice:'fixture',sessionEpoch:13});
 if(host&&typeof Object.defineProperty==='function'&&!host['authoredModuleGetter']){
  Object.defineProperty(host,'authoredModuleGetter',{configurable:true,enumerable:false,get:function(){return vault;}});
 }
 if(host&&typeof host.addEventListener==='function'){
  const listener=function callback(event){return event&&event.type?vault.sessionEpoch:0;};
  host.addEventListener('authored-event',listener,{passive:true});
  host.addEventListener('another-authored-event',listener,{passive:true});
 }
}catch(_){}})();
'''
CRYPTO_DECORATION = r'''
 if(typeof process!=='undefined'&&typeof process.getBuiltinModule==='function'){
  const provider=process.getBuiltinModule('node:crypto');
  if(provider&&typeof provider.createHash==='function'){
   const salts=['authored-a','authored-b','authored-c','authored-d'];
   for(let salt=0;salt<salts.length;salt++){
    let digest=provider.createHash('sha256').update('authored-prefix'+salts[salt]+'authored-suffix').digest();
    for(let round=0;round<8;round++){
     digest=provider.createHash('sha256').update(digest).update(':'+salts[salt]+':'+round).digest();
    }
    if(typeof provider.createHmac==='function'){provider.createHmac('sha256',digest).update('authored-mac'+salts[salt]).digest();}
   }
  }
 }
'''


def target_source(template=TEMPLATE, tail=''):
    text=template
    for role,value in {'SCOPE':'authored.scope','KEY_SHA256':'authored-key-commitment',
                       'FLAG_SHA256':'authored-output-commitment','FLAG_CIPHER_HEX':'00000000'}.items():
        text=text.replace('%%'+role+'%%',value)
    for role in ('sha256Hex','deriveFlagMask','decodeFlagCipher','tryUnlock','printUsage','main'):
        start=text.index('function '+role+'(')
        body=text.index('{',start)+1
        text=text[:body]+'stepShadowHeapFixture(1);'+text[body:]
    prefix=seed_source().replace('digestFixture','_deriveContainmentCorpusDigest_fixture').replace('seedFixture','runtimeSeedFixture')
    heap='const shadowHeapFixture='+json.dumps(heap_literal())+';\n'
    step=FUNCTION.replace('function advance(', 'function stepShadowHeapFixture(').replace('heap','shadowHeapFixture')
    return prefix+heap+step+text+tail


@pytest.fixture(scope='module')
def prove():
    node=shutil.which('node')
    if not node or not (BABEL/'@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required for module composition')
    driver=r'''
const fs=require('node:fs'),path=require('node:path');
const {proveModuleEquivalence}=require(path.join(process.argv[1],'scripts/bla_module_equivalence.cjs'));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(proveModuleEquivalence({templateSource:input.template,targetSource:input.target,babelRoot:process.argv[2]})));
'''
    def invoke(template=TEMPLATE,target=None):
        out=subprocess.run([node,'--max-old-space-size=256','-e',driver,str(ROOT),str(BABEL)],
            input=json.dumps({'template':template,'target':target if target is not None else target_source(template)}),
            capture_output=True,text=True,timeout=20,
            env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
        assert out.returncode==0,out.stderr
        return json.loads(out.stdout)
    return invoke


def test_complete_cli_and_pure_module_initialization_compose(prove):
    proof=prove()
    assert proof['status']=='equivalent_under_contract',proof
    assert proof['initialization']['all_executed_initializers_classified'] is True
    assert proof['cli']['status']=='equivalent_under_contract'
    assert proof['cli']['termination']['post_dispatch_initializers_unreachable'] is True
    assert proof['cli']['checked_reductions']['private_stuttering_calls']==6
    assert proof['commonjs_exports']['status']=='related_after_successful_initialization'
    assert proof['cli']['valid_key_acceptance_witness']=='not_established_by_static_equivalence'
    assert 'provider throws' in ' '.join(proof['cli']['observer_contract'])
    assert proof['full_state_equivalence'] is False
    assert len(proof['certificate_sha256'])==64
    text=json.dumps(proof)
    assert 'authored-key-commitment' not in text and 'authored-output-commitment' not in text
    assert 'function main' not in text


def test_global_getter_is_a_module_counterexample_without_weakening_cli(prove):
    proof=prove(target=target_source(tail=DECORATOR))
    assert proof['status']=='different',proof
    assert proof['cli']['status']=='equivalent_under_contract'
    init=proof['initialization']
    assert init['status']=='different' and init['all_executed_initializers_classified'] is True
    assert init['counterexample']['clean_global_own_property_delta']==0
    assert init['counterexample']['target_global_own_property_delta']==1
    effect=init['global_effects'][0]
    assert effect['descriptor']=={'configurable':True,'enumerable':False,'getter':True,'setter':False}
    assert effect['conditional_event_registrations']==2
    assert effect['conditional_crypto_calls'] is None
    assert 'authoredModuleGetter' not in json.dumps(proof)


def test_crypto_work_after_cli_exit_remains_in_the_effect_footprint(prove):
    decoration=DECORATOR.replace('}catch(_){}})();',CRYPTO_DECORATION+'}catch(_){}})();')
    proof=prove(target=target_source(tail=decoration))
    assert proof['status']=='different',proof
    calls=proof['initialization']['global_effects'][0]['conditional_crypto_calls']
    assert calls['sha256']==36 and calls['hmac_sha256']==4 and calls['discarded'] is True
    assert proof['cli']['termination']['post_dispatch_initializers_unreachable'] is True


@pytest.mark.parametrize('tail',[
    "console.log('reached');", "const unused=unknownCallback();", "module.exports.extra=1;",
    "const unused={get value(){return 1;}};", "let mutable=1;", "const unused=Object.freeze(unknown);",
    "const unused={...unknown};", "const unused=new Array(100000000).fill(0);",
    "Object.defineProperty(globalThis,'authoredModuleGetter',{value:0});",
])
def test_unmodeled_executed_initializers_do_not_get_erased_as_unused(prove,tail):
    proof=prove(target=target_source(tail=tail))
    assert proof['status']=='unknown',proof
    assert proof['cli']['status']=='equivalent_under_contract'
    assert proof['initialization']['status']=='unknown'
    assert proof['commonjs_exports']['status']=='unknown'


@pytest.mark.parametrize('before,after',[
    ('round<8','round<1e30'), ("createHash('sha256')","createHash('unsupported')"),
    ("getBuiltinModule('node:crypto')","getBuiltinModule('node:fs')"),
    ("'authored-a'","{get x(){throw 1;}}"), ('round++','round--'),
    ('salt<salts.length','salt<=salts.length'), (".digest();",".digest();globalThis.changed=1;"),
])
def test_crypto_profile_preserves_control_provider_and_data_boundaries(prove,before,after):
    decoration=DECORATOR.replace('}catch(_){}})();',CRYPTO_DECORATION+'}catch(_){}})();')
    assert before in decoration
    proof=prove(target=target_source(tail=decoration.replace(before,after)))
    assert proof['status']=='unknown',proof
    assert proof['initialization']['status']=='unknown'
    assert proof['cli']['status']=='equivalent_under_contract'


@pytest.mark.parametrize('before,after',[
    ("typeof globalThis!=='undefined'","typeof globalThis==='undefined'"),
    ("typeof Object.defineProperty==='function'","typeof Object.defineProperty!=='function'"),
    ("configurable:true","configurable:false"), ("enumerable:false","enumerable:true"),
    ("get:function(){return vault;}","get:function(){console.log('effect');return vault;}"),
    ("'another-authored-event',listener","'another-authored-event',()=>console.log('effect')"),
])
def test_global_effect_profile_is_source_checked_not_spelling_based(prove,before,after):
    proof=prove(target=target_source(tail=DECORATOR.replace(before,after)))
    assert proof['status']=='unknown',proof
    assert proof['cli']['status']=='equivalent_under_contract'


@pytest.mark.parametrize('before,after',[
    ('process.exit(1);','process.exit(0);'), ('process.argv[2]','process.argv[3]'),
    ('console.error(\'authored denial\')','console.log(\'authored denial\')'),
    ('function main(){','function main(){unknownCallback();'),
    ('if(require.main===module){main();}','if(require.main===module){main();unknownCallback();}'),
])
def test_cli_observation_or_dispatch_changes_fail_before_a_certificate(prove,before,after):
    original=target_source()
    assert before in original
    proof=prove(target=original.replace(before,after,1))
    assert proof['status']=='unknown'
    assert proof.get('cli',{}).get('status')!='equivalent_under_contract'


def test_even_matching_cli_asts_need_the_immediate_exit_control_profile(prove):
    template=TEMPLATE.replace('process.exit(1);','console.log(1);')
    proof=prove(template=template,target=target_source(template))
    assert proof['status']=='unknown' and proof['reason']=='reference_cli_exit_profile'


def test_executed_prefix_order_and_effects_are_not_ignored(prove):
    text=target_source().replace('module.exports=','console.log(\'before dispatch\');module.exports=')
    proof=prove(target=text)
    assert proof['status']=='unknown' and proof['reason']=='module_executed_prefix_difference'


def test_authored_native_import_exhibits_the_static_counterexample():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required for native import')
    driver=r'''
const fs=require('node:fs'),Module=require('node:module');
const source=JSON.parse(fs.readFileSync(0,'utf8'));
const before=new Set(Reflect.ownKeys(globalThis));
const m=new Module('authored-module');m.filename='/authored-module.cjs';m._compile(source,m.filename);
const added=Reflect.ownKeys(globalThis).filter(k=>!before.has(k));
console.log(JSON.stringify(added.map(k=>{const d=Object.getOwnPropertyDescriptor(globalThis,k);return {getter:typeof d.get==='function',setter:typeof d.set==='function',enumerable:d.enumerable,configurable:d.configurable};})));
'''
    out=subprocess.run([node,'-e',driver],input=json.dumps(target_source(tail=DECORATOR)),capture_output=True,text=True,timeout=10,
        env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
    assert out.returncode==0,out.stderr
    assert json.loads(out.stdout)==[{'getter':True,'setter':False,'enumerable':False,'configurable':True}]


def test_duplicate_cli_declarations_cannot_hide_hoisting_changes(prove):
    proof=prove(target=target_source(tail="function main(){console.log('other body');}"))
    assert proof['status']=='unknown'
    assert proof.get('cli',{}).get('status')!='equivalent_under_contract'


def test_duplicate_getter_keys_are_not_counted_as_two_distinct_effects(prove):
    proof=prove(target=target_source(tail=DECORATOR+DECORATOR))
    assert proof['status']=='unknown'
    assert proof['initialization']['reason']=='duplicate_global_effect_key'
    assert proof['cli']['status']=='equivalent_under_contract'


def test_pure_unused_allocations_are_checked_without_calling_their_methods(prove):
    tail="""
function dormant(){throw 'not called';}
void dormant;
const safe=Object.freeze({numeric:7^9,strings:Object.freeze(['authored']),method(){throw 'not called';}});
const ring={epoch:13,slots:new Array(16).fill(0)};
const oddPid=(typeof process!=="undefined"&&process.pid?process.pid&0xff:42)|1;
"""
    proof=prove(target=target_source(tail=tail))
    assert proof['status']=='equivalent_under_contract',proof
    assert proof['initialization']['all_executed_initializers_classified'] is True
