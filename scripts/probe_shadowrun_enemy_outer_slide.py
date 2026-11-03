#!/usr/bin/env python3
"""Native comparisons for the bounded captured actor-loop prefix."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_outer import SOURCE,lift_enemy_outer
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def word(b,n):return int.from_bytes(b[n:n+2],'big')
def long(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for x in ('rom','core','run','output'):p.add_argument('--'+x,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);receipt=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['patches'] or receipt['memory_injection_mode']!='no memory patches':raise ValueError('capture or source mismatch')
 cases=[];inputs=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  b=bytes(raw[i^1] for i in range(65536))
  for index in range(3):
   original=b[0x400+index*256:0x500+index*256]
   if word(original,14)!=11 or original[0x10]!=37 or long(original,0x3a) not in (0xb574,0xb45c) or not (original[0x11]&4) or not original[0x4c] or not original[0x9c] or word(original,0x16)&0x8000:continue
   for selected,d0,animation in ((0,0,None),):
    actor=bytearray(original);actor[0x11]=(actor[0x11]&~16)|selected
    if animation is not None: actor[0x16:0x18]=animation.to_bytes(2,'big')
    cases.append({'name':f'{frame}-{index}-{selected}-{d0}-{animation}','registers':{'A0':0xff0400,'D0':d0,'D7':0},'ram':[{'address':0xff0400,'data':actor.hex()}]});inputs.append((frame,index,d0,bytes(actor)))
 contract={'name':'captured-actor-loop-prefix','entry':0xa8fa,'code_ranges':[{'start':0xa8fa,'end':0xaa76},{'start':0x15bb4,'end':0x15bb6}], 'stop_pcs':[0xaa70,0xaa74,0xaa4c,0xab02,0xa9a6], 'stack_scratch_bytes':128,'max_instructions':250,'watch':[{'name':'actor','address':0xff0400,'length':256}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract))
 q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 for row in r['cases']:
  print(hex(row['registers_after']['PC']))
  after=bytes.fromhex(row['ram_after']['actor'])
  print('timer',word(after,0xdc),'flags',after[0x11])
if __name__=='__main__':main()
