"""Small symbolic UIL composition over versioned block contracts.

The existing fdisbull-il-1 primitive evaluator is unchanged. This explicit
module profile adds contract-bound invocation and unsigned remainder.
"""
from copy import deepcopy
from .interaction_il import validate_il, execute_il, _typed
from .udc_layers import _contract, run_selection, digest


def _primitive(program,body):
 return {'format':'fdisbull-il-1','role':program['role'],'variables':program['variables'],'resources':program['resources'],'body':body,'evidence':program.get('evidence',{})}


def validate_module_uil(project,program):
 if type(program) is not dict or program.get('format')!='fdisbull-module-uil-1' or program.get('role') not in ('udl','uil'):raise ValueError('invalid module UIL format/role')
 if set(program)-{'format','role','variables','resources','body','evidence'}:raise ValueError('unknown module UIL fields')
 validate_il(_primitive(program,[]));variables=program['variables'];seen=set();count=[0]
 def value(item,typ=None):
  if isinstance(item,dict):
   if set(item)!={'var'} or item['var'] not in variables:raise ValueError('unknown module UIL value')
   actual=variables[item['var']]['type']
   if typ is not None and actual!=typ:raise ValueError('module invocation value type differs')
   return actual
  if type(item) not in (int,bool) or typ is not None and not _typed(item,typ):raise ValueError('invalid module literal')
  return None
 def visit(body,depth=0):
  if depth>32 or type(body) is not list:raise ValueError('module UIL depth/body budget')
  for node in body:
   count[0]+=1
   if count[0]>1024 or type(node) is not dict or not isinstance(node.get('id'),str) or node['id'] in seen:raise ValueError('module UIL node budget/identity')
   seen.add(node['id']);op=node.get('op')
   if op=='invoke':
    if set(node)!={'id','op','binding','contract','inputs','outputs'} or not isinstance(node['binding'],str) or not node['binding']:raise ValueError('invalid module invocation')
    contract=_contract(project,node['contract'])
    if type(node['inputs']) is not dict or set(node['inputs'])!=set(contract['inputs']) or type(node['outputs']) is not dict or set(node['outputs'])!=set(contract['outputs']):raise ValueError('incomplete module invocation ports')
    for port,item in node['inputs'].items():value(item,contract['inputs'][port])
    for port,var in node['outputs'].items():
     if not isinstance(var,str) or var not in variables or variables[var]['type']!=contract['outputs'][port]:raise ValueError('module result binding type differs')
    if len(set(node['outputs'].values()))!=len(node['outputs']):raise ValueError('module outputs require distinct result variables')
   elif op=='remainder':
    if set(node)!={'id','op','var','value'} or node['var'] not in variables or not variables[node['var']]['type'].startswith('u'):raise ValueError('remainder requires an unsigned variable')
    value(node['value'],variables[node['var']]['type'])
   elif op=='if':
    if set(node)!={'id','op','condition','then','else'}:raise ValueError('invalid module conditional')
    validate_il(_primitive(program,[{'id':'condition-check','op':'require','condition':node['condition']}]))
    visit(node['then'],depth+1);visit(node['else'],depth+1)
   else:validate_il(_primitive(program,[node]))
 visit(program['body']);return True


def execute_module_uil(project,program,selection,*,state=None,max_steps=1024):
 validate_module_uil(project,program)
 if type(max_steps) is not int or not 1<=max_steps<=100000:raise ValueError('invalid module UIL execution budget')
 selected=project.udl_selection_info(selection,full=True)['document']
 initial={k:v['initial'] for k,v in program['variables'].items()} if state is None else deepcopy(state)
 if type(initial) is not dict or set(initial)!=set(program['variables']) or any(not _typed(initial[k],v['type']) for k,v in program['variables'].items()):raise ValueError('invalid module UIL initial state')
 # Validate every selected invocation before execution, including untaken arms.
 def preflight(body):
  for node in body:
   if node['op']=='invoke':
    if node['binding'] not in selected['bindings']:raise ValueError('module UIL binding is unselected')
    layer=project.udl_layer_info(selected['bindings'][node['binding']],full=True)['document']
    if layer['contract']!=node['contract']:raise ValueError('selected module has a different contract revision')
   if node['op']=='if':preflight(node['then']);preflight(node['else'])
 preflight(program['body'])
 work=deepcopy(initial);calls=[];events=[];visited=[]
 def val(item):return work[item['var']] if isinstance(item,dict) else item
 def condition(c):
  op=c['op']
  if op=='eq':return val(c['left'])==val(c['right'])
  if op=='bit_test':return bool(val(c['value'])&(1<<c['bit']))
  if op=='not':return not condition(c['condition'])
  return all(condition(child) for child in c['conditions'])
 def run(body):
  nonlocal work
  for node in body:
   if len(visited)>=max_steps:raise ValueError('module UIL step budget exhausted')
   visited.append(node['id']);op=node['op']
   if op=='invoke':
    receipt=run_selection(project,selection,node['binding'],{k:val(v) for k,v in node['inputs'].items()})
    for port,var in node['outputs'].items():work[var]=receipt['outputs'][port]
    calls.append(receipt);events.extend(receipt['events'])
   elif op=='remainder':
    divisor=val(node['value'])
    if divisor==0:raise ValueError('zero unsigned remainder divisor')
    work[node['var']]%=divisor
   elif op=='if':run(node['then'] if condition(node['condition']) else node['else'])
   else:
    result=execute_il(_primitive(program,[node]),state=work,max_steps=max_steps)
    if result['status']!='complete':raise ValueError(result.get('error','module primitive needs a host'))
    work=result['state'];events.extend(result['events'])
 try:
  run(program['body'])
 except ValueError as exc:
  return {'status':'refused','complete':False,'state':initial,'events':[],'calls':calls,'visited':visited,'error':str(exc),'uil_sha256':digest(program),'selection':selection,'scope':'pure modeled/isolated block execution; no host effects committed'}
 return {'status':'complete','complete':True,'state':work,'events':events,'calls':calls,'visited':visited,'uil_sha256':digest(program),'selection':selection}
