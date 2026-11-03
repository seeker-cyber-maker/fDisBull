#!/usr/bin/env python3
"""Compare held-A assisted arena input against original captured checkpoints."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom, _source_capture
from fdisbull.udl_shadowrun import ROM_SHA256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('rom','capture','original-native','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);m=assisted_arena_from_capture(rom,a.capture)
    capture_sha='a4b1f40b59b3c3d035e96b6e079ec038e8bc8967a67d0a8acd8a18dcd5743563'
    checkpoints=(6000,6011,6012,6013,6014,6029,6030,6041,6042,6043,6044,6050,6060,6070,6079)
    common=(('shadowrun_arena_hp',0x14c,1),('shadowrun_hostile_rng',0xf9f8,2),
            ('shadowrun_hostile_ammo',0x44e,1),('shadowrun_play_ammo',0x14e,1),
            ('shadowrun_attack_callback',0x43a,4),('shadowrun_attack_animation',0x416,2),
            ('shadowrun_attack_service_timer',0x4b6,2),('shadowrun_attack_action_timer',0x4dc,2),
            ('shadowrun_attack_counter',0x4b5,1))
    projectile=(('shadowrun_linked_x_fixed',0xc00,4),('shadowrun_linked_y_fixed',0xc04,4),
                ('shadowrun_play_shot_timer',0x1dc,2))
    checked=[]
    for f in range(6000,6080):
        m.call('shadowrun_arena_frame',64 if f>=6013 else 0);state=m.snapshot()
        if state['shadowrun_arena_frame_status']!=1:raise ValueError(f'Model refused frame {f}')
        if f not in checkpoints:continue
        identity,arrays,_=_source_capture(a.original_native/f'scene-{f:06}',ROM_SHA256)
        if identity['frame']!=f or identity['capture_json_sha256']!=capture_sha:raise ValueError('Unexpected original capture')
        raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
        fields=common+(projectile if f in (6043,6044,6050) else ())
        errors=[(n,state[n],int.from_bytes(memory[o:o+w],'big')) for n,o,w in fields
                if state[n]!=int.from_bytes(memory[o:o+w],'big')]
        if f>=6043 and (state['shadowrun_field_first_slot'],state['shadowrun_field_second_slot'])!=(10,11):
            errors.append(('allocated_slots',state['shadowrun_field_first_slot'],state['shadowrun_field_second_slot']))
        if state['shadowrun_play_actor_hp'][0]!=memory[0x44c]:errors.append(('hostile_hp',state['shadowrun_play_actor_hp'][0],memory[0x44c]))
        if errors:raise ValueError(f'Source mismatch at {f}: {errors}')
        checked.append(f)
    if tuple(checked)!=checkpoints:raise ValueError('Missing source checkpoints')
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-arena-return-fire-1',
        'source_sha256':hashlib.sha256(rom).hexdigest(),'program_sha256':hashlib.sha256(canonical(m.program)).hexdigest(),
        'source_capture_sha256':capture_sha,'checked_frames':checked,'player_input':'A held frames 6013–6079',
        'player_ammo':[12,11],'hostile_hp':[10,10],'source_slots':[10,11],
        'scope':'assisted stationary encounter checkpoints; overlapping enemy impact-wait and player projectile; no natural encounter or general concurrency claim'},indent=2)+'\n')


if __name__=='__main__':main()
