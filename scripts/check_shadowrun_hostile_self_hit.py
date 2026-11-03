#!/usr/bin/env python3
"""Compare prepared item10 self-contact from two consecutive original frames."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_self_hit import SOURCE,lift_hostile_self_hit
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();rec=json.loads(rr);author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or rec['rom_sha256']!=ROM_SHA256 or rec['core_sha256']!=CORE or not rec['patches'] or any(x['frame']!=6000 for x in rec['patches']):raise ValueError('source or assisted capture mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 b=frame(6029);after=frame(6030);actor=b[0x400:0x500];pr=b[0xb00:0xc00]
 if (w(actor,14),actor[0x10],actor[0x4c],actor[0x4d],actor[0x76],actor[0x77],actor[0x78],actor[0x7b],actor[0x7c],actor[0x9b],pr[0x57],pr[0x9f],w(b,0xf9f8))!=(8,5,10,2,3,5,5,4,3,2,10,1,52645):raise ValueError('prepared actor/projectile mismatch')
 cases=[]
 for hp in (1,10):
  for effect in (0,1,4,7):
   for seed in (17,52645):
    for timer in (0,4):
     low=bytearray(b[0x100:0x1100]);t=0x300;q=0xa00
     low[t:t+2]=after[0x400:0x402];low[t+4:t+6]=after[0x404:0x406];low[t+0x4c]=hp;low[q+0x9f]=effect
     g=bytearray(b[0xf000:0xfe00]);g[0x9f8:0x9fa]=seed.to_bytes(2,'big');g[0xce]=timer
     cases.append({'name':f'{hp}-{effect}-{seed}-{timer}','registers':{'A0':0xff0b00},'ram':[{'address':0xff0100,'data':low.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe000].hex()},{'address':0xffef00,'data':b[0xef00:0xf000].hex()},{'address':0xfff000,'data':g.hex()}]})
 spans=[(0x14e0a,0x14edc),(0x14f26,0x14f86),(0x15aba,0x15bb4),(0xe7c8,0xe9cc),(0x55948,0x55b16),(0x55e62,0x55f44),(0x55786,0x55848),(0xd3a,0xdfc)]
 contract={'name':'prepared-hostile-self-contact','entry':0x14e0a,'code_ranges':[{'start':x,'end':y} for x,y in spans], 'stop_pcs':[0x14e60,0x14e8a,0x14e30,0x14eda],'stack_scratch_bytes':128,'max_instructions':2000,'watch':[{'name':'actors','address':0xff0100,'length':4096},{'name':'global_a','address':0xffdd00,'length':768},{'name':'global_b','address':0xffef00,'length':256},{'name':'global_c','address':0xfff000,'length':3584}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 prog=lift_hostile_self_hit(rom);m=GameMachine(prog,{0:rom});actual_match=False
 for inp,n in zip(cases,r['cases']):
  hp,effect,seed,timer=map(int,inp['name'].split('-'));pc=n['registers_after']['PC']
  if pc!=(0x14e60 if not effect else 0x14e8a):raise AssertionError(('miss',inp['name'],hex(pc)))
  m.set_state({'shadowrun_selfhit_profile':1,'shadowrun_selfhit_hp':hp,'shadowrun_selfhit_effect':effect,'shadowrun_selfhit_rng':seed,'shadowrun_selfhit_death_timer':timer,'shadowrun_selfhit_party_a':b[0x18d],'shadowrun_selfhit_party_b':b[0x28d],'shadowrun_selfhit_party_c':b[0x38d]});m.call('shadowrun_hostile_self_hit');s=m.snapshot()
  actors=bytes.fromhex(n['ram_after']['actors']);g=bytes.fromhex(n['ram_after']['global_c']);got=tuple(s[k] for k in ('shadowrun_selfhit_hp','shadowrun_selfhit_rng','shadowrun_selfhit_death_timer','shadowrun_selfhit_party_a','shadowrun_selfhit_party_b','shadowrun_selfhit_party_c'));expected=(actors[0x34c],w(g,0x9f8),g[0xce],actors[0x8d],actors[0x18d],actors[0x28d])
  if not s['shadowrun_selfhit_supported'] or got!=expected:raise AssertionError((inp['name'],got,expected))
  if hp==10 and effect==1 and seed==52645 and timer==b[0xf0ce]:
   if (expected[0],expected[1])!=(after[0x44c],w(after,0xf9f8)):raise AssertionError('consecutive capture mismatch')
   actual_match=True
 if not actual_match:raise AssertionError('no actual-frame matching case')
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','cases':len(cases),'actual_frame_transition_matched':actual_match,'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'trace_sha256':r['trace_sha256'],'scope':'prepared item10 projectile self-contact; target position taken from following frame; controlled HP/effect/RNG/timer; item3 armor, actor reaction excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
