#!/usr/bin/env python3
"""Check rejected and admitted firing through the actual shared Z runtime."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom
from fdisbull.shadowrun_z import ShadowrunRuntime

def main():
    p=argparse.ArgumentParser()
    for n in ('rom','capture','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);machine=assisted_arena_from_capture(rom,a.capture)
    for frame in range(6000,6043):
        machine.call('shadowrun_arena_frame',64 if frame>=6013 else 0)
        if machine.snapshot()['shadowrun_arena_frame_status']!=1:raise ValueError(f'Preparation stopped at {frame}')
    base=machine.snapshot()
    if (base['shadowrun_play_shot_timer'],base['shadowrun_play_ammo'],base['shadowrun_arena_player_pending'])!=(65535,12,1):
        raise ValueError('Expected source-qualified held-A firing boundary')
    checks=[]
    for name,change in (('unequipped',{'shadowrun_play_weapon_slot':127,'shadowrun_play_weapon_item':0}),
                        ('empty_ammo',{'shadowrun_play_ammo':0})):
        candidate=deepcopy(machine);candidate.set_state(change);runtime=ShadowrunRuntime(candidate)
        before=runtime.machine.snapshot();result=runtime.advance(64)
        if result['status']!='unsupported' or result['frames_executed']!=0 or runtime.machine.snapshot()!=before:
            raise ValueError(f'{name} did not reject atomically: {result}')
        direct=deepcopy(candidate);direct.call('shadowrun_arena_frame',64);after=direct.snapshot()
        if (after['shadowrun_arena_frame_status'],after['shadowrun_play_refused'],after['shadowrun_play_shot_timer'],
            after['shadowrun_arena_player_pending'])!=(2,1,65535,1):raise ValueError(f'{name} direct boundary mismatch')
        checks.append(name)
    runtime=ShadowrunRuntime(deepcopy(machine));result=runtime.advance(64);valid=runtime.machine.snapshot()
    if result['status']!='advanced' or valid['shadowrun_play_ammo']!=11 or valid['shadowrun_play_shot_timer']!=51:
        raise ValueError(f'Valid source-qualified shot failed: {result}')
    selector=assisted_arena_from_capture(rom,a.capture);selector.set_state({'shadowrun_target_d1_magic':1})
    runtime=ShadowrunRuntime(selector);before=runtime.machine.snapshot();result=runtime.advance(16)
    if result['status']!='unsupported' or result['frames_executed']!=0 or runtime.machine.snapshot()!=before:
        raise ValueError(f'Unsupported targeting did not roll back: {result}')
    if a.output.exists():raise ValueError('Output exists')
    a.output.write_text(json.dumps({'status':'passed','program_sha256':hashlib.sha256(canonical(machine.program)).hexdigest(),
        'refused_z_transactions':checks+['unsupported_targeting'],'valid_shot_ammo':[12,11],
        'scope':'actual shared arena and Z transaction; prepared held-A boundary and two controlled unsupported inventory variants'},indent=2)+'\n')

if __name__=='__main__':main()
