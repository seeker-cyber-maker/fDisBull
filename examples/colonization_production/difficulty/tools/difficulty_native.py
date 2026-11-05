"""Source-instruction comparison for difficulty-sensitive Colonization slices.
User-owned originals are required. No source game bytes are distributed by this
script. Entries are explicit function cuts, not complete original processes.
"""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,os,sys
import capstone
from fdisbull.ne import load_ne
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'previous/tools'))
import new_native
SOURCES={
 'DOS':dict(difficulty=0x53a6,control=0x543f,morale=(0xa02d,0xa0af),food=(0xa247,0xa2ac),secondary=(0xa3ab,0xa3b6),
            worker=[(0xa188,0xa1c7),(0xa127,0xa132),(0xa206,0xa220)]),
 'WIN':dict(difficulty=0x76a2,control=0x773b,morale=(0xe097,0xe149),food=(0xcab5,0xcb31),secondary=(0xcc60,0xcc71),
            worker=[(0xe25f,0xe299),(0xe2eb,0xe313)],maximum=(0x12982,0x129ab))}

def cases():
 rows=[]
 def add(kind,d,p=8,sol=0,n=0,c=0,t=13,r=3,x=0,bits=7,g=9,s=0,stock=0,use_worker=0,flags=None):
  status=(4 if sol>=50 else 0)|(2 if sol>=100 else 0) if flags is None else flags
  rows.append({'kind':kind,'words':[len(rows),d,p,sol,n,c,status,t,r,x,bits,g,s,stock,use_worker]})
 for d in range(5):
  for p in range(32):
   for sol in range(101):add('human-morale-exhaustive',d,p,sol)
  for p in range(32):
   for sol in (0,49,50,99,100):
    for n,c in ((0,1),(0,2),(4,0)):add('control-boundary',d,p,sol,n,c)
  for g in range(16):
   for s in range(16):
    for bits in (3,7):add('fixed-production-grid',d,g=g,s=s,bits=bits)
  for p in (6,8,12,20,31):
   for sol in (0,49,50,100):
    for r,x in ((1,0),(2,0),(3,0),(3,1)):
     for bits in (1,3,7):add('coupled-worker-pipeline',d,p,sol,r=r,x=x,bits=bits,use_worker=1)
  for t in (*range(32),-1,-32768,32767):add('food-terrain-grid',d,t=t)
  for flags in (0,2,4,6):add('explicit-status',d,12,0,flags=flags)
 return rows

def build(private,out):
 out=new_native.require_private_output(out)
 out.mkdir(parents=True,exist_ok=False)
 original_build=out/'prior_builder';new_native.build(private,original_build)
 md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_16);md.detail=True
 receipts={};data_rows=cases()
 for edition,ext in SOURCES.items():
  spec=new_native.SPECS[edition];data=(private/spec['file']).read_bytes()
  assert hashlib.sha256(data).hexdigest()==spec['sha']
  asm=(original_build/f'{edition}.s').read_text()
  source_fixes={}
  if edition=='WIN':
   for f in load_ne(data).metadata['ne']['fixups']:
    if f['source_segment_index']==4:
     for pos in f['sources']:source_fixes[pos['file_offset']]=f
  newfix=[];bounds=[]
  def rawcut(name,span):
   lo,hi=span;raw=data[lo:hi];instructions=list(md.disasm(raw,lo));assert sum(i.size for i in instructions)==len(raw)
   allowed={i.address for i in instructions}|{hi};patches=[];lines=[f'{name}_raw:']
   for ins in instructions:
    if ins.group(capstone.CS_GRP_JUMP):
     assert ins.operands[0].type==capstone.x86.X86_OP_IMM and ins.operands[0].imm in allowed
    if ins.mnemonic=='call':
     target=next((k for k,(a,b) in spec['ranges'].items() if a==ins.operands[0].imm),None)
     assert target
     lines.append(f'.byte 0xe8\n.word {target}_body - . - 2')
    else:lines.append('.byte '+','.join(str(x) for x in ins.bytes))
   for offset,f in source_fixes.items():
    if lo<=offset<hi:
     assert f['source_type']=='selector16' and f['target_segment_index'] in [19,20]
     newfix.append(f'mov word ptr cs:[{name}_raw+{offset-lo}],ax')
     patches.append({'offset':offset-lo,'target_segment':f['target_segment_index']})
   bounds.append({'name':name,'range':[lo,hi],'bytes':len(raw),'instructions':len(instructions),'sha256':hashlib.sha256(raw).hexdigest(),'selector_fixups':patches})
   return '\n'.join(lines)
  # Controlled entry: SOL is the return of the separately scoped colony_rebel.
  morale=rawcut('morale',ext['morale'])
  food=rawcut('food',ext['food']);secondary=rawcut('secondary',ext['secondary'])
  if edition=='DOS':
   morale_setup='';morale_finish='mov ax,[bp-14]\nmov cx,[bp-8]\nmov dx,[bp-10]'
   food_setup='';food_finish='mov al,byte ptr [0xa891]\nxor ah,ah'
   sec_setup='mov byte ptr [0xa894],0';sec_finish='mov al,byte ptr [0xa894]\nxor ah,ah'
   worker_setup='mov word ptr [bp-22],10\nmov word ptr [bp-2],24\nmov word ptr [bp-18],ax\nmov word ptr [bp-14],dx\nmov word ptr [bp-28],cx'
   worker_result='mov ax,word ptr [bp-6]'
  else:
   morale_setup='mov [bp-20],ax';morale_finish='mov ax,[bp-24]\nmov cx,[bp-18]\nmov dx,[bp-22]'
   food_setup='mov [bp-14],ax';food_finish='mov al,byte ptr [0x4852]\nxor ah,ah'
   sec_setup='mov byte ptr [0x4855],0';sec_finish='mov al,byte ptr [0x4855]\nxor ah,ah'
   worker_setup='mov word ptr [bp-4],10\nmov word ptr [bp-12],24\nmov di,ax\nmov word ptr [bp-24],dx\nmov word ptr [bp-8],cx\nmov word ptr [bp-26],0'
   worker_result='mov ax,si'
  wrappers=f'''\nmorale_proc:
 push bp
 mov bp,sp
 sub sp,64
 {morale_setup}
 {morale}
 {morale_finish}
 leave
 ret
food_proc:
 push bp
 mov bp,sp
 sub sp,64
 {food_setup}
 {food}
 {food_finish}
 leave
 ret
secondary_proc:
 push bp
 mov bp,sp
 sub sp,64
 {sec_setup}
 {secondary}
 {sec_finish}
 leave
 ret
'''
  # Retain only selected manufacturing case + original expert/zero-clamp exits.
  # Every original conditional edge is rebound to the corresponding retained PC.
  instrs=[]
  for lo,hi in ext['worker']:
   v=list(md.disasm(data[lo:hi],lo));assert sum(i.size for i in v)==hi-lo
   instrs+=v;bounds.append({'name':'worker-path','range':[lo,hi],'sha256':hashlib.sha256(data[lo:hi]).hexdigest()})
  addresses={i.address for i in instrs};exitpc=ext['worker'][-1][1]
  workers=['worker_proc:','push bp','mov bp,sp','sub sp,64',worker_setup]
  for ins in instrs:
   workers.append(f'worker_pc_{ins.address:x}:')
   if ins.mnemonic=='call':
    target=ins.operands[0].imm
    known={a:k+'_body' for k,(a,b) in spec['ranges'].items()}
    if edition=='WIN':known[0x12982]='maximum_body'
    if target not in known:raise ValueError(('worker missing call',hex(target)))
    workers.append(f'.byte 0xe8\n.word {known[target]} - . - 2')
   elif ins.group(capstone.CS_GRP_JUMP):
    target=ins.operands[0].imm
    assert target in addresses or target==exitpc,(edition,hex(ins.address),hex(target))
    workers.append(f'{ins.mnemonic} worker_pc_{target:x}')
   else:workers.append('.byte '+','.join(str(x) for x in ins.bytes))
  workers.extend([f'worker_pc_{exitpc:x}:',worker_result,'leave','ret'])
  if edition=='WIN':
   maximum=rawcut('maximum',ext['maximum']).replace('maximum_raw:','maximum_body:')
   workers.append(maximum)
  def native_call(name):
   return ('mov ds,word ptr cs:[data_segment]\n' if edition=='DOS' else '')+f'push cs\ncall {name}_body\npush cs\npop ds\nmov es,word ptr [data_segment]\n'
  set_ds='mov ds,word ptr cs:[data_segment]' if edition=='DOS' else 'push cs\npop ds'
  loop=f'''next_case:
 push cs
 pop ds
 mov bx,word ptr [inh]
 mov cx,30
 mov dx,offset rec
 mov ah,0x3f
 int 0x21
 jc fail
 or ax,ax
 jz done
 cmp ax,30
 jne fail
 mov es,word ptr [data_segment]
 mov ax,[rec]
 mov [result],ax
 mov al,byte ptr [rec+2]
 mov byte ptr es:[{ext['difficulty']}],al
 mov al,byte ptr [rec+4]
 mov byte ptr es:[0xe01f],al
 mov al,byte ptr [rec+8]
 mov byte ptr es:[0xe01a],al
 xor ah,ah
 imul bx,ax,52
 mov al,byte ptr [rec+10]
 mov byte ptr es:[bx+{ext['control']}],al
 mov al,byte ptr [rec+12]
 mov byte ptr es:[0xe01c],al
 mov al,byte ptr [rec+20]
 mov byte ptr es:[{spec['buildingbits']+3}],al
 mov ax,[rec+6]
 {set_ds}
 call morale_proc
 push cs
 pop ds
 mov [result+2],cx
 mov [result+4],dx
 mov [result+6],ax
 mov ax,[rec+14]
 {set_ds}
 call food_proc
 push cs
 pop ds
 mov [result+8],ax
 {set_ds}
 call secondary_proc
 push cs
 pop ds
 mov [result+10],ax
 mov ax,[rec+16]
 mov cx,[rec+18]
 mov dx,[result+6]
 push 0
 push 0
 push 0
 push 0
 {set_ds}
 call worker_proc
 add sp,8
 push cs
 pop ds
 mov es,word ptr [data_segment]
 mov [result+12],ax
 cmp word ptr [rec+28],0
 jne choose_worker
 mov ax,[rec+22]
choose_worker:
 mov word ptr es:[{spec['a']+20}],ax
 mov word ptr es:[{spec['b']+20}],0
 mov ax,[rec+24]
 mov word ptr es:[{spec['a']+4}],ax
 mov ax,[rec+26]
 mov word ptr es:[0xe09e],ax
 push 10
 push 2
 {native_call('recipe')}
 add sp,4
 mov ax,word ptr es:[{spec['b']+4}]
 mov [result+14],ax
 mov ax,word ptr es:[{spec['short']+4}]
 mov [result+16],ax
 mov ax,word ptr es:[{spec['deficit']+4}]
 mov [result+18],ax
 {'push 0' if edition=='WIN' else ''}
 push 0
 push 10
 {native_call('net')}
 add sp,{6 if edition=='WIN' else 4}
 mov [result+20],ax
 mov ax,[rec+2]
 mov [result+22],ax
 mov bx,[outh]
 mov dx,offset result
 mov cx,24
 mov ah,0x40
 int 0x21
 jc fail
 cmp ax,24
 jne fail
 jmp next_case
'''
  # All selector bindings receive the same isolated source-data segment. The
  # original source segment identities remain recorded; no live selector claim.
  asm=asm.replace('next_case:\n'+asm.split('next_case:\n',1)[1].split('done:\n',1)[0],loop)
  asm=asm.replace('rec:.fill 20,1,0','rec:.fill 30,1,0').replace('result:.fill 16,1,0','result:.fill 24,1,0')
  asm=asm.replace('NEWCASE.BIN','DIFFCASE.BIN').replace(f'{edition}NEW.BIN',f'{edition}DIFF.BIN')
  asm=asm.replace('mov ax,word ptr [data_segment]\n ', 'mov ax,word ptr [data_segment]\n '+ '\n '.join(newfix)+'\n ',1)
  asm+=wrappers+'\n'+'\n'.join(workers)+'\n'
  src=out/f'{edition}.s';src.write_text(asm)
  subprocess.run(['as','--32',str(src),'-o',str(out/f'{edition}.o')],check=True)
  subprocess.run(['ld','-m','elf_i386','-Ttext','0x100','--oformat','binary',str(out/f'{edition}.o'),'-o',str(out/f'{edition}.COM')],check=True)
  assert (out/f'{edition}.COM').stat().st_size<0x4000
  receipts[edition]={'source_sha256':spec['sha'],'new_source_cuts':bounds,'difficulty_offset':ext['difficulty'],'controller_offset':ext['control'],'harness_sha256':hashlib.sha256((out/f'{edition}.COM').read_bytes()).hexdigest()}
 (out/'DIFFCASE.BIN').write_bytes(b''.join(struct.pack('<15H',*[x&65535 for x in r['words']]) for r in data_rows))
 (out/'cases.json').write_text(json.dumps(data_rows,separators=(',',':')))
 (out/'bindings.json').write_text(json.dumps(receipts,indent=2))
 return len(data_rows)

def run(private,out,backend):
 count=build(private,out)
 cmd=[str(backend.resolve()),'-defaultconf','-defaultmapper','-nogui','-c','cycles max','-c',f'mount c "{out.resolve()}"','-c','c:','-c','DOS.COM','-c','WIN.COM','-c','exit']
 with (out/'native.log').open('w') as log:
  p=subprocess.run(cmd,env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'},stdout=log,stderr=subprocess.STDOUT,timeout=100)
 assert p.returncode==0,p.returncode
 for ed in SOURCES:
  f=out/f'{ed}DIFF.BIN';assert f.stat().st_size==count*24,(ed,f.stat().st_size,count*24)
 print('Complete',count,'cases in each edition')
 return count
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--private',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--backend',type=Path,required=True);v=a.parse_args();run(v.private,v.output,v.backend)
