#!/usr/bin/env python3
"""Check a controlled same-loop assisted enemy shot against original CPU."""
import argparse
import hashlib
import json
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom
from fdisbull.udl_shadowrun import ROM_SHA256


def sha(x):return hashlib.sha256(x).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','capture','same-loop','reaction-loop','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);machine=assisted_arena_from_capture(rom,a.capture)
    raw=(a.same_loop/'receipt.json').read_bytes();receipt=json.loads(raw)
    if (receipt.get('format')!='fdisbull-genesis-native-boundary-1' or not receipt.get('complete') or
        receipt.get('source_sha256')!=ROM_SHA256 or
        receipt.get('core_sha256')!='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268' or
        receipt.get('cases_completed')!=1 or not receipt.get('inputs_unchanged')):
        raise ValueError('Original boundary receipt is invalid')
    case=receipt['cases'][0];before=(a.same_loop/'ram-before.bin').read_bytes();after=(a.same_loop/'ram-after.bin').read_bytes()
    if len(before)!=65536 or len(after)!=65536 or sha(before)!=case['ram_before_sha256'] or sha(after)!=case['ram_after_sha256']:
        raise ValueError('Original RAM does not match receipt')
    reaction_raw=(a.reaction_loop/'receipt.json').read_bytes();reaction_receipt=json.loads(reaction_raw)
    reaction_after=(a.reaction_loop/'ram-after.bin').read_bytes()
    if (not reaction_receipt.get('complete') or reaction_receipt.get('source_sha256')!=ROM_SHA256 or
        reaction_receipt.get('core_sha256')!='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268' or
        reaction_receipt.get('cases_completed')!=1 or not reaction_receipt.get('inputs_unchanged') or
        sha(reaction_after)!=reaction_receipt['cases'][0]['ram_after_sha256']):
        raise ValueError('Original reaction receipt is invalid')
    word=lambda memory,offset:int.from_bytes(memory[offset:offset+2],'big')
    if (word(before,0x100),word(before,0x104),word(before,0x400),word(before,0x404),before[0x44e],word(before,0xf9f8))!=(15584,11210,16096,11210,48,2):
        raise ValueError('Unexpected assisted actor setup')
    machine.call('shadowrun_arena_same_loop');s=machine.snapshot()
    checks={'supported':s['shadowrun_arena_supported']==1 and s['shadowrun_hostile_fired']==1,
        'ammo':s['shadowrun_hostile_ammo']==after[0x44e], 'rng':s['shadowrun_hostile_rng']==word(after,0xf9f8),
        'heading':s['shadowrun_hostile_heading']==word(after,0xb2e),
        'projectile_x':(s['shadowrun_hostile_motion_x']>>16)==word(after,0xb00),
        'projectile_y':(s['shadowrun_hostile_motion_y']>>16)==word(after,0xb04),
        'lifetime':s['shadowrun_hostile_motion_lifetime']==after[0xb89],
        'effect':s['shadowrun_hostile_motion_effect']==after[0xb9f],
        'player_hp':s['shadowrun_arena_hp']==after[0x14c],
        'burst_unknown':s['shadowrun_hostile_motion_continuation_required']==1,
        'reaction_callback':s['shadowrun_reaction_callback']==int.from_bytes(reaction_after[0x13a:0x13e],'big'),
        'reaction_animation':s['shadowrun_reaction_animation']==word(reaction_after,0x116),
        'reaction_flags':s['shadowrun_reaction_flags_low']==reaction_after[0x111],
        'reaction_counter':s['shadowrun_reaction_counter']==reaction_after[0x1ce],
        'reaction_hp':s['shadowrun_arena_hp']==reaction_after[0x14c]}
    if not all(checks.values()):raise ValueError('Assisted same-loop chain differs: '+repr(checks))
    machine.call('shadowrun_arena_launch')
    if machine.snapshot()['shadowrun_arena_supported']!=0:raise ValueError('Unmodeled burst was not refused')
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-assisted-arena-2',
        'program_sha256':sha(canonical(machine.program)),'source_sha256':sha(rom),
        'original_receipt_sha256':sha(raw),'reaction_receipt_sha256':sha(reaction_raw),
        'checks':checks,'player_hp':[10,s['shadowrun_arena_hp']],
        'scope':'controlled same-loop launch through HP update and separately continued reaction; relocated actor, sound disabled; later burst refused'},indent=2)+'\n')


if __name__=='__main__':main()
