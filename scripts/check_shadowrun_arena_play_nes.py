#!/usr/bin/env python3
"""Compare completed assisted-arena NES publications to shared GameIL."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom


def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('rom','capture','build','run','source-check','output'):p.add_argument('--'+n,required=True,type=Path)
    p.add_argument('--held-check',type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);model=assisted_arena_from_capture(rom,a.capture)
    build=json.loads((a.build/'play-receipt.json').read_text());original_raw=a.source_check.read_bytes();original=json.loads(original_raw)
    receipt_raw=(a.run/'receipt.json').read_bytes();receipt=json.loads(receipt_raw);trace=(a.run/'ram_trace.json').read_bytes()
    held=bool(a.held_check)
    if held:
        held_raw=a.held_check.read_bytes();held_original=json.loads(held_raw)
        if held_original.get('program_sha256')!=build['program_sha256'] or len(held_original.get('checked_frames',[]))!=15:
            raise ValueError('Held-A source comparison mismatch')
    expected_inputs=[{'start':152,'end':950,'buttons':['A']}] if held else []
    if (build['program_sha256']!=sha(canonical(model.program)) or original['program_sha256']!=build['program_sha256'] or
        original.get('matching_dense_frames')!=61 or original.get('matching_later_checkpoints')!=[6070,6079] or build['output_sha256']!=sha((a.build/'play.nes').read_bytes()) or
        receipt['rom_sha256']!=build['output_sha256'] or receipt['ram_trace_sha256']!=sha(trace) or
        receipt['core_sha256']!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or receipt['inputs']!=expected_inputs or receipt['patches']):
        raise ValueError('Arena native/source provenance mismatch')
    fields=(('shadowrun_player_x',4,2),('shadowrun_player_y',6,2),('shadowrun_camera_x',14,2),('shadowrun_camera_y',16,2),
            ('shadowrun_play_ammo',34,1),('shadowrun_play_shot_timer',53,2),('shadowrun_target_selected',55,1),
            ('shadowrun_field_rng',51,2),('shadowrun_linked_motion_state',71,1),
            ('shadowrun_linked_x_fixed',75,4),('shadowrun_linked_y_fixed',79,4),
            ('shadowrun_arena_hp',84,1),('shadowrun_arena_frame_status',85,1),('shadowrun_arena_player_ready',86,1),
            ('shadowrun_arena_burst_active',87,1),('shadowrun_hostile_ammo',88,1),
            ('shadowrun_burst_x',90,4),('shadowrun_burst_y',94,4),('shadowrun_burst_rng',98,2),
            ('shadowrun_burst_anim_word',100,2),('shadowrun_burst_counter',102,1),('shadowrun_burst_lifetime',103,1),
            ('shadowrun_reaction_animation',104,2),('shadowrun_reaction_counter',106,1),('shadowrun_reaction_action_timer',107,2),
            ('shadowrun_attack_animation',109,2),('shadowrun_attack_service_timer',111,2),('shadowrun_attack_action_timer',113,2),
            ('shadowrun_attack_counter',115,1),('shadowrun_attack_callback',116,4))
    previous=0;count=0;first=None;last=None;published=None;stopped=False
    for row in json.loads(trace)['frames']:
        state=bytes.fromhex(row['raw']['state'])
        if len(state)<125:raise ValueError('Missing native boundary latch')
        if stopped:
            if not state[124] or state[:124]!=published[:124]:raise ValueError('Native resumed after boundary')
            continue
        if state[:2]==b'SW' and not state[22]&1 and state[124]:
            if published is None or state[:124]!=published[:124]:raise ValueError('Unsupported tick changed completed publication')
            model.call('shadowrun_arena_frame',64 if held and count>=13 else 0);expected=model.snapshot()
            if expected['shadowrun_arena_frame_status']!=2:raise ValueError('Native stop was not a model boundary')
            stopped=True;continue
        if state[:2]!=b'SW' or state[22]&1 or state[23]==previous:continue
        if state[23]!=(previous+1)&255 or state[3]:raise ValueError('Missing tick or source-table lookup fault')
        model.call('shadowrun_arena_frame',64 if held and count>=13 else 0);expected=model.snapshot();previous=state[23];count+=1
        errors=[(n,int.from_bytes(state[o:o+w],'little'),expected[n]) for n,o,w in fields
                if int.from_bytes(state[o:o+w],'little')!=expected[n]]
        if state[89]!=expected['shadowrun_play_actor_hp'][0]:errors.append(('hostile_hp',state[89],expected['shadowrun_play_actor_hp'][0]))
        if errors:raise ValueError(f'NES mismatch at physical frame {row["frame"]}: {errors}')
        if first is None:first=row['frame']
        last=row['frame'];published=state
    if count<80 or not stopped:raise ValueError(f'Expected at least 80 completed modeled ticks and an unpublished stop, got {count}')
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-arena-play-nes-1','program_sha256':build['program_sha256'],
        'nes_sha256':build['output_sha256'],'source_comparison_sha256':sha(original_raw),
        'native_receipt_sha256':sha(receipt_raw),'native_trace_sha256':sha(trace),
        'matched_source_dense_ticks':61,'source_later_ticks':[71,80],'matched_model_native_ticks':count,
        'held_source_comparison_sha256':sha(held_raw) if held else None,
        'explicit_stop_tick':count+1,'unsupported_tick_published':False,'first_physical_frame':first,'last_physical_frame':last,
        'scope':('assisted stationary held-A route; original checkpoints and native/model ticks' if held else
                 'assisted stationary no-input arena through second hostile shot; source sparse after tick61; later service stops; no complete gameplay claim')},indent=2)+'\n')


if __name__=='__main__':main()
