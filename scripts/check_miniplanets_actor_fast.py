#!/usr/bin/env python3
"""Qualify actor intrinsics on sim6502 against reviewed C, UIL and original CPU receipts.

Original ROM/table/vector bytes stay in a new private output directory. The
C baseline retains the reviewed procedure bodies; only test call names and
read-only handler-order observers are substituted. Native mapper integration
and full-game speed are separate, unchanged acceptance gates.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine,canonical
from fdisbull.udl_miniplanets_full import lift_full_game
from check_miniplanets_game_fast import extract,array,ROM_SHA256
from check_miniplanets_native import _private_output
from check_miniplanets_nes_game import encode_state
GENESIS_SHA='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
HANDLERS=('run_key','run_raft','run_mace','run_bomb','run_switch','run_electricity','run_ball','run_orb','run_fireball','run_child','run_bomb_fx','run_spring_fx')
MAPPING=(None,'run_key',*(['run_raft']*4),*(['run_mace']*2),'run_bomb','run_switch',*(['run_electricity']*2),*(['run_ball']*4),*(['run_orb']*4),*(['run_fireball']*4),'run_key','run_child','run_bomb_fx','run_spring_fx')
HELPERS=('play_sfx','rand16','get_tile','get_collision','set_tile','collides_player','hurt_player','win_stage','update_subpixel')
sha=lambda raw:hashlib.sha256(raw).hexdigest()

HARNESS=r'''
#include <stdio.h>
#include <string.h>
#include <sim65.h>
DECLARATIONS
u8 reference_state[STATE_SIZE],native_state[STATE_SIZE],before_state[STATE_SIZE];
u8 reference_trace[96],actor_trace[96];u16 actor_trace_len,reference_trace_len;
u16 hv_tape[256],hv_count,hv_cursor,reference_hv;
u8 harness_fault;
TABLES
u8 rom8(u8 region,u32 offset){if(region!=0||offset<0xA514UL||offset>=0xA614UL){harness_fault=1;return 0;}return native_collision[(u16)(offset-0xA514UL)];}
u16 rom16(u8 region,u32 offset){u16 p;if(region!=0||offset<0x658F8UL||offset>=0x65B87UL){harness_fault=1;return 0;}p=(u16)(offset-0x658F8UL);return((u16)source_sine[p]<<8)|source_sine[p+1];}
u16 hv16(void){if(hv_cursor>=hv_count){harness_fault=2;return 0;}return hv_tape[hv_cursor++];}
void trace_call(u8 kind,u8 slot){if(actor_trace_len>=48){harness_fault=3;return;}actor_trace[actor_trace_len*2]=kind;actor_trace[actor_trace_len*2+1]=slot;actor_trace_len++;}
PROTOTYPES
BODIES
WRAPPERS
SERIALIZERS
static u32 cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
int main(void){u8 command[4],slot,entry;u16 i,sp_before;u32 count,start,baseline_cycles,native_cycles;count=0;
 while(fread(command,1,4,stdin)==4){entry=command[0];slot=command[1];hv_count=command[2]|((u16)command[3]<<8);if(hv_count>256)return 10;
  if(fread(before_state,1,STATE_SIZE,stdin)!=STATE_SIZE)return 11;
  for(i=0;i<hv_count;i=i+1){u8 b[2];if(fread(b,1,2,stdin)!=2)return 12;hv_tape[i]=b[0]|((u16)b[1]<<8);}
  restore_state(before_state);hv_cursor=0;actor_trace_len=0;harness_fault=0;
  sp_before=stack_pointer();start=cycles();if(entry==0)reference_run_objects();else reference_run_fireball(slot);baseline_cycles=cycles()-start;
  if(!same_stack(sp_before)||harness_fault){fprintf(stderr,"reference fault case%lu code%u\n",count,harness_fault);return 13;}
  capture_state(reference_state);reference_hv=hv_cursor;reference_trace_len=actor_trace_len;memcpy(reference_trace,actor_trace,96);
  restore_state(before_state);hv_cursor=0;actor_trace_len=0;harness_fault=0;
  sp_before=stack_pointer();start=cycles();if(entry==0)run_objects();else run_fireball(slot);native_cycles=cycles()-start;
  if(!same_stack(sp_before)||harness_fault){fprintf(stderr,"native fault case%lu code%u\n",count,harness_fault);return 14;}
  capture_state(native_state);
  if(memcmp(reference_state,native_state,STATE_SIZE)){for(i=0;i<STATE_SIZE;i=i+1)if(reference_state[i]!=native_state[i]){fprintf(stderr,"state mismatch case%lu byte%u expected%u actual%u\n",count,i,reference_state[i],native_state[i]);return 15;}}
  if(reference_hv!=hv_cursor||reference_trace_len!=actor_trace_len||memcmp(reference_trace,actor_trace,actor_trace_len*2)){fprintf(stderr,"order/HV mismatch case%lu\n",count);return 16;}
  fwrite(native_state,1,STATE_SIZE,stdout);fwrite(&hv_cursor,1,2,stdout);fwrite(&actor_trace_len,1,2,stdout);fwrite(actor_trace,1,96,stdout);fwrite(&baseline_cycles,1,4,stdout);fwrite(&native_cycles,1,4,stdout);count++;
 }
 fprintf(stderr,"PASS %lu cases\n",count);return 0;
}
'''


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ('rom','cc65-root','output'):ap.add_argument('--'+n,required=True)
 ap.add_argument('--original-root',action='append',default=[])
 args=ap.parse_args();out=_private_output(args.output);out.mkdir()
 rom=Path(args.rom).read_bytes();assert sha(rom)==ROM_SHA256
 source_paths=[ROOT/'src/fdisbull/game_sources'/n for n in ('miniplanets_full.c','miniplanets_actors.c','nes_game_fast.s')]
 captured={p:p.read_bytes() for p in [*source_paths,ROOT/'src/fdisbull/game_il.py',Path(__file__)]}
 full,actors,assembly=(captured[p].decode() for p in source_paths)
 model=lift_full_game(rom)['program'];machine=GameMachine(model,{0:rom},environment={'hv16':[0],'sound_busy':[0]});zero=machine.snapshot()
 # Reuse the qualified ABI's logical packing, not its physical addresses.
 # C globals are copied by symbol and sizeof, making host layout irrelevant.
 layout={};at=0
 for name,value in zero.items():
  typ=machine.global_types[name];scalar=typ[0] if isinstance(value,list) else typ
  bits,signed=scalar;n=len(value) if isinstance(value,list) else 1
  layout[name]={'offset':at,'length':n*bits//8,'element_bits':bits,'signed':signed,'array_length':n};at+=n*bits//8
 size=at
 # Actual reviewed C helpers/actors. Primitive helper names are kept separate
 # from the existing ASM exports, preserving an independent C arithmetic path.
 helper_source='\n'.join(extract(full,n) for n in HELPERS)
 actor_source=actors
 actor_source=re.sub(r'void run_objects\(void\)\s*\{.*?^\}','',actor_source,flags=re.M|re.S)
 actor_source=actor_source.replace('void run_fireball(u8 slot)','void reference_run_fireball(u8 slot)',1)
 actor_source=actor_source.replace('u8 mace_x(u8 slot)','u8 reference_mace_x(u8 slot)',1).replace('u8 mace_y(u8 slot)','u8 reference_mace_y(u8 slot)',1)
 for n in ('mace_x','mace_y'):
  actor_source=re.sub(r'(?<!reference_)\b'+n+r'\(', 'reference_'+n+'(',actor_source)
 body=helper_source+'\n'+actor_source
 for n in HELPERS:body=re.sub(r'\b'+n+r'\b','reference_'+n,body)
 ref_dispatch=extract(actors,'run_objects').replace('void run_objects','void reference_run_objects',1)
 for n in HANDLERS:ref_dispatch=re.sub(r'\b'+n+r'\(',('trace_reference_fireball' if n=='run_fireball' else 'trace_'+n)+'(',ref_dispatch)
 prefix=full[:full.index('void play_sfx(u8 id) {')]
 wrappers=[]
 for i,n in enumerate(HANDLERS,1):
  wrappers.append(f'void trace_{n}(u8 slot){{trace_call({i},slot);{n}(slot);}}')
 wrappers.append('void trace_reference_fireball(u8 slot){trace_call(9,slot);reference_run_fireball(slot);}')
 prototypes=['u16 stack_pointer(void);u8 same_stack(u16 original);void run_fireball(u8 slot);']
 for n in HELPERS:
  prototypes.append(re.sub(r'\b'+n+r'\b','reference_'+n,extract(full,n).split('{',1)[0].strip())+';')
 prototypes.extend('void '+('reference_run_fireball' if n=='run_fireball' else n)+'(u8 slot);' for n in HANDLERS)
 prototypes.extend(['u8 reference_mace_x(u8 slot);u8 reference_mace_y(u8 slot);'])
 prototypes.extend('void trace_'+n+'(u8 slot);' for n in HANDLERS);prototypes.append('void trace_reference_fireball(u8 slot);')
 serializers=[]
 for verb,operation in [('capture','memcpy(p+{at},&{name},{length});'),('restore','memcpy(&{name},p+{at},{length});')]:
  serializers.append('void '+verb+'_state(u8*p){'+''.join(operation.format(at=spec['offset'],name=name,length=spec['length']) for name,spec in layout.items())+'}')
 sine=rom[0x658f8:0x65b88];words=[int.from_bytes(sine[i:i+2],'big') for i in range(0,512,2)]
 tables=array('source_sine',sine)+array('native_sine_lo',[x&255 for x in words])+array('native_sine_hi',[x>>8 for x in words])+array('native_collision',rom[0xa514:0xa614])
 harness=(HARNESS.replace('STATE_SIZE',str(size)).replace('DECLARATIONS',prefix).replace('TABLES',tables).replace('PROTOTYPES','\n'.join(prototypes)).replace('BODIES',body+'\n'+ref_dispatch).replace('WRAPPERS','\n'.join(wrappers)).replace('SERIALIZERS','\n'.join(serializers)))
 (out/'harness.c').write_text(harness);(out/'fast.s').write_text(assembly)
 asm=['.export _native_actor_lo,_native_actor_hi,_native_actor_bank,_banked_call,_stack_pointer,_same_stack','.importzp ptr4,c_sp']
 asm+=['.import _trace_'+n for n in HANDLERS]
 asm+=['.segment "RODATA"','_native_actor_lo:','.byte '+','.join('0' if n is None else '<_trace_'+n for n in MAPPING),'_native_actor_hi:','.byte '+','.join('0' if n is None else '>_trace_'+n for n in MAPPING),'_native_actor_bank:','.res28,0'.replace('.res28','.res 28')]
 asm+=['.segment "CODE"','_banked_call:','jmp (ptr4)','_stack_pointer:','lda c_sp','ldx c_sp+1','rts','_same_stack:','cmp c_sp','bne no','cpx c_sp+1','bne no','lda #1','ldx #0','rts','no:','lda #0','ldx #0','rts']
 (out/'probe.s').write_text('\n'.join(asm)+'\n')
 tc=Path(args.cc65_root);cfg=(tc/'cfg/sim6502.cfg').read_text().replace('    RODATA:','    GAMEFAST: load = MAIN, type = ro;\n    RODATA:');(out/'sim.cfg').write_text(cfg)
 command=[str(tc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/'harness.c'),str(out/'fast.s'),str(out/'probe.s')]
 build=subprocess.run(command,capture_output=True,text=True,timeout=120);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr[-2000:])
 original=[];original_files={}
 for directory in map(Path,args.original_root):
  for path in sorted(directory.glob('native-*/receipt.json')):
   raw=path.read_bytes();receipt=json.loads(raw);original_files[str(path)]=sha(raw)
   assert receipt['complete'] and receipt['source_sha256']==ROM_SHA256 and receipt['core_sha256']==GENESIS_SHA
   for c in receipt['cases']:
    if c['contract']['entry']!=0x4a72:continue
    state={**zero}
    for name,data in c['ram_before'].items():
     if name not in layout:continue
     state[name]=list(bytes.fromhex(data)) if isinstance(zero[name],list) else int.from_bytes(bytes.fromhex(data),'big',signed=layout[name]['signed'])
    hv=[r['value'] for r in c.get('observed_hv_reads',[])] or [0]*256
    original.append({'name':'original/'+path.parent.name+'/'+c['contract']['name'],'entry':0,'slot':0,'before':state,'hv':hv,'original_after':c['ram_after'],'uil':True})
 def cases():
  yield from original
  for slot in range(48):
   for typ in range(256):
    pool=[0]*192;pool[slot*4:slot*4+4]=[typ,32,32,4]
    yield {'name':f'dispatch/{slot}/{typ}','entry':0,'slot':0,'before':{**zero,'objects':pool,'keys_left':1,'player_x':160,'player_y':160},'hv':[0]*256,'uil':slot in (0,23,47)}
  for slot in (0,23,47):
   for typ in (0,19,20,21,22,23,24,255):
    for base in (0,127,255):
     for axis in (0,1):
      for delta in range(256):
       pool=[0]*192;pool[slot*4:slot*4+4]=[typ,(base+delta)&255 if axis==0 else base,(base+delta)&255 if axis==1 else base,0]
       yield {'name':f'fireball/{slot}/{typ}/{base}/{axis}/{delta}','entry':1,'slot':slot,'before':{**zero,'objects':pool,'player_x':base,'player_y':base},'hv':[],'uil':slot==47 and base==255}
  for jump in (0,1,47,48,49,255):
   for die in (0,1,255):
    for guard in ('none','muteki','player_win','shake_timer'):
     for priority in range(256):
      pool=[0]*192;pool[4:8]=[23,255,0,77]
      before={**zero,'objects':pool,'player_jump':jump,'player_die':die,'current_sfx':priority,'sfx_to_play':255}
      if guard!='none':before[guard]=255
      yield {'name':f'guard/{jump}/{die}/{guard}/{priority}','entry':1,'slot':1,'before':before,'hv':[],'uil':priority in (0,12,13,14,255)}
  for slot in (0,23,46):
   pool=[0]*192;pool[slot*4:slot*4+8]=[9,64,64,1,8,64,64,3]
   yield {'name':f'order/later-bomb-fx/{slot}','entry':0,'slot':0,'before':{**zero,'objects':pool,'player_x':64,'player_y':64,'keys_left':1},'hv':[],'uil':True}
  for slot in (0,23,47):
   pool=[0]*192;pool[slot*4:slot*4+4]=[8,64,64,3]
   yield {'name':f'order/current-bomb-no-fx-reentry/{slot}','entry':0,'slot':0,'before':{**zero,'objects':pool,'player_x':64,'player_y':64,'keys_left':1},'hv':[],'uil':True}
 selected={};counts={};original_checked=0;case_count=0;steps=0;call_trace=[];original_call=machine._call
 def observe(name,values):
  if name in HANDLERS:call_trace.extend([HANDLERS.index(name)+1,values[0].number])
  return original_call(name,values)
 machine._call=observe
 with (out/'cases.bin').open('wb') as stream:
  for i,c in enumerate(cases()):
   hv=c['hv'];assert len(hv)<=256
   stream.write(struct.pack('<BBH',c['entry'],c['slot'],len(hv)));stream.write(encode_state(c['before'],layout));stream.write(struct.pack('<'+'H'*len(hv),*hv))
   group=c['name'].split('/')[0];counts[group]=counts.get(group,0)+1;case_count+=1
   if c['uil']:
    machine.set_state(c['before']);machine.events=[];machine.environment={'hv16':hv if hv else [0],'sound_busy':[0]};machine.environment_cursor={};call_trace.clear()
    machine.call('run_objects' if c['entry']==0 else 'run_fireball',*(() if c['entry']==0 else (c['slot'],)))
    state=machine.snapshot();steps+=machine.steps
    if 'original_after' in c:
     for name,data in c['original_after'].items():
      if name not in layout:continue
      expected=list(bytes.fromhex(data)) if isinstance(zero[name],list) else int.from_bytes(bytes.fromhex(data),'big',signed=layout[name]['signed'])
      assert state[name]==expected,(c['name'],name)
     original_checked+=1
    assert not machine.events
    selected[i]=(c['name'],encode_state(state,layout),machine.environment_cursor.get('hv16',0),bytes(call_trace) if c['entry']==0 else b'')
 with (out/'cases.bin').open('rb') as source,(out/'results.bin').open('wb') as target:
  run=subprocess.run([str(tc/'bin/sim65'),str(out/'check')],stdin=source,stdout=target,stderr=subprocess.PIPE,timeout=300)
 (out/'run.txt').write_bytes(run.stderr)
 if run.returncode:raise AssertionError(run.stderr.decode(errors='replace')[-2000:])
 result=(out/'results.bin').read_bytes();stride=size+108;assert len(result)==stride*case_count,(len(result),stride,case_count)
 total_c=total_asm=0
 for i in range(case_count):
  record=result[i*stride:(i+1)*stride];hv,n=struct.unpack_from('<HH',record,size)
  baseline,native=struct.unpack_from('<II',record,size+100);total_c+=baseline;total_asm+=native
  if i in selected:
   name,state,wanted_hv,trace=selected[i]
   assert record[:size]==state,(name,'UILstate')
   assert hv==wanted_hv,(name,'HV',hv,wanted_hv)
   assert record[size+4:size+4+n*2]==trace,(name,'actor-order')
 assert all(p.read_bytes()==raw for p,raw in captured.items())
 assert all(sha(Path(p).read_bytes())==digest for p,digest in original_files.items())
 report={'format':'miniplanets-actor-intrinsic-sim6502-1','status':'passed','cases':case_count,'case_groups':counts,'typed_uil_cases':len(selected),'typed_uil_steps':steps,'retained_original_cpu_cases_replayed':original_checked,'full_state_bytes':size,'handler_order_and_hv_checked':True,'rom_sha256':ROM_SHA256,'program_sha256':sha(canonical(model)),'sources':{p.name:sha(raw) for p,raw in captured.items()},'native_check_sha256':sha((out/'check').read_bytes()),'original_receipts':original_files,'toolchain':{n:sha((tc/'bin'/n).read_bytes()) for n in ['cl65','cc65','ca65','ld65','sim65']},'c_reference_cycles_total':total_c,'asm_cycles_total':total_asm,'cycle_scope':'Counter-included sim6502 execution with shared real C handlers and same-bank trampoline; C reference is unbanked reviewed source, not a whole-game FPS baseline.','limits':['Retained originalCPU receipts are revalidated, not described as fresh original execution.','Final real NES bank/IRQ integration, all4822cases and busy-stage FPS/audio/projection gates remain required.'],'inputs_unchanged':True}
 (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='original_receipts'},indent=2))

if __name__=='__main__':main()
