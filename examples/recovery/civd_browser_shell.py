"""Prepare/verify a private browser shell against independently observed originals.

prepare FRESH_ORACLE_ROOT NEW_OUTPUT
verify FRESH_ORACLE_ROOT OUTPUT

Between phases, run run_browser_shell.mjs with OUTPUT, private npm dependencies
and Chrome. Fresh original preparation and chain preparation are separate inputs;
this script never recomputes their expected values from an authored food formula.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull.udc_web_shell import build_web_shell

UIL='332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed'
sha=lambda data:hashlib.sha256(data).hexdigest()


def plan():
    cells={'stock':('i16',10,'Food stored'),'produced':('i16',9,'Food produced'),
           'population':('i8',3,'Population'),'supported':('i16',2,'Supported units'),
           'support_cost':('i16',1,'Support cost'),'sentinel':('u16',23130,'Preserved control')}
    return {'format':'fdisbull-web-orchestration-1','title':'Food production',
        'state':{k:{'type':t,'initial':v,'label':label} for k,(t,v,label) in cells.items()},
        'inputs':{k:k for k in cells if k!='sentinel'},'outputs':{'new_stock':'stock'},
        'concurrency':'latest-request-wins'}


def prepare(root,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a new private shell output outside Git')
    cases=json.loads((root/'originals/cases.json').read_text())
    chain=json.loads((root/'chain-originals/chain-vectors.json').read_text())
    assert cases['module_uil_sha256']==chain['module_uil_sha256']==UIL and cases['vectors']==2018
    food=next(s for s in cases['suites'] if s['name']=='food')
    abi=food['builds']['wasm32-scalar-1']['build']['abi']
    selections={'wasm':food['builds']['wasm32-scalar-1']['selection'],
                'webgpu':food['builds']['webgpu-wgsl-scalar-1']['selection']}
    # Read the qualified project through a new private copy, keeping the oracle
    # projects and every earlier receipt unchanged.
    database=output.with_name(output.name+'-selection.fdb')
    if database.exists():raise ValueError('private selection destination exists')
    with sqlite3.connect((root/'originals/474.05.fdb').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(database) as dst:
        src.backup(dst)
    with Project(database) as project:manifest=build_web_shell(project,selections,plan(),output)
    assert manifest['module_uil_sha256']==UIL
    rows=food['vectors'];normal=[];invalid=[]
    for index,row in enumerate(rows):
        inputs=dict(zip(abi['inputs'],row['input']))
        if index<cases['vectors']:
            assert row['expected']['status']==0
            normal.append({'inputs':inputs,'expected':{'new_stock':row['expected']['data'][0]}})
        else:
            typed=not (-128<=inputs['population']<=127 and -32768<=inputs['stock']<=32767)
            invalid.append({'inputs':inputs,'expected':'state-type-refused' if typed else 'refused'})
    study={'format':'fdisbull-browser-shell-study-1','module_uil_sha256':UIL,
           'normal':normal,'invalid':invalid,'chain':chain}
    (output/'study.json').write_text(json.dumps(study,indent=2)+'\n')
    return {'status':'prepared','module_uil_sha256':UIL,'normal':len(normal),'invalid':len(invalid),'chain_steps':chain['steps']}


def verify(root,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    manifest=json.loads((output/'shell.json').read_text());study=json.loads((output/'study.json').read_text())
    assert manifest['module_uil_sha256']==study['module_uil_sha256']==UIL
    assert digest(manifest['program'])==UIL and digest(manifest['plan'])==manifest['plan_sha256']
    for name,value in manifest['artifacts'].items():assert sha((output/name).read_bytes())==value
    normal=[r['expected']['new_stock'] for r in study['normal']]
    chain=[r['expected']['new_stock'] for r in study['chain']['vectors']]
    # Independently bind normalized expectations to fresh raw DOS observations.
    import struct
    for index in range(3):
        assert list(struct.unpack('<'+'h'*len(normal),(root/f'originals/oracle/F{index}.OUT').read_bytes()))==normal
        assert list(struct.unpack('<'+'h'*len(chain),(root/f'chain-originals/oracle/F{index}.OUT').read_bytes()))==chain
    hosts={}
    for host in ('node','browser'):
        result=json.loads((output/(host+'-shell-result.json')).read_text())
        assert result['status']=='passed' and result['module_uil_sha256']==UIL
        assert result['adapter']['isFallbackAdapter'] is False
        for backend in ('wasm','webgpu'):
            assert result['normal'][backend]['outputs']==normal
            assert result['normal'][backend]['cases']==len(normal)
        assert result['chain']['outputs']==chain and result['chain']['steps']==len(chain)
        assert result['checks'] and all(c['status']=='passed' for c in result['checks'])
        if host=='browser':
            assert len(result['uiChecks'])>=6 and all(c['status']=='passed' for c in result['uiChecks'])
        sanitized={k:v for k,v in result.items() if k not in ('normal','chain')}
        sanitized['normal']={b:{'cases':len(normal),'mismatches':0,'outputs_sha256':digest(normal)} for b in ('wasm','webgpu')}
        sanitized['chain']={'steps':len(chain),'mismatches':0,'outputs_sha256':digest(chain),'alternating_backends':True}
        hosts[host]=sanitized
    cases=json.loads((root/'originals/cases.json').read_text())
    for tag,expected in cases['originals'].items():
        assert sha((Path(cases['build_root'])/tag.replace('.','')/'CIV.EXE').read_bytes())==expected
    for name,key in [('MASM','masm_sha256'),('LINK','linker_sha256')]:
        assert sha((Path(cases['tools'])/f'BIN/{name}.EXE').read_bytes())==cases['oracle'][key]
    # Do not export private source directories/commands or retained target bytes.
    result={'format':'fdisbull-browser-shell-verification-1','status':'passed','module_uil_sha256':UIL,
        'module_program':manifest['program'],'plan':manifest['plan'],'plan_sha256':manifest['plan_sha256'],
        'layout':manifest['layout'],'interface':manifest['interface'],'artifacts':manifest['artifacts'],
        'normal_cases_per_backend_per_host':len(normal),'chain_steps_per_host':len(chain),
        'original_native':cases['original_native'],'original_cpu_invocations':len(normal)*3,
        'original_dosbox_invocations':len(normal)*3,'chain_cpu_derivation_invocations':len(chain),
        'chain_cpu_validation_invocations':len(chain)*3,'chain_dosbox_invocations':len(chain)*3,
        'host_results':hosts,'original_kernel_source':'fresh original CPU and DOSBox inputs; separate original-derived carried-state chain',
        'original_baseline_sha256':sha((root/'ORACLE_SUMMARY.json').read_bytes()),
        'original_chain_summary_sha256':sha((root/'chain-originals/SUMMARY.json').read_bytes()),
        'originals_unchanged':True,'scope':'finite original-backed kernels and owned browser state transitions; no full-game or timing qualification'}
    # Raw originals summaries stay private; exact hashes above bind them.
    encoded=json.dumps(result,indent=2)
    assert not any(s in encoded for s in ('/Users/','/Volumes/','code_hex','data_base64'))
    (output/'shell-verification.json').write_text(encoded+'\n')
    return result


if __name__=='__main__':
    import sys
    if not __debug__:raise RuntimeError('qualification requires assertions enabled')
    if len(sys.argv)!=4 or sys.argv[1] not in ('prepare','verify'):raise SystemExit(__doc__)
    print(json.dumps(globals()[sys.argv[1]](*sys.argv[2:]),indent=2))
