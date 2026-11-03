#!/usr/bin/env python3
"""Compare bounded lifetime-expiry continuation against original frames."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_expiry_cycle import SOURCE,lift_hostile_expiry_cycle
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
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=frame(6050);after=frame(6051);pr=before[0xb00:0xc00];ar=after[0xb00:0xc00]
 if (pr[0x89],pr[0x9f],pr[0x10],pr[0x11],w(before,0xf9f8))!=(0,0,1,1,42588):raise ValueError('expiry seed mismatch')
 prog=lift_hostile_expiry_cycle(rom);m=GameMachine(prog,{0:rom});targets=[after[0x400+i*256:0x500+i*256] for i in range(7)]
 m.set_state({'shadowrun_burst_profile':1,'shadowrun_burst_x':l(pr,0),'shadowrun_burst_y':l(pr,4),'shadowrun_burst_vx':w(pr,0x4c),'shadowrun_burst_vy':w(pr,0x4e),'shadowrun_burst_counter':pr[0x41],'shadowrun_burst_flags':pr[0x10],'shadowrun_burst_flags_low':pr[0x11],'shadowrun_burst_lifetime':pr[0x89],'shadowrun_burst_effect':pr[0x9f],'shadowrun_burst_rng':w(before,0xf9f8),'shadowrun_burst_anim_word':w(pr,0x16),'shadowrun_burst_anim_increment':w(pr,0x18),'shadowrun_burst_anim_accumulator':w(pr,0x1a),'shadowrun_burst_anim_threshold':w(pr,0x1c),'shadowrun_burst_anim_index':w(pr,0x1e),'shadowrun_player_damage_hp':before[0x14c],'shadowrun_x_min':w(after,0xddd6),'shadowrun_x_max':w(after,0xddd2),'shadowrun_y_min':w(after,0xddd8),'shadowrun_y_max':w(after,0xddd4),'shadowrun_terrain_map':list(after[0x1700:0x2200]),'shadowrun_hostile_motion_player_x':w(after,0x100),'shadowrun_hostile_motion_player_y':w(after,0x104),'shadowrun_target_x':[w(t,0) for t in targets],'shadowrun_target_y':[w(t,4) for t in targets],'shadowrun_target_flags':[t[0x10] for t in targets],'shadowrun_play_actor_hp':[t[0x4c] for t in targets]})
 m.call('shadowrun_hostile_expiry_cycle');s=m.snapshot();keys=('x','y','vx','vy','flags','flags_low','counter','lifetime','effect','anim_word','anim_increment','anim_accumulator','anim_index')
 got=tuple(s['shadowrun_burst_'+k] for k in keys)+(s['shadowrun_player_damage_hp'],s['shadowrun_burst_rng'])
 exp=(l(ar,0),l(ar,4),w(ar,0x4c),w(ar,0x4e),ar[0x10],ar[0x11],ar[0x41],ar[0x89],ar[0x9f],w(ar,0x16),w(ar,0x18),w(ar,0x1a),w(ar,0x1e),after[0x14c],w(after,0xf9f8))
 if not s['shadowrun_hostile_expiry_supported'] or got!=exp:raise AssertionError((got,exp,s['shadowrun_hostile_motion_state']))
 result={'status':'passed','source_transition':[6050,6051],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted ordinary retreat, source player/actor positions supplied to projectile collision; zero-effect lifetime expiry and one sprite pass, future burst separate'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
