#!/usr/bin/env python3
"""Compare captured actor movement service against controlled original CPU."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_move import SOURCE,lift_enemy_move
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run).resolve();capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);receipt=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or receipt['patches'] or receipt['memory_injection_mode']!='no memory patches':raise ValueError('source identity or patch mismatch')
 cases=[];inputs=[]
 for frame in (6389,6390):
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes();meta=cap['files'][rel]
  if len(raw)!=65536 or meta['sha256']!=sha(raw):raise ValueError('captured RAM mismatch')
  b=bytes(raw[i^1] for i in range(65536));glob=b[0xdd00:0xe200]
  for index in (1,):
   actor=b[0x400+index*256:0x500+index*256];w=lambda n:int.from_bytes(actor[n:n+2],'big');l=lambda n:int.from_bytes(actor[n:n+4],'big')
   if w(14)!=11 or l(0x3a)!=0xb574 or actor[0x10]!=0x25 or not actor[0x9e]&32 or actor[0xb0]&128 or actor[0x78]!=1 or int.from_bytes(b[0xdf84:0xdf86],'big') not in (0,65535):continue
   cases.append({'name':f'{frame}-{index}','registers':{'A0':0xff0400},'ram':[{'address':0xff0400,'data':actor.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':glob.hex()},{'address':0xffef10,'data':b[0xef10:0xef14].hex()}]});inputs.append((frame,index,b,actor))
 if not cases:raise ValueError('no admitted captured actor states')
 contract={'name':'captured-actor-clear-move','entry':0xb574,
  'code_ranges':[{'start':0xb530,'end':0xb732},{'start':0xb732,'end':0xb7f0},{'start':0xbade,'end':0xbbf6},{'start':0xb48c,'end':0xb49c},{'start':0xe7c8,'end':0xeb4e},{'start':0xedfa,'end':0xee10}],
  'stop_pcs':[0xb6e2,0xb442],'stack_scratch_bytes':128,'max_instructions':1000,
  'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'globals','address':0xffdd00,'length':1280},{'name':'corners','address':0xffef10,'length':4}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(cases):raise AssertionError('incomplete native comparison')
 for v in r['cases']:
  x=bytes.fromhex(v['ram_after']['actor']);w=lambda n:int.from_bytes(x[n:n+2],'big');print(hex(v['registers_after']['PC']), w(0),w(4),hex(w(0x2e)),hex(w(0x34)),hex(w(0x36)),x[0x11],hex(w(0xb8)),hex(w(0x16)))
if __name__=='__main__':main()
