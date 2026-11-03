#!/usr/bin/env python3
"""Compare a terminal HP/RNG boundary to an assisted original-core capture."""
from pathlib import Path
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_hostile_cycle import lift_hostile_cycle
parser=argparse.ArgumentParser()
for name in ('rom','capture','output'): parser.add_argument('--'+name,required=True)
args=parser.parse_args()
root=Path(args.capture);cap=json.loads((root/'capture.json').read_text());receipt=(root/'native/receipt.json').read_bytes()
receipt_hash=hashlib.sha256(receipt).hexdigest()
if receipt_hash!='a1c969d5c64b651e9be1fb53bc840b60c223d7ef30eb2b3defadeadfc31a982f': raise ValueError('unexpected source capture')
def frame(n):
 key=f'native/scene-{n:06d}/ram.bin';raw=(root/key).read_bytes();assert hashlib.sha256(raw).hexdigest()==cap['files'][key]['sha256'];return bytes(raw[i^1] for i in range(65536))
w=lambda b,i:int.from_bytes(b[i:i+2],'big');l=lambda b,i:int.from_bytes(b[i:i+4],'big')
a=frame(6241);b=frame(6242);pr=a[0xb00:0xc00];rom=Path(args.rom).read_bytes();m=GameMachine(lift_hostile_cycle(rom),{0:rom})
m.set_state({'shadowrun_burst_profile':1,'shadowrun_burst_x':l(pr,0),'shadowrun_burst_y':l(pr,4),'shadowrun_burst_origin_x':w(pr,0x58),'shadowrun_burst_origin_y':w(pr,0x5a),'shadowrun_burst_heading':w(pr,0x2e),'shadowrun_burst_vx':w(pr,0x4c),'shadowrun_burst_vy':w(pr,0x4e),'shadowrun_burst_counter':pr[0x41],'shadowrun_burst_flags':pr[0x10],'shadowrun_burst_flags_low':pr[0x11],'shadowrun_burst_lifetime':pr[0x89],'shadowrun_burst_effect':pr[0x9f],'shadowrun_burst_shooter_effect':a[0x49f],'shadowrun_burst_anim_word':w(pr,0x16),'shadowrun_burst_anim_increment':w(pr,0x18),'shadowrun_burst_anim_accumulator':w(pr,0x1a),'shadowrun_burst_anim_threshold':w(pr,0x1c),'shadowrun_burst_anim_index':w(pr,0x1e),'shadowrun_player_damage_hp':a[0x14c],'shadowrun_player_damage_armor':a[0x176],'shadowrun_x_min':w(a,0xddd6),'shadowrun_x_max':w(a,0xddd2),'shadowrun_y_min':w(a,0xddd8),'shadowrun_y_max':w(a,0xddd4),'shadowrun_burst_rng':w(a,0xf9f8),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_hostile_motion_player_x':w(b,0x100),'shadowrun_hostile_motion_player_y':w(b,0x104),'shadowrun_target_x':[w(b,0x400+i*0x100) for i in range(7)],'shadowrun_target_y':[w(b,0x404+i*0x100) for i in range(7)],'shadowrun_target_flags':[b[0x410+i*0x100] for i in range(7)],'shadowrun_play_actor_hp':[b[0x44c+i*0x100] for i in range(7)]})
m.call('shadowrun_hostile_cycle_tick');s=m.snapshot();actual=[s['shadowrun_hostile_cycle_supported'],s['shadowrun_hostile_cycle_reaction'],s['shadowrun_player_damage_hp'],s['shadowrun_burst_rng']];expected=[1,3,b[0x14c],w(b,0xf9f8)];assert actual==expected and s['shadowrun_hostile_motion_state']==2
m.call('shadowrun_hostile_cycle_tick');s2=m.snapshot();assert s2['shadowrun_hostile_cycle_supported']==0 and s2['shadowrun_player_damage_hp']==0 and s2['shadowrun_burst_rng']==expected[3]
out=Path(args.output);out.mkdir(mode=0o700,parents=True)
source=ROOT/'src/fdisbull/game_sources/shadowrun_hostile_cycle.c'
result={'status':'passed','capture_receipt_sha256':receipt_hash,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_frame_before':6241,'source_frame_after':6242,'player_hp_before':a[0x14c],'player_hp_after':b[0x14c],'rng_before':w(a,0xf9f8),'rng_after':w(b,0xf9f8),'terminal_handoff':3,'later_cycle_refused':True,'scope':'Assisted original source capture; target/projectile positions and terrain supplied from capture only as comparison inputs. Death animation, game-over behavior and full-frame parity are not modeled.'}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
