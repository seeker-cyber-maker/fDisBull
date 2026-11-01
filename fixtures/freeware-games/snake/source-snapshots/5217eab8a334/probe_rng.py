from pathlib import Path
from copy import deepcopy
import json, hashlib, struct
from fdisbull.udc_web_memory import execute_memory_uil,validate_memory_uil,digest
from examples.recovery.snake_model import _original_call, pack_state, core_state, STATE, INPUT

ROOT=Path('${USER_HOME}/.codex/tmp/snake-rng-2026-10-31/probes')
FROZEN=Path('${PRIVATE_PROJECTS}/Snake-browser-study-2026-10-31/model-02')
EXE=Path('${PRIVATE_PROJECTS}/fDisBull-targets-private/targets/fixture-snake/SNAKE.EXE')
MAP=Path('${PRIVATE_PROJECTS}/fDisBull-targets-private/sources/snake-fixture-v1/oracle/SNAKE.MAP')
sha=lambda b:hashlib.sha256(b).hexdigest()
raw=(FROZEN/'snake.uil.json').read_bytes();program=json.loads(raw)
assert digest(program)=='a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720'
source_sha=sha(EXE.read_bytes());assert source_sha=='f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be'
E=lambda op,a,b:{'op':op,'left':a,'right':b}
s={'load':606}
value=E('and',E('or',E('xor',E('shr',s,1),E('and',E('sub',0,E('and',s,1)),0xB400)),E('mul',E('eq',s,0),0xACE1)),65535)
variant={'op':'store','index':606,'value':value}
mutant=deepcopy(program);replaced=[]
def visit(value):
 if isinstance(value,dict):
  if value.get('id') in ('step.44','action.130','action.196'):
   assert value['op']=='store' and value['index']==606
   replaced.append(value['id']);value['value']=deepcopy(variant['value'])
  for v in value.values():visit(v)
 elif isinstance(value,list):
  for v in value:visit(v)
visit(mutant);assert len(replaced)==3
validate_memory_uil(mutant)
(ROOT/'lfsr16-variant-store.json').write_text(json.dumps(variant,indent=2)+'\n')
def original(s):return (s*25173+13849)&65535
def alternate(s):return (((s>>1)^((-(s&1))&0xB400)) if s else 0xACE1)&65535
def cycle(fn,start):
 seen={};seq=[];value=start
 while value not in seen:
  seen[value]=len(seq);seq.append(value);value=fn(value)
 return {'start':start,'period':len(seq)-seen[value],'transient':seen[value], 'return_value':value,'sequence_sha256':sha(struct.pack('<'+'H'*len(seq),*seq))}
seeds=(0,1,65535,32768,4660)
result={'format':'snake-rng-independent-probe-1','canonical_uil_sha256':digest(program),'canonical_file_sha256':sha(raw),'original_sha256':source_sha,
 'alternate':'Galois LFSR16 mask0xB400, explicit zero output0xACE1','variant_store':variant,'patched_reference_nodes':replaced,
 'variant_reference_notice':'In-memory intentionally mutated reference only. Canonical source file is unchanged; alternative is not equivalent to precise original UIL.',
 'cycles':{'original':cycle(original,4660),'alternate_nonzero':cycle(alternate,4660),'alternate_from_zero':cycle(alternate,0)},
 'transitions':[{'before':s,'original_next':original(s),'alternate_next':alternate(s),'original_candidate':original(s)%600,'alternate_candidate':alternate(s)%600} for s in seeds]}

# Direct original CPU step calls prove the unchanged original behavior for this
# input direction schedule. This is a kernel input adapter, not native keyboard
# consumption evidence. No board/cell intervention occurs along either path.
w=[0]*70000
w=execute_memory_uil(program,'reset',w)['words']
original_words=w.copy();alternate_words=w.copy();cpu=core_state(w,all_cells=True)
schedule=[(1,'initial-right')]*4+[(1,'right-to-column29')]*17+[(2,'down-to-original-food')]*2+[(3,'left-after-second-food'),(0,'up-after-second-food'),(1,'close-four-cell-loop')]
rows=[]
for i,(direction,label) in enumerate(schedule,1):
 original_words[STATE['pending_direction']]=direction;alternate_words[STATE['pending_direction']]=direction;cpu['pending_direction']=direction
 original_result=execute_memory_uil(program,'step',original_words);assert original_result['status']=='complete';original_words=original_result['words']
 alternate_result=execute_memory_uil(mutant,'step',alternate_words);assert alternate_result['status']=='complete';alternate_words=alternate_result['words']
 cpu=_original_call(EXE,MAP,cpu)
 assert core_state(original_words,all_cells=True)==cpu,(i,label)
 read=lambda words:{k:words[STATE[k]] for k in ('snake_length','direction','score','rng_seed','tick_count','game_status','paused','food_cell')}
 row={'step':i,'label':label,'requested_direction':direction,'original':read(original_words),'alternate':read(alternate_words),'original_cells':original_words[:original_words[600]],'alternate_cells':alternate_words[:alternate_words[600]]}
 rows.append(row)
assert rows[3]['original']['food_cell']==389 and rows[3]['alternate']['food_cell']==530
assert rows[-1]['original']['game_status']==1 and rows[-1]['alternate']['game_status']==0
assert rows[-1]['original']['score']==2 and rows[-1]['alternate']['score']==1
result['ordinary_route']={'adapter':'Same declared pending-direction/step schedule; original executable CPU verifies each original step. Native keyboard consumption not tested here.','steps':rows,'original_cpu_step_calls':len(rows),'first_food_divergence_step':4,'second_original_growth_step':23,'outcome_divergence_step':26,'board_interventions':0}

# Compare the frozen native corpus at the game-state projection without costly
# drawing; its only renderer state effects (framecount +1, needs_render=0) are
# explicit emulation here and labelled, never a full raster claim.
study=json.loads((FROZEN/'browser-study-06.json').read_text());initial=json.loads((FROZEN/'initial-words.json').read_text())
arm_results=[]
for name,model in [('original',program),('alternate',mutant)]:
 words=initial.copy()
 for k,v in study['initial_services'].items():words[STATE[k]]=v
 words=execute_memory_uil(model,'reset',words)['words']
 def render_state_only(words):
  if words[STATE['needs_render']]:words[STATE['frame_count']]=(words[STATE['frame_count']]+1)&65535;words[STATE['needs_render']]=0
 render_state_only(words)
 comparisons=[]
 for observation in study['observations']:
  if observation.get('intervention'):words[:len(observation['intervention']['words'])]=observation['intervention']['words']
  for event in observation['events']:
   for key,index in INPUT.items():words[index]=event.get(key,0)
   state=execute_memory_uil(model,'action',words);assert state['status']=='complete';words=state['words'];render_state_only(words)
  expected=observation['expected_state'];differences=[{'index':i,'expected':a,'actual':b} for i,(a,b) in enumerate(zip(expected,words)) if a!=b]
  comparisons.append({'id':observation['id'],'differing_words':differences})
 if name=='original':assert all(not x['differing_words'] for x in comparisons)
 arm_results.append({'name':name,'observations':len(comparisons),'divergent_observations':[x for x in comparisons if x['differing_words']]})
result['frozen_corpus_state_probe']={'rendering':'Renderer state effects emulated for state-only projection; no raster claim. Root will execute actual compiled complete renderers.','arms':arm_results}
assert (FROZEN/'snake.uil.json').read_bytes()==raw and sha(EXE.read_bytes())==source_sha
(ROOT/'independent-rng-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'report':str(ROOT/'independent-rng-results.json'),'transitions':result['transitions'],'cycles':result['cycles'],'last_route':rows[-1], 'corpus_first':arm_results[1]['divergent_observations'][0],'corpus_divergences':len(arm_results[1]['divergent_observations'])}))
# Exhaustive numeric recurrence/finite-domain checks, without drawing or using
# the mutation writer as the expected implementation.
outputs_original=[original(s) for s in range(65536)]
outputs_alternate=[alternate(s) for s in range(65536)]
assert all(0<=v<65536 for v in outputs_alternate)
assert 0 not in outputs_alternate
result['finite_u16_domain']={'seeds':65536,'original_distinct_outputs':len(set(outputs_original)),
 'alternate_distinct_outputs':len(set(outputs_alternate)),
 'equal_transitions':sum(a==b for a,b in zip(outputs_original,outputs_alternate)),
 'original_output_sha256':sha(struct.pack('<65536H',*outputs_original)),
 'alternate_output_sha256':sha(struct.pack('<65536H',*outputs_alternate)),
 'alternate_zero_absorbing':False,'quality_claim':'No statistical/security quality claim; modulo600 and first-free scan remain biased projections.'}

# Finite original-case projection of the deliberately changed calculation.
case_rows=[];case_deltas=[]
for item in study['cases']:
 before=pack_state(item['initial'])
 computed=execute_memory_uil(mutant,'step',before);assert computed['status']=='complete'
 after=core_state(computed['words'],all_cells=True)
 baseline=item['original']
 different={k:{'original':baseline[k],'alternate':after[k]} for k in baseline if after[k]!=baseline[k]}
 case_rows.append({'id':item['id'],'initial':item['initial'],'original':baseline,'alternate':after})
 if different:case_deltas.append({'id':item['id'],'different':different})
result['original_case_predictions']={'cases':len(case_rows),'changed_cases':len(case_deltas),'deltas':case_deltas,
 'scope':'Alternative semantic reference predictions. Actual generated code is a separate parent qualification.'}
(ROOT/'alternate-cases.json').write_text(json.dumps({'format':'snake-alternate-rng-reference-cases-1','variant':'lfsr16-b400-zero-ace1','canonical_uil_sha256':digest(program),'cases':case_rows},indent=2)+'\n')
(ROOT/'independent-rng-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'finite_u16_domain':result['finite_u16_domain'],'original_cases':len(case_rows),'changed_cases':len(case_deltas),'changed_ids':[r['id'] for r in case_deltas]}))
