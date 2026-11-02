#!/usr/bin/env python3
"""Compile assisted captured-actor hit/depletion cases for NES and compare.

This diagnostic uses a captured actor relocated onto an existing projectile.
It is not an ordinary encounter or a playable target-linked shot.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from fdisbull.game_il import GameMachine,canonical,emit_c
from fdisbull.shadowrun_field_combat import lift_field_motion
from check_shadowrun_system_nes import compare

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','core','cc65-root','source-run','original','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();rom=a.rom.read_bytes();core=a.core.read_bytes();program=lift_field_motion(rom)
 if sha(core)!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60':raise ValueError('wrong NES core')
 summary_raw=(a.original/'summary.json').read_bytes();summary=json.loads(summary_raw);receipt_raw=(a.original/'native/receipt.json').read_bytes();receipt=json.loads(receipt_raw)
 if (summary.get('status')!='passed' or summary.get('cases')!=36 or summary.get('rom_sha256')!=sha(rom) or summary.get('program_sha256')!=sha(canonical(program)) or not receipt['complete'] or not receipt['inputs_unchanged'] or receipt['trace_sha256']!=summary['trace_sha256'] or len(receipt['cases'])!=36):raise ValueError('original qualification mismatch')
 cap=json.loads((a.source_run/'capture.json').read_text());raw=(a.source_run/'native/scene-006037/ram.bin').read_bytes()
 if sha(raw)!=summary['source_ram_sha256'] or cap['files']['native/scene-006037/ram.bin']['sha256']!=sha(raw):raise ValueError('source capture mismatch')
 b=bytes(raw[i^1] for i in range(65536));w=lambda x:int.from_bytes(b[x:x+2],'big');terrain=list(b[0x1700:0x2200]);proj=b[0xb00:0xc00]
 states=[];original=[]
 watch=['shadowrun_field_motion_y_fixed','shadowrun_field_motion_lifetime','shadowrun_field_target_hp','shadowrun_field_rng','shadowrun_field_death_timer','shadowrun_field_type13_deaths','shadowrun_field_party_counter_a','shadowrun_field_party_counter_b','shadowrun_field_party_counter_c','shadowrun_field_supported','shadowrun_field_motion_state']
 for case in receipt['cases']:
  hp,timer,deaths,override,shot=map(int,case['contract']['name'].split('-'))
  states.append({'shadowrun_field_captured_profile':1,'shadowrun_field_path_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,'shadowrun_field_slots_busy':0,'shadowrun_field_target_flags':0x25,'shadowrun_field_target_flags_b0':0,'shadowrun_field_target_flags_9e':0x20,'shadowrun_field_target_flags_9a':override,'shadowrun_field_target_type':19,'shadowrun_field_target_defense_bonus':2,'shadowrun_field_death_timer':timer,'shadowrun_field_type13_deaths':deaths,'shadowrun_field_party_counter_a':254,'shadowrun_field_party_counter_b':255,'shadowrun_field_party_counter_c':0,'shadowrun_field_target_x':0x3ce0,'shadowrun_field_target_y':0x2e59,'shadowrun_field_target_hp':hp,'shadowrun_field_target_a':1,'shadowrun_field_target_b':2,'shadowrun_field_target_c':2,'shadowrun_field_target_posture':2,'shadowrun_field_source_effect':shot,'shadowrun_field_rng':w(0xf9f8),'shadowrun_field_motion_state':1,'shadowrun_field_motion_steps':4,'shadowrun_field_motion_lifetime':proj[0x89],'shadowrun_field_motion_y_fixed':int.from_bytes(proj[4:8],'big'),'shadowrun_x_max':w(0xddd2),'shadowrun_y_max':w(0xddd4),'shadowrun_x_min':w(0xddd6),'shadowrun_y_min':w(0xddd8),'shadowrun_rect_base':0x172daa})
  pr=bytes.fromhex(case['ram_after']['projectile']);tar=bytes.fromhex(case['ram_after']['target']);g=bytes.fromhex(case['ram_after']['global_c'])
  original.append([int.from_bytes(pr[4:8],'big'),pr[0x89],tar[0x4c],int.from_bytes(g[0x9f8:0x9fa],'big'),g[0xce],g[0xbfa],int(case['ram_after']['counter_a'],16),int(case['ram_after']['counter_b'],16),int(case['ram_after']['counter_c'],16),1,2])
 m=GameMachine(program,{0:rom});baseline=m.snapshot();baseline['shadowrun_terrain_map']=terrain;expected=[]
 for state,want in zip(states,original):
  m.set_state(baseline);m.set_state(state);m.call('shadowrun_field_captured_tick');snap=m.snapshot();got=[snap[k] for k in watch]
  if got!=want:raise ValueError('current GameIL differs from original qualification')
  expected.append(dict(zip(watch,got)))
 watch.append('diagnostic_rom_fault')
 for row in expected:row['diagnostic_rom_fault']=0
 out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 out.mkdir(mode=0o700,parents=True)
 rect=rom[0x172daa:0x172eea]
 lines=['typedef unsigned char u8;typedef unsigned int u16;typedef unsigned long u32;', 'static const u8 rect[320]={'+','.join(map(str,rect))+'};',
 'u8 diagnostic_rom_fault;u16 rom16(u8 region,u32 at){u16 i;if(region || at<0x172daaUL || at>=0x172ee9UL){diagnostic_rom_fault=1;return 0;}i=(u16)(at-0x172daaUL);return ((u16)rect[i]<<8)|rect[i+1];}',emit_c(program),
 'static const u8 terrain[2816]={'+','.join(map(str,terrain))+'};', '#define PUB ((volatile u8*)0x0700)', '#define STATUS (*(volatile u8*)0x2002)', 'static void wait_frame(void){while(STATUS&128U){}while(!(STATUS&128U)){} }']
 for key in states[0]:
  bits,signed=m.global_types[key];ctype=('signed ' if signed else 'unsigned ')+{8:'char',16:'int',32:'long'}[bits]
  lines.append(f'static const {ctype} case_{key}[{len(states)}]={{'+','.join(str(s[key])+'UL' for s in states)+'};')
 lines+=['void main(void){u16 i,j;u32 value;*(volatile u8*)0x2000=0;*(volatile u8*)0x2001=0;PUB[0]=0;PUB[1]=0;PUB[2]=0;PUB[3]=0;',
 'for(j=0;j<2816;j++)shadowrun_terrain_map[j]=terrain[j];',f'for(i=0;i<{len(states)}U;i++){{','wait_frame();PUB[0]++;diagnostic_rom_fault=0;']
 for key,value in baseline.items():
  if not isinstance(value,list):lines.append(f'{key}={value}UL;')
  elif key!='shadowrun_terrain_map':
   lines.append(f'for(j=0;j<{len(value)}U;j++){key}[j]=0;')
 for key in states[0]:lines.append(f'{key}=case_{key}[i];')
 lines+=['shadowrun_field_captured_tick();','PUB[1]=(u8)i;PUB[2]=(u8)(i>>8);']
 for i,key in enumerate(watch):
  lines.append(f'value=(u32){key};')
  for j in range(4):lines.append(f'PUB[{4+i*4+j}]=(u8)(value>>{j*8});')
 lines+=['PUB[3]=0x53;PUB[0]++;}','PUB[3]=0x57;for(;;){}}']
 (out/'check.c').write_text('\n'.join(lines));root=a.cc65_root.resolve();env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
 cmd=[str(root/'bin/cl65'),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),'--lib-path',str(root/'lib'),'-I',str(root/'include'),'-o','check.nes','check.c']
 q=subprocess.run(cmd,cwd=out,env=env,text=True,capture_output=True,timeout=120);(out/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError(q.stderr[-3000:])
 image=(out/'check.nes').read_bytes();(out/'watch.json').write_text(json.dumps([{'name':'publication','offset':1792,'length':4+4*len(watch)}]))
 q=subprocess.run([sys.executable,str(ROOT/'scripts/check_console_udc.py'),'--core',str(a.core),'--rom',str(out/'check.nes'),'--system','nes','--frames','600','--watch',str(out/'watch.json'),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-3000:])
 nr=json.loads((out/'native/receipt.json').read_text());trace=(out/'native/ram_trace.json').read_bytes()
 if nr['rom_sha256']!=sha(image) or nr['core_sha256']!=sha(core) or nr['ram_trace_sha256']!=sha(trace) or nr['patches']:raise ValueError('NES provenance mismatch')
 result=compare(json.loads(trace),{'watch':watch,'reference_results':expected});result.update({'format':'fdisbull-shadowrun-field-actor-nes-1','program_sha256':sha(canonical(program)),'nes_sha256':sha(image),'nes_trace_sha256':sha(trace),'original_summary_sha256':sha(summary_raw),'scope':'assisted captured actor relocated to projectile, zero-effect and damage/depletion; not ordinary acquisition'})
 (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
