"""Narrow source-bound local switch guards; no whole-program reachability claim.

Uses actual Capstone operand widths and Z3 partial-register semantics. Models plain MOV stores with byte-wise aliasing; refuses calls, nonflat memory
and unsupported instructions in the selected slice.
"""
from pathlib import Path
import sqlite3, json
import capstone as cs
from capstone.x86_const import X86_OP_REG,X86_OP_IMM,X86_OP_MEM
import z3 as z

ALIASES={}
for full,lo,byte,hi in [('eax','ax','al','ah'),('ebx','bx','bl','bh'),('ecx','cx','cl','ch'),('edx','dx','dl','dh')]:
 for name,start,size in [(full,0,32),(lo,0,16),(byte,0,8),(hi,8,8)]:ALIASES[name]=(full,start,size)
for full,lo in [('esi','si'),('edi','di'),('esp','sp'),('ebp','bp')]:
 ALIASES[full]=(full,0,32);ALIASES[lo]=(full,0,16)
md=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_32);md.detail=True
class Unsupported(ValueError):pass
class State:
 def __init__(self):
  self.r={r:z.BitVec(r,32) for r in ['eax','ebx','ecx','edx','esi','edi','esp','ebp']}
  self.mem=z.Array('stable_flat_memory',z.BitVecSort(32),z.BitVecSort(8))
 def get(self,name):
  if name not in ALIASES:raise Unsupported('register '+name)
  full,lo,n=ALIASES[name];return z.Extract(lo+n-1,lo,self.r[full]) if n<32 else self.r[full]
 def put(self,name,value):
  full,lo,n=ALIASES[name];value=resize(value,n)
  if n==32:self.r[full]=value;return
  old=self.r[full];parts=[]
  if lo+n<32:parts.append(z.Extract(31,lo+n,old))
  parts.append(value)
  if lo>0:parts.append(z.Extract(lo-1,0,old))
  self.r[full]=z.Concat(*parts)
 def addr(self,i,op):
  m=op.mem
  seg=i.reg_name(m.segment) if m.segment else ''
  if seg not in ('','ds','ss','cs'):raise Unsupported('nonflat segment '+seg)
  a=z.BitVecVal(m.disp & 0xffffffff,32)
  if m.base:a+=resize(self.get(i.reg_name(m.base)),32)
  if m.index:a+=resize(self.get(i.reg_name(m.index)),32)*m.scale
  return a
 def value(self,i,op):
  n=op.size*8
  if op.type==X86_OP_REG:return self.get(i.reg_name(op.reg))
  if op.type==X86_OP_IMM:return z.BitVecVal(op.imm & ((1<<n)-1),n)
  if op.type==X86_OP_MEM:
   a=self.addr(i,op);b=[z.Select(self.mem,a+k) for k in range(op.size)]
   return z.Concat(*b[::-1]) if len(b)>1 else b[0]
  raise Unsupported('operand')
 def step(self,i):
  ops=i.operands;m=i.mnemonic
  if i.addr_size!=4:raise Unsupported('address-size override')
  if m=='nop':return
  if m=='mov' and ops and ops[0].type==X86_OP_MEM:
   dst=self.addr(i,ops[0]);v=resize(self.value(i,ops[1]),ops[0].size*8)
   for byte in range(ops[0].size):self.mem=z.Store(self.mem,dst+byte,z.Extract(byte*8+7,byte*8,v))
   return
  if not ops or ops[0].type!=X86_OP_REG:raise Unsupported('unsupported write/operation '+m)
  dst=i.reg_name(ops[0].reg);n=ops[0].size*8
  if m in ('mov','movzx','movsx'):
   v=self.value(i,ops[1]);self.put(dst,resize(v,n,signed=m=='movsx'));return
  if m=='lea':self.put(dst,self.addr(i,ops[1]));return
  a=self.get(dst)
  if m in ('inc','dec'):self.put(dst,a+(1 if m=='inc' else -1));return
  if m not in ('xor','and','or','add','sub','shl','shr','sar'):raise Unsupported('operation '+m)
  b=resize(self.value(i,ops[1]),n)
  v={'xor':lambda:a^b,'and':lambda:a&b,'or':lambda:a|b,'add':lambda:a+b,'sub':lambda:a-b,
     'shl':lambda:a<<(b&31),'shr':lambda:z.LShR(a,b&31),'sar':lambda:a>>(b&31)}[m]()
  self.put(dst,v)
def resize(v,n,signed=False):
 k=v.size()
 if k==n:return v
 return (z.SignExt(n-k,v) if signed else z.ZeroExt(n-k,v)) if k<n else z.Extract(n-1,0,v)
def decode_record(r):
 i=next(md.disasm(bytes.fromhex(r['bytes']),int(r['address'],16)),None)
 if i is None or i.size!=r['size']:raise Unsupported('decoder disagreement')
 return i

def prove_sequence(seq,guard_index):
 state=State();cond=None;bound=None
 for j,i in enumerate(seq[:-1]):
  if i.addr_size!=4:raise Unsupported('address-size override')
  if j==guard_index:
   if i.mnemonic!='cmp' or i.operands[1].type!=X86_OP_IMM:raise Unsupported('guard')
   left=state.value(i,i.operands[0]);right=resize(state.value(i,i.operands[1]),left.size())
   bound=i.operands[1].imm & ((1<<left.size())-1)
   if bound>255:raise Unsupported('large table')
   cond=z.ULE(left,right)
  elif j==guard_index+1:
   if i.mnemonic not in ('ja','jnbe'):raise Unsupported('not unsigned-above escape')
   if i.operands[0].type!=X86_OP_IMM or seq[guard_index+2].address<=i.operands[0].imm<=seq[-1].address:raise Unsupported('guard branch does not escape suffix')
  else:state.step(i)
 jump=seq[-1];o=jump.operands[0]
 if jump.addr_size!=4 or jump.mnemonic!='jmp' or o.type!=X86_OP_MEM or o.size!=4 or bool(o.mem.base)==bool(o.mem.index):raise Unsupported('table jump form')
 index=(resize(state.get(jump.reg_name(o.mem.index)),32)*o.mem.scale if o.mem.index else resize(state.get(jump.reg_name(o.mem.base)),32))
 table=o.mem.disp & 0xffffffff
 feasible=z.Solver();feasible.set(timeout=3000);feasible.add(cond)
 if feasible.check()!=z.sat:raise Unsupported('vacuous or unknown guard feasibility')
 s=z.Solver();s.set(timeout=3000);s.add(cond,z.Or(z.UGT(index,bound*4),(index&3)!=0,z.ULT(index+table,z.BitVecVal(table,32))))
 result=s.check()
 return {'guard_feasible':True,'bound':bound,'entry_count':bound+1,'table':hex(table),'verdict':str(result),
         'counterexample':str(s.model()) if result==z.sat else None,
         'index_expression':str(z.simplify(index)),
         'claim':'Local guard fallthrough bounds an aligned table byte offset under stable valid flat memory; no runtime reachability or table integrity proof.'}

def qualify(c):
 ins={int(x['address'],16):dict(x) for x in c.execute('select * from instructions where version=1')};ends={}
 for a,x in ins.items():ends.setdefault(a+x['size'],[]).append(a)
 out=[]
 for a,x in sorted(ins.items()):
  if x['flow']!='indirect_jump':continue
  rev=[a];cur=a
  for _ in range(28):
   p=ends.get(cur,[])
   if len(p)!=1:break
   cur=p[0];rev.append(cur)
  seq=[ins[p] for p in rev[::-1]];candidates=[]
  for k in range(len(seq)-2):
   if seq[k]['mnemonic']=='cmp' and seq[k+1]['mnemonic'] in ('ja','jnbe') and all(q['flow']=='next' for q in seq[k+2:-1]):candidates.append(k)
  rec={'dispatch':hex(a),'stored_operand':x['operands']}
  if not candidates:rec['status']='no_supported_guard';out.append(rec);continue
  k=candidates[-1]
  # Include up to 8 straight-line predecessor instructions to capture reload identity.
  lo=k
  while lo>0 and k-lo<8 and seq[lo-1]['flow']=='next':lo-=1
  attempts=[]
  for start in range(lo,k+1):
   try:
    decoded=[decode_record(q) for q in seq[start:]]
    proof=prove_sequence(decoded,k-start)
    attempts.append({'start':hex(int(seq[start]['address'],16)),'verdict':proof['verdict']})
    if proof['verdict']=='unsat':
     rec.update(proof);rec['status']='locally_bounded';rec['slice_start']=hex(int(seq[start]['address'],16));rec['guard']=hex(int(seq[k]['address'],16));rec['escape']=hex(int(seq[k+1]['target'],16));break
   except (Unsupported,z.Z3Exception,KeyError) as e:attempts.append({'start':hex(int(seq[start]['address'],16)),'error':str(e)})
  else:rec['status']='unproved_or_unsupported'
  rec['attempts']=attempts;out.append(rec)
 return out
