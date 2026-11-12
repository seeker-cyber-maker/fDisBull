"""Authored fixtures for source replay, noninterference and call composition."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_bla_shadow_heap_proof import FUNCTION, heap_literal


ROOT = Path(__file__).resolve().parents[1]
BABEL = Path(os.environ.get('FDISBULL_BABEL_ROOT',
    '/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules'))
TEMPLATE = r'''
const {createHash}=require('node:crypto');
const SCOPE='%%SCOPE%%',KEY_SHA256='%%KEY_SHA256%%',FLAG_SHA256='%%FLAG_SHA256%%',FLAG_CIPHER_HEX='%%FLAG_CIPHER_HEX%%';
const LICENSE_RPC={verifyEntitlement:'/authored'};
function sha256Hex(value){return createHash('sha256').update(String(value),'utf8').digest('hex');}
function deriveFlagMask(key){return createHash('sha256').update(`${SCOPE}|${key}`,'utf8').digest();}
function decodeFlagCipher(key){
 const mask=deriveFlagMask(key);const cipher=Buffer.from(FLAG_CIPHER_HEX,'hex');const plain=Buffer.alloc(cipher.length);
 for(let i=0;i<cipher.length;i++){plain[i]=cipher[i]^mask[i%mask.length];}
 return plain.toString('utf8');
}
function tryUnlock(key){
 if(typeof key!=='string')return null;
 if(key.length<1)return null;
 if(key===LICENSE_RPC.verifyEntitlement)return null;
 if(sha256Hex(key)!==KEY_SHA256)return null;
 const result=decodeFlagCipher(key);
 if(!result.startsWith('entry{')||!result.endsWith('}'))return null;
 if(sha256Hex(result)!==FLAG_SHA256)return null;
 return result;
}
module.exports={sha256Hex,tryUnlock,SCOPE,KEY_SHA256,FLAG_SHA256,LICENSE_RPC};
'''


def target_source(template=TEMPLATE):
    source=template
    for role,value in {'SCOPE':'authored.scope','KEY_SHA256':'authored-key-commitment',
                       'FLAG_SHA256':'authored-output-commitment','FLAG_CIPHER_HEX':'00000000'}.items():
        source=source.replace('%%'+role+'%%',value)
    for role,param in [('sha256Hex','value'),('deriveFlagMask','key'),('decodeFlagCipher','key'),('tryUnlock','key')]:
        source=source.replace(f'function {role}({param}){{',f'function {role}({param}){{stepShadowHeapFixture(1);')
    prefix=('const runtimeSeedFixture=(12 & 262140) | (typeof _deriveContainmentCorpusDigest_fixture==="function" '
            '&& _deriveContainmentCorpusDigest_fixture(0)===7 ? 1 : 0);\n'
            'function _deriveContainmentCorpusDigest_fixture(){return 7;}\n'
            'const shadowHeapFixture='+json.dumps(heap_literal())+';\n')
    mutator=FUNCTION.replace('function advance(', 'function stepShadowHeapFixture(').replace('heap','shadowHeapFixture')
    return prefix+mutator+'\n'+source


@pytest.fixture(scope='module')
def compose():
    node=shutil.which('node')
    if not node or not (BABEL/'@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required for composition')
    driver=r'''
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require(path.join(process.argv[1],'scripts/bla_function_analysis.cjs'));
const {composeFunctionEquivalence}=require(path.join(process.argv[1],'scripts/bla_function_equivalence.cjs'));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
try {
 const a=analyze(input.template,input.target,{babelRoot:process.argv[2]});
 const r=a.runtime;
 const options={templateSource:input.template,targetSource:input.target,babelRoot:process.argv[2],
  functionNames:r.functionNames,seedName:r.seedName,heapName:r.heapName,heapStepName:r.heapStepName,
  cryptoBindingName:r.cryptoBindingName,cipherName:r.cipherName,
  globalMap:{sha256Hex:'sha256Hex',deriveFlagMask:'deriveFlagMask',decodeFlagCipher:'decodeFlagCipher',tryUnlock:'tryUnlock',
    createHash:'createHash',SCOPE:'SCOPE',KEY_SHA256:'KEY_SHA256',FLAG_SHA256:'FLAG_SHA256',FLAG_CIPHER_HEX:'FLAG_CIPHER_HEX',LICENSE_RPC:'LICENSE_RPC'},
  guardProofs:a.report.guard_reductions,contractionLedger:a.report.contraction_ledger,
  heapProof:r.shadowHeapProof,noninterferenceProof:r.heapNoninterference};
 if(input.mode==='missing_ni')delete options.noninterferenceProof;
 if(input.mode==='forged_ni')options.noninterferenceProof={status:'proved'};
 if(input.mode==='missing_step')options.contractionLedger=options.contractionLedger.filter(x=>x.kind!=='private_heap_step');
 if(input.mode==='extra_step')options.contractionLedger.push({kind:'private_heap_step',source_offsets:[1,2],argument_count:1});
 if(input.mode==='guard_evidence')options.guardProofs=[{kind:'invented'}];
 if(input.mode==='stale_source')options.targetSource+='\n// changed source receipt\n';
 if(input.mode==='role_mapping')options.globalMap.KEY_SHA256='SCOPE';
 if(input.mode==='stale_heap')options.heapProof={...options.heapProof,status:'unknown'};
 console.log(JSON.stringify(composeFunctionEquivalence(options)));
}catch(error){console.log(JSON.stringify({status:'unknown',reason:'source_rejected_before_composition'}));}
'''

    def invoke(template=TEMPLATE,target=None,mode=None):
        result=subprocess.run([node,'--max-old-space-size=256','-e',driver,str(ROOT),str(BABEL)],
            input=json.dumps({'template':template,'target':target if target is not None else target_source(template),'mode':mode}),
            text=True,capture_output=True,timeout=20,
            env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    return invoke


def test_source_replay_composes_all_four_function_contracts(compose):
    c=compose()
    assert c['status']=='equivalent_under_contract',c
    assert len(c['functions'])==4 and len(c['constants'])==5
    assert c['call_graph']['decodeFlagCipher']==['deriveFlagMask']
    assert c['composition_order'].index('deriveFlagMask')<c['composition_order'].index('decodeFlagCipher')
    assert c['composition_order'][-1]=='tryUnlock'
    assert c['full_state_equivalence'] is False
    assert c['finite_runtime_checks_are_not_proof'] is True
    assert len(c['noninterference_certificate_sha256'])==64
    assert 'primitive' in c['input_domains']['sha256Hex']
    assert 'nonstrings return null' in c['input_domains']['tryUnlock']
    assert 'Coupled total synchronous' in c['leaf_contract']['provider']
    assert 'LICENSE_RPC' in c['public_state_contract']
    serialized=json.dumps(c)
    assert 'authored-key-commitment' not in serialized and 'authored-output-commitment' not in serialized
    assert 'function sha256Hex' not in serialized


def test_pure_guard_and_literal_replay_is_bound_to_the_real_source_site(compose):
    source=target_source().replace("return createHash('sha256')",
        "return (Math.imul(runtimeSeedFixture ^ 7,runtimeSeedFixture ^ 7)&7)===0 ? 'unreachable' : createHash('sha'+'256')",1)
    c=compose(target=source)
    assert c['status']=='equivalent_under_contract',c
    assert c['checked_reductions']=={'opaque_guards':1,'private_stuttering_calls':4}


@pytest.mark.parametrize('mode',['missing_ni','forged_ni','missing_step','extra_step','guard_evidence','stale_source','role_mapping','stale_heap'])
def test_missing_stale_or_mismatched_evidence_cannot_compose(compose,mode):
    c=compose(mode=mode)
    assert c['status']=='unknown' and 'certificate_sha256' not in c


@pytest.mark.parametrize('before,after',[
    ("String(value)","String(LICENSE_RPC)"),
    ("String(value)","mystery(value)"),
    (".update(String(value),'utf8')",".push(String(value),'utf8')"),
    ("Buffer.from(FLAG_CIPHER_HEX,'hex')","Buffer.alloc(FLAG_CIPHER_HEX)"),
    ("plain.toString('utf8')","key.toString('utf8')"),
    ("if(typeof key!=='string')return null;","if(typeof key==='string')return null;"),
    ("deriveFlagMask(key);","decodeFlagCipher(key);"),
    ("const LICENSE_RPC={verifyEntitlement:'/authored'};","const LICENSE_RPC={verifyEntitlement:'/authored',__proto__:'x'};"),
    ("return result;","if(result.length<1)return null;"),
    ("function deriveFlagMask(key){","function deriveFlagMask(key){if(key.length>0)return null;"),
])
def test_matching_asts_need_typed_leaf_and_input_contracts(compose,before,after):
    template=TEMPLATE.replace(before,after)
    c=compose(template=template)
    assert c['status']=='unknown'


def test_shadowed_private_step_cannot_be_erased_as_a_stutter(compose):
    source=target_source().replace('function sha256Hex(value){','function sha256Hex(stepShadowHeapFixture){').replace('String(value)','String(stepShadowHeapFixture)')
    assert compose(target=source)['status']=='unknown'


def test_changed_observable_constant_is_a_difference(compose):
    source=target_source().replace("verifyEntitlement:'/authored'","verifyEntitlement:'/different'")
    assert compose(target=source)['status']=='unknown'
