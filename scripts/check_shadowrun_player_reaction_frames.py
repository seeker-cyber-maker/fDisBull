#!/usr/bin/env python3
"""Compare bounded party reaction projection to assisted full-core frames."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_reaction import SOURCE,lift_player_reaction
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or not r['patches'] or any(x['frame']!=6000 for x in r['patches']):raise ValueError('source or assisted capture mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 initial=frame(5999);first=frame(6000);source=initial[0x100:0x200];after=first[0x100:0x200]
 if (w(source,14),source[0x10],source[0x4c],after[0x4c],l(after,0x3a))!=(3,15,10,5,0xb07e):raise ValueError('prepared nonlethal impact mismatch')
 prog=lift_player_reaction(rom);m=GameMachine(prog,{0:rom});m.set_state({'shadowrun_reaction_kind':w(source,14),'shadowrun_reaction_x':w(source,0),'shadowrun_reaction_y':w(source,4),'shadowrun_reaction_heading':w(source,0x2e),'shadowrun_reaction_animation':w(source,0x16),'shadowrun_reaction_increment':w(source,0x18),'shadowrun_reaction_accumulator':w(source,0x1a),'shadowrun_reaction_threshold':w(source,0x1c),'shadowrun_reaction_index':w(source,0x1e),'shadowrun_reaction_move_state':w(source,0x38),'shadowrun_reaction_action_timer':w(source,0xdc),'shadowrun_reaction_callback':l(source,0x3a),'shadowrun_reaction_flags':source[0x10],'shadowrun_reaction_flags_low':source[0x11],'shadowrun_reaction_hp':after[0x4c],'shadowrun_reaction_max_hp':after[0x9c],'shadowrun_reaction_counter':source[0xce],'shadowrun_reaction_corners':list(source[0xd0:0xd4]),'shadowrun_terrain_map':list(initial[0x1700:0x2200]),'shadowrun_x_max':w(initial,0xddd2),'shadowrun_y_max':w(initial,0xddd4),'shadowrun_x_min':w(initial,0xddd6),'shadowrun_y_min':w(initial,0xddd8),'shadowrun_rect_base':l(initial,0xddec),'shadowrun_probe_corners':list(initial[0xef10:0xef14])})
 m.call('shadowrun_reaction_start');sounds=dirty=0;rows=[]
 for f in range(6000,6012):
  observed=frame(f);actor=observed[0x100:0x200]
  if observed[0x1700:0x2200]!=initial[0x1700:0x2200] or (w(actor,0),w(actor,4))!=(w(source,0),w(source,4)):raise ValueError('terrain or player moved')
  m.call('shadowrun_reaction_outer_gate');s=m.snapshot()
  if not s['shadowrun_reaction_supported'] or s['shadowrun_reaction_admitted']:raise AssertionError(('unexpected early admission',f))
  m.call('shadowrun_reaction_callback_tick');s=m.snapshot();sounds+=s['shadowrun_reaction_sound_due']
  m.call('shadowrun_reaction_advance');s=m.snapshot();dirty+=s['shadowrun_reaction_graphics_pending']
  m.call('shadowrun_reaction_select');s=m.snapshot()
  if not s['shadowrun_reaction_supported']:raise AssertionError(('reaction refused',f))
  got=tuple(s[k] for k in ('shadowrun_reaction_animation','shadowrun_reaction_increment','shadowrun_reaction_accumulator','shadowrun_reaction_index','shadowrun_reaction_move_state','shadowrun_reaction_action_timer','shadowrun_reaction_callback','shadowrun_reaction_counter','shadowrun_reaction_corners'))
  expected=(w(actor,0x16),w(actor,0x18),w(actor,0x1a),w(actor,0x1e),w(actor,0x38),w(actor,0xdc),l(actor,0x3a),actor[0xce],list(actor[0xd0:0xd4]))
  if got!=expected:raise AssertionError((f,got,expected))
  rows.append({'frame':f,'animation':w(actor,0x16),'counter':actor[0xce]})
 m.call('shadowrun_reaction_outer_gate');s=m.snapshot();actor=frame(6012)[0x100:0x200]
 if not s['shadowrun_reaction_supported'] or not s['shadowrun_reaction_admitted'] or s['shadowrun_reaction_action_timer']!=w(actor,0xdc):raise AssertionError('next-frame input admission mismatch')
 summary={'status':'passed','matched_frames':len(rows),'first_admission_frame':6012,'sound_due_events':sounds,'graphics_pending_events':dirty,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted original hostile projectile hit and stationary positive-HP party reaction; sound and sprite upload effects excluded; ACAE internal input guards not asserted'}
 out=_private_directory(a.output);out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
