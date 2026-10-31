"""Run the first-party local pilot, without GitHub or external recompilers.

Requires installed fdisbull, Z3 for symbolic checks, GCC/Clang and Node for the
selected validation realizations. No dependency download or installation occurs.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import random
import shutil
import subprocess
import time
from importlib import metadata
import fdisbull

ROOT=Path(__file__).resolve().parents[1]
fdisbull.__path__.insert(0,str(ROOT/'src'/'fdisbull'))
from fdisbull.console_synthesis import *
from fdisbull.console_synthesis.targets import admit
from fdisbull.interaction_il import execute_il


def write(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def make(code,ram=((0x10,'operand'),)):
    return recover(NativeBacking('authored-pilot','bank_A',0x8000,bytes.fromhex(code)),Bindings(ram))


def symbolic(document,operation):
    import z3
    variables=document['variables']
    initial={n:(z3.Bool('input_'+n[1:]) if d['type']=='bool' else z3.BitVec('input_'+n[1:],16))
             for n,d in variables.items()}
    constraints=[z3.ULE(initial[n],255 if d['type']=='u8' else 65535)
                 for n,d in variables.items() if d['type']!='bool']
    def value(v,state):
        return state[v['var']] if isinstance(v,dict) else (z3.BoolVal(v) if type(v)is bool else z3.BitVecVal(v,16))
    def cond(c,state):
        op=c['op']
        if op=='eq':return value(c['left'],state)==value(c['right'],state)
        if op=='bit_test':
            return z3.BoolVal(False) if c['bit']>=16 else z3.Extract(c['bit'],c['bit'],value(c['value'],state))==1
        if op=='not':return z3.Not(cond(c['condition'],state))
        return z3.And(*(cond(x,state) for x in c['conditions']))
    def run(body,state):
        state=dict(state);valid=z3.BoolVal(True)
        for b in body:
            if b['op']=='if':
                choice=cond(b['condition'],state)
                yes,ok_y=run(b['then'],state);no,ok_n=run(b['else'],state)
                state={k:z3.If(choice,yes[k],no[k]) for k in state}
                valid=z3.And(valid,z3.If(choice,ok_y,ok_n))
            else:
                n=b['var'];v=value(b['value'],state);typ=variables[n]['type']
                if b['op']=='set':
                    if typ!='bool':valid=z3.And(valid,z3.ULE(v,255 if typ=='u8' else 65535))
                    state[n]=v
                else:
                    expr=state[n]+v if b['op']=='add' else state[n]-v
                    state[n]=expr & z3.BitVecVal(255 if typ=='u8' else 65535,16)
        return state,valid
    final,valid=run(document['body'],initial)
    # Reference formulas use explicit 9/10-bit arithmetic, independently of
    # the recovered document's u16 workspace and sign-condition expansion.
    a=z3.Extract(7,0,initial['$value']);b=z3.Extract(7,0,initial['$operand'])
    carry9=z3.If(initial['$carry'],z3.BitVecVal(1,9),z3.BitVecVal(0,9))
    wide_a=z3.ZeroExt(1,a);wide_b=z3.ZeroExt(1,b)
    total=(wide_a+wide_b+carry9 if operation==0 else
           wide_a-wide_b-(1-carry9) if operation==1 else wide_a-wide_b)
    result=z3.Extract(7,0,total)
    carry10=z3.If(initial['$carry'],z3.BitVecVal(1,10),z3.BitVecVal(0,10))
    signed_total=(z3.SignExt(2,a)+z3.SignExt(2,b)+carry10 if operation==0 else
                  z3.SignExt(2,a)-z3.SignExt(2,b)-(1-carry10))
    expected={
        '$value':initial['$value'] if operation==2 else z3.ZeroExt(8,result),
        '$operand':initial['$operand'],
        '$carry':z3.Extract(8,8,total)==1 if operation==0 else total>=0,
        '$zero':result==0,'$negative':z3.Extract(7,7,result)==1,
        '$overflow':initial['$overflow'] if operation==2 else z3.Or(signed_total < -128,signed_total > 127),
        '$index_x':initial['$index_x'],'$index_y':initial['$index_y'],
    }
    solver=z3.Solver();solver.set(timeout=10000)
    solver.add(*constraints)
    assert solver.check()==z3.sat,'admitted input domain must be nonempty'
    solver.add(z3.Or(z3.Not(valid),*(final[n]!=v for n,v in expected.items())))
    answer=solver.check()
    return {'result':str(answer),'domain':'all u8 operands and Boolean flags; D=0; declared projection',
            'claim':'authored IL against arithmetic specification, not original CPU proof',
            'counterexample':str(solver.model()) if answer==z3.sat else None}


def run(out:Path):
    missing=[name for name in ('gcc','clang','node') if shutil.which(name) is None]
    if missing:
        raise SystemExit('Required validation tools unavailable: '+', '.join(missing))
    try:
        import z3
    except ImportError as exc:
        raise SystemExit('Install an approved z3-solver package in this environment first') from exc
    out.mkdir(parents=True,exist_ok=False)
    blocks={'adc':make('65 10'),'sbc':make('E5 10'),'cmp':make('C5 10'),
            'saved':make('A9 01 48 A9 02 68 85 10'),
            'carry_chain':make('38 A9 FF 69 00 85 10 A9 00 69 00'),
            'branch':make('A5 10 F0 04 A9 07 85 11',((0x10,'operand'),(0x11,'destination')))}
    for name,b in blocks.items():
        d=out/name;d.mkdir()
        write(d/'program.uil.json',b.document())
        write(d/'program.udl.json',b.document('udl'))
        write(d/'bindings.json',{'source':b.backing.__dict__ | {'code':b.backing.code.hex()},
             'bindings':b.bindings.__dict__,'admission':b.admission.__dict__,
             'source_map':json.loads(b.source_map_bytes),
             'note':'authored bytes, not commercial game material; original execution requires a separate CPU provider'})
        (d/'generated.c').write_text(emit_c(b.document()),encoding='utf-8')
        (d/'generated.mjs').write_text(emit_javascript(b.document()),encoding='utf-8')
    report={'scope':'first-party mechanism pilot; no original CPU, game or console device execution',
            'host':platform.platform(),'python':platform.python_version(),
            'fdisbull':metadata.version('fdisbull'),
            'z3_distribution':metadata.version('z3-solver'),
            'z3_runtime':z3.get_full_version(),
            'node':subprocess.run([shutil.which('node'),'--version'],capture_output=True,text=True,check=True).stdout.strip(),
            'native':[],'symbolic':{},'javascript':{},'controls':{},'files':{}}
    compilers=[(Path(shutil.which('gcc')),'-O0'),(Path(shutil.which('gcc')),'-O2'),(Path(shutil.which('clang')),'-O2')]
    # One independent arithmetic checker, called with each generated native function.
    oracle=out/'arithmetic_oracle.so'
    subprocess.run([str(compilers[0][0]),'-std=c11','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror',
                    str(ROOT/'scripts'/'console_synthesis_oracle.c'),'-o',str(oracle)],check=True,capture_output=True)
    lib=ctypes.CDLL(str(oracle))
    check=lib.check_arithmetic
    check.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    check.restype=ctypes.c_uint32
    public=('$value','$operand','$carry','$zero','$negative','$overflow','$index_x','$index_y')
    for number,(compiler,opt) in enumerate(compilers):
        total_cases=0;details=[]
        for op,name in enumerate(('adc','sbc','cmp')):
            native=compile_c(blocks[name].document(),out/f'build_{number}_{name}',compiler,opt)
            indices=(ctypes.c_uint32*8)(*(native.names.index(n) for n in public))
            failure=(ctypes.c_uint32*6)(*([0]*6))
            start=time.perf_counter()
            count=check(ctypes.cast(native.function,ctypes.c_void_p),op,indices,len(native.names),failure)
            elapsed=time.perf_counter()-start
            assert count==131072,(name,count,list(failure))
            total_cases+=count
            details.append({'operation':name,'cases':count,'seconds':elapsed,'compiler':native.compiler_version,
                            'artifact_sha256':hashlib.sha256(native.path.read_bytes()).hexdigest()})
        report['native'].append({'compiler':str(compiler),'optimization':opt,'cases':total_cases,'details':details})
    for op,name in enumerate(('adc','sbc','cmp')):
        report['symbolic'][name]=symbolic(blocks[name].document(),op)
        assert report['symbolic'][name]['result']=='unsat',report['symbolic'][name]
    # Same generated IL used by real evaluator and standalone JavaScript.
    rng=random.Random(20261031)
    for name,b in blocks.items():
        cases=[];expected=[]
        for i in range(128):
            state=b.state()
            for var,decl in b.document()['variables'].items():
                if not var.startswith('$tmp_'):
                    state[var]=bool(rng.getrandbits(1)) if decl['type']=='bool' else rng.randrange(256)
            evaluated=execute_il(b.document(),state)
            assert evaluated['status']=='complete',evaluated
            cases.append(state);expected.append(evaluated['state'])
        d=out/name;write(d/'input_cases.json',cases)
        runner=d/'batch.mjs'
        runner.write_text("import {readFileSync} from 'node:fs';\nimport {run} from './generated.mjs';\n"
                          "const inputs=JSON.parse(readFileSync(new URL('./input_cases.json',import.meta.url),'utf8'));\n"
                          "console.log(JSON.stringify(inputs.map(run)));\n")
        cp=subprocess.run([shutil.which('node'),str(runner)],check=True,capture_output=True,text=True,timeout=20)
        observed=json.loads(cp.stdout)
        assert first_difference(expected,observed,tuple(sorted(b.document()['variables']))) is None
        write(d/'observed.json',observed)
        report['javascript'][name]={'cases':len(cases),'comparison':'complete shared-IL state, including temporaries'}
    saved=blocks['saved']
    result=execute_il(saved.document(),saved.state())
    assert result['state']['$operand']==1
    report['controls']['saved_value']={'expected':1,'actual':result['state']['$operand']}
    # A deliberately wrong translation must be detected, not learned as the answer.
    mutant=deepcopy(blocks['adc'].document())
    for statement in mutant['body']:
        if statement['op']=='if' and statement['condition']=={'op':'eq','left':{'var':'$carry'},'right':True}:
            statement['then']=[];break
    wrong=compile_c(mutant,out/'mutant',compilers[0][0])
    indices=(ctypes.c_uint32*8)(*(wrong.names.index(n) for n in public));failure=(ctypes.c_uint32*6)()
    count=check(ctypes.cast(wrong.function,ctypes.c_void_p),0,indices,len(wrong.names),failure)
    assert count<131072
    report['controls']['carry_mutant']={'first_case_index':int(count),'counterexample':list(failure),'detected':True}
    # One integrated path: saved-state arithmetic, mapping switch, restoration, native output.
    mapping=CodeMap();bindings=Bindings(((0x10,'result'),))
    a=NativeBacking('composition','A',0x8000,bytes.fromhex('A9 01 48 A9 02 68 85 10'))
    b=NativeBacking('composition','B',0x8000,bytes.fromhex('A9 03 48 A9 04 68 85 10'))
    mapping.map('window',a);lease,ba=mapping.select('window',bindings)
    native_a=compile_c(ba.document(),out/'composition_a',compilers[0][0])
    result_a=mapping.execute(lease,native_a,ba.state())['$result']
    snap=mapping.snapshot();mapping.map('window',b)
    try:mapping.execute(lease,native_a,ba.state())
    except StaleSelection:rejected=True
    else:raise AssertionError('stale selection executed')
    next_lease,bb=mapping.select('window',bindings)
    native_b=compile_c(bb.document(),out/'composition_b',compilers[0][0])
    result_b=mapping.execute(next_lease,native_b,bb.state())['$result']
    mapping.restore(snap);restored,br=mapping.select('window',bindings)
    result_restored=mapping.execute(restored,native_a,br.state())['$result']
    assert (result_a,result_b,result_restored)==(1,3,1)
    report['controls']['mapping_composition']={'observed_results':[result_a,result_b,result_restored],
        'stale_rejected':rejected,'cached_recovery_reused':br.identity==ba.identity}
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.suffix not in {'.so'}:
            report['files'][str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'verification.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.output.resolve())
