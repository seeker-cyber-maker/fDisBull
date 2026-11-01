#!/usr/bin/env python3
"""Compare one explicitly serviced captured actor state to the next source frame."""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.game_il import canonical
from fdisbull.shadowrun_ai_play import actor_service_from_capture
from fdisbull.shadowrun_replay import _read_rom, _source_capture
from fdisbull.udl_shadowrun import ROM_SHA256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',required=True)
    parser.add_argument('--capture',required=True,help='receipt-bound source frame 5999 directory')
    parser.add_argument('--next-capture',required=True,help='next frame of the same source run')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    rom=_read_rom(args.rom)
    identity,arrays,_=_source_capture(args.next_capture,ROM_SHA256)
    if (identity['frame']!=6000 or identity['capture_json_sha256']!=
            'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c'):
        raise ValueError('Expected next frame from the same reviewed capture')
    raw=arrays['ram']; memory=bytes(raw[i^1] for i in range(len(raw)))
    machine=actor_service_from_capture(rom,args.capture)
    for slot in range(3): machine.call('shadowrun_ai_service_slot',slot)
    state=machine.snapshot()
    fields=(('shadowrun_target_x',0),('shadowrun_target_y',4),
            ('shadowrun_ai_slot_heading',0x2e),('shadowrun_ai_slot_move_state',0x38),
            ('shadowrun_ai_slot_collision_state',0xb8),('shadowrun_ai_slot_speed',0xca),
            ('shadowrun_ai_slot_animation',0x16))
    result=[]
    for slot in range(3):
        base=0x400+slot*0x100
        comparisons={name:state[name][slot]==int.from_bytes(memory[base+offset:base+offset+2],'big')
                     for name,offset in fields}
        comparisons['corners']=state['shadowrun_ai_slot_corners'][slot*4:slot*4+4]==list(memory[base+0xd0:base+0xd4])
        comparisons['event_flags']=state['shadowrun_target_flags_b0'][slot]==memory[base+0xb0]
        comparisons['supported']=state['shadowrun_ai_slot_status'][slot]==1
        result.append({'slot':slot,'fields':comparisons})
    if not all(all(x['fields'].values()) for x in result):
        raise ValueError('Actor service differs from source frame: '+repr(result))
    receipt={'format':'fdisbull-shadowrun-actor-service-comparison-1',
             'program_sha256':hashlib.sha256(canonical(machine.program)).hexdigest(),
             'source_rom_sha256':hashlib.sha256(rom).hexdigest(),
             'capture_json_sha256':identity['capture_json_sha256'],
             'source_frames':[5999,6000], 'actors':result,
             'scope':'one explicit clear-terrain service per actor; not scheduler, AI, native execution or fire'}
    Path(args.output).write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__': main()
