#!/usr/bin/env python3
"""Compare prepared hostile B574 movement with original CPU."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_move import SOURCE,lift_hostile_move
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','baseline','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.baseline);rcraw=(root/'receipt.json').read_bytes();rc=json.loads(rcraw);base=(root/'ram-after.bin').read_bytes();author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or not rc['complete'] or not rc['inputs_unchanged'] or rc['source_sha256']!=ROM_SHA256 or rc['core_sha256']!=CORE or len(base)!=65536 or sha(base)!=rc['cases'][0]['ram_after_sha256']:raise ValueError('identity or prepared receipt mismatch')
 cases=[];inputs=[]
 for heading in (0,0x4000,0x8000,0xc000):
  for distance in (0x80,0x180,0x280,0x400,0x645):
   b=bytearray(base);actor=bytearray(b[0x400:0x500]);actor[0x2e:0x30]=heading.to_bytes(2,'big');actor[0xc8:0xca]=distance.to_bytes(2,'big');b[0x400:0x500]=actor
   cases.append({'name':f'{heading}-{distance}','registers':{'A0':0xff0400},'ram':[{'address':0xff0400,'data':actor.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe200].hex()},{'address':0xffef10,'data':b[0xef10:0xef14].hex()}]});inputs.append((heading,distance,bytes(b),bytes(actor)))
 contract={'name':'prepared-hostile-movement','entry':0xb574,'code_ranges':[{'start':x,'end':y} for x,y in [(0xb530,0xb732),(0xb77e,0xb7b8),(0xbade,0xbb0a),(0xbbe4,0xbbf6),(0xb48c,0xb49c),(0xe7c8,0xeb4e),(0xedfa,0xee10)]], 'stop_pcs':[0xb6e2,0xbaf8,0xb442],'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'globals','address':0xffdd00,'length':1280},{'name':'corners','address':0xffef10,'length':4}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 prog=lift_hostile_move(rom);m=GameMachine(prog,{0:rom});passed=refused=0
 for (heading,distance,b,actor),native in zip(inputs,r['cases']):
  ww=lambda n:w(actor,n);glob=lambda n:w(b,n)
  m.set_state({'shadowrun_ai_x':ww(0),'shadowrun_ai_y':ww(4),'shadowrun_ai_heading':ww(0x2e),'shadowrun_ai_target_heading':ww(0x34),'shadowrun_ai_transition_heading':ww(0x36),'shadowrun_ai_kind':ww(0xe),'shadowrun_ai_distance':ww(0xc8),'shadowrun_ai_move_state':ww(0x38),'shadowrun_ai_collision_state':ww(0xb8),'shadowrun_ai_speed':ww(0xca),'shadowrun_ai_animation':ww(0x16),'shadowrun_ai_callback':l(actor,0x3a),'shadowrun_ai_flags':actor[0x10],'shadowrun_ai_flags_low':actor[0x11],'shadowrun_ai_equipment_flags':actor[0x9e],'shadowrun_ai_event_flags':actor[0xb0],'shadowrun_ai_attribute':actor[0x78],'shadowrun_ai_combat_global':glob(0xdf84),'shadowrun_ai_corners':list(actor[0xd0:0xd4]),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':glob(0xddd2),'shadowrun_y_max':glob(0xddd4),'shadowrun_x_min':glob(0xddd6),'shadowrun_y_min':glob(0xddd8),'shadowrun_rect_base':l(b,0xddec),'shadowrun_probe_corners':list(b[0xef10:0xef14])})
  m.call('shadowrun_hostile_move_tick');s=m.snapshot();pc=native['registers_after']['PC']
  if not s['shadowrun_hostile_move_supported']:
   refused+=1
   if pc==0xb6e2:raise AssertionError(('unexpected refusal',heading,distance))
   continue
  if pc!=0xb6e2:raise AssertionError(('accepted fallback',heading,distance,hex(pc)))
  af=bytes.fromhex(native['ram_after']['actor']);got=tuple(s[k] for k in ('shadowrun_ai_x','shadowrun_ai_y','shadowrun_ai_heading','shadowrun_ai_move_state','shadowrun_ai_collision_state','shadowrun_ai_speed','shadowrun_ai_animation','shadowrun_ai_event_flags','shadowrun_ai_corners'))
  expected=(w(af,0),w(af,4),w(af,0x2e),w(af,0x38),w(af,0xb8),w(af,0xca),w(af,0x16),af[0xb0],list(af[0xd0:0xd4]))
  if got!=expected:raise AssertionError((heading,distance,got,expected))
  passed+=1
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','source_states':len(cases),'clear_matched':passed,'fallback_refused':refused,'rom_sha256':sha(rom),'core_sha256':sha(core),'prepared_receipt_sha256':sha(rcraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'trace_sha256':r['trace_sha256'],'scope':'prepared kind8 attribute5 combat movement; controlled headings/distances, collision fallback refused'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
