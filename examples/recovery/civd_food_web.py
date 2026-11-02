"""Reproduce the private food comparison with fresh original CPU/DOS execution.

prepare PREVIOUS BUILD_ROOT NEW_OUTPUT TOOLS DOSBOX
verify OUTPUT

Between the phases, run run_web_blocks.mjs with OUTPUT and a locally installed
webgpu module. No game bytes, project DB, oracle harness or emitted target is a
publication input. The verifier returns a sanitized aggregate receipt.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Qualification must run with Python assertions enabled')

import copy
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import struct

from fdisbull.project import Project
from fdisbull.interaction_il import execute_il
from fdisbull.stock_flow import PORTS, native16_adapter, decode_state, commit_state
from fdisbull.udc_layers import digest, register_contract, register_layer, select_layers, _native_code
from fdisbull.udc_native16 import execute_native16
from fdisbull.udc_web import BOUNDS, Lowerer, TARGETS, build_web_block
from examples.recovery.civd_food_swap import host_state, frame_values, dos_oracle

UIL = '332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed'
TAGS = ('474.01','474.03','474.05')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def copy_project(source,destination):
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def model(contract,row):
    for name,typ in contract['inputs'].items():
        low,high = BOUNDS[typ]
        if not low <= row[name] <= high: return {'status':1,'data':[]}
        domain = contract.get('domain',{}).get(name)
        if domain and not domain['min'] <= row[name] <= domain['max']: return {'status':1,'data':[]}
    program = contract['behavior']['program']
    state = {k:v['initial'] for k,v in program['variables'].items()}
    state.update({'$'+k:bool(v) if contract['inputs'][k]=='bool' else v for k,v in row.items()})
    result = execute_il(program,state=state)
    return ({'status':0,'data':[int(result['state']['$'+k]) for k in sorted(contract['outputs'])]}
            if result['status']=='complete' else {'status':1,'data':[]})


def authored_suites():
    def contract(name,inputs,outputs,variables,body):
        return {'format':'fdisbull-block-contract-1','name':name,'inputs':inputs,'outputs':outputs,
            'behavior':{'kind':'uil','program':{'format':'fdisbull-il-1','role':'uil',
                'variables':{'$'+k:{'type':t,'initial':False if t=='bool' else 0} for k,t in variables.items()},
                'resources':{},'body':body}}}
    atomic = contract('atomic.require',{'x':'i16','delta':'i16','allow':'bool'},{'x':'i16'},
        {'x':'i16','delta':'i16','allow':'bool'},[
            {'id':'update','op':'add','var':'$x','value':{'var':'$delta'}},
            {'id':'guard','op':'require','condition':{'op':'eq','left':{'var':'$allow'},'right':True}}])
    narrow = contract('narrow.set',{'value':'i16'},{'small':'i8'},{'value':'i16','small':'i8'},[
        {'id':'narrow','op':'set','var':'$small','value':{'var':'$value'}}])
    condition = {'op':'and','conditions':[{'op':'bit_test','value':{'var':'$flags'},'bit':31},
        {'op':'not','condition':{'op':'eq','left':{'var':'$x'},'right':0}}]}
    branch = contract('branch.bits',{'flags':'i16','x':'u16'},{'x':'u16'},{'flags':'i16','x':'u16'},[
        {'id':'branch','op':'if','condition':condition,
         'then':[{'id':'plus','op':'add','var':'$x','value':1}],
         'else':[{'id':'minus','op':'subtract','var':'$x','value':1}]}])
    return [
        ('atomic',atomic,[dict(x=x,delta=d,allow=a) for x,d,a in itertools.product(
            (-32768,5,32767),(-1,3,32767),(0,1))]+[dict(x=5,delta=3,allow=2)]),
        ('narrow',narrow,[{'value':n} for n in (-32768,-129,-128,-1,0,1,127,128,32767)]),
        ('branch',branch,[dict(flags=f,x=x) for f,x in itertools.product((-32768,-1,0,1,32767),(0,1,65535))])]


def module_for(contract,ident):
    ports = {**contract['inputs'],**contract['outputs']}
    return {'format':'fdisbull-module-uil-1','role':'uil','resources':{},
        'variables':{'$'+k:{'type':t,'initial':False if t=='bool' else 0} for k,t in ports.items()},
        'body':[{'id':'invoke','op':'invoke','binding':'block','contract':ident,
                 'inputs':{k:{'var':'$'+k} for k in contract['inputs']},
                 'outputs':{k:'$'+k for k in contract['outputs']}}]}


def prepare(previous,builds,output,tools,dosbox):
    previous,builds,output,tools,dosbox = [Path(p).resolve() for p in (previous,builds,output,tools,dosbox)]
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('Choose a new private output outside Git')
    old = json.loads((previous/'report.json').read_text())
    vectors = json.loads((previous/'vectors.json').read_text())
    assert digest(vectors)==old['vectors_sha256'] and digest(old['module_uil'])==UIL
    originals = {tag:builds/tag.replace('.','')/'CIV.EXE' for tag in TAGS}
    assert all(sha(p.read_bytes())==old['originals'][tag] for tag,p in originals.items())
    for name,key in [('MASM','masm_sha256'),('LINK','linker_sha256')]:
        assert sha((tools/f'BIN/{name}.EXE').read_bytes())==old['oracle'][key]
    output.mkdir(mode=0o700)
    sources = {}; native_rows = []
    for tag in TAGS:
        project_path = output/(tag+'.fdb')
        copy_project(previous/(tag+'-swap.fdb'),project_path)
        row = next(r for r in old['matrix'] if r['host']==r['backing']==tag)
        with Project(project_path) as project:
            choice = next(r for r in old['restart'] if r['host']==tag)['selection']
            doc = project.udl_selection_info(choice,full=True)['document']
            layer = project.udl_layer_info(doc['bindings']['food'],full=True)['document']
            code = _native_code(project,layer)
            assert sha(code)==row['source_code_sha256']
            observed = []
            for i,vector in enumerate(vectors):
                record,frame = frame_values(i)
                adapter = native16_adapter(row['adapter'],record=record,frame=frame)
                value = execute_native16(code,layer['implementation'],adapter,vector,PORTS,{'new_stock':'i16'})['outputs']['new_stock']
                assert model(old['contract'],vector)=={'status':0,'data':[value]}
                observed.append(value)
        native_rows.append({'edition':tag,'cases':len(vectors),'outputs_sha256':digest(observed),
                            'code_sha256':sha(code),'original_sha256':old['originals'][tag]})
        sources[tag] = {'code':code,'layout':row['adapter'],'observed':observed}
    oracle_dir = output/'oracle'; oracle_dir.mkdir()
    dos,oracle = dos_oracle(oracle_dir,sources,vectors,tools,dosbox)
    for index,tag in enumerate(TAGS):
        assert dos[tag]==sources[tag]['observed']
        retained = (previous/f'F{index}.OUT').read_bytes()
        row = next(r for r in old['matrix'] if r['host']==r['backing']==tag)
        assert sha(retained)==row['results_sha256']
        assert (oracle_dir/f'F{index}.OUT').read_bytes()==retained
        native_rows[index]['dosbox_outputs_sha256'] = sha(retained)
    invalid = [{**vectors[0],k:n} for k,values in (
        ('support_cost',(0,3)),('population',(-129,128)),('stock',(-32769,32768))) for n in values]
    inputs = [('food',old['contract'],vectors+invalid),*authored_suites()]
    suites = []
    with Project(output/'474.05.fdb') as project:
        for name,contract,rows in inputs:
            ident = register_contract(project,contract)['id']
            module = old['module_uil'] if name=='food' else module_for(contract,ident)
            layer = register_layer(project,{'format':'fdisbull-udl-layer-1','name':name+'.portable',
                'contract':ident,'implementation':{'backend':'uil','program':contract['behavior']['program']}})
            builds_for = {}
            for target in TARGETS:
                binding = module['body'][0]['binding']
                selected = select_layers(project,name+'.'+target,{binding:layer['id']},program=module,target=target)
                relative = name+'/'+target
                built = build_web_block(project,selected['id'],output/relative)
                builds_for[target] = {'directory':relative,'build':built,'selection':selected['id']}
            suite = {'name':name,'builds':builds_for,'vectors':[
                {'input':[int(row[k]) for k in sorted(contract['inputs'])],'expected':model(contract,row)} for row in rows]}
            if name=='food': assert [v['expected']['data'][0] for v in suite['vectors'][:len(vectors)]]==dos[TAGS[0]]
            suites.append(suite)
    with Project(output/'474.05.fdb') as project:
        for suite in suites:
            for entry in suite['builds'].values():
                doc = project.udl_selection_info(entry['selection'],full=True)['document']
                assert digest(doc['program'])==entry['build']['module_uil_sha256']
    # Deliberately corrupt the lowering while retaining the same module UIL.
    # This bypasses the public builder's model gate solely as a negative control.
    food = suites[0]; mutant = copy.deepcopy(food); mutant.update(name='food-mutant',negative_control=True)
    lower = Lowerer(old['contract'])
    node = next(n for n in lower.program['body'] if n['id']=='resident-consumption')
    node['op'] = 'subtract'
    for target,item in mutant['builds'].items():
        origin = output/item['directory']; dest = output/'food-mutant'/target
        import shutil
        shutil.copytree(origin,dest)
        if target==TARGETS[0]:
            (dest/'block.wasm').write_bytes(lower.wasm()); (dest/'block.wat').write_text(lower.wat())
        else: (dest/'block.wgsl').write_text(lower.wgsl())
        build = item['build']
        build['artifacts'] = {n:sha((dest/n).read_bytes()) for n in build['artifacts']}
        (dest/'build.json').write_text(json.dumps(build,indent=2)+'\n')
        item['directory'] = str(dest.relative_to(output))
    suites.append(mutant)
    manifest = {'format':'fdisbull-web-food-study-2','module_uil_sha256':UIL,'vectors_sha256':digest(vectors),
        'originals':old['originals'],'original_native':native_rows,'oracle':oracle,'suites':suites,
        'previous':str(previous),'build_root':str(builds),'tools':str(tools),'vectors':len(vectors),
        'negative_control':'explicitly corrupted lowering; not an accepted selected build'}
    (output/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert all(sha(p.read_bytes())==old['originals'][tag] for tag,p in originals.items())
    return {'prepared':True,'original_cpu_invocations':len(vectors)*3,'fresh_dosbox_invocations':len(vectors)*3,
            'normal_cases_per_backend':sum(len(s['vectors']) for s in suites if not s.get('negative_control'))}


def verify(output):
    output = Path(output).resolve()
    manifest = json.loads((output/'cases.json').read_text())
    observations = json.loads((output/'node-observations.json').read_text())
    executed = json.loads((output/'node-result.json').read_text())
    assert executed['status']=='passed' and executed['module_uil_sha256']==UIL
    old = json.loads((Path(manifest['previous'])/'report.json').read_text())
    vectors = json.loads((Path(manifest['previous'])/'vectors.json').read_text())
    assert digest(vectors)==manifest['vectors_sha256'] and digest(old['module_uil'])==UIL
    roundtrips = 0
    for suite in manifest['suites']:
        observed = observations[suite['name']]
        for target,entry in suite['builds'].items():
            root = output/entry['directory']
            built = json.loads((root/'build.json').read_text())
            assert built==entry['build']
            assert all(sha((root/n).read_bytes())==value for n,value in built['artifacts'].items())
            actual = observed[target]
            assert len(actual)==len(suite['vectors'])
            mismatches = sum(a!=v['expected'] for a,v in zip(actual,suite['vectors']))
            if suite.get('negative_control'): assert mismatches>0
            else: assert mismatches==0
            if suite['name']=='food':
                assert built['module_uil_sha256']==UIL
                for tag in TAGS:
                    binding = next(r for r in old['matrix'] if r['host']==r['backing']==tag)['adapter']
                    for i,vector in enumerate(vectors):
                        data,stack,record,frame = host_state(binding,vector,i)
                        assert decode_state(binding,data,stack,record=record,frame=frame)==vector
                        value = actual[i]['data'][0]
                        updated = commit_state(binding,data,value,record=record)
                        offset = native16_adapter(binding,record=record)['outputs']['new_stock']['offset']
                        assert int.from_bytes(updated[offset:offset+2],'little',signed=True)==value
                        assert updated[:offset]==data[:offset] and updated[offset+2:]==data[offset+2:]
                        roundtrips += 1
    assert all(sha((Path(manifest['build_root'])/tag.replace('.','')/'CIV.EXE').read_bytes())==value
               for tag,value in manifest['originals'].items())
    for name,key in [('MASM','masm_sha256'),('LINK','linker_sha256')]:
        assert sha((Path(manifest['tools'])/f'BIN/{name}.EXE').read_bytes())==manifest['oracle'][key]
    # Only aggregate, hash-bound observations cross the publication boundary.
    result = {'format':'fdisbull-web-food-verification-2','status':'passed','module_uil_sha256':UIL,
        'vectors_sha256':manifest['vectors_sha256'],'original_native':manifest['original_native'],
        'fresh_original_cpu_invocations':manifest['vectors']*3,'fresh_dosbox_invocations':manifest['vectors']*3,
        'host_adapter_roundtrips':roundtrips,'originals_unchanged':True,'toolchain_pins_unchanged':True,
        'execution':executed,'scope':'finite isolated food kernels; host layout checks in Python; no whole-game or timing parity',
        'builds':{s['name']:{t:e['build'] for t,e in s['builds'].items()} for s in manifest['suites'] if not s.get('negative_control')}}
    browser = output/'browser-result.json'
    if browser.exists():
        browser_result = json.loads(browser.read_text())
        assert browser_result['status']=='passed' and browser_result['module_uil_sha256']==UIL
        assert json.loads((output/'browser-observations.json').read_text())==observations
        result['browser_execution'] = browser_result
        result['browser_node_observation_equality'] = True
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    import sys
    if sys.argv[1:2]==['prepare'] and len(sys.argv)==7: result = prepare(*sys.argv[2:])
    elif sys.argv[1:2]==['verify'] and len(sys.argv)==3: result = verify(sys.argv[2])
    else: raise SystemExit(__doc__)
    print(json.dumps(result,indent=2))
