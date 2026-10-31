"""Build a browser shell with unchanged module UIL and explicit host ownership."""
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import tempfile

from .udc_layers import digest
from .udc_web import BOUNDS, Lowerer, build_web_block

FORMAT='fdisbull-browser-shell-1'
PLAN='fdisbull-web-orchestration-1'


def validate_plan(document,contract):
    if type(document) is not dict or not {'format','state','inputs','outputs'}<=document.keys() or set(document)-{'format','state','inputs','outputs','concurrency','title'}:
        raise ValueError('invalid browser orchestration fields')
    plan=deepcopy(document)
    plan.setdefault('concurrency','latest-request-wins')
    if plan['format']!=PLAN or plan['concurrency']!='latest-request-wins':
        raise ValueError('unsupported browser orchestration profile')
    if 'title' in plan and (not isinstance(plan['title'],str) or len(plan['title'])>256):
        raise ValueError('invalid browser title')
    state=plan['state']
    if type(state) is not dict or not 1<=len(state)<=256:raise ValueError('invalid typed state arena')
    offset=0;cells={}
    for name,d in sorted(state.items()):
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,95}',name):raise ValueError('invalid state cell name')
        if type(d) is not dict or not {'type','initial'}<=d.keys() or set(d)-{'type','initial','label'} or d['type'] not in BOUNDS:
            raise ValueError('unsupported state cell')
        typ=d['type'];initial=d['initial'];low,high=BOUNDS[typ]
        if typ=='bool':valid=type(initial) is bool
        else:valid=type(initial) is int and low<=initial<=high
        if not valid:raise ValueError('invalid typed state initial value')
        if 'label' in d and (not isinstance(d['label'],str) or len(d['label'])>128):raise ValueError('invalid state label')
        size=1 if typ in ('bool','i8','u8') else 2
        offset+=offset%size;cells[name]={'offset':offset,'size':size,'type':typ};offset+=size
    for side in ('inputs','outputs'):
        mapping=plan[side]
        if type(mapping) is not dict or set(mapping)!=set(contract[side]):raise ValueError('incomplete shell port adapter')
        for port,name in mapping.items():
            if not isinstance(name,str) or name not in state or state[name]['type']!=contract[side][port]:raise ValueError('shell state/port type mismatch')
    if len(set(plan['outputs'].values()))!=len(plan['outputs']):raise ValueError('aliased shell output commits')
    return plan,{'cells':cells,'stride':offset+offset%2}


def admission(lower):
    result={}
    for name,typ in lower.contract['inputs'].items():
        low,high=BOUNDS[typ]
        for domain in (lower.contract.get('domain',{}),lower.domain):
            if name in domain:low=max(low,domain[name]['min']);high=min(high,domain[name]['max'])
        if low>high:raise ValueError('empty admission domain')
        result[name]={'min':low,'max':high}
    return result


def build_web_shell(project,selections,plan,destination):
    """Build only: two equivalent providers, one module, one typed host plan."""
    destination=Path(destination).expanduser().absolute()
    if os.path.lexists(destination):raise ValueError('browser shell needs new output outside Git')
    destination=destination.resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('browser shell needs new output outside Git')
    if type(selections) is not dict or set(selections)!={'wasm','webgpu'}:raise ValueError('select both Wasm and WebGPU providers')
    lowers={name:Lowerer.from_selection(project,ident) for name,ident in selections.items()}
    for name,target in [('wasm','wasm32-scalar-1'),('webgpu','webgpu-wgsl-scalar-1')]:
        if lowers[name].capsule['target']!=target:raise ValueError('wrong selected browser provider target')
    wasm,gpu=lowers['wasm'],lowers['webgpu']
    for key in ('module_uil_sha256','contract_sha256'):
        if wasm.capsule[key]!=gpu.capsule[key]:raise ValueError('browser providers need identical UIL and contract')
    if admission(wasm)!=admission(gpu):raise ValueError('browser providers have different admission domains')
    contract=wasm.contract
    normalized,layout=validate_plan(plan,contract)
    program=project.udl_selection_info(selections['wasm'],full=True)['document']['program']
    artifacts={name:files('fdisbull').joinpath('web_runtime/'+name).read_bytes()
               for name in ('index.html','app.mjs','shell.mjs','block.mjs')}
    variants={}
    with tempfile.TemporaryDirectory(prefix='fdisbull-web-shell-') as temporary:
        for name,ident in selections.items():
            root=Path(temporary)/name;built=build_web_block(project,ident,root)
            directory='blocks/'+name
            variants[name]={'directory':directory,'build':built,'layer_domain':lowers[name].domain,
                            'effective_domain':admission(lowers[name])}
            for path in root.iterdir():artifacts[directory+'/'+path.name]=path.read_bytes()
    sha=lambda b:hashlib.sha256(b).hexdigest()
    manifest={'format':FORMAT,'module_uil_sha256':digest(program),'program':program,
        'contract':contract,'contract_sha256':digest(contract),'binding':program['body'][0]['binding'],
        'interface':{'inputs':contract['inputs'],'outputs':contract['outputs'],'domain':admission(wasm)},
        'plan':normalized,'plan_sha256':digest(normalized),'layout':layout,'variants':variants,
        'artifacts':{name:sha(data) for name,data in artifacts.items()},'execution':False,'source_to_uil':False,
        'scope':'one canonical pure invocation; typed owned records; snapshot/compute/guarded output commit'}
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    for name,data in artifacts.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    (destination/'shell.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return manifest
