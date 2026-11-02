#!/usr/bin/env python3
"""Compare second original hostile launch, first impact and two RNG phases."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,author_program,canonical
from fdisbull.shadowrun_hostile import lift_hostile
from fdisbull.shadowrun_hostile_motion import lift_hostile_motion
from fdisbull.shadowrun_player_damage import lift_player_damage
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
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or len(r['patches'])!=5 or any(x['frame']!=6000 or x['memory_id']!=2 for x in r['patches']) or {(x['offset'],len(x['data_hex'])//2) for x in r['patches']}!=expected:raise ValueError('source or injection mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=frame(6164);after=frame(6165);actor=before[0x400:0x500];player=after[0x100:0x200];pr=after[0xb00:0xc00]
 if (w(actor,14),actor[0x10],actor[0x4e],w(actor,0xdc),w(actor,0xb6),l(actor,0xa2),player[0x4c],player[0x76],w(before,0xf9f8))!=(8,5,46,65535,0,0xff0100,3,1,36416):raise ValueError('prelaunch mismatch')
 if any(before[0xb10+i*256]&1 for i in range(6)) or before[0x1700:0x2200]!=after[0x1700:0x2200]:raise ValueError('allocator or terrain mismatch')
 trace=(root/'native/ram-writes.json').read_bytes()
 if sha(trace)!=cap['files']['native/ram-writes.json']['sha256']:raise ValueError('writer trace mismatch')
 lift_hostile(rom);lift_hostile_motion(rom);lift_player_damage(rom)
 base=ROOT/'src/fdisbull/game_sources';names=['shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_hostile.c','shadowrun_hostile_motion.c','shadowrun_player_damage.c'];chunks=[(base/n).read_bytes() for n in names]
 stub='typedef unsigned char u8; typedef unsigned int u16; u16 shadowrun_target_x[7],shadowrun_target_y[7]; u8 shadowrun_target_flags[7],shadowrun_play_actor_hp[7];'
 source='\n'.join('\n'.join(line for line in c.decode().splitlines() if not line.startswith('extern ')) for c in chunks[:2])+ '\n'+stub+'\n'+'\n'.join('\n'.join(line for line in c.decode().splitlines() if not line.startswith('extern ')) for c in chunks[2:])
 prog=author_program(source,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}]);m=GameMachine(prog,{0:rom});records=[before[0x400+i*256:0x500+i*256] for i in range(7)]
 m.set_state({'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_min':w(before,0xddd6),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_min':w(before,0xddd8),'shadowrun_y_max':w(before,0xddd4),'shadowrun_target_x':[w(x,0) for x in records],'shadowrun_target_y':[w(x,4) for x in records],'shadowrun_target_flags':[x[0x10] for x in records],'shadowrun_play_actor_hp':[x[0x4c] for x in records], 'shadowrun_hostile_profile':1,'shadowrun_hostile_x':w(actor,0),'shadowrun_hostile_y':w(actor,4),'shadowrun_hostile_player_x':w(player,0),'shadowrun_hostile_player_y':w(player,4),'shadowrun_hostile_ammo':actor[0x4e],'shadowrun_hostile_contact':w(actor,0xc),'shadowrun_hostile_rng':w(before,0xf9f8),'shadowrun_hostile_target_existing':1,'shadowrun_hostile_timer':w(actor,0xb6),'shadowrun_hostile_cooldown':w(actor,0xdc)})
 m.call('shadowrun_hostile_tick');s=m.snapshot()
 if not s['shadowrun_hostile_supported'] or not s['shadowrun_hostile_fired'] or s['shadowrun_hostile_effect']!=1 or s['shadowrun_hostile_ammo']!=45:raise AssertionError(('launch',s['shadowrun_hostile_supported'],s['shadowrun_hostile_rng'],s['shadowrun_hostile_effect']))
 m.set_state({'shadowrun_hostile_motion_profile':1,'shadowrun_hostile_motion_state':1,'shadowrun_hostile_motion_x':s['shadowrun_hostile_projectile_x']*65536,'shadowrun_hostile_motion_y':s['shadowrun_hostile_projectile_y']*65536,'shadowrun_hostile_motion_vx':s['shadowrun_hostile_velocity_x'],'shadowrun_hostile_motion_vy':s['shadowrun_hostile_velocity_y'],'shadowrun_hostile_motion_lifetime':s['shadowrun_hostile_lifetime'],'shadowrun_hostile_motion_effect':s['shadowrun_hostile_effect'],'shadowrun_hostile_motion_player_x':w(player,0),'shadowrun_hostile_motion_player_y':w(player,4)})
 m.call('shadowrun_hostile_motion_tick');t=m.snapshot()
 if not t['shadowrun_hostile_motion_supported'] or t['shadowrun_hostile_motion_state']!=2:raise AssertionError('original player contact not reached')
 m.set_state({'shadowrun_player_damage_profile':1,'shadowrun_player_damage_item':10,'shadowrun_player_damage_effect':s['shadowrun_hostile_effect'],'shadowrun_player_damage_armor':player[0x76],'shadowrun_player_damage_hp':before[0x14c],'shadowrun_player_damage_rng':s['shadowrun_hostile_rng']})
 m.call('shadowrun_player_hit');u=m.snapshot()
 got=(t['shadowrun_hostile_motion_x'],t['shadowrun_hostile_motion_y'],t['shadowrun_hostile_motion_lifetime'],u['shadowrun_player_damage_hp'],u['shadowrun_player_damage_rng'])
 exp=(l(pr,0),l(pr,4),pr[0x89],after[0x14c],w(after,0xf9f8))
 if not u['shadowrun_player_damage_supported'] or u['shadowrun_player_damage_depleted'] or got!=exp:raise AssertionError((got,exp))
 result={'status':'passed','cases':1,'launch_frame':6165,'rng_before':36416,'rng_after_attack':s['shadowrun_hostile_rng'],'rng_after_defense':u['shadowrun_player_damage_rng'],'player_hp_before':before[0x14c],'player_hp_after':u['shadowrun_player_damage_hp'],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'writer_trace_sha256':sha(trace),'authoring_sha256':[sha(c) for c in chunks],'program_sha256':sha(canonical(prog)),'scope':'assisted source-constructed moving-origin hostile relaunch and same-frame player impact; player position after its source movement supplied; no natural encounter claim'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
