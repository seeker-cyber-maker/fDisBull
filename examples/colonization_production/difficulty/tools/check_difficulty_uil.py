"""Compare expanded common UIL and native host outputs with recorded original cuts."""
from pathlib import Path
import argparse, json, struct, hashlib, time
from build_difficulty_uil import make, input_row
from fdisbull.common_uil import digest
from fdisbull.uil_runtime import execute_program
from fdisbull.uil_codegen import compile_program
from fdisbull.uil_native_codegen import run_native_records

def run(root: Path, native: Path, output: Path, editions=('DOS', 'WIN')):
    output.mkdir(parents=True, exist_ok=False)
    cases=json.loads((native/'cases.json').read_text())
    inputs=[input_row(row['words']) for row in cases]
    # Fixed, reproducible sample across the entire corpus plus all food/flag cases.
    selected=sorted(set(range(0,len(cases),211)) | {i for i,c in enumerate(cases) if c['kind'] in ('food-terrain-grid','explicit-status')})
    receipt={'cases_per_edition':len(cases),'python_common_selected_indices':selected,'editions':[]}
    for edition in editions:
        p,v,_=make(edition)
        cat={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
        orch={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),'bindings':[], 'ownership':'copy-in-copy-out','max_call_depth':32}
        refs=list(struct.iter_unpack('<12H',(native/f'{edition}DIFF.BIN').read_bytes()))
        assert len(refs)==len(inputs)
        t=time.perf_counter()
        for i in selected:
            r=execute_program(p,v,inputs=inputs[i])
            assert r['status']=='complete',(edition,i,r)
            assert [int(x)&65535 for x in r['outputs']]==list(refs[i][1:11]),(edition,i,r,refs[i])
        interpreted_time=time.perf_counter()-t
        print(edition, 'Python comparison passed', len(selected), 'seconds', interpreted_time, flush=True)
        dest=output/edition.lower()
        manifest=compile_program(p,v,cat,orch,str(dest),target='linux-x64',c_compiler='/usr/bin/gcc')
        print(edition, 'native built', flush=True)
        t=time.perf_counter()
        rows=[]
        for at in range(0,len(inputs),1024):
            rows.extend(run_native_records([str(dest/'program')],manifest,inputs[at:at+1024],cwd=dest,timeout=60))
        elapsed=time.perf_counter()-t
        assert len(rows)==len(inputs)
        for i,(r,ref) in enumerate(zip(rows,refs)):
            assert r['status']=='complete',(edition,i,r)
            assert [int(x)&65535 for x in r['outputs']]==list(ref[1:11]),(edition,i,r,ref)
        entry={'edition':edition,'common_python_cases':len(selected),'native_cases':len(rows),'mismatches':0,
               'common_python_seconds':interpreted_time,'native_batch_seconds':elapsed,
               'program_sha256':digest(p),'executable_sha256':hashlib.sha256((dest/'program').read_bytes()).hexdigest(),
               'source_result_sha256':hashlib.sha256((native/f'{edition}DIFF.BIN').read_bytes()).hexdigest(),
               'target':'linux-x64','boundary':'10 declared outputs; source cut/context requirements apply'}
        receipt['editions'].append(entry);print(json.dumps(entry),flush=True)
        (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--edition',choices=('DOS','WIN'));a.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a.add_argument('--native-dir',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();run(x.root,x.native_dir,x.output,(x.edition,) if x.edition else ('DOS','WIN'))
