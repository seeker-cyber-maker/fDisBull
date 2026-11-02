#!/usr/bin/env python3
"""Check the assisted stationary source checkpoints and terminal HP boundary."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom, _source_capture
from fdisbull.udl_shadowrun import ROM_SHA256

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    p=argparse.ArgumentParser()
    for n in ('rom','capture','original','terminal-check','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);m=assisted_arena_from_capture(rom,a.capture)
    receipt=(a.original/'native/receipt.json').read_bytes();terminal=a.terminal_check.read_bytes();t=json.loads(terminal)
    if (sha(receipt)!='6e5acb72551bd9d5ebc3e2e0b4a6b9839729637f311ed8e9e085766c5bd0bc52' or
        sha(terminal)!='592a315e1f594a8fc61bf90304ee757414c15e38634e42e6bd9553b9d154bfab' or
        (t['source_frame_before'],t['source_frame_after'],t['player_hp_after'],t['rng_after'])!=(6241,6242,0,2258)):
        raise ValueError('Unreviewed source evidence')
    fields=(('shadowrun_arena_hp',0x14c,1),('shadowrun_hostile_ammo',0x44e,1),
        ('shadowrun_hostile_rng',0xf9f8,2),('shadowrun_attack_animation',0x416,2),
        ('shadowrun_attack_action_timer',0x4dc,2),('shadowrun_attack_service_timer',0x4b6,2))
    frames=[]
    for frame in range(6000,6243):
        m.call('shadowrun_arena_frame',0);s=m.snapshot()
        if frame<6242 and s['shadowrun_arena_frame_status']!=1:raise ValueError(f'Unexpected stop at {frame}')
        if frame==6241 and (s['shadowrun_arena_hp'],s['shadowrun_hostile_rng'])!=(1,6170):raise ValueError('Pre-hit state mismatch')
        path=a.original/'native'/f'scene-{frame:06}'
        if not path.exists():continue
        identity,arrays,_=_source_capture(path,ROM_SHA256)
        if identity['frame']!=frame or identity['capture_json_sha256']!='20a4b50e0ff750dd4e92e251ca2be31ac9128961dfd12bee0c81e4183bb8220f':raise ValueError('Unexpected source capture')
        raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
        bad=[(n,s[n],int.from_bytes(memory[o:o+w],'big')) for n,o,w in fields if s[n]!=int.from_bytes(memory[o:o+w],'big')]
        if bad:raise ValueError(f'Source mismatch at {frame}: {bad}')
        frames.append(frame)
    if (s['shadowrun_arena_hp'],s['shadowrun_hostile_rng'],s['shadowrun_arena_frame_status'])!=(0,2258,3):raise ValueError('Terminal state mismatch')
    m.call('shadowrun_arena_frame',0);after=m.snapshot()
    if (after['shadowrun_arena_hp'],after['shadowrun_hostile_rng'],after['shadowrun_arena_frame_status'])!=(0,2258,3):raise ValueError('Terminal state advanced')
    if a.output.exists():raise ValueError('Output exists')
    a.output.write_text(json.dumps({'status':'passed','program_sha256':sha(canonical(m.program)),
        'original_receipt_sha256':sha(receipt),'terminal_component_sha256':sha(terminal),'checked_frames':frames,
        'terminal_frame':6242,'terminal_hp':0,'terminal_rng':2258,
        'scope':'assisted stationary source checkpoints and terminal damage handoff; original death continuation excluded'},indent=2)+'\n')

if __name__=='__main__':main()
