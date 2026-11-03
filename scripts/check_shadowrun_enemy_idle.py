#!/usr/bin/env python3
"""Compare captured actor movement service against controlled original CPU."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_idle import SOURCE,lift_enemy_idle
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run).resolve();capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);receipt=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or receipt['patches'] or receipt['memory_injection_mode']!='no memory patches':raise ValueError('source identity or patch mismatch')
 cases=[];inputs=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes();meta=cap['files'][rel]
  if len(raw)!=65536 or meta['sha256']!=sha(raw):raise ValueError('captured RAM mismatch')
  b=bytes(raw[i^1] for i in range(65536));glob=b[0xdd00:0xe200]
  for index in range(3):
   actor=b[0x400+index*256:0x500+index*256];w=lambda n:int.from_bytes(actor[n:n+2],'big');l=lambda n:int.from_bytes(actor[n:n+4],'big')
   if w(14)!=11 or l(0x3a)!=0xb45c or actor[0x10]!=0x25 or not actor[0x9e]&32 or actor[0xb0]&128 or actor[0x78]!=1 or int.from_bytes(b[0xdf84:0xdf86],'big') not in (0,65535):continue
   cases.append({'name':f'{frame}-{index}','registers':{'A0':0xff0400},'ram':[{'address':0xff0400,'data':actor.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':glob.hex()},{'address':0xffef10,'data':b[0xef10:0xef14].hex()}]});inputs.append((frame,index,b,actor))
 if not cases:raise ValueError('no admitted captured actor states')
 contract={'name':'captured-actor-clear-move','entry':0xb45c,
  'code_ranges':[{'start':0xb45c,'end':0xb49c},{'start':0xe7c8,'end':0xeb4e},{'start':0xedfa,'end':0xee10}],
  'stop_pcs':[0xb48a],'stack_scratch_bytes':128,'max_instructions':1000,
  'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'globals','address':0xffdd00,'length':1280},{'name':'corners','address':0xffef10,'length':4}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(cases):raise AssertionError('incomplete native comparison')
 program=lift_enemy_idle(rom);m=GameMachine(program,{0:rom});passed=0;refused=0
 for (frame,index,b,actor),native in zip(inputs,r['cases']):
  w=lambda n:int.from_bytes(actor[n:n+2],'big');glob=lambda n:int.from_bytes(b[n:n+2],'big');l=lambda n:int.from_bytes(actor[n:n+4],'big')
  m.set_state({'shadowrun_ai_x':w(0),'shadowrun_ai_y':w(4),'shadowrun_ai_heading':w(0x2e),'shadowrun_ai_target_heading':w(0x34),'shadowrun_ai_transition_heading':w(0x36),'shadowrun_ai_kind':w(0xe),'shadowrun_ai_distance':w(0xc8),'shadowrun_ai_move_state':w(0x38),'shadowrun_ai_collision_state':w(0xb8),'shadowrun_ai_speed':w(0xca),'shadowrun_ai_animation':w(0x16),'shadowrun_ai_callback':l(0x3a),'shadowrun_ai_flags':actor[0x10],'shadowrun_ai_flags_low':actor[0x11],'shadowrun_ai_equipment_flags':actor[0x9e],'shadowrun_ai_event_flags':actor[0xb0],'shadowrun_ai_attribute':actor[0x78],'shadowrun_ai_combat_global':glob(0xdf84),'shadowrun_ai_corners':list(actor[0xd0:0xd4]),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':glob(0xddd2),'shadowrun_y_max':glob(0xddd4),'shadowrun_x_min':glob(0xddd6),'shadowrun_y_min':glob(0xddd8),'shadowrun_rect_base':int.from_bytes(b[0xddec:0xddf0],'big'),'shadowrun_probe_corners':list(b[0xef10:0xef14])})
  m.call('shadowrun_ai_idle_tick');s=m.snapshot();pc=native['registers_after']['PC']
  if not s['shadowrun_ai_idle_supported']:
   refused+=1
   if pc==0xb48a:raise AssertionError(('unexpected refusal',frame,index))
   continue
  if pc!=0xb48a:raise AssertionError(('model accepted fallback',frame,index,hex(pc)))
  outactor=bytes.fromhex(native['ram_after']['actor']);v=lambda n:int.from_bytes(outactor[n:n+2],'big');
  got=tuple(s[k] for k in ('shadowrun_ai_x','shadowrun_ai_y','shadowrun_ai_heading','shadowrun_ai_move_state','shadowrun_ai_collision_state','shadowrun_ai_speed','shadowrun_ai_animation','shadowrun_ai_event_flags','shadowrun_ai_corners'))
  expected=(v(0),v(4),v(0x2e),v(0x38),v(0xb8),v(0xca),v(0x16),outactor[0xb0],list(outactor[0xd0:0xd4]))
  if got!=expected:raise AssertionError((frame,index,got,expected))
  passed+=1
 if SOURCE.read_bytes()!=author:raise ValueError('authoring changed')
 summary={'status':'passed','source_states':len(cases),'clear_matched':passed,'fallback_refused':refused,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(program)),'trace_sha256':r['trace_sha256'],'scope':'controlled captured actor B45C idle callback; decision and attack dispatch excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
