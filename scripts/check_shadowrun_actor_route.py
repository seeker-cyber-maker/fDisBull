#!/usr/bin/env python3
"""Compare a bounded ordinary-direction route against source actor snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_ai_play import actor_service_from_capture
from fdisbull.shadowrun_replay import _read_rom, _source_capture
from fdisbull.udl_shadowrun import ROM_SHA256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',required=True);p.add_argument('--native',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    rom=_read_rom(a.rom);machine=actor_service_from_capture(rom,a.native/'scene-005999')
    fields=(('shadowrun_target_x',0),('shadowrun_target_y',4),('shadowrun_target_contact',12),
            ('shadowrun_ai_slot_heading',0x2e),('shadowrun_ai_slot_target_heading',0x34),
            ('shadowrun_ai_slot_distance',0xc8),('shadowrun_ai_slot_service_timer',0xb6))
    global_fields=(('shadowrun_player_x',0x100),('shadowrun_player_y',0x104),
                   ('shadowrun_camera_x',0xddc6),('shadowrun_camera_y',0xddc8))
    source_hash='b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c'
    for frame in range(6000,6060):
        machine.call('shadowrun_ai_frame',8)
        identity,arrays,_=_source_capture(a.native/f'scene-{frame:06}',ROM_SHA256)
        if identity['frame']!=frame or identity['capture_json_sha256']!=source_hash:
            raise ValueError('Source frame identity changed')
        raw=arrays['ram'];mem=bytes(raw[i^1] for i in range(len(raw)))
        word=lambda n:int.from_bytes(mem[n:n+2],'big')
        state=machine.snapshot()
        failures=[(i,name,state[name][i],word(0x400+i*256+offset))
                  for i in range(3) for name,offset in fields
                  if state[name][i]!=word(0x400+i*256+offset)]
        failures += [(name,state[name],word(offset)) for name,offset in global_fields if state[name]!=word(offset)]
        if failures or state['shadowrun_ai_slot_status'][:3]!=[1,1,1]:
            raise ValueError(f'Diverged at source frame {frame}: {failures}')
    receipt={'format':'fdisbull-shadowrun-actor-route-1',
             'source_rom_sha256':hashlib.sha256(rom).hexdigest(),
             'program_sha256':hashlib.sha256(canonical(machine.program)).hexdigest(),
             'capture_json_sha256':source_hash, 'first_frame':6000,'last_frame':6059,
             'source_actor_slots':[0,1,2], 'compared_ticks':60,
             'actor_fields':[name for name,_ in fields], 'other_fields':[name for name,_ in global_fields],
             'scope':'ordinary held Right; bounded calm movement, no actor attacks or waypoint arrival'}
    if a.output.exists():raise ValueError('output already exists')
    a.output.write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
