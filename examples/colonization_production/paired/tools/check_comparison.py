"""Compare separately recovered common-UIL programs with fresh source-body output."""
from pathlib import Path
import sys,struct,json,hashlib,time,subprocess,copy
from fdisbull.uil_runtime import execute_program
from fdisbull.common_uil import digest
from fdisbull.uil_codegen import compile_program
from build_uil import make,entry,NAMES
R=Path(__file__).resolve().parents[1]
s16=lambda x:((x+32768)&65535)-32768
s8=lambda x:((x+128)&255)-128

def main():
 native=R/'private/new_native';cases=json.loads((native/'cases.json').read_text());models={e:make(e) for e in ['DOS','WIN']};records={e:list(struct.iter_unpack('<8H',(native/f'{e}NEW.BIN').read_bytes())) for e in models}
 errors=[];mismatches=[];t=time.monotonic();outputs={e:[] for e in models}
 for row in cases:
  cid,level,stock,supply,demand,pop,index,packed,production,bits=row
  inputs=[level,s16(stock),s16(supply),s16(demand),s8(pop),index,packed,s16(production),bits.bit_count()]
  for e,(p,v,n) in models.items():
   result=execute_program(p,v,inputs=inputs)
   if result['status']!='complete':raise AssertionError(result)
   actual=[int(x)&65535 for x in result['outputs']];expected=list(records[e][cid][1:])
   if actual!=expected:
    errors.append(dict(edition=e,case=row,uil=actual,native=expected))
    if len(errors)>10:raise AssertionError(errors)
   outputs[e].append(result['outputs'])
  if records['DOS'][cid]!=records['WIN'][cid]:mismatches.append(dict(case=cid,inputs=inputs,dos=outputs['DOS'][-1],windows=outputs['WIN'][-1]))
 if errors:raise AssertionError(errors)
 report={'fresh_native_cases_per_edition':len(cases),'common_uil_suite_evaluations':len(cases)*2,'paired_result_differences':len(mismatches),'first_differences':mismatches[:8],'uil_native_disagreements':errors,'seconds':time.monotonic()-t}
 byfield={n:sum(d[i+1]!=w[i+1] for d,w in zip(records['DOS'],records['WIN'])) for i,n in enumerate(['capacity','available','packed_value','consumed','shortage','unmet','net'])}
 report['different_native_cases_by_field']=byfield
 # Distinguish source-shaped algebraic differences from behavioral differences.
 report['structural_differences']={n:{'same_function_ast':models['DOS'][0]['functions'][i]==models['WIN'][0]['functions'][i],'same_constants':models['DOS'][1]['functions'][i]['constants']==models['WIN'][1]['functions'][i]['constants']} for i,n in enumerate(NAMES)}
 # Regenerate portable independent programs using the actual supplied v0.30 generator.
 generated=[]
 for e,(p,v,n) in models.items():
  cat={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
  orch={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':32}
  for target,cmd,file in [('python',[sys.executable],'program.py'),('javascript',['node'],'program.mjs')]:
   dest=R/'deliverable/generated'/e.lower()/target
   if dest.exists():raise ValueError('refuse overwrite generated output')
   dest.parent.mkdir(parents=True,exist_ok=True)
   res=compile_program(p,v,cat,orch,str(dest),target=target)
   chosen=cases[:262]+cases[-512:] # complete levels and all small supply/production pairs
   requests=[]
   for row in chosen:
    cid,level,stock,supply,demand,pop,index,packed,production,bits=row
    requests.append(json.dumps({'inputs':[level,s16(stock),s16(supply),s16(demand),s8(pop),index,packed,s16(production),bits.bit_count()]}))
   run=subprocess.run(cmd+[str(dest/file)],input='\n'.join(requests)+'\n',capture_output=True,text=True,timeout=30)
   if run.returncode:raise AssertionError(run.stderr)
   replies=[json.loads(x) for x in run.stdout.splitlines()]
   assert len(replies)==len(chosen)
   for row,reply in zip(chosen,replies):
    assert reply['status']=='complete',reply
    # protocol integer output can be decimal strings for 64-bit scalar, none here
    assert [int(x) for x in reply['outputs']]==[int(x) for x in outputs[e][row[0]]],(e,target,row,reply)
   generated.append(dict(edition=e,target=target,cases=len(chosen),passed=True))
 report['generated_targets']=generated
 (R/'deliverable/results').mkdir(parents=True,exist_ok=True)
 (R/'deliverable/results/comparison.json').write_text(json.dumps(report,indent=2)+'\n')
 (R/'deliverable/results/differences.json').write_text(json.dumps(mismatches,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
