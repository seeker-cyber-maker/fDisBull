#!/usr/bin/env python3
"""Compare held-A party recovery with a full-core assisted original capture."""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_reaction_idle_walk import SOURCE,lift_player_reaction_idle_walk
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
 if any(x['start']<=6062<x['end'] for x in r['inputs']):raise ValueError('unexpected input')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=frame(6062);after=frame(6063);v=before[0x100:0x200];n=after[0x100:0x200]
 if (w(v,14),v[0x10],v[0x4c],l(v,0x3a),w(v,0xdc),w(before,0xdd22),w(before,0xdfe6))!=(3,15,3,0xb07e,30,0,0):raise ValueError('source precondition mismatch')
 if before[0x1700:0x2200]!=after[0x1700:0x2200] or (w(v,0),w(v,4))!=(w(n,0),w(n,4)):raise ValueError('source moved or terrain changed')
 prog=lift_player_reaction_idle_walk(rom);m=GameMachine(prog,{0:rom})
 m.set_state({'shadowrun_reaction_kind':w(v,14),'shadowrun_reaction_x':w(v,0),'shadowrun_reaction_y':w(v,4),'shadowrun_reaction_heading':w(v,0x2e),'shadowrun_reaction_animation':w(v,0x16),'shadowrun_reaction_increment':w(v,0x18),'shadowrun_reaction_accumulator':w(v,0x1a),'shadowrun_reaction_threshold':w(v,0x1c),'shadowrun_reaction_index':w(v,0x1e),'shadowrun_reaction_move_state':w(v,0x38),'shadowrun_reaction_action_timer':w(v,0xdc),'shadowrun_reaction_callback':l(v,0x3a),'shadowrun_reaction_flags':v[0x10],'shadowrun_reaction_flags_low':v[0x11],'shadowrun_reaction_hp':v[0x4c],'shadowrun_reaction_max_hp':v[0x9c],'shadowrun_reaction_counter':v[0xce],'shadowrun_reaction_corners':list(v[0xd0:0xd4]),'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_max':w(before,0xddd4),'shadowrun_x_min':w(before,0xddd6),'shadowrun_y_min':w(before,0xddd8),'shadowrun_rect_base':l(before,0xddec),'shadowrun_probe_corners':list(before[0xef10:0xef14]),'shadowrun_reaction_cursor':v[0x43],'shadowrun_reaction_attr_a':v[0x78],'shadowrun_reaction_attr_b':v[0x7b],'shadowrun_reaction_gear':w(v,0x90),'shadowrun_reaction_speed':w(v,0xca),'shadowrun_reaction_input_flags':w(before,0xdd22),'shadowrun_reaction_input_heading':w(before,0xdd04),'shadowrun_reaction_global_e6':w(before,0xdfe6),'shadowrun_reaction_global_3a':w(before,0xdf3a),'shadowrun_reaction_global_18a':before[0xe18a],'shadowrun_reaction_global_18b':before[0xe18b]})
 m.call('shadowrun_reaction_step');s=m.snapshot()
 if not s['shadowrun_reaction_step_supported'] or s['shadowrun_reaction_step_result']!=2:raise AssertionError('input admission refused')
 m.set_state({'shadowrun_reaction_normal_sprite_speed':28});m.call('shadowrun_reaction_resume_idle_walk');s=m.snapshot()
 keys=('animation','increment','accumulator','index','move_state','action_timer','callback','counter','corners','flags_low','cursor')
 got=tuple(s['shadowrun_reaction_'+k] for k in keys)
 expected_state=(w(n,0x16),w(n,0x18),w(n,0x1a),w(n,0x1e),w(n,0x38),w(n,0xdc),l(n,0x3a),n[0xce],list(n[0xd0:0xd4]),n[0x11],n[0x43])
 if not s['shadowrun_reaction_idle_walk_supported'] or got!=expected_state:raise AssertionError(('held recovery',got,expected_state))
 summary={'status':'passed','matched_source_transition':[6062,6063],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted moving encounter, party no-input recovery after source combat walk, party sprite speed28 supplied; audio and sprite payloads excluded'}
 out=_private_directory(a.output);out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
