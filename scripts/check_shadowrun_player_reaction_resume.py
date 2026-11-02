#!/usr/bin/env python3
"""Compare two full-core source hit/reaction/no-input-recovery windows."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_reaction_resume import SOURCE,lift_player_reaction_resume
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
 if any(x['start']<6043 and x['end']>5999 for x in r['inputs']):raise ValueError('input was present in admitted windows')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 prog=lift_player_reaction_resume(rom);m=GameMachine(prog,{0:rom});rows=[]
 for hit,priorhp,posthp in ((6000,10,5),(6030,5,3)):
  before=frame(hit-1);first=frame(hit);actor=before[0x100:0x200];new=first[0x100:0x200]
  if (w(actor,14),actor[0x10],actor[0x4c],new[0x4c],l(new,0x3a))!=(3,15,priorhp,posthp,0xb07e):raise ValueError('source hit mismatch')
  m.set_state({'shadowrun_reaction_kind':w(actor,14),'shadowrun_reaction_x':w(actor,0),'shadowrun_reaction_y':w(actor,4),'shadowrun_reaction_heading':w(actor,0x2e),'shadowrun_reaction_animation':w(actor,0x16),'shadowrun_reaction_increment':w(actor,0x18),'shadowrun_reaction_accumulator':w(actor,0x1a),'shadowrun_reaction_threshold':w(actor,0x1c),'shadowrun_reaction_index':w(actor,0x1e),'shadowrun_reaction_move_state':w(actor,0x38),'shadowrun_reaction_action_timer':((w(actor,0xdc)-1)&65535) if not (w(actor,0xdc)&32768) else w(actor,0xdc),'shadowrun_reaction_callback':l(actor,0x3a),'shadowrun_reaction_flags':actor[0x10],'shadowrun_reaction_flags_low':actor[0x11],'shadowrun_reaction_hp':posthp,'shadowrun_reaction_max_hp':actor[0x9c],'shadowrun_reaction_counter':actor[0xce],'shadowrun_reaction_corners':list(actor[0xd0:0xd4]),'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_max':w(before,0xddd4),'shadowrun_x_min':w(before,0xddd6),'shadowrun_y_min':w(before,0xddd8),'shadowrun_rect_base':l(before,0xddec),'shadowrun_probe_corners':list(before[0xef10:0xef14])})
  m.call('shadowrun_reaction_start');m.call('shadowrun_reaction_sprite_only');s=m.snapshot()
  if not s['shadowrun_reaction_sprite_supported']:raise AssertionError('hit-frame sprite refused')
  for f in range(hit,hit+12):
   actual=frame(f);v=actual[0x100:0x200]
   if actual[0x1700:0x2200]!=before[0x1700:0x2200] or (w(v,0),w(v,4))!=(w(actor,0),w(actor,4)):raise ValueError('terrain or player moved')
   if f>hit:
    m.call('shadowrun_reaction_step');s=m.snapshot()
    if not s['shadowrun_reaction_step_supported'] or s['shadowrun_reaction_step_result']!=1:raise AssertionError(('reaction step refused',f))
   got=tuple(s[k] for k in ('shadowrun_reaction_animation','shadowrun_reaction_increment','shadowrun_reaction_accumulator','shadowrun_reaction_index','shadowrun_reaction_move_state','shadowrun_reaction_action_timer','shadowrun_reaction_callback','shadowrun_reaction_counter','shadowrun_reaction_corners','shadowrun_reaction_flags_low'))
   expected_state=(w(v,0x16),w(v,0x18),w(v,0x1a),w(v,0x1e),w(v,0x38),w(v,0xdc),l(v,0x3a),v[0xce],list(v[0xd0:0xd4]),v[0x11])
   if got!=expected_state:raise AssertionError((f,got,expected_state))
  pre=frame(hit+11);v=pre[0x100:0x200];m.call('shadowrun_reaction_step');s=m.snapshot()
  if not s['shadowrun_reaction_step_supported'] or s['shadowrun_reaction_step_result']!=2:raise AssertionError('input admission refused')
  m.set_state({'shadowrun_reaction_cursor':v[0x43],'shadowrun_reaction_attr_a':v[0x78],'shadowrun_reaction_attr_b':v[0x7b],'shadowrun_reaction_gear':w(v,0x90),'shadowrun_reaction_speed':w(v,0xca),'shadowrun_reaction_input_flags':w(pre,0xdd22),'shadowrun_reaction_input_heading':w(pre,0xdd04),'shadowrun_reaction_global_e6':w(pre,0xdfe6),'shadowrun_reaction_global_3a':w(pre,0xdf3a),'shadowrun_reaction_global_18a':pre[0xe18a],'shadowrun_reaction_global_18b':pre[0xe18b]})
  m.call('shadowrun_reaction_resume_idle');s=m.snapshot();v=frame(hit+12)[0x100:0x200]
  got=tuple(s[k] for k in ('shadowrun_reaction_animation','shadowrun_reaction_increment','shadowrun_reaction_accumulator','shadowrun_reaction_index','shadowrun_reaction_move_state','shadowrun_reaction_action_timer','shadowrun_reaction_callback','shadowrun_reaction_counter','shadowrun_reaction_corners','shadowrun_reaction_flags_low','shadowrun_reaction_cursor'))
  expected_state=(w(v,0x16),w(v,0x18),w(v,0x1a),w(v,0x1e),w(v,0x38),w(v,0xdc),l(v,0x3a),v[0xce],list(v[0xd0:0xd4]),v[0x11],v[0x43])
  if not s['shadowrun_reaction_resume_supported'] or got!=expected_state:raise AssertionError(('idle recovery',hit+12,got,expected_state))
  rows.append({'hit_frame':hit,'hp_before':priorhp,'hp_after':posthp,'reaction_frames':12,'idle_recovery_frame':hit+12,'action_timer_after_recovery':w(v,0xdc)})
 summary={'status':'passed','windows':rows,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'two assisted hostile-source launches; no player/projectile patches; stationary player and no input; sound and graphics payloads excluded'}
 out=_private_directory(a.output);out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
