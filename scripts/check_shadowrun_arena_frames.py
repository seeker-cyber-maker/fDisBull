#!/usr/bin/env python3
"""Compare the bounded, no-input assisted arena through hostile idle."""
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
    for name in ('rom','capture','original-native','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);machine=assisted_arena_from_capture(rom,a.capture)
    identity_hash='848cc21f3dc8bbfeac991b6af9a7b73ad21ba362a2f709db33c1d9e94b3e1f95'
    proj=(('shadowrun_burst_x',0xb00,4),('shadowrun_burst_y',0xb04,4),
          ('shadowrun_burst_heading',0xb2e,2),('shadowrun_burst_flags',0xb10,1),
          ('shadowrun_burst_flags_low',0xb11,1),('shadowrun_burst_counter',0xb41,1),
          ('shadowrun_burst_lifetime',0xb89,1),('shadowrun_burst_effect',0xb9f,1),
          ('shadowrun_burst_anim_word',0xb16,2),('shadowrun_burst_anim_increment',0xb18,2),
          ('shadowrun_burst_anim_accumulator',0xb1a,2),('shadowrun_burst_anim_index',0xb1e,2),
          ('shadowrun_hostile_rng',0xf9f8,2),('shadowrun_arena_hp',0x14c,1))
    reaction=(('shadowrun_reaction_animation',0x116,2),('shadowrun_reaction_increment',0x118,2),
              ('shadowrun_reaction_accumulator',0x11a,2),('shadowrun_reaction_index',0x11e,2),
              ('shadowrun_reaction_counter',0x1ce,1),('shadowrun_reaction_action_timer',0x1dc,2))
    actor=(('shadowrun_attack_x',0x400,2),('shadowrun_attack_y',0x404,2),
           ('shadowrun_attack_callback',0x43a,4),('shadowrun_attack_animation',0x416,2),
           ('shadowrun_attack_increment',0x418,2),('shadowrun_attack_accumulator',0x41a,2),
           ('shadowrun_attack_service_timer',0x4b6,2),('shadowrun_attack_action_timer',0x4dc,2),
           ('shadowrun_attack_counter',0x4b5,1))
    checkpoints=[]
    for frame in range(6000,6080):
        machine.call('shadowrun_arena_frame',0);state=machine.snapshot()
        if state['shadowrun_arena_frame_status']!=1:raise ValueError(f'Model refused frame {frame}')
        if frame>6060 and frame not in (6070,6079):continue
        identity,arrays,_=_source_capture(a.original_native/f'scene-{frame:06}',ROM_SHA256)
        if identity['frame']!=frame or identity['capture_json_sha256']!=identity_hash:raise ValueError('Unexpected original capture')
        raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
        fields=proj+actor+(reaction if not state['shadowrun_arena_player_ready'] else (('shadowrun_play_shot_timer',0x1dc,2),))
        errors=[(name,state[name],int.from_bytes(memory[offset:offset+width],'big'))
                for name,offset,width in fields if state[name]!=int.from_bytes(memory[offset:offset+width],'big')]
        if errors:raise ValueError(f'Source mismatch at {frame}: {errors}')
        checkpoints.append(frame)
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-arena-frame-comparison-1',
        'source_sha256':hashlib.sha256(rom).hexdigest(),'program_sha256':hashlib.sha256(canonical(machine.program)).hexdigest(),
        'original_capture_sha256':identity_hash,'first_source_frame':6000,'last_dense_source_frame':6060,
        'matching_dense_frames':61,'matching_later_checkpoints':checkpoints[61:],
        'scope':'assisted stationary no-input source-constructed encounter through second hostile shot; other NPCs removed target-side, audio/graphics not compared'},indent=2)+'\n')


if __name__=='__main__':main()
