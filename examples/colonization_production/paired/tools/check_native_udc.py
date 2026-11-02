"""Build and execute both recovered editions through v0.30's native Linux UDC."""
from pathlib import Path
import json,struct,hashlib
from build_uil import make
from fdisbull.common_uil import digest
from fdisbull.uil_codegen import compile_program
from fdisbull.uil_native_codegen import run_native_records
R=Path(__file__).resolve().parents[1]
s16=lambda x:((x+32768)&65535)-32768
s8=lambda x:((x+128)&255)-128
cases=json.loads((R/'private/new_native/cases.json').read_text());inputs=[]
for _,level,stock,supply,demand,pop,index,packed,production,bits in cases:
 inputs.append([level,s16(stock),s16(supply),s16(demand),s8(pop),index,packed,s16(production),bits.bit_count()])
results=[]
for edition in ['DOS','WIN']:
 program,presentation,_=make(edition)
 catalog={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
 orchestration={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(program),'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':32}
 dest=R/'private'/('native64_'+edition.lower())
 manifest=compile_program(program,presentation,catalog,orchestration,str(dest),target='linux-x64',c_compiler='/usr/bin/gcc')
 (R/'deliverable/results'/f'{edition.lower()}_native64_build.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(edition,'built',list(manifest.keys()),flush=True)
 rows=run_native_records([str(dest/'program')],manifest,inputs,cwd=dest,timeout=30)
 source=list(struct.iter_unpack('<8H',(R/'private/new_native'/f'{edition}NEW.BIN').read_bytes()))
 assert len(rows) == len(source) == len(cases), 'incomplete native output stream'
 for i,(row,ref) in enumerate(zip(rows,source)):
  assert row['status']=='complete',row
  assert [int(v)&65535 for v in row['outputs']]==list(ref[1:]),(edition,i,row,ref)
 results.append({'edition':edition,'target':'linux-x64','cases':len(rows),'mismatches':0,'executable_sha256':hashlib.sha256((dest/'program').read_bytes()).hexdigest(),'first_outputs':[r['outputs'] for r in rows[:6]],'scope':'Generated ELF64 host computation, no GUI or complete game; compared to isolated DOS/Win16 source closures.'})
print(json.dumps(results,indent=2))
(R/'deliverable/results/native64.json').write_text(json.dumps(results,indent=2)+'\n')
