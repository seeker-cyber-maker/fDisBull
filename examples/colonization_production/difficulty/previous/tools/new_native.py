"""Reproduce four additional paired kernel closures from exact user-owned inputs.
Only selector/callee relocation operands are rebound. No helper return is stubbed.
This is isolated source-instruction execution, not a complete Win16 application.
"""
from pathlib import Path
import argparse, hashlib, struct, json, subprocess, os, random
from fdisbull.ne import load_ne
import capstone
R=Path(__file__).resolve().parents[1]
SPECS={
'DOS':{'file':'VICEROY.EXE','sha':'a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3',
'ranges':{'capacity':(0x8d00,0x8d26),'surplus':(0x8f02,0x8f29),'packed':(0x8f2a,0x8f6c),'recipe':(0x8e84,0x8f02),'wrapper':(0x8e46,0x8e84),'balance':(0x8e02,0x8e46),'net':(0x8dbc,0x8e01),'job':(0x8d9c,0x8dbc),'grade':(0x864e,0x8686),'building':(0x863e,0x864e),'flag':(0x860e,0x863e)},
'a':0x8dc8,'b':0x8e0a,'short':0x8e32,'deficit':0x8e5a,'mapping':0x2a2,'jobmap':0x2f4,'chain':0x8f86,'buildingbits':0x5dca},
'WIN':{'file':'COLONIZE.EXE','sha':'ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650',
'ranges':{'capacity':(0xbce7,0xbd1a),'surplus':(0xbf9d,0xbfec),'packed':(0xbfec,0xc039),'recipe':(0xbf43,0xbf9d),'wrapper':(0xbee9,0xbf43),'balance':(0xbe69,0xbee9),'net':(0xbddd,0xbe64),'job':(0xbdaf,0xbddd),'grade':(0xb408,0xb44a),'building':(0xb3e8,0xb408),'flag':(0xb3a3,0xb3e8)},
'a':0x122,'b':0x164,'short':0x18c,'deficit':0x1b4,'mapping':0xa6,'jobmap':0xf7,'chain':0xd320,'buildingbits':0x7ba6}}

def require_private_output(path):
 path=Path(path).expanduser().resolve()
 if any((parent/'.git').exists() for parent in (path,*path.parents)):
  raise ValueError('source-retaining output must be outside a Git checkout')
 return path

def build(private,out):
 out=require_private_output(out)
 out.mkdir(parents=True,exist_ok=False)
 m=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_16);m.detail=True
 records={}
 for edition,s in SPECS.items():
  data=(private/s['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==s['sha']
  selectors={}
  if edition=='WIN':
   for f in load_ne(data).metadata['ne']['fixups']:
    if f['source_segment_index']!=4:continue
    for src in f['sources']:
     selectors[src['file_offset']]=f
  assert data[(0x1d9a0+0x2a2+10) if edition=='DOS' else (303616+0xa6+10)]==2
  assert data[(0x1d9a0+0x2f4+10) if edition=='DOS' else (303616+0xf7+10)]==24
  targets={lo:n for n,(lo,hi) in s['ranges'].items()};chunks=[];fixes=[];receipts=[]
  for name,(lo,hi) in s['ranges'].items():
   raw=data[lo:hi];chunks.append(f'{name}_body:');count=0;callfix=[];selfix=[]
   for i in m.disasm(raw,lo):
    count+=i.size
    if i.mnemonic=='call':
     target=i.operands[0].imm
     if target not in targets:raise ValueError((edition,name,'missing call',hex(target)))
     assert bytes(i.bytes[:1])==b'\xe8' and i.size==3
     chunks.append(f'.byte 0xe8\n.word {targets[target]}_body - . - 2')
     callfix.append(dict(offset=i.address-lo,target=targets[target]))
    else:chunks.append('.byte '+','.join(hex(c) for c in i.bytes))
   assert count==len(raw),(edition,name,count,len(raw))
   for off,f in selectors.items():
    if not lo<=off<hi:continue
    assert f['target_kind']=='internal' and f['source_type']=='selector16' and f['target_segment_index'] in [19,20]
    fixes.append(f'mov word ptr cs:[{name}_body+{off-lo}],ax')
    selfix.append(dict(offset=off-lo,target_segment=f['target_segment_index']))
   receipts.append(dict(operation=name,file_range=[lo,hi],sha256=hashlib.sha256(raw).hexdigest(),instructions=len(list(m.disasm(raw,lo))),calls=callfix,selectors=selfix))
  def call(name):
   return ('mov ds,word ptr cs:[data_segment]\n' if edition=='DOS' else '')+f'push cs\ncall {name}_body\npush cs\npop ds\nmov es,word ptr [data_segment]\n'
  asm=f'''.code16
.intel_syntax noprefix
.global _start
_start:
 mov ax,cs
 mov ds,ax
 mov es,ax
 mov ss,ax
 mov sp,0xfff0
 mov bx,0x1000
 mov ah,0x4a
 int 0x21
 jc fail
 mov bx,0x1000
 mov ah,0x48
 int 0x21
 jc fail
 mov word ptr [data_segment],ax
 mov es,ax
 xor di,di
 xor ax,ax
 mov cx,0x8000
 cld
 rep stosw
 mov ax,word ptr [data_segment]
 {chr(10).join(fixes)}
 {'mov word ptr es:[0x8542],0xe000\n mov word ptr es:[0x8dc6],0' if edition=='DOS' else 'mov word ptr [0x484c],0xe000\n mov word ptr [0x484e],ax\n mov word ptr [0x4850],0'}
 mov byte ptr es:[{s['chain']+24*12}],25
 mov byte ptr es:[{s['chain']+25*12}],26
 mov byte ptr es:[{s['chain']+26*12}],0xff
 mov byte ptr es:[{s['jobmap']+10}],24
 mov byte ptr es:[{s['mapping']+10}],2
 mov dx,offset infile
 mov ax,0x3d00
 int 0x21
 jc fail
 mov word ptr [inh],ax
 mov dx,offset outfile
 xor cx,cx
 mov ah,0x3c
 int 0x21
 jc fail
 mov word ptr [outh],ax
next_case:
 push cs
 pop ds
 mov bx,word ptr [inh]
 mov cx,20
 mov dx,offset rec
 mov ah,0x3f
 int 0x21
 jc fail
 or ax,ax
 jz done
 cmp ax,20
 jne fail
 mov es,word ptr [data_segment]
 mov ax,word ptr [rec]
 mov word ptr [result],ax
 mov al,byte ptr [rec+2]
 mov byte ptr es:[0xe095],al
 {call('capacity')}
 mov word ptr [result+2],ax
 mov ax,word ptr [rec+4]
 mov word ptr es:[0xe09e],ax
 mov ax,word ptr [rec+6]
 mov word ptr es:[{s['a']+4}],ax
 mov ax,word ptr [rec+8]
 mov word ptr es:[{s['b']+4}],ax
 push 2
 {call('surplus')}
 add sp,2
 mov word ptr [result+4],ax
 mov al,byte ptr [rec+10]
 mov byte ptr es:[0xe01f],al
 mov bx,word ptr [rec+12]
 shr bx,1
 mov al,byte ptr [rec+14]
 mov byte ptr es:[bx+0xe060],al
 push word ptr [rec+12]
 {call('packed')}
 add sp,2
 mov word ptr [result+6],ax
 mov ax,word ptr [rec+16]
 mov word ptr es:[{s['a']+20}],ax
 mov word ptr es:[{s['b']+20}],0
 mov al,byte ptr [rec+18]
 mov byte ptr es:[{s['buildingbits']+3}],al
 # recipe(input_resource=2, output_resource=10); all original dependencies execute.
 push 10
 push 2
 {call('recipe')}
 add sp,4
 mov ax,word ptr es:[{s['b']+4}]
 mov word ptr [result+8],ax
 mov ax,word ptr es:[{s['short']+4}]
 mov word ptr [result+10],ax
 mov ax,word ptr es:[{s['deficit']+4}]
 mov word ptr [result+12],ax
 # Observe downstream net output with optional report suppressed.
 {'push 0' if edition=='WIN' else ''}
 push 0
 push 10
 {call('net')}
 add sp,{6 if edition=='WIN' else 4}
 mov word ptr [result+14],ax
 mov bx,word ptr [outh]
 mov dx,offset result
 mov cx,16
 mov ah,0x40
 int 0x21
 jc fail
 cmp ax,16
 jne fail
 jmp next_case
done:
 mov bx,word ptr [inh]
 mov ah,0x3e
 int 0x21
 mov bx,word ptr [outh]
 mov ah,0x3e
 int 0x21
 mov ax,0x4c00
 int 0x21
fail:
 mov ax,0x4c01
 int 0x21
infile:.asciz "NEWCASE.BIN"
outfile:.asciz "{edition}NEW.BIN"
inh:.word 0
outh:.word 0
data_segment:.word 0
rec:.fill 20,1,0
result:.fill 16,1,0
{chr(10).join(chunks)}
'''
  src=out/f'{edition}.s';src.write_text(asm)
  subprocess.run(['as','--32',str(src),'-o',str(out/f'{edition}.o')],check=True)
  subprocess.run(['ld','-m','elf_i386','-Ttext','0x100','--oformat','binary',str(out/f'{edition}.o'),'-o',str(out/f'{edition}.COM')],check=True)
  records[edition]=dict(source_sha256=s['sha'],blocks=receipts,harness_sha256=hashlib.sha256((out/f'{edition}.COM').read_bytes()).hexdigest())
 # The first six are interpretable branch discriminators. Others stress abstract admitted states.
 cases=[]
 def add(level,stock,supply,demand,count,index,packed,production,bits):cases.append([len(cases),level,stock,supply,demand,count,index,packed,production,bits])
 for stock,supply,production,bits in [(0,0,9,7),(0,3,9,7),(0,6,9,7),(0,0,9,3),(2,0,9,7),(0,0,10,7)]:add(1,stock,supply,2,8,1,0xa5,production,bits)
 for level in range(256):add(level,10,3,8,4,level%8,level,level,7)
 rng=random.Random(0xC0102030)
 for _ in range(2048):
  vals=[rng.randint(-32768,32767) for j in range(4)]
  add(rng.randrange(256),vals[0],vals[1],vals[2],rng.randint(-128,127),rng.randrange(32),rng.randrange(256),vals[3],rng.randrange(8))
 # All small production/supply combinations, with and without qualifying building chain.
 for production in range(16):
  for supply in range(16):
   for bits in [3,7]:add(2,0,supply,0,20,0,0x81,production,bits)
 (out/'NEWCASE.BIN').write_bytes(b''.join(struct.pack('<10H',*[x&65535 for x in row]) for row in cases))
 (out/'cases.json').write_text(json.dumps(cases))
 (out/'bindings.json').write_text(json.dumps(records,indent=2))
 return cases

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--private',type=Path,default=R/'private');ap.add_argument('--output',type=Path,default=R/'private/new_native');ap.add_argument('--backend',type=Path,required=True);a=ap.parse_args()
 cases=build(a.private,a.output)
 env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
 cmd=[str(a.backend.resolve()),'-defaultconf','-defaultmapper','-nogui','-c','cycles max','-c',f'mount c "{a.output.resolve()}"','-c','c:','-c','DOS.COM','-c','WIN.COM','-c','exit']
 p=subprocess.run(cmd,env=env,stdout=(R/'new_native.log').open('w'),stderr=subprocess.STDOUT,timeout=40)
 print('native process',p.returncode,'cases',len(cases))
 for e in SPECS:
  out=(a.output/f'{e}NEW.BIN').read_bytes();print(e,len(out));assert len(out)==len(cases)*16
  print(list(struct.iter_unpack('<8H',out))[:6])
