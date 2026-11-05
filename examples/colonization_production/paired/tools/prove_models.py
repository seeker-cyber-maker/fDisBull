"""Bit-vector checks of authored common UIL models, not formal x86 proofs."""
from pathlib import Path
import json,z3
from build_uil import make
from fdisbull.common_uil import expression_type
R=Path(__file__).resolve().parents[1]

def symbolic(program,pres,index,inputs):
 f=program['functions'][index];binding=pres['functions'][index]
 def val(x,d):
  return z3.BoolVal(x) if d['type']=='bool' else z3.BitVecVal(int(x),int(d['type'][1:]))
 state=[val(x,d) for x,d in zip(binding['initial'],f['variables'])]
 for slot,x in zip(f['inputs'],inputs):state[slot]=x
 constants=[val(x,d) for x,d in zip(binding['constants'],f['constants'])]
 domains=[]
 def ev(e,s):
  if 'var' in e:return s[e['var']]
  if 'const' in e:return constants[e['const']]
  a=[ev(x,s) for x in e['args']];op=e['op'];typ=e['type'];operand=expression_type(e['args'][0],f)['type'];unsigned=operand.startswith('u')
  if op=='cast':
   if typ=='bool':return a[0]!=0
   width=int(typ[1:]);old=a[0].size()
   if width==old:return a[0]
   if width<old:return z3.Extract(width-1,0,a[0])
   return z3.ZeroExt(width-old,a[0]) if unsigned else z3.SignExt(width-old,a[0])
  if op=='select':return z3.If(*a)
  if op=='not':return z3.Not(a[0])
  x,y=a
  if op=='add':return x+y
  if op=='sub':return x-y
  if op=='mul':return x*y
  if op=='div':return z3.UDiv(x,y) if unsigned else x/y
  if op=='and':return x&y
  if op=='or':return x|y
  if op=='shr':return z3.LShR(x,y) if unsigned else x>>y
  if op=='eq':return x==y
  if op=='ne':return x!=y
  if op=='lt':return z3.ULT(x,y) if unsigned else x<y
  if op=='le':return z3.ULE(x,y) if unsigned else x<=y
  if op=='gt':return z3.UGT(x,y) if unsigned else x>y
  if op=='ge':return z3.UGE(x,y) if unsigned else x>=y
  raise ValueError(op)
 def run(body,s):
  s=list(s)
  for node in body:
   op=node['op']
   if op=='set':s[node['dst']]=ev(node['value'],s)
   elif op=='if':
    c=ev(node['condition'],s);yes=run(node['then'],s);no=run(node['else'],s);s=[z3.If(c,x,y) for x,y in zip(yes,no)]
   elif op=='call':
    result,ds=symbolic(program,pres,node['function'],[ev(x,s) for x in node['inputs']]);domains.extend(ds)
    for dst,value in zip(node['outputs'],result):s[dst]=value
   elif op=='require':domains.append(ev(node['condition'],s))
   else:raise ValueError(op)
  return s
 final=run(f['body'],state)
 return [final[i] for i in f['outputs']],domains

def main():
 d,p,_=make('DOS');w,q,_=make('WIN');out=[];proofdir=R/'deliverable/proofs';proofdir.mkdir(parents=True,exist_ok=True)
 names=['input_balance','net_production','capacity_from_level','stock_available','packed_slot_read','production_input_pipeline']
 for i,name in enumerate(names):
  f=d['functions'][i];inputs=[]
  for k in f['inputs']:
   typ=f['variables'][k]['type'];inputs.append(z3.Bool(f'x_{i}_{k}') if typ=='bool' else z3.BitVec(f'x_{i}_{k}',int(typ[1:])))
  a,da=symbolic(d,p,i,inputs);b,db=symbolic(w,q,i,inputs)
  domain=z3.And(*(da+db));different=z3.Or(*[x!=y for x,y in zip(a,b)])
  s=z3.Solver();s.set(timeout=20000);s.add(domain,different)
  result=s.check();row={'operation':name,'counterexample_query':str(result),'scope':'Authored common-UIL bit-vector semantics with declared require predicates; not x86 transition proof'}
  (proofdir/(name+'.smt2')).write_text(s.to_smt2())
  ds=z3.Solver();ds.add(domain);row['domain_satisfiable']=str(ds.check())
  if result==z3.sat:
   model=s.model();row['counterexample_raw']=[str(model.eval(x,model_completion=True)) for x in inputs]
   row['dos']=[str(model.eval(x,model_completion=True)) for x in a];row['windows']=[str(model.eval(x,model_completion=True)) for x in b]
  out.append(row)
  if i<5:assert result==z3.unsat,row
  else:assert result==z3.sat,row
  if i==5:
   s=z3.Solver();s.set(timeout=20000);s.add(domain,z3.ULE(inputs[-1],2),different);res=s.check();assert res==z3.unsat
   (proofdir/'pipeline_without_bonus.smt2').write_text(s.to_smt2());out.append({'operation':'production_input_pipeline_when_building_count_at_most_two','counterexample_query':str(res),'domain_satisfiable':'sat'})
 (R/'deliverable/results/proofs.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
