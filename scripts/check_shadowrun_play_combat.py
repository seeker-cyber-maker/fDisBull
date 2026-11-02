#!/usr/bin/env python3
"""Compare an assisted-target NES combat route to its shared GameIL state.

This checks the target compilation and controls, not original-game AI, scene
reachability or projectile-pool parity. NPCs retain captured fixed positions.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_play import machine_from_capture,lift_play
from check_shadowrun_opening_route import checked_receipt,indexed_frames,NES_CORE_SHA,SOURCE_ROM_SHA

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--natural',action='store_true')
 for n in ('rom','capture','build','run','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=(a.build/'play.nes').read_bytes();build_raw=(a.build/'play-receipt.json').read_bytes();build=json.loads(build_raw)
 if sha(rom)!=SOURCE_ROM_SHA or build.get('output_sha256')!=sha(nes) or build.get('program_sha256')!=sha(canonical(lift_play(rom))):raise ValueError('source/build mismatch')
 rr=(a.run/'receipt.json').read_bytes();receipt=json.loads(rr);checked_receipt(receipt,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 exp=[{'start':100,'end':104,'buttons':['SELECT']}]+[{'start':120+10*i,'end':124+10*i,'buttons':['RIGHT']} for i in range(7)]+[{'start':200+10*i,'end':204+10*i,'buttons':['DOWN']} for i in range(3)]+[{'start':240,'end':244,'buttons':['A']},{'start':280,'end':284,'buttons':['B']},{'start':300,'end':650,'buttons':['A']}]
 if a.natural:
  exp=[{'start':100,'end':160,'buttons':['LEFT']},{'start':180,'end':201,'buttons':['UP']},{'start':220,'end':224,'buttons':['B']},{'start':240,'end':620,'buttons':['A']}]
 if receipt.get('inputs')!=exp or receipt.get('watches')!=[{'name':'state','offset':1792,'length':84}]:raise ValueError('input/watch mismatch')
 trace=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(trace,receipt);m=machine_from_capture(rom,a.capture)
 first=bytes.fromhex(frames[99]['raw']['state']);prior=first[23]
 if first[:2]!=b'SW' or first[22]&1 or prior>90:raise ValueError('invalid ready publication')
 for _ in range(prior):m.call('shadowrun_play_frame',0)
 mapping={'UP':1,'DOWN':2,'LEFT':4,'RIGHT':8,'B':16,'SELECT':32,'A':64,'START':128}
 fields=[('shadowrun_player_x',4,2),('shadowrun_player_y',6,2),('shadowrun_camera_x',14,2),('shadowrun_camera_y',16,2),('shadowrun_play_ammo',34,1),('shadowrun_play_shot_pending',41,1),('shadowrun_play_shot_used',42,1),('shadowrun_field_rng',51,2),('shadowrun_play_shot_timer',53,2),('shadowrun_target_selected',55,1),('shadowrun_linked_motion_state',71,1),('shadowrun_linked_motion_lifetime',72,1),('shadowrun_linked_motion_steps',73,1),('shadowrun_actors_hit_slot',74,1),('shadowrun_linked_x_fixed',75,4),('shadowrun_linked_y_fixed',79,4),('shadowrun_field_outcome',83,1),('shadowrun_field_supported',43,1)]
 mismatches=[];compared=0;hp_transitions=[];last_hp=None;shot_ticks=[];last_shots=0;logical=0
 for f in range(100,min(receipt['frames'],700)):
  row=frames[f];b=bytes.fromhex(row['raw']['state'])
  if len(b)!=84 or b[:2]!=b'SW' or b[22]&1:continue
  if b[23]==prior:continue
  if b[23]!=(prior+1)&255:raise ValueError('missed a completed target tick')
  prior=b[23];pad=0
  for x in exp:
   if x['start']<=f<x['end']:
    for button in x['buttons']:pad|=mapping[button]
  m.call('shadowrun_play_frame',pad);s=m.snapshot();logical+=1;compared+=1
  for name,off,width in fields:
   actual=int.from_bytes(b[off:off+width],'little')
   if actual!=s[name]:mismatches.append({'frame':f,'field':name,'expected':s[name],'observed':actual})
  hp=list(b[64:71])
  if hp!=s['shadowrun_play_actor_hp']:mismatches.append({'frame':f,'field':'actor_hp','expected':s['shadowrun_play_actor_hp'],'observed':hp})
  if hp!=last_hp:hp_transitions.append({'frame':f,'hp':hp});last_hp=hp
  if b[42]!=last_shots:shot_ticks.append({'frame':f,'logical':logical,'ammo':b[34],'shots':b[42]});last_shots=b[42]
 if not hp_transitions or hp_transitions[-1]['hp'][0 if a.natural else 1]!=0 or last_shots!=3:mismatches.append({'field':'expected target depletion sequence'})
 result={'format':'fdisbull-shadowrun-play-combat-nes-1','nes_sha256':sha(nes),'build_receipt_sha256':sha(build_raw),'native_receipt_sha256':sha(rr),'native_trace_sha256':sha(trace),'logical_updates':compared,'shot_events':shot_ticks,'hp_transitions':hp_transitions,'mismatches':mismatches,'scope':('ordinary D-pad selection and fire with frozen captured NPCs' if a.natural else 'assisted player placement and frozen captured NPCs')+'; target-adapted single projectile; NES output versus shared GameIL, source leaf checks separate'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f'{compared} logical updates, {len(mismatches)} mismatches, {last_shots} shots')
 if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
