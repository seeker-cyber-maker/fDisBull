from pathlib import Path
import hashlib,json,struct
from fdisbull.udc_web_memory import digest,execute_memory_uil
from examples.recovery.snake_model import _original_call,pack_state,core_state,STATE
root=Path(__file__).parent
private=Path('${USER_HOME}/Documents/Codex_Projects/fDisBull-local-studies/Snake-selectable-RNG-2026-10-31')
frozen=Path('${PRIVATE_PROJECTS}/Snake-browser-study-2026-10-31/model-02')
exe=Path('${PRIVATE_PROJECTS}/fDisBull-targets-private/targets/fixture-snake/SNAKE.EXE')
map_path=Path('${PRIVATE_PROJECTS}/fDisBull-targets-private/sources/snake-fixture-v1/oracle/SNAKE.MAP')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source_hash=sha(exe)
assert source_hash=='f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be'
program=json.loads((frozen/'snake.uil.json').read_text())
assert digest(program)=='a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720'
udl=json.loads((frozen/'snake.udl.json').read_text())
assert {**udl,'role':'uil'}==program
study=json.loads((private/'rng-study-02.json').read_text())
rows=[]
for item in study['cases']:
 actual=_original_call(exe,map_path,item['initial'])
 assert actual==item['original'],item['id']
 result=execute_memory_uil(program,'step',pack_state(item['initial']))
 assert result['status']=='complete' and core_state(result['words'],all_cells=True)==actual,item['id']
 rows.append({'id':item['id'],'initial':item['initial'],'original':actual})
(root/'fresh-original-cases.json').write_text(json.dumps({'cases':rows},indent=2)+'\n')
state=dict(study['cases'][0]['initial'])
# Reset is a declared original-state adapter for a fresh ordinary route.
reset=execute_memory_uil(program,'reset',[0]*70000)['words']
state=core_state(reset,all_cells=True)
schedule=[1]*21+[2]*2+[3,0,1]
route=[]
for number,direction in enumerate(schedule,1):
 state['pending_direction']=direction
 state=_original_call(exe,map_path,state)
 route.append({'step':number,'direction':direction,'state':state})
 assert all(0<=value<=65535 for key,value in state.items() if key not in ('cells','all_cells'))
assert route[3]['state']['rng_seed']==10589 and route[3]['state']['food_cell']==389
assert route[22]['state']['snake_length']==5 and route[22]['state']['score']==2
assert route[25]['state']['game_status']==1 and route[25]['state']['snake_length']==5
(root/'fresh-original-outcome.json').write_text(json.dumps({'steps':route},indent=2)+'\n')
assert sha(exe)==source_hash
palette=json.loads((private/'build-03/browser/memory-shell.json').read_text())['plan']['frame']['palette'] if (private/'build-03/browser/memory-shell.json').exists() else json.loads((frozen.parent/'build-03/browser/memory-shell.json').read_text())['plan']['frame']['palette']
result={'format':'fdisbull-snake-macos-original-oracle-1','status':'fresh_finite_original_match','original_sha256':source_hash,'map_sha256':sha(map_path),'canonical_uil_sha256':digest(program),'udl_sha256':digest(udl),'cases':len(rows),'original_cpu_calls':len(rows)+len(route),'outcome_steps':len(route),'mismatches':0,'unchanged_original':True,'palette':palette,'scope':'Isolated original DOS x86-16 step code with declared normalized memory/register adapter; original keyboard/mouse and graphics evidence remain separate frozen native observations','case_file_sha256':sha(root/'fresh-original-cases.json'),'outcome_file_sha256':sha(root/'fresh-original-outcome.json')}
(root/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
