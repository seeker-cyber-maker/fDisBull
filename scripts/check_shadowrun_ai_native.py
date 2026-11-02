#!/usr/bin/env python3
"""Compare completed directional-actor publications with the shared model."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_ai_play import actor_service_from_capture
from fdisbull.shadowrun_replay import _read_rom


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','capture','build','run','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom)
    machine=actor_service_from_capture(rom,a.capture)
    build=json.loads((a.build/'play-receipt.json').read_text()); rr=(a.run/'receipt.json').read_bytes();receipt=json.loads(rr)
    trace=(a.run/'ram_trace.json').read_bytes()
    if (build['program_sha256']!=sha(canonical(machine.program)) or
        build['output_sha256']!=sha((a.build/'play.nes').read_bytes()) or
        receipt['rom_sha256']!=build['output_sha256'] or receipt['ram_trace_sha256']!=sha(trace) or
        receipt['core_sha256']!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or
        receipt['patches'] or receipt['inputs']!=[{'start':100,'end':160,'buttons':['RIGHT']}]):
        raise ValueError('Native comparison provenance mismatch')
    rows=json.loads(trace)['frames'];last=0;count=0;first=None;final=None
    for row in rows:
        raw=bytes.fromhex(row['raw']['state'])
        if raw[:2]!=b'SW' or raw[22]&1 or raw[23]==last:continue
        if raw[23]!=(last+1)&255:raise ValueError('Missing a completed logical publication')
        if raw[3]:raise ValueError('Native ROM lookup fault')
        machine.call('shadowrun_ai_frame',raw[10]&15)
        state=machine.snapshot();last=raw[23];count+=1
        for slot in range(3):
            i=84+slot*5
            actual=(raw[i],int.from_bytes(raw[i+1:i+3],'little'),int.from_bytes(raw[i+3:i+5],'little'))
            expected=(state['shadowrun_ai_slot_status'][slot],state['shadowrun_target_x'][slot],state['shadowrun_target_y'][slot])
            if actual!=expected:raise ValueError(f'Actor mismatch at physical frame {row["frame"]}, slot {slot}')
        for name,offset in (('shadowrun_player_x',4),('shadowrun_player_y',6),('shadowrun_camera_x',14),('shadowrun_camera_y',16)):
            if int.from_bytes(raw[offset:offset+2],'little')!=state[name]:
                raise ValueError(f'{name} mismatch at physical frame {row["frame"]}')
        if first is None:first=row['frame']
        final=row['frame']
    if count<1:raise ValueError('No completed publications')
    if a.output.exists():raise ValueError('output already exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-ai-native-comparison-1',
        'program_sha256':build['program_sha256'],'rom_sha256':build['output_sha256'],
        'native_receipt_sha256':sha(rr),'native_trace_sha256':sha(trace),
        'logical_ticks':count,'first_physical_frame':first,'last_physical_frame':final,
        'sampled_input':'published source-normalized direction bits',
        'scope':'directional captured actors only; no attack, menus, general AI or real-time parity'},indent=2)+'\n')


if __name__=='__main__':main()
