#!/usr/bin/env python3
"""Compare source-derived hostile movement and sprite clocks to full core."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_combat_walk import SOURCE,lift_player_combat_walk
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 expected={(0x400,256),(0xdf84,2),(0xdfd8,2),(0xe186,2),(0xf9f8,2)}
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or len(r['patches'])!=5 or any(x['frame']!=6000 or x['memory_id']!=2 for x in r['patches']) or {(x['offset'],len(x['data_hex'])//2) for x in r['patches']}!=expected:raise ValueError('source or assisted injection mismatch')
 if not any(x['start']==6041 and x['end']>6050 and x['buttons']==['UP'] for x in r['inputs']):raise ValueError('missing UP turn')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 b=frame(6040);v=b[0x100:0x200];prog=lift_player_combat_walk(rom);m=GameMachine(prog,{0:rom})
 m.set_state({'shadowrun_player_x':w(v,0),'shadowrun_player_y':w(v,4),'shadowrun_player_heading':w(v,0x2e),'shadowrun_player_target_heading':0,'shadowrun_player_kind':w(v,14),'shadowrun_player_contact':w(v,12),'shadowrun_player_flags':v[0x10],'shadowrun_player_equipment_flags':v[0x9e],'shadowrun_player_event_flags':v[0xb0],'shadowrun_player_combat_attribute':v[0x78],'shadowrun_player_combat_global':w(b,0xdf84),'shadowrun_global_special_mode':0,'shadowrun_global_vector_flags':0,'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_max':w(b,0xddd4),'shadowrun_x_min':w(b,0xddd6),'shadowrun_y_min':w(b,0xddd8),'shadowrun_rect_base':l(b,0xddec),'shadowrun_probe_corners':list(b[0xef10:0xef14])})
 for f in range(6041,6051):
  actual=frame(f);z=actual[0x100:0x200]
  if actual[0x1700:0x2200]!=b[0x1700:0x2200]:raise ValueError('terrain changed')
  m.call('shadowrun_player_combat_walk');s=m.snapshot()
  got=(s['shadowrun_player_x'],s['shadowrun_player_y'],s['shadowrun_player_heading'],s['shadowrun_player_move_state'],s['shadowrun_player_step_timer'],s['shadowrun_player_collision_movement_state'],s['shadowrun_player_event_flags'],s['shadowrun_player_record_corners'])
  exp=(w(z,0),w(z,4),w(z,0x2e),w(z,0x38),w(z,0xca),w(z,0xb8),z[0xb0],list(z[0xd0:0xd4]))
  if not s['shadowrun_player_combat_walk_supported'] or got!=exp:raise AssertionError((f,got,exp,s['shadowrun_player_combat_walk_supported']))
 result={'status':'passed','matched_frames':10,'source_frames':[6041,6050],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted constructed hostile with ordinary LEFT-to-UP controller turn; captured party clear movement, sprite service separate'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
