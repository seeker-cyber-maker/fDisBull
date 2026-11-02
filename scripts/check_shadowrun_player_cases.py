#!/usr/bin/env python3
"""Compare captured original 68000 player cases with source-bound GameIL.

Consumes a private `probe_genesis_function.py` batch receipt from the
explicitly supported normal-player path. No original ROM bytes or traces
are emitted into the source tree. This is bounded component evidence, not a
whole-game or natural-reachability claim.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from fdisbull.game_il import GameMachine,canonical
from fdisbull.udl_shadowrun import lift_opening_walk

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--rom',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();program=lift_opening_walk(rom);machine=GameMachine(program,{0:rom});bad=[];total=0;identities=[];counts={'accepted':0,'blocked':0,'unresolved':0}
 for path in a.receipt:
  payload=path.read_bytes();identities.append(hashlib.sha256(payload).hexdigest());report=json.loads(payload)
  if not report.get('complete') or report.get('source_sha256')!=hashlib.sha256(rom).hexdigest():raise ValueError('native receipt/source mismatch')
  for case in report['cases']:
   if not case.get('complete'):raise ValueError('incomplete native case')
   contract=case['contract'];entries=contract['ram'];data=bytes.fromhex(entries[0]['data']);o=bytes.fromhex(entries[1]['data'])
   if len(data)!=2816 or len(o)!=212:raise ValueError('unexpected test fixture layout')
   w=lambda i:int.from_bytes(o[i:i+2],'big')
   machine.set_state({'shadowrun_terrain_map':list(data),'shadowrun_player_x':w(0),'shadowrun_player_y':w(4),'shadowrun_player_contact':w(12),'shadowrun_player_kind':w(14),'shadowrun_player_flags':o[16],'shadowrun_player_flags_low':o[17],'shadowrun_player_heading':w(46),'shadowrun_player_target_heading':w(52),'shadowrun_player_equipment_flags':o[0x9e],'shadowrun_player_callback':int.from_bytes(o[0x3a:0x3e],'big'),'shadowrun_global_special_mode':0,'shadowrun_global_vector_flags':0,'shadowrun_scene_mode':2,'shadowrun_event_mode':0,'shadowrun_probe_flags':o[16],'shadowrun_x_min':44,'shadowrun_x_max':1876,'shadowrun_y_min':44,'shadowrun_y_max':1304,'shadowrun_rect_base':0x172daa,'shadowrun_probe_corners':[0x91,0x92,0x93,0x94],'shadowrun_probe_map_offset':0xabcd,'shadowrun_probe_special':0xffff,'shadowrun_raw_status':0x1234,'shadowrun_boundary_hit':0x1234,'shadowrun_slope_mode':0x1234,'shadowrun_fallback_direction':0,'shadowrun_player_event_flags':255,'shadowrun_player_collision_movement_state':0xabcd,'shadowrun_player_transition_heading':w(0x36),'shadowrun_player_animation_selector':w(0x16)})
   machine.call('shadowrun_player_walk_bounded');s=machine.snapshot();result=s['shadowrun_player_walk_result']
   if result not in (1,2):counts['unresolved']+=1;total+=1;continue
   counts['accepted' if result==1 else 'blocked']+=1
   watched=case['ram_after'];z=bytes.fromhex(watched['object']);w2=lambda i:int.from_bytes(z[i:i+2],'big')
   expected={'shadowrun_player_heading':w2(46),'shadowrun_player_x':w2(0),'shadowrun_player_y':w2(4),'shadowrun_player_move_state':w2(56),'shadowrun_player_step_timer':w2(0xca),'shadowrun_player_direction':int(watched['direction'],16),'shadowrun_fallback_direction':int(watched.get('fallback','0000'),16),'shadowrun_player_event_flags':z[0xb0],'shadowrun_player_flags_low':z[0x11],'shadowrun_player_callback':int.from_bytes(z[0x3a:0x3e],'big'),'shadowrun_player_animation_selector':w2(0x16),'shadowrun_player_transition_heading':w2(0x36),'shadowrun_player_collision_movement_state':w2(0xb8),'shadowrun_player_record_corners':list(z[0xd0:0xd4]),'shadowrun_probe_corners':list(bytes.fromhex(watched['corners'])),'shadowrun_probe_map_offset':int(watched['offset'],16),'shadowrun_probe_special':int(watched['special'],16),'shadowrun_raw_status':int(watched['raw'],16),'shadowrun_boundary_hit':int(watched['boundary'],16),'shadowrun_slope_mode':int(watched['slope'],16)}
   actual={k:s[k] for k in expected}
   if actual!=expected:bad.append({'case':total,'native':expected,'uil':actual})
   total+=1
 out.parent.mkdir(parents=True,exist_ok=True)
 result={'format':'fdisbull-shadowrun-player-component-check-1','source_sha256':hashlib.sha256(rom).hexdigest(),'program_sha256':hashlib.sha256(canonical(program)).hexdigest(),'native_receipt_sha256':identities,'cases':total,'classification':counts,'mismatches':bad,'scope':'controlled component state; unresolved events are not compared or called passes'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='mismatches'}));
 if bad:raise AssertionError(f'{len(bad)} native/UIL mismatches')
if __name__=='__main__':main()
