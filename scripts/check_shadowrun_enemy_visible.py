#!/usr/bin/env python3
"""Controlled original contact-visible movement service comparison."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_visible import SOURCE,lift_enemy_visible
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);rc=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or rc['patches'] or rc['memory_injection_mode']!='no memory patches':raise ValueError('identity or capture patches')
 cases=[];inputs=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or cap['files'][rel]['sha256']!=sha(raw):raise ValueError('RAM mismatch')
  base=bytes(raw[i^1] for i in range(65536));actor=base[0x400:0x500]
  if w(actor,14)!=11 or actor[0x10]!=37 or not w(actor,0xc):continue
  for forced in (False,True):
   b=bytearray(base)
   if forced:b[0x4b6:0x4b8]=b'\0\0'
   spans=[(0x100,0x1100),(0x1100,0x2100),(0x2100,0x2200),(0xdd00,0xe200),(0xef10,0xef14),(0xf000,0xfd00)]
   cases.append({'name':f'{frame}-{int(forced)}','registers':{'A0':0xff0400},'ram':[{'address':0xff0000+x,'data':b[x:y].hex()} for x,y in spans]});inputs.append((frame,forced,bytes(b)))
 contract={'name':'contact-visible-service','entry':0x13904,'code_ranges':[{'start':x,'end':y} for x,y in [(0xe7c8,0xee10),(0x13904,0x13a00),(0x13ef4,0x13ffe),(0x142ae,0x14312),(0x144e8,0x14640),(0x14d8e,0x14e0a),(0x14f26,0x151da),(0x15aba,0x15bc0),(0x15ca4,0x15dcc)]], 'stop_pcs':[0x1390c,0x13918,0x142ce,0x13e9e,0x1461c,0x145ae,0x149c0,0x14c2a,0x1460c,0x13e56,0x13e4c], 'stack_scratch_bytes':256,'max_instructions':10000,'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'other_low','address':0xff0100,'length':768},{'name':'other_mid','address':0xff0500,'length':4096},{'name':'other_map','address':0xff1500,'length':4096},{'name':'globals','address':0xffdd00,'length':1280},{'name':'terrain_scratch','address':0xffef10,'length':4},{'name':'high','address':0xfff000,'length':3328}], 'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 prog=lift_enemy_visible(rom);m=GameMachine(prog,{0:rom});passed=refused=0;branches={}
 for (frame,forced,b),native in zip(inputs,r['cases']):
  actor=b[0x400:0x500];ww=lambda n:w(actor,n)
  m.set_state({'shadowrun_ai_x':ww(0),'shadowrun_ai_y':ww(4),'shadowrun_ai_heading':ww(0x2e),'shadowrun_ai_target_heading':ww(0x34),'shadowrun_ai_kind':ww(0xe),'shadowrun_ai_distance':ww(0xc8),'shadowrun_ai_collision_state':ww(0xb8),'shadowrun_ai_animation':ww(0x16),'shadowrun_ai_callback':l(actor,0x3a),'shadowrun_ai_flags':actor[0x10],'shadowrun_ai_equipment_flags':actor[0x9e],'shadowrun_ai_event_flags':actor[0xb0],'shadowrun_ai_combat_global':w(b,0xdf84),'shadowrun_ai_service_timer':ww(0xb6),'shadowrun_ai_service_contact':ww(0xc),'shadowrun_ai_waypoint_x':ww(0x96),'shadowrun_ai_waypoint_y':ww(0x98),'shadowrun_ai_service_direction':actor[0xb1],'shadowrun_ai_service_pause':b[0xe175], 'shadowrun_ai_visible_player_x':w(b,0x100),'shadowrun_ai_visible_player_y':w(b,0x104),'shadowrun_ai_visible_class':actor[0x4d],'shadowrun_ai_visible_alert':b[0xe16f]})
  m.call('shadowrun_ai_visible_service');s=m.snapshot();pc=native['registers_after']['PC']
  if not s['shadowrun_ai_visible_supported']:refused+=1;continue
  if pc not in (0x1460c,0x145ae):raise AssertionError((frame,forced,hex(pc)))
  after=bytes.fromhex(native['ram_after']['actor']);got=tuple(s[k] for k in ('shadowrun_ai_service_timer','shadowrun_ai_target_heading','shadowrun_ai_distance','shadowrun_ai_callback','shadowrun_ai_event_flags','shadowrun_ai_service_direction','shadowrun_ai_equipment_flags'))
  expected=(w(after,0xb6),w(after,0x34),w(after,0xc8),l(after,0x3a),after[0xb0],after[0xb1],after[0x9e])
  if got!=expected:raise AssertionError((frame,forced,got,expected))
  passed+=1;branches[hex(pc)]=branches.get(hex(pc),0)+1
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','source_states':len(cases),'matched':passed,'refused':refused,'matched_terminal_pcs':branches,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'trace_sha256':r['trace_sha256'],'scope':'contact-visible facing-away actor service projection; scratch/LOS effects excluded; includes forced timer expiry'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
