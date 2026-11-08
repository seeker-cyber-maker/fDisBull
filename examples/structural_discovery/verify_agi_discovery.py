"""Check discovered scalar and parser slices from a private AGI directory.

Selects candidates by opcode/control-flow shape, not game title or fixed offset.
Uses original source bytes with authored input states. This is not an original
interpreter run or a general natural-language parser test.
"""
from pathlib import Path
from copy import deepcopy
import json
from fdisbull.agi import load_logic
from fdisbull.agi_lift import lift_logic
from fdisbull.agi_slice import run_slice
from fdisbull.interaction_il import execute_il
import argparse
from fdisbull.agi_scenes import inspect_scenes
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('game_dir',type=Path,help='private AGI directory containing LOGDIR and VOL files')
ap.add_argument('--output',required=True,type=Path,help='new private JSON receipt outside the input and Git')
args=ap.parse_args();root=args.game_dir.resolve();out=args.output
if root.is_symlink() or not root.is_dir():ap.error('expected an AGI resource directory')
if out.exists() or out.is_symlink():ap.error('output must be new')
parent=out.parent.resolve()
if not parent.is_dir() or root==parent or root in parent.parents or any((p/'.git').exists() for p in (parent,*parent.parents)):
 ap.error('receipt parent must already exist outside input/Git')
if any(p.is_symlink() for p in (out.parent,*out.parent.parents)):ap.error('receipt parent cannot contain symlinks')
census=inspect_scenes(root,profile='2.917',include_ir=True,include_text=True)
receipts=[];refusals=[]
for logic in census['logics']:
 rows=logic['ir']['instructions'];by={r['offset']:r for r in rows}
 for r in rows:
  cond=r.get('conditions',[])
  if r['operation']!='if' or len(cond)!=1 or cond[0].get('opcode')!=1:continue
  start=r['offset'];end=next(s['offset'] for s in r['successors'] if s['kind']=='false')
  pos=r['end_offset'];body=[]
  while pos<end and pos in by and len(body)<8:
   q=by[pos]
   if q['operation'] not in ('assignn','addn','subn','set','reset'):break
   body.append(q);pos=q['end_offset']
  if pos!=end or not body:continue
  index,constant=cond[0]['operands'];touched={f'$agi_v{index}':0}
  for q in body:
   key=('$agi_f' if q['operation'] in ('set','reset') else '$agi_v')+str(q['operands'][0])
   touched[key]=(q['operation']=='reset') if key.startswith('$agi_f') else ((q['operands'][1]^255) if q['operation']=='assignn' else 17)
  res=load_logic(root/'LOGDIR',root,logic['logic'],profile='2.917')
  try:lifted=lift_logic(res,initial_state=touched,entry_offset=start-2,stop_offsets=[end-2])
  except ValueError as e:
   refusals.append({'logic':logic['logic'],'entry':start,'reason':str(e)});continue
  mismatches=[];changed=0
  for value in range(256):
   before={'variables':[0]*256,'flags':[False]*256,'ego':{'x':80,'y':90},'words':[], 'player_control':True}
   for key,initial in touched.items():before['flags' if key.startswith('$agi_f') else 'variables'][int(key[6:])]=initial
   before['variables'][index]=value
   inputs=dict(touched);inputs[f'$agi_v{index}']=value
   source=run_slice(res.payload,before,entry=start,stop=end)
   result=execute_il(lifted['uil'],inputs)
   selected={k:source['state']['flags' if k.startswith('$agi_f') else 'variables'][int(k[6:])] for k in touched}
   if selected!=result['state'] or not result['complete']:mismatches.append(value)
   changed+=selected!=inputs
  receipts.append({'logic':logic['logic'],'resource_sha256':res.resource_sha256,
                   'entry_payload':start,'stop_payload':end,'cases':256,'mismatches':mismatches,
                   'cases_changing_selected_state':changed,'initial_state':touched,'predicate_variable':index,'predicate_value':constant,
                   'scope':'original LOGIC bytes through independent bounded slice evaluator versus existing scalar UIL lifter; no native game run'})
  break
 if len(receipts)>=3:break
# Choose one said-only conditional, stop immediately after its first flag effect.
# Both the true and false outcomes use their own qualified stop boundaries.
parser=None
for logic in census['logics']:
 by={r['offset']:r for r in logic['ir']['instructions']}
 for r in by.values():
  terms=r.get('conditions',[])
  if r['operation']!='if' or len(terms)!=1 or terms[0].get('operation')!='said':continue
  groups=terms[0]['word_groups']
  if any(g in (1,9999) for g in groups):continue
  first=by.get(r['end_offset'])
  if not first or first['operation']!='set' or first['operands'][0] in (2,4):continue
  res=load_logic(root/'LOGDIR',root,logic['logic'],profile='2.917');flag=first['operands'][0]
  false_stop=next(s['offset'] for s in r['successors'] if s['kind']=='false')
  cases=[]
  for mode in ('match','wrong-word','not-ready','already-consumed'):
   state={'variables':[0]*256,'flags':[False]*256,'ego':{'x':80,'y':90},'words':list(groups),'player_control':True}
   state['flags'][2]=mode!='not-ready';state['flags'][4]=mode=='already-consumed'
   if mode=='wrong-word':state['words']=[65534]
   stop=first['end_offset'] if mode=='match' else false_stop
   result=run_slice(res.payload,state,entry=r['offset'],stop=stop)
   cases.append({'case':mode,'set_flag':result['state']['flags'][flag],
                 'input_claimed':result['state']['flags'][4],'pc':result['pc']})
  try:
   lift_logic(res,initial_state={},entry_offset=r['offset']-2,
              stop_offsets=[first['end_offset']-2,false_stop-2])
  except ValueError as e:refusal=str(e)
  else:raise AssertionError('Unexpected parser predicate lift acceptance')
  parser={'logic':logic['logic'],'entry_payload':r['offset'],'source_sha256':res.resource_sha256,
          'groups':groups,'flag':flag,'cases':cases,'scalar_lifter_refusal':refusal,
          'scope':'parsed group semantics, not a general natural-language parser or native interpreter replay'}
  break
 if parser:break
result={'scalar_slices':receipts,'scalar_cases':sum(r['cases'] for r in receipts),
        'refused_candidates':refusals,'scalar_mismatches':sum(len(r['mismatches']) for r in receipts),'parser_slice':parser,'runtime_observed':False}
expected_parser=[True,False,False,False]
result['checks_passed']=(len(receipts)==3 and result['scalar_mismatches']==0 and parser is not None
                        and [c['set_flag'] for c in parser['cases']]==expected_parser
                        and [c['input_claimed'] for c in parser['cases']]==[True,False,False,True])
with out.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
out.chmod(0o600)
print(json.dumps({'scalar_cases':result['scalar_cases'],'scalar_mismatches':result['scalar_mismatches'],
                  'parser_cases':len(parser['cases']) if parser else 0,'checks_passed':result['checks_passed'],
                  'receipt':str(out),'runtime_observed':False}))
raise SystemExit(0 if result['checks_passed'] else 1)
