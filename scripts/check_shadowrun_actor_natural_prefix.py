#!/usr/bin/env python3
"""Compare an ordinary combat-route prefix and report its first unsupported actor."""
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
    for name in ('rom','capture','original-native','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);machine=actor_service_from_capture(rom,a.capture)
    first,arrays,_=_source_capture(a.original_native/'scene-005999',ROM_SHA256)
    if first['capture_json_sha256']!='d9c8e708d3e7f16785747c0356b0b271dba6f1d942e05fd64f10cf878753e6fa' or hashlib.sha256(arrays['ram']).hexdigest()!='b5872bdca05e98203f81cd5bdfdd4dd82d8a9f516ee694be01a15d1ba0ce0417':
        raise ValueError('Unexpected natural route or initial source state')
    checked=[];stop=None
    for frame in range(6000,6122):
        pad=4 if frame<6060 else 1 if 6080<=frame<=6100 else 16 if frame==6120 else 0
        machine.call('shadowrun_ai_overlap_refresh');machine.set_state({'shadowrun_ai_overlap_slot':0});machine.call('shadowrun_ai_overlap_check_one')
        if not machine.snapshot()['shadowrun_ai_overlap_supported']:
            stop={'frame':frame,'reason':'player overlap not modeled'};break
        machine.call('shadowrun_play_frame',pad)
        for slot in range(3):
            machine.call('shadowrun_ai_overlap_refresh');machine.set_state({'shadowrun_ai_overlap_slot':slot+3});machine.call('shadowrun_ai_overlap_check_one')
            if not machine.snapshot()['shadowrun_ai_overlap_supported']:
                stop={'frame':frame,'slot':slot,'reason':'actor overlap not modeled'};break
            machine.call('shadowrun_ai_outer_slot',slot)
            if machine.snapshot()['shadowrun_ai_slot_status'][slot]!=1:
                stop={'frame':frame,'slot':slot,'reason':'actor service refused'};break
        if stop:break
        machine.call('shadowrun_target_refresh');state=machine.snapshot()
        if frame in (6059,6079,6100,6119,6120,6121):
            identity,arrays,_=_source_capture(a.original_native/f'scene-{frame:06}',ROM_SHA256)
            if identity['capture_json_sha256']!=first['capture_json_sha256']:raise ValueError('Capture changed')
            raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
            word=lambda x:int.from_bytes(memory[x:x+2],'big')
            expected=[(word(0x400+i*256),word(0x404+i*256)) for i in range(3)]
            actual=list(zip(state['shadowrun_target_x'][:3],state['shadowrun_target_y'][:3]))
            if actual!=expected or (state['shadowrun_player_x'],state['shadowrun_player_y'])!=(word(0x100),word(0x104)):
                raise ValueError(f'Position mismatch at {frame}')
            pointer=int.from_bytes(memory[0x1a2:0x1a6],'big')
            expected_selection=255 if pointer==0 else (pointer-0xff0400)//256
            if state['shadowrun_target_selected']!=expected_selection:
                raise ValueError(f'Target selection mismatch at {frame}')
            checked.append(frame)
    if checked!=[6059,6079,6100,6119,6120,6121] or stop is not None:
        raise ValueError(f'Unexpected comparison boundary: {checked}, {stop}')
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-natural-actor-prefix-1',
        'program_sha256':hashlib.sha256(canonical(machine.program)).hexdigest(),
        'source_capture_sha256':first['capture_json_sha256'], 'matched_position_frames':checked,
        'first_unsupported':stop,'scope':'ordinary source route prefix; no extrapolation beyond refusal'},indent=2)+'\n')


if __name__=='__main__':main()
