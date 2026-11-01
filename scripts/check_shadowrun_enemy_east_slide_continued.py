#!/usr/bin/env python3
"""Compare real unpatched civilian east-wall slide with source frames."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_east_slide import SOURCE,lift_enemy_east_slide
from fdisbull.udl_shadowrun import ROM_SHA256
from fdisbull.console_udc import _private_directory
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(x):return hashlib.sha256(x).hexdigest()
def w(x,n):return int.from_bytes(x[n:n+2],'big')
def l(x,n):return int.from_bytes(x[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or r['patches']:raise ValueError('source identity or unpatched capture mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 program=lift_enemy_east_slide(rom);m=GameMachine(program,{0:rom})
 native=json.loads((root.parent/'enemy-east-continued-probe-03/native/receipt.json').read_text());original=bytes.fromhex(native['cases'][1]['ram_after']['actor'])
 for f in (6389,6390,6391):
  b=frame(f-1);v=b[0x500:0x600];z=original if f==6391 else frame(f)[0x500:0x600]
  m.set_state({'shadowrun_ai_x':w(v,0),'shadowrun_ai_y':w(v,4),'shadowrun_ai_kind':w(v,14),'shadowrun_ai_target_heading':w(v,0x34),'shadowrun_ai_distance':w(v,0xc8),'shadowrun_ai_collision_state':w(v,0xb8),'shadowrun_ai_animation':w(v,0x16),'shadowrun_ai_callback':l(v,0x3a),'shadowrun_ai_flags':v[0x10],'shadowrun_ai_equipment_flags':v[0x9e],'shadowrun_ai_event_flags':v[0xb0],'shadowrun_ai_combat_global':w(b,0xdf84),'shadowrun_ai_heading':w(v,0x2e),'shadowrun_ai_transition_heading':w(v,0x36),'shadowrun_ai_move_state':w(v,0x38),'shadowrun_ai_speed':w(v,0xca),'shadowrun_ai_flags_low':v[0x11],'shadowrun_ai_attribute':v[0x78],'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_max':w(b,0xddd4),'shadowrun_x_min':w(b,0xddd6),'shadowrun_y_min':w(b,0xddd8),'shadowrun_rect_base':l(b,0xddec)})
  m.call('shadowrun_ai_actor_tick');s=m.snapshot()
  if s['shadowrun_ai_supported'] or s['shadowrun_collision_status']!=127:raise AssertionError('missing source wall')
  m.call('shadowrun_ai_east_slide');s=m.snapshot();keys=('x','y','heading','target_heading','transition_heading','move_state','collision_state','speed','animation','flags_low','event_flags','corners');got=tuple(s['shadowrun_ai_'+k] for k in keys);exp=(w(z,0),w(z,4),w(z,0x2e),w(z,0x34),w(z,0x36),w(z,0x38),w(z,0xb8),w(z,0xca),w(z,0x16),z[0x11],z[0xb0],list(z[0xd0:0xd4]))
  if not s['shadowrun_ai_east_slide_supported'] or got!=exp:raise AssertionError((f,got,exp))
 result={'status':'passed','source_frames':[6389,6390],'controlled_source_continuation':6391,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(program)),'scope':'unpatched courtyard actor1 clear proposal followed by eastward terrain fallback; other cases refused'}
 _private_directory(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
