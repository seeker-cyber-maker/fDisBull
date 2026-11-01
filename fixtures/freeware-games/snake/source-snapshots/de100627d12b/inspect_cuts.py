from pathlib import Path
import json,hashlib
source=Path('${PRIVATE_PROJECTS}/Snake-browser-study-2026-10-31/model-02/snake.uil.json')
p=json.loads(source.read_text())
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k not in ('id','evidence')}
 if isinstance(x,list):return [clean(v) for v in x]
 return x
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def walk_lists(nodes,path):
 yield nodes,path
 for i,n in enumerate(nodes):
  for key in ('body','then','else'):
   if isinstance(n.get(key),list):yield from walk_lists(n[key],path+[i,key])
def flat(nodes):
 for n in nodes:
  yield n
  for key in ('body','then','else'):
   if isinstance(n.get(key),list):yield from flat(n[key])
def locals_read(x):
 if isinstance(x,dict):
  out={x['var']} if set(x)=={'var'} else set()
  return out|set().union(*(locals_read(v) for k,v in x.items() if k not in ('id','evidence'))) if x else out
 if isinstance(x,list):return set().union(*(locals_read(v) for v in x)) if x else set()
 return set()
def locals_written(nodes):return {n['var'] for n in flat(nodes) if n['op']=='set'}
def find(pattern,function):
 matches=[]
 for nodes,path in walk_lists(p['functions'][function]['body'],['functions',function,'body']):
  for i in range(len(nodes)-len(pattern)+1):
   selected=nodes[i:i+len(pattern)]
   if clean(selected)==clean(pattern):
    ids=[n['id'] for n in flat(selected)]
    matches.append({'function':function,'list_path':path,'start':i,'count':len(pattern),'entry_id':ids[0],'last_preorder_id':ids[-1],'nodes':len(ids),'node_ids':ids,'semantic_digest':digest(clean(selected)),'locals_read':sorted(locals_read(selected)),'locals_written':sorted(locals_written(selected)),'following_local_reads_in_same_list':sorted(locals_read(nodes[i+len(pattern):])),'following_node_ids_in_same_list':[n['id'] for n in nodes[i+len(pattern):]]})
 return matches
step=p['functions']['step']['body']
rng=None
for nodes,path in walk_lists(step,['functions','step','body']):
 for i,n in enumerate(nodes):
  if n['op']=='store' and n['index']==606 and n['value'].get('op')=='and':
   assert rng is None;rng=nodes[i:];rngpath=path+[i]
assert rng is not None
report={'format':'fdisbull-snake-structural-cut-probe-1','source':str(source),'source_file_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'module_uil_sha256':digest(p),'program_role':p['role'],'function_node_counts':{f:len(list(flat(d['body']))) for f,d in p['functions'].items()},'step_regions':find(step,'step')+find(step,'action'),'rng_regions':find(rng,'step')+find(rng,'action'),'rng_pattern_top_nodes':len(rng),'step_local_writes':sorted(locals_written(step)),'rng_local_writes':sorted(locals_written(rng))}
Path('${USER_HOME}/.codex/tmp/snake-nested-udc-2026-10-31/probes/cuts.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('step_regions','rng_regions')},indent=2))
for group in ('step_regions','rng_regions'):
 for m in report[group]: print(group,json.dumps({k:v for k,v in m.items() if k not in ('node_ids',)},sort_keys=True))
# Definite-assignment check: a cut has an input-local dependency only when it
# reads a local before assigning it on that path. A while can execute zero times.
def incoming_reads(nodes,defined=None):
 defined=set() if defined is None else set(defined);needed=set()
 for n in nodes:
  op=n['op']
  if op=='set':
   needed |= locals_read(n['value'])-defined; defined.add(n['var'])
  elif op=='store':needed |= (locals_read(n['index'])|locals_read(n['value']))-defined
  elif op=='if':
   needed |= locals_read(n['condition'])-defined
   a,ar=incoming_reads(n['then'],defined);b,br=incoming_reads(n['else'],defined)
   needed|=ar|br;defined=a&b
  elif op=='while':
   needed |= locals_read(n['condition'])-defined
   _,br=incoming_reads(n['body'],defined);needed|=br
  elif op=='return':needed |= locals_read(n.get('value'))-defined
  else:raise ValueError(op)
 return defined,needed
for group in ('step_regions','rng_regions'):
 for m in report[group]:
  ns=p
  for part in m['list_path']:ns=ns[part]
  selected=ns[m['start']:m['start']+m['count']]
  m['incoming_local_reads_before_assignment']=sorted(incoming_reads(selected)[1])
  # Collect all lexical suffixes on the way from this list to function exit.
  suffix_reads=locals_read(ns[m['start']+m['count']:]);enclosing_loops=[]
  cursor=p
  for pos,part in enumerate(m['list_path']):
   if isinstance(cursor,list):
    suffix_reads |= locals_read(cursor[part+1:])
   elif isinstance(cursor,dict) and cursor.get('op')=='while':
    enclosing_loops.append(cursor['id']);suffix_reads |= locals_read(cursor['condition'])
   cursor=cursor[part]
  m['all_ancestor_suffix_local_reads']=sorted(suffix_reads)
  m['enclosing_loop_ids']=enclosing_loops
report['total_statement_nodes']=sum(report['function_node_counts'].values())
Path('${USER_HOME}/.codex/tmp/snake-nested-udc-2026-10-31/probes/cuts.json').write_text(json.dumps(report,indent=2)+'\n')
assert all(not m['incoming_local_reads_before_assignment'] and not m['all_ancestor_suffix_local_reads'] and not m['enclosing_loop_ids'] for group in ('step_regions','rng_regions') for m in report[group])
print('Definite-assignment and all-ancestor continuation liveness: no external local inputs, no live continuation locals, no enclosing loops for all six regions.')
report['rng_seed_regions']=find(rng[:1],'step')+find(rng[:1],'action')
Path('${USER_HOME}/.codex/tmp/snake-nested-udc-2026-10-31/probes/cuts.json').write_text(json.dumps(report,indent=2)+'\n')
print('RNG seed-only nodes:', [(x['entry_id'],x['semantic_digest']) for x in report['rng_seed_regions']])
