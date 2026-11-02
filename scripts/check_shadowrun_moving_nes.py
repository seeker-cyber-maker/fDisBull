#!/usr/bin/env python3
"""Compare the assisted moving-arena NES to its shared, source-checked model."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser()
    for name in ('rom','capture','build','run','source-check','output'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);model=assisted_arena_from_capture(rom,a.capture,moving=True)
    build=json.loads((a.build/'play-receipt.json').read_text());source_raw=a.source_check.read_bytes();source=json.loads(source_raw)
    receipt_raw=(a.run/'receipt.json').read_bytes();receipt=json.loads(receipt_raw);trace=(a.run/'ram_trace.json').read_bytes()
    if (build['arena_preset']!='moving' or build['program_sha256']!=sha(canonical(model.program)) or
        source['program_sha256']!=build['program_sha256'] or source['matched_frames']<50 or
        build['output_sha256']!=sha((a.build/'play.nes').read_bytes()) or receipt['rom_sha256']!=build['output_sha256'] or
        receipt['ram_trace_sha256']!=sha(trace) or receipt['core_sha256']!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or
        receipt['inputs']!=[{'start':86,'end':322,'buttons':['LEFT']}] or receipt['patches']):
        raise ValueError('Native/source provenance mismatch')
    fields=(('shadowrun_player_x',4,2),('shadowrun_player_y',6,2),('shadowrun_camera_x',14,2),('shadowrun_camera_y',16,2),
        ('shadowrun_arena_hp',84,1),('shadowrun_arena_frame_status',85,1),('shadowrun_arena_player_ready',86,1),
        ('shadowrun_arena_burst_active',87,1),('shadowrun_hostile_ammo',88,1),('shadowrun_burst_x',90,4),
        ('shadowrun_burst_y',94,4),('shadowrun_burst_rng',98,2),('shadowrun_burst_anim_word',100,2),
        ('shadowrun_burst_counter',102,1),('shadowrun_burst_lifetime',103,1),('shadowrun_reaction_animation',104,2),
        ('shadowrun_reaction_counter',106,1),('shadowrun_reaction_action_timer',107,2),('shadowrun_attack_animation',109,2),
        ('shadowrun_attack_service_timer',111,2),('shadowrun_attack_action_timer',113,2),('shadowrun_attack_counter',115,1),
        ('shadowrun_attack_callback',116,4),('shadowrun_hostile_x',120,2),('shadowrun_hostile_y',122,2))
    prev=count=0;first=last=None;published=None;stopped=False
    for row in json.loads(trace)['frames']:
        data=bytes.fromhex(row['raw']['state'])
        if len(data)<125:raise ValueError('Missing native boundary latch')
        if stopped:
            if not data[124] or data[:124]!=published[:124]:raise ValueError('Native resumed after boundary')
            continue
        if data[:2]==b'SW' and not data[22]&1 and data[124]:
            if published is None or data[:124]!=published[:124]:raise ValueError('Unsupported tick changed completed publication')
            model.call('shadowrun_arena_frame',0);state=model.snapshot()
            if state['shadowrun_arena_frame_status']!=2:raise ValueError('Native stop was not a model boundary')
            stopped=True;continue
        if data[:2]!=b'SW' or data[22]&1 or data[23]==prev:continue
        if data[23]!=(prev+1)&255 or data[3]:raise ValueError('Publication gap or source ROM fault')
        prev=data[23];count+=1;model.call('shadowrun_arena_frame',4 if 2<=count<=41 else 0);state=model.snapshot()
        errors=[(n,int.from_bytes(data[o:o+w],'little'),state[n]) for n,o,w in fields if int.from_bytes(data[o:o+w],'little')!=state[n]]
        if errors:raise ValueError(f'Native mismatch at tick {count}: {errors}')
        if first is None:first=row['frame']
        last=row['frame'];published=data
    if count!=124 or not stopped:
        raise ValueError(f'Expected 124 completed ticks and an unpublished attempted stop; got {count}')
    if a.output.exists():raise ValueError('Output already exists')
    a.output.write_text(json.dumps({'status':'passed','nes_sha256':build['output_sha256'],
        'program_sha256':build['program_sha256'],'source_comparison_sha256':sha(source_raw),
        'native_receipt_sha256':sha(receipt_raw),'native_trace_sha256':sha(trace),
        'matched_ticks':count,'attempted_stop_tick':count+1,'unsupported_tick_published':False,'first_physical_frame':first,'last_physical_frame':last,
        'scope':'assisted moving arena, player and enemy position, shots, HP, recovery and explicit unsupported stop',
        'excluded':['natural encounter','real-time parity','death continuation']},indent=2)+'\n')

if __name__=='__main__':main()
