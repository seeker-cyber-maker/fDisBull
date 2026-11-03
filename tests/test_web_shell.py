"""Browser shell owns typed state while the selected food module stays fixed."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.project import Project
from fdisbull.stock_flow import maintenance_contract, maintenance_module
from fdisbull.udc_layers import register_contract, register_layer, select_layers, digest


def plan():
    types = {'stock':'i16','produced':'i16','population':'i8','supported':'i16','support_cost':'i16','sentinel':'u16'}
    values = dict(stock=10,produced=9,population=3,supported=2,support_cost=1,sentinel=23130)
    return {'format':'fdisbull-web-orchestration-1','title':'Food production',
        'state':{k:{'type':t,'initial':values[k]} for k,t in types.items()},
        'inputs':{k:k for k in maintenance_contract()['inputs']},'outputs':{'new_stock':'stock'},
        'concurrency':'latest-request-wins'}


def fixture(tmp_path,domains=None):
    binary=tmp_path/'authored.com';binary.write_bytes(bytes.fromhex('b8004ccd21'))
    project=Project.create(tmp_path/'shell.fdb',binary,image='com')
    shared=json.loads((Path(__file__).resolve().parents[1]/'docs/evidence/civd-food-swaps/shared-uil.json').read_text())
    contract=shared['contract'];stored=register_contract(project,contract);module=shared['module_uil']
    assert stored['id']==shared['contract_id']
    selections={}
    for kind,target in [('wasm','wasm32-scalar-1'),('webgpu','webgpu-wgsl-scalar-1')]:
        layer={'format':'fdisbull-udl-layer-1','name':kind,'contract':stored['id'],
               'implementation':{'backend':'uil','program':contract['behavior']['program']}}
        if domains and kind in domains:layer['domain']=domains[kind]
        retained=register_layer(project,layer)
        selections[kind]=select_layers(project,kind,{'food':retained['id']},program=module,target=target)['id']
    return project,selections,module


def test_shell_build_preserves_module_and_separates_orchestration(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    from fdisbull.udc_api import METHODS
    assert 'build-web-shell' in METHODS
    project,selections,module=fixture(tmp_path)
    with project:
        receipt=build_web_shell(project,selections,plan(),tmp_path/'browser')
    manifest=json.loads((tmp_path/'browser/shell.json').read_text())
    assert manifest['program']==module and manifest['module_uil_sha256']==digest(module)
    assert manifest['plan']['outputs']=={'new_stock':'stock'}
    assert manifest['execution'] is False and manifest['source_to_uil'] is False
    assert receipt==manifest
    for name in ('index.html','app.mjs','shell.mjs','block.mjs'):
        assert (tmp_path/'browser'/name).is_file()
    assert manifest['variants']['wasm']['build']['module_uil_sha256']==manifest['variants']['webgpu']['build']['module_uil_sha256']


def test_different_admission_domains_are_not_interchangeable(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    project,selections,_=fixture(tmp_path,domains={'webgpu':{'support_cost':{'min':2,'max':2}}})
    with project,pytest.raises(ValueError,match='admission'):
        build_web_shell(project,selections,plan(),tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_invalid_plan_and_existing_output_refuse_without_emission(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    project,selections,_=fixture(tmp_path)
    with project:
        for mutate in [lambda p:p['inputs'].update(population='stock'),
                       lambda p:p['state']['stock'].update(initial=32768),
                       lambda p:p.update(concurrency='unqualified'),
                       lambda p:p.update(extra='ignored')]:
            bad=copy.deepcopy(plan());mutate(bad)
            with pytest.raises(ValueError):build_web_shell(project,selections,bad,tmp_path/'bad')
            assert not (tmp_path/'bad').exists()
        (tmp_path/'keep').mkdir();(tmp_path/'keep/user.txt').write_text('keep')
        with pytest.raises(ValueError):build_web_shell(project,selections,plan(),tmp_path/'keep')
        assert (tmp_path/'keep/user.txt').read_text()=='keep'


@pytest.mark.skipif(not shutil.which('node'),reason='actual Wasm orchestration needs Node')
def test_wasm_memory_and_async_orchestration(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    project,selections,_=fixture(tmp_path)
    with project:build_web_shell(project,selections,plan(),tmp_path/'browser')
    script=Path(__file__).with_name('web_shell_checks.mjs')
    run=subprocess.run([shutil.which('node'),str(script),str(tmp_path/'browser')],capture_output=True,text=True,timeout=60,check=True)
    result=json.loads(run.stdout)
    assert result['status']=='passed' and result['wasm_cases']>=12


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'),reason='real GPU shell acceptance needs explicit local npm dependencies')
def test_real_gpu_shell_memory_async_and_loss(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    project,selections,_=fixture(tmp_path)
    with project:build_web_shell(project,selections,plan(),tmp_path/'browser')
    script=Path(__file__).with_name('web_shell_checks.mjs')
    run=subprocess.run([shutil.which('node'),str(script),str(tmp_path/'browser'),os.environ['FDISBULL_WEBGPU_MODULE_ROOT']],capture_output=True,text=True,timeout=90,check=True)
    result=json.loads(run.stdout)
    assert result['status']=='passed' and result['gpu_cases']>=12


@pytest.mark.skipif(not shutil.which('node'),reason='actual malformed-output execution needs Node')
def test_corrupted_lowering_cannot_write_an_out_of_type_output(tmp_path):
    from fdisbull.udc_web_shell import build_web_shell
    from fdisbull.udc_web import Lowerer
    project,selections,_=fixture(tmp_path)
    with project:manifest=build_web_shell(project,selections,plan(),tmp_path/'browser')
    # Deliberate compiler fault: preserve the asserted module identity but emit
    # a real Wasm function returning 40000 for the signed-word output. The public
    # builder never accepts this mismatched implementation; this tests the final
    # commit boundary independently of compiler/model agreement.
    contract=manifest['contract'];wrong=copy.deepcopy(contract['behavior']['program'])
    wrong['variables']['$new_stock']={'type':'u16','initial':40000};wrong['body']=[]
    binary=Lowerer(contract,wrong).wasm();(tmp_path/'browser/fault.wasm').write_bytes(binary)
    manifest['variants']['wasm']['build']['artifacts']['block.wasm']=hashlib.sha256(binary).hexdigest()
    (tmp_path/'browser/fault.json').write_text(json.dumps(manifest))
    script="""
import fs from 'node:fs/promises';import assert from 'node:assert/strict';
import {createShell,createWasmProvider} from './shell.mjs';
const m=JSON.parse(await fs.readFile('fault.json'));
const p=await createWasmProvider(m.variants.wasm.build,await fs.readFile('fault.wasm'));
const s=await createShell(m,{wasm:p});s.addRecord('a');s.selectEntity('a');
const before=s.snapshot();const r=await s.step();
assert.equal(r.status,'failed');assert.equal(r.reason,'Invalid logical output type');
assert.equal(r.committed,false);assert.deepEqual(s.snapshot(),before);
await s.dispose();console.log('passed');
"""
    (tmp_path/'browser/fault.mjs').write_text(script)
    run=subprocess.run([shutil.which('node'),'fault.mjs'],cwd=tmp_path/'browser',capture_output=True,text=True,timeout=30,check=True)
    assert run.stdout.strip()=='passed'
