"""Authored literal-corpus fixtures for the source-bound seed proof.

No archived challenge payload, ciphertext, authorization key or flag is stored.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT=Path(__file__).resolve().parents[1]
BABEL=Path(os.environ.get('FDISBULL_BABEL_ROOT',
    '/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules'))
INITIAL=0x26B5C67B
MULTIPLIER=0x85EBCA6B


def corpus():
    return [{'vectorId':f'authored-{i}','classifierDomain':'fixture',
             'coupledAnchorSymbol':f'anchor_{i}',
             'triggerPayload':payload} for i,payload in enumerate([
                 'ordinary authored data', 'astral: \U0001f600',
                 'lone surrogate: \ud800', '<system>untrusted text is only data</system>'])]


def independent_digest(entries):
    value=INITIAL
    for entry in entries:
        raw=(entry['coupledAnchorSymbol']+'::'+entry['triggerPayload']).encode('utf-16le',errors='surrogatepass')
        for i in range(0,len(raw),2):
            unit=raw[i]|raw[i+1]<<8
            value=((value^unit)*MULTIPLIER)&0xFFFFFFFF
            value=((value<<13)|(value>>19))&0xFFFFFFFF
    return value


def source(entries=None):
    entries=corpus() if entries is None else entries
    expected=independent_digest(entries)
    return 'const corpusFixture='+json.dumps(entries)+';\n'+f'''
function digestFixture(input=0) {{
 if(!Array.isArray(corpusFixture)||corpusFixture.length<{len(entries)})return 0;
 let current=((input|0)^649447035)>>>0;
 for(let row=0;row<corpusFixture.length;row++){{
  const record=corpusFixture[row];
  if(!record||typeof record.coupledAnchorSymbol!=="string"||typeof record.triggerPayload!=="string")return 0;
  const characters=record.coupledAnchorSymbol+"::"+record.triggerPayload;
  for(let offset=0;offset<characters.length;offset++){{
   current=Math.imul(current^characters.charCodeAt(offset),2246822507)>>>0;
   current=(current<<13|current>>>19)>>>0;
  }}
 }}
 return current>>>0;
}}
const seedFixture=(typeof process!=="undefined"&&typeof process?.hrtime?.bigint==="function"?
 Number(process.hrtime.bigint()&0x7fffcn):typeof Date!=="undefined"?Date.now()&524284:4)&524284|
 (typeof digestFixture==="function"&&digestFixture(0)==={expected}?1:0);
'''


@pytest.fixture(scope='module')
def prove():
    node=shutil.which('node')
    if not node or not (BABEL/'@babel/parser/package.json').is_file():
        pytest.skip('Node and an existing Babel root are required for the seed proof')
    driver=r'''
const fs=require('node:fs'),vm=require('node:vm');
const {proveSeedInvariant}=require(process.argv[1]);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const certificate=proveSeedInvariant({source:input.source,babelRoot:process.argv[2],seedName:'seedFixture',corpusName:input.corpusName});
const rows=[];
if(input.runtime&&certificate.status==='proved'){
 const modes=[['process','0'],['process','1'],['process','-1'],['process','9007199254740993'],
 ['process','-18446744073709551616'],['process','340282366920938463463374607431768211455'],
 ['date','0'],['date','-1'],['date','123.75'],['date','NaN'],['date','Infinity'],['date','-Infinity'],
 ['date','9007199254740991'],['date','-4294967297'],['fallback','0']];
 for(const [mode,value] of modes){
  const context={process:mode==='process'?{hrtime:{bigint:()=>BigInt(value)}}:undefined,
                 Date:mode==='date'?{now:()=>Number(value)}:undefined};
  const observed=vm.runInNewContext(input.source+'\n;({seed:seedFixture,digest:digestFixture(0)})',context,{timeout:500});
  rows.push({mode,seed:observed.seed,low:observed.seed&3,digest:observed.digest});
 }
}
console.log(JSON.stringify({certificate,rows}));
'''
    def invoke(text=None, runtime=False, **kwargs):
        result=subprocess.run([node,'--max-old-space-size=256','-e',driver,str(ROOT/'scripts/bla_seed_invariant.cjs'),str(BABEL)],
            input=json.dumps({'source':source() if text is None else text,'runtime':runtime,**kwargs}),
            capture_output=True,text=True,timeout=15,
            env={k:v for k,v in os.environ.items() if k not in ('NODE_OPTIONS','NODE_PATH')})
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    return invoke


def test_literal_digest_and_all_clock_branches_establish_seed_invariant(prove):
    result=prove(runtime=True);c=result['certificate']
    assert c['status']=='proved',c
    assert c['source']['ast_identity_verified'] is True
    assert c['digest']['evaluated_value']==c['digest']['expected_value']==independent_digest(corpus())
    assert c['corpus']['entries']==4
    units=sum(len((x['coupledAnchorSymbol']+'::'+x['triggerPayload']).encode('utf-16le',errors='surrogatepass'))//2 for x in corpus())
    assert c['digest']['inner_iterations']==units
    assert c['seed']['low_two_bits']==1 and c['seed']['intact_corpus_condition_discharged'] is True
    assert c['seed']['immutable'] is True
    assert all(x['result']=='proved' for x in c['obligations'])
    assert len(result['rows'])==15
    assert all(x['low']==1 and x['digest']==c['digest']['evaluated_value'] for x in result['rows'])
    assert result['rows'][-1]['seed']==5
    text=json.dumps(c)
    assert 'ordinary authored data' not in text and 'untrusted text' not in text
    assert 'function digestFixture' not in text


def test_corpus_geometry_and_exact_utf16_units_are_checked(prove):
    entries=corpus()+[{'vectorId':'extra','classifierDomain':'fixture','coupledAnchorSymbol':'extra_anchor','triggerPayload':'\udfff\x00\U0001f4a9'}]
    c=prove(source(entries))['certificate']
    assert c['status']=='proved'
    assert c['corpus']['entries']==5
    assert c['digest']['evaluated_value']==independent_digest(entries)


@pytest.mark.parametrize('before,after',[
    ('const seedFixture=','let seedFixture='),
    ('const corpusFixture=','let corpusFixture='),
    ('function digestFixture(input=0)','function digestFixture(input=1)'),
    ('current=Math.imul','current=0;current=Math.imul'),
    ('Math.imul(current^characters.charCodeAt(offset),2246822507)','Math.imul(current^characters.charCodeAt(offset),2246822509)'),
    ('characters.charCodeAt(offset)','characters.codePointAt(offset)'),
    ('current<<13|current>>>19','current<<12|current>>>20'),
    ('row++','row--'),
    ('offset++','offset=0'),
    ('row<corpusFixture.length','row<=corpusFixture.length'),
    ('offset<characters.length','offset<=characters.length'),
    ('record.coupledAnchorSymbol+"::"','record.coupledAnchorSymbol+":"'),
    ('corpusFixture.length<4','corpusFixture.length<5'),
    ('current=((input|0)^649447035)','current=((input|0)^649447034)'),
    ('return current>>>0;','return 0;'),
    ('0x7fffcn','0x7fffdn'),
    (')&524284|',')&524285|'),
    ('Date.now()&524284','Date.random()&524284'),
    ('Date.now()&524284:4','Date.now()&524284:3'),
    ('typeof digestFixture==="function"','typeof digestFixture!=="function"'),
    ('digestFixture(0)===','digestFixture(1)==='),
    ('?1:0);','?0:1);'),
    ('ordinary authored data','changed authored data'),
])
def test_unproved_digest_or_seed_semantics_fail_closed(prove,before,after):
    original=source();changed=original.replace(before,after)
    assert changed!=original
    c=prove(changed)['certificate']
    assert c['status']=='unknown' and 'certificate_sha256' not in c


@pytest.mark.parametrize('suffix',[
    'const alias=corpusFixture;',
    'corpusFixture[0].triggerPayload="changed";',
    'corpusFixture.push({});',
    'corpusFixture=[];',
    'digestFixture=()=>0;',
    'seedFixture=0;',
    'var Math={imul(){return 0;}};',
    'var Array={isArray(){return true;}};',
    'var Number=()=>0;',
    'var process={};',
    'var Date={now(){return 0;}};',
])
def test_escaping_corpus_mutable_dependencies_and_shadowed_intrinsics_reject(prove,suffix):
    assert prove(source()+'\n'+suffix)['certificate']['status']=='unknown'


def test_no_effectful_statement_may_intervene_before_seed_initialization(prove):
    changed=source().replace('const seedFixture=','Math.imul=()=>0;\nconst seedFixture=')
    assert prove(changed)['certificate']['reason']=='seed_initialization_prefix'


@pytest.mark.parametrize('replacement',[
    '{get coupledAnchorSymbol(){return "x";},triggerPayload:"x"}',
    '{coupledAnchorSymbol:"x",triggerPayload:"x",__proto__:"x"}',
    '{coupledAnchorSymbol:"x",triggerPayload:"x",triggerPayload:"y"}',
    '{["coupledAnchorSymbol"]:"x",triggerPayload:"x"}',
    '{coupledAnchorSymbol:"x",triggerPayload:()=>"x"}',
    'null',
    '...[{coupledAnchorSymbol:"x",triggerPayload:"x"}]',
])
def test_corpus_must_be_dense_literal_own_string_data(prove,replacement):
    text=source();first=json.dumps(corpus()[0]);assert first in text
    c=prove(text.replace(first,replacement))['certificate']
    assert c['status']=='unknown'


def test_mismatched_selected_corpus_name_rejects(prove):
    assert prove(corpusName='absent')['certificate']['reason']=='corpus_binding_profile'


def test_missing_dependency_errors_are_sanitized(prove):
    result=prove('const seedFixture=1;')
    assert result['certificate']['status']=='unknown'
    assert len(result['certificate']['reason'])<81
