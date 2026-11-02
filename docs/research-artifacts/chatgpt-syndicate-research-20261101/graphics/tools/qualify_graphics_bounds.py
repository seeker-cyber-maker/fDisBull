"""Bounded arithmetic/callee obligations, kept separate from CFG admission."""
from pathlib import Path
import os
import json,struct,hashlib,collections
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
import z3
P=Path(os.environ['SYNDICATE_PRIVATE']).resolve();raw=(P/'region-10000.bin').read_bytes();
manifest=json.loads((P/'region-manifest.json').read_text());
if manifest['original_sha256']!='bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078' or hashlib.sha256(raw).hexdigest()!=manifest['regions']['0x10000']['sha256']:
 raise ValueError('wrong source identity; do not apply these source anchors')
cs=Cs(CS_ARCH_X86,CS_MODE_32);cs.detail=True
proofs=[]
def check(name,assumptions,violation):
 s=z3.Solver();s.set(timeout=5000);s.add(*assumptions,violation);r=s.check()
 proofs.append({'case':name,'result':str(r),'counterexample':str(s.model()) if r==z3.sat else None})
 return r
l,r=z3.BitVecs('left right',32)
mask=z3.BitVecVal(0xfff8,32);rem=r-((l&mask)+8)
assumptions=[l>=0,l<r,r<=640,(l&mask)!=(r&mask)]
assert check('caller-initial-nonnegative-remainder',assumptions,z3.Or(rem<0,rem>632))==z3.unsat
n=z3.BitVec('remainder',32)
assert check('loop-preserves-nonnegative-and-decreases',[n>=0,n<=632,n>16],z3.Or(n-16<0,n-16>=n))==z3.unsat
assert check('exit-index-0-through-16',[n>=0,n<=632,z3.Not(n>16)],z3.Or(n<0,n>16))==z3.unsat
assert check('upper-bound-only-is-insufficient',[z3.Not(n>16)],n<0)==z3.sat
assert check('losing-left-right-order-is-insufficient',[l>=0,l<=640,r>=0,r<=640,(l&mask)!=(r&mask)],rem<0)==z3.sat
# Exhaustive small display-coordinate domain checks the arithmetic independently
# from the solver model. Domain is not inferred from all game callers.
indices=collections.Counter();pairs=0;maxiters=0
for left in range(640):
 for right in range(left+1,641):
  if (left&0xfff8)==(right&0xfff8):continue
  q=right-((left&0xfff8)+8);k=0
  assert q>=0
  while q>16:q-=16;k+=1
  assert 0<=q<=16
  maxiters=max(maxiters,k);indices[q]+=1;pairs+=1
# Inspect ALL targets of both color helper tables for complete bounded paths.
# This checks preservation of EDI at the ISA register-write level, not all
# arbitrary aliasing or memory-access contracts.
helpers=[]
for t in [0x42b9f,0x42d77]:
 for color in range(16):
  target=struct.unpack_from('<I',raw,t-0x10000+4*color)[0];seq=[]
  for ins in cs.disasm(raw[target-0x10000:target-0x10000+128],target):
   reads,writes=ins.regs_access();assert 'edi' not in [ins.reg_name(x) for x in writes]
   seq.append(ins)
   if ins.mnemonic=='ret':break
  assert seq[-1].mnemonic=='ret'
  assert all(i.mnemonic in ['and','or','add','loop','ret'] for i in seq)
  # LOOP is only the column helper's loop to this very target.
  for ins in seq:
   if ins.mnemonic=='loop':assert ins.operands[0].imm==target
  blob=b''.join(i.bytes for i in seq)
  helpers.append({'table':hex(t),'color':color,'target':hex(target),'instruction_count':len(seq),'source_sha256':hashlib.sha256(blob).hexdigest(),'edi_written':False})
# Bind the decisive source operations in all four caller families.
expected={0x41f99:('sub','edi, eax'),0x41fb8:('cmp','edi, 0x10'),0x41fcd:('sub','edi, 0x10'),0x4221e:('sub','edi, eax'),0x4223d:('cmp','edi, 0x10'),0x42252:('sub','edi, 0x10'),0x42537:('sub','edi, eax'),0x4255b:('cmp','edi, 0x10'),0x42575:('sub','edi, 0x10'),0x428aa:('sub','edi, eax'),0x428ce:('cmp','edi, 0x10'),0x428e8:('sub','edi, 0x10')}
bindings=[]
for address,(mn,op) in expected.items():
 ins=next(cs.disasm(raw[address-0x10000:address-0x10000+15],address,count=1));assert (ins.mnemonic,ins.op_str)==(mn,op)
 bindings.append({'address':hex(address),'instruction_sha256':hashlib.sha256(ins.bytes).hexdigest(),'checked':True})
result={'qualification':'Authored local bit-vector/loop obligations plus checked source anchors and exhaustive admitted endpoint pairs; NOT all-path/caller proof or production edges.','assumptions':['0 <= absolute left < right <= 640, different aligned byte cells','selected planar mode; color 0..15; positive clipped height for column helper','nonaliasing stable frame/stack/tables; no asynchronous mutation; successful memory access','actual execution from the inspected caller path; unsupported integer overflow outside admitted domain'], 'solver_version':z3.get_version_string(),'proofs':proofs,'endpoint_pairs':pairs,'tail_index_counts':dict(sorted(indices.items())),'maximum_middle_iterations':maxiters,'source_helper_paths':helpers,'source_anchor_checks':bindings}
with (P/'evidence/graphics-bound-proof-replayed.json').open('x') as out:
 out.write(json.dumps(result,indent=2)+'\n')
print('pairs',pairs,'indices',sorted(indices),'max iterations',maxiters,'checks',len(proofs),'helper paths',len(helpers))
