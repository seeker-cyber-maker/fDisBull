"""The portable scalar backends execute authored cases with independent answers."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.project import Project
from fdisbull.stock_flow import maintenance_contract, maintenance_module
from fdisbull.udc_layers import digest, register_contract, register_layer, select_layers


def project_at(tmp_path):
    source = tmp_path/'authored.com'
    source.write_bytes(bytes.fromhex('b8004ccd21'))
    return Project.create(tmp_path/'authored.fdb',source,image='com')


def selected(project,target,mutate=None,domain=None):
    contract = maintenance_contract()
    stored = register_contract(project,contract)
    program = copy.deepcopy(contract['behavior']['program'])
    if mutate: mutate(program)
    layer = {'format':'fdisbull-udl-layer-1','name':'portable.food',
             'contract':stored['id'],'implementation':{'backend':'uil','program':program}}
    if domain: layer['domain'] = domain
    retained = register_layer(project,layer)
    module = maintenance_module(stored['id'])
    choice = select_layers(project,'web.food',{'food':retained['id']},program=module,target=target)
    return choice['id'],module


def test_public_build_surface_is_discoverable():
    from fdisbull.udc_api import METHODS
    assert 'build-web-block' in METHODS


def test_json_method_resolves_a_persisted_selection(tmp_path):
    from fdisbull.cli import respond
    with project_at(tmp_path) as p:
        choice,_ = selected(p,'webgpu-wgsl-scalar-1')
    result = respond({'method':'build-web-block','params':{'project':str(tmp_path/'authored.fdb'),
                     'selection':choice,'destination':str(tmp_path/'web')}})
    assert result['ok'],result
    assert result['result']['target']=='webgpu-wgsl-scalar-1'
    assert result['result']['execution'] is False


@pytest.mark.parametrize('target,artifact',[('wasm32-scalar-1','block.wasm'),('webgpu-wgsl-scalar-1','block.wgsl')])
def test_persisted_selection_build_is_deterministic_and_build_only(tmp_path,target,artifact):
    from fdisbull.udc_web import build_web_block
    with project_at(tmp_path) as p:
        choice,module = selected(p,target)
    with Project(tmp_path/'authored.fdb') as p:
        a = build_web_block(p,choice,tmp_path/'a')
        b = build_web_block(p,choice,tmp_path/'b')
    assert a == b
    assert a['module_uil_sha256'] == digest(module)
    assert a['execution'] is False and a['source_to_uil'] is False
    assert (tmp_path/'a'/artifact).read_bytes() == (tmp_path/'b'/artifact).read_bytes()
    assert (tmp_path/'a/host.mjs').is_file()
    assert a['abi']['inputs'] == sorted(maintenance_contract()['inputs'])


def test_wrong_rule_target_and_git_outputs_refuse_before_emission(tmp_path):
    from fdisbull.udc_web import build_web_block
    with project_at(tmp_path) as p:
        wrong,_ = selected(p,'wasm32-scalar-1',lambda d:d['body'].append(
            {'id':'wrong','op':'set','var':'$new_stock','value':0}))
        with pytest.raises(ValueError,match='qualified'):
            build_web_block(p,wrong,tmp_path/'wrong')
        other,_ = selected(p,'not-a-web-backend')
        with pytest.raises(ValueError,match='target'):
            build_web_block(p,other,tmp_path/'other')
        good,_ = selected(p,'wasm32-scalar-1')
        (tmp_path/'repo/.git').mkdir(parents=True)
        with pytest.raises(ValueError,match='outside Git'):
            build_web_block(p,good,tmp_path/'repo/output')
        (tmp_path/'dangling').symlink_to(tmp_path/'missing')
        with pytest.raises(ValueError,match='new private'):
            build_web_block(p,good,tmp_path/'dangling')
        assert not (tmp_path/'missing').exists()
    assert not any((tmp_path/n).exists() for n in ('wrong','other','repo/output'))


@pytest.mark.skipif(not shutil.which('node'),reason='actual WebAssembly execution needs Node')
def test_real_wasm_signed_boundaries_guards_and_host_validation(tmp_path):
    from fdisbull.udc_web import build_web_block
    with project_at(tmp_path) as p:
        choice,_ = selected(p,'wasm32-scalar-1')
        built = build_web_block(p,choice,tmp_path/'web')
    good = [
        ({'stock':10,'produced':9,'population':3,'supported':2,'support_cost':1},11),
        ({'stock':10,'produced':9,'population':3,'supported':2,'support_cost':2},9),
        ({'stock':32767,'produced':32767,'population':-128,'supported':-32768,'support_cost':2},254),
        ({'stock':-32768,'produced':-32768,'population':127,'supported':32767,'support_cost':1},32515)]
    bad = [{**good[0][0],name:value} for name,values in (
        ('population',(-129,128)),('support_cost',(0,3)),('stock',(-32769,32768))) for value in values]
    rows = [[r[k] for k in built['abi']['inputs']] for r in [x for x,_ in good]+bad]
    (tmp_path/'web/rows.json').write_text(json.dumps(rows))
    script = """
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {instantiateWasm,runWASM} from './host.mjs';
const build=JSON.parse(await fs.readFile('build.json'));
const bytes=await fs.readFile('block.wasm');
const rows=JSON.parse(await fs.readFile('rows.json'));
const instance=await instantiateWasm(bytes,build);
assert.throws(()=>runWASM(instance,build.abi,[[1]]));
assert.throws(()=>runWASM(instance,build.abi,[[NaN,...rows[0].slice(1)]]));
assert.throws(()=>runWASM(instance,build.abi,[[2147483648,...rows[0].slice(1)]]));
assert.throws(()=>runWASM(instance,build.abi,[Array(rows[0].length)]));
assert.throws(()=>runWASM(instance,build.abi,Array(1)));
const corrupt=bytes.slice();corrupt[0]^=1;
await assert.rejects(()=>instantiateWasm(corrupt,build));
console.log(JSON.stringify(runWASM(instance,build.abi,rows)));
"""
    (tmp_path/'web/run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'),'run.mjs'],cwd=tmp_path/'web',text=True,capture_output=True,check=True)
    frames = json.loads(run.stdout)
    assert frames[:4] == [{'status':0,'data':[answer]} for _,answer in good]
    assert frames[4:] == [{'status':1,'data':[]}]*6


@pytest.mark.skipif(not shutil.which('node'),reason='actual WebAssembly execution needs Node')
def test_extra_layer_domain_is_enforced_in_emitted_code(tmp_path):
    from fdisbull.udc_web import build_web_block
    with project_at(tmp_path) as p:
        choice,_ = selected(p,'wasm32-scalar-1',domain={'support_cost':{'min':2,'max':2}})
        build_web_block(p,choice,tmp_path/'web')
    script = """
import fs from 'node:fs/promises';
import {instantiateWasm,runWASM} from './host.mjs';
const b=JSON.parse(await fs.readFile('build.json'));
const i=await instantiateWasm(await fs.readFile('block.wasm'),b);
const rows=[1,2].map(c=>b.abi.inputs.map(n=>({stock:10,produced:9,population:3,supported:2,support_cost:c})[n]));
console.log(JSON.stringify(runWASM(i,b.abi,rows)));
"""
    (tmp_path/'web/run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'),'run.mjs'],cwd=tmp_path/'web',text=True,capture_output=True,check=True)
    assert json.loads(run.stdout) == [{'status':1,'data':[]},{'status':0,'data':[9]}]


@pytest.mark.parametrize('typ,start,expected',[
    ('u8',255,0),('u16',65535,0),('i8',127,-128),('i16',32767,-32768)])
@pytest.mark.skipif(not shutil.which('node'),reason='actual WebAssembly execution needs Node')
def test_reusable_block_widths_have_independent_wrap_answers(tmp_path,typ,start,expected):
    from fdisbull.udc_web import build_web_block
    from examples.recovery.civd_food_web import module_for
    program = {'format':'fdisbull-il-1','role':'uil','variables':{'$x':{'type':typ,'initial':0}},
               'resources':{},'body':[{'id':'increment','op':'add','var':'$x','value':1}]}
    contract = {'format':'fdisbull-block-contract-1','name':'authored.increment','inputs':{'x':typ},
                'outputs':{'x':typ},'behavior':{'kind':'uil','program':program}}
    with project_at(tmp_path) as p:
        ident = register_contract(p,contract)['id']
        layer = register_layer(p,{'format':'fdisbull-udl-layer-1','name':'increment',
            'contract':ident,'implementation':{'backend':'uil','program':program}})
        choice = select_layers(p,'increment',{'block':layer['id']},program=module_for(contract,ident),target='wasm32-scalar-1')
        build_web_block(p,choice['id'],tmp_path/'web')
    script = f"""
import fs from 'node:fs/promises';
import {{instantiateWasm,runWASM}} from './host.mjs';
const b=JSON.parse(await fs.readFile('build.json'));
const bytes=await fs.readFile('block.wasm');
const i=await instantiateWasm(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),b);
console.log(JSON.stringify(runWASM(i,b.abi,[[{start}]])));
"""
    (tmp_path/'web/run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'),'run.mjs'],cwd=tmp_path/'web',text=True,capture_output=True,check=True)
    assert json.loads(run.stdout) == [{'status':0,'data':[expected]}]


def test_profile_refuses_wider_values_resources_and_high_bit_tests():
    from fdisbull.udc_web import Lowerer
    from examples.recovery.civd_food_web import authored_suites
    branch = authored_suites()[-1][1]
    for change in (
        lambda c:c['behavior']['program']['body'][0]['condition']['conditions'][0].update(bit=63),
        lambda c:c['behavior']['program']['resources'].update(sound={'kind':'sound','uri':'cue'}),
        lambda c:c['behavior']['program']['variables']['$flags'].update(type='i64')):
        bad = copy.deepcopy(branch);change(bad)
        if bad['behavior']['program']['variables']['$flags']['type']=='i64': bad['inputs']['flags']='i64'
        with pytest.raises(ValueError): Lowerer(bad)


def test_variable_dictionary_order_does_not_change_code():
    from fdisbull.udc_web import Lowerer
    contract = maintenance_contract()
    reversed_ = copy.deepcopy(contract)
    reversed_['behavior']['program']['variables'] = dict(reversed(list(reversed_['behavior']['program']['variables'].items())))
    a,b = Lowerer(contract),Lowerer(reversed_)
    assert (a.wasm(),a.wat(),a.wgsl()) == (b.wasm(),b.wat(),b.wgsl())


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'),reason='real GPU acceptance needs explicit local webgpu npm dependencies')
def test_real_gpu_matches_independent_answers_and_recovers_from_compile_failure(tmp_path):
    from fdisbull.udc_web import build_web_block
    with project_at(tmp_path) as p:
        choice,_ = selected(p,'webgpu-wgsl-scalar-1')
        build_web_block(p,choice,tmp_path/'web')
    script = """
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {runGPU} from './host.mjs';
const require=createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT,'package.json'));
const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));
Object.assign(globalThis,globals);
let gpu=create(['backend='+ (process.env.FDISBULL_GPU_BACKEND || 'metal')]);
const adapter=await gpu.requestAdapter();assert.equal(adapter.info.isFallbackAdapter,false);
const device=await adapter.requestDevice();
try {
 const b=JSON.parse(await fs.readFile('build.json'));
 const code=await fs.readFile('block.wgsl','utf8');
 const cases=[
  {stock:10,produced:9,population:3,supported:2,support_cost:1},
  {stock:32767,produced:32767,population:-128,supported:-32768,support_cost:2},
  {stock:10,produced:9,population:128,supported:2,support_cost:1}];
 const rows=cases.map(c=>b.abi.inputs.map(n=>c[n]));
 const broken=structuredClone(b),bad='invalid WGSL';
 broken.artifacts['block.wgsl']=crypto.createHash('sha256').update(bad).digest('hex');
 await assert.rejects(()=>runGPU(device,bad,broken,rows));
 const pending=runGPU(device,code,b,rows);rows[0].fill(0);
 const results=await pending;
 assert.deepEqual(results,[{status:0,data:[11]},{status:0,data:[254]},{status:1,data:[]}]);
 console.log('passed');
} finally {device.destroy();gpu=null;}
"""
    (tmp_path/'web/run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'),'run.mjs'],cwd=tmp_path/'web',text=True,capture_output=True,timeout=60,check=True)
    assert run.stdout.strip() == 'passed'
