#!/usr/bin/env python3
"""Compare an assisted same-loop enemy-shot diagnostic on FCEUmm and GameIL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from fdisbull.game_il import canonical
from fdisbull.shadowrun_ai_play import emit_reachable_c
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_hostile_linked import SOURCE as LINKED_SOURCE
from fdisbull.shadowrun_replay import _read_rom


def sha(x):return hashlib.sha256(x).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','capture','core','cc65-root','original-check','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--player-launch-check',type=Path)
    p.add_argument('--player-contact-check',type=Path)
    a=p.parse_args();rom=_read_rom(a.rom);core=a.core.read_bytes()
    if sha(core)!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60':raise ValueError('wrong NES core')
    original_raw=a.original_check.read_bytes();original=json.loads(original_raw)
    machine=assisted_arena_from_capture(rom,a.capture)
    if original['program_sha256']!=sha(canonical(machine.program)) or not all(original['checks'].values()):
        raise ValueError('Original comparison differs from current model')
    player=bool(a.player_launch_check or a.player_contact_check)
    if player:
        if not a.player_launch_check or not a.player_contact_check:raise ValueError('Both player-shot source qualifications are required')
        for path in (a.player_launch_check,a.player_contact_check):
            check=json.loads(path.read_text())
            if check.get('status')!='passed' or check.get('rom_sha256')!=sha(rom) or check.get('authoring_sha256')!=sha(LINKED_SOURCE.read_bytes()):
                raise ValueError('Player-shot source qualification mismatch')
        machine.set_state({'shadowrun_target_selected':0})
    initial=machine.snapshot();entry='shadowrun_arena_player_launch' if player else 'shadowrun_arena_same_loop'
    machine.call(entry);expected=machine.snapshot()
    watches=(['shadowrun_arena_player_supported','shadowrun_play_ammo','shadowrun_field_source_effect','shadowrun_hostile_rng',
              'shadowrun_linked_heading','shadowrun_linked_x_fixed','shadowrun_linked_y_fixed',
              'shadowrun_linked_motion_lifetime','shadowrun_linked_motion_state','shadowrun_field_target_hp',
              'shadowrun_player_attack_difficulty'] if player else
             ['shadowrun_arena_supported','shadowrun_arena_hp','shadowrun_hostile_ammo','shadowrun_hostile_rng',
             'shadowrun_hostile_heading','shadowrun_hostile_motion_x','shadowrun_hostile_motion_y',
             'shadowrun_hostile_motion_lifetime','shadowrun_hostile_motion_state','shadowrun_hostile_motion_effect',
             'shadowrun_hostile_motion_continuation_required','shadowrun_reaction_callback','shadowrun_reaction_animation',
             'shadowrun_reaction_flags_low','shadowrun_reaction_counter'])
    if not expected['shadowrun_arena_player_supported' if player else 'shadowrun_arena_supported']:raise ValueError('Reference diagnostic refused')
    native,_=emit_reachable_c(machine.program,roots=[entry])
    out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
    parent=out.parent
    def admit(n):
        r=subprocess.run([sys.executable,'/Users/tiga/.codex/bin/storage_admit.py','--path',str(parent),
                          '--expected-bytes',str(n)],capture_output=True,text=True,timeout=30)
        if r.returncode:raise ValueError('External storage admission rejected: '+r.stdout[-1000:])
    admit(200000000);out.mkdir(mode=0o700)
    # Source table slices and terrain are generated only in the private output.
    tables=(('linked',0x15a4c,0x16396),('reaction',0xc072,0xc082),('weapon',0xd4540,0xd4780),
            ('armor',0xd4d50,0xd4ea0),('grade',0x166ad4,0x166ad7))
    def array(name,data):return 'static const unsigned char '+name+'[]={' + ','.join(str(x) for x in data)+'};\n'
    source='unsigned char rom8(unsigned char,unsigned long);\nunsigned int rom16(unsigned char,unsigned long);\n'+native
    source+=array('terrain',bytes(initial['shadowrun_terrain_map']))
    for name,lo,hi in tables:source+=array(name,rom[lo:hi])
    source+='static unsigned char fault;\nunsigned char rom8(unsigned char r,unsigned long x){if(r){fault=1;return 0;}\n'
    for name,lo,hi in tables:source+=f'if(x>={lo}UL && x<{hi}UL)return {name}[(unsigned int)(x-{lo}UL)];\n'
    source+='fault=1;return 0;}\nunsigned int rom16(unsigned char r,unsigned long x){return ((unsigned int)rom8(r,x)<<8)|rom8(r,x+1UL);}\n'
    source+='void main(void){unsigned int i;unsigned long v;volatile unsigned char *p=(volatile unsigned char*)0x700;\n'
    source+='for(i=0;i<2816;i++)shadowrun_terrain_map[i]=terrain[i];\n'
    names=['shadowrun_player_x','shadowrun_player_y','shadowrun_x_min','shadowrun_x_max','shadowrun_y_min','shadowrun_y_max',
           'shadowrun_player_kind','shadowrun_player_flags','shadowrun_player_flags_low','shadowrun_player_heading','shadowrun_play_shot_timer',
           'shadowrun_arena_profile','shadowrun_arena_hp','shadowrun_arena_armor','shadowrun_arena_player_sprite_current','shadowrun_hostile_x','shadowrun_hostile_y',
           'shadowrun_hostile_contact','shadowrun_hostile_timer','shadowrun_hostile_cooldown','shadowrun_hostile_ammo','shadowrun_hostile_rng']
    if player:names += ['shadowrun_arena_player_ready','shadowrun_play_shot_eligible','shadowrun_play_weapon_slot',
                        'shadowrun_play_weapon_item','shadowrun_play_ammo','shadowrun_target_selected',
                        'shadowrun_field_death_timer','shadowrun_field_party_counter_a','shadowrun_field_party_counter_b','shadowrun_field_party_counter_c']
    for name in names:source+=f'{name}={initial[name]}UL;\n'
    for name in ('shadowrun_target_flags','shadowrun_target_x','shadowrun_target_y','shadowrun_play_actor_hp'):
        for i,v in enumerate(initial[name]):source+=f'{name}[{i}]={v}UL;\n'
    source+=entry+'();p[0]=0x53;p[1]=0x57;p[2]=fault;\n'
    for i,name in enumerate(watches):
        source+=f'v=(unsigned long){name};'
        for j in range(4):source+=f'p[{3+4*i+j}]=(unsigned char)(v>>{8*j});'
        source+='\n'
    marker=3+4*len(watches)
    source+=f'p[{marker}]=0xa5;for(;;){{}}}}\n'
    (out/'check.c').write_text(source)
    root=a.cc65_root.resolve();env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    tool=root/'bin/cl65';tracked=[tool,root/'bin/cc65',root/'bin/ca65',root/'bin/ld65',root/'cfg/nes.cfg',root/'lib/nes.lib']
    hashes={str(x):sha(x.read_bytes()) for x in tracked}
    q=subprocess.run([str(tool),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),'--lib-path',str(root/'lib'),
                      '-I',str(root/'include'),'-o','check.nes','check.c'],cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'build.log').write_text(q.stdout+q.stderr)
    if q.returncode:raise ValueError('Arena NES compilation failed: '+q.stderr[-3000:])
    image=(out/'check.nes').read_bytes();(out/'watch.json').write_text(json.dumps([{'name':'state','offset':1792,'length':marker+1}]))
    admit(100000000)
    q=subprocess.run([sys.executable,str(Path(__file__).parent/'check_console_udc.py'),'--core',str(a.core),'--rom',str(out/'check.nes'),
                      '--system','nes','--frames','180','--watch',str(out/'watch.json'),'--output',str(out/'native')],
                     env=env,capture_output=True,text=True,timeout=120)
    if q.returncode:raise ValueError('Arena NES run failed: '+q.stderr[-3000:])
    receipt_raw=(out/'native/receipt.json').read_bytes();receipt=json.loads(receipt_raw);trace=(out/'native/ram_trace.json').read_bytes()
    if (receipt['rom_sha256']!=sha(image) or receipt['core_sha256']!=sha(core) or receipt['ram_trace_sha256']!=sha(trace) or receipt['patches'] or
        _read_rom(a.rom)!=rom or any(sha(x.read_bytes())!=hashes[str(x)] for x in tracked)):
        raise ValueError('Native provenance changed')
    completed=[]
    for row in json.loads(trace)['frames']:
        data=bytes.fromhex(row['raw']['state'])
        if data[:2]==b'SW' and data[marker]==0xa5:
            if data[2] or any(int.from_bytes(data[3+4*i:7+4*i],'little')!=expected[name] for i,name in enumerate(watches)):
                raise ValueError('NES arena differs at physical frame '+str(row['frame']))
            completed.append(row['frame'])
    if not completed:raise ValueError('NES did not complete diagnostic')
    (out/'comparison.json').write_text(json.dumps({'format':'fdisbull-shadowrun-arena-nes-1',
        'program_sha256':sha(canonical(machine.program)),'nes_sha256':sha(image),
        'original_comparison_sha256':sha(original_raw),'native_receipt_sha256':sha(receipt_raw),
        'native_trace_sha256':sha(trace),'first_completed_frame':completed[0],'fields':watches,
        'player_source_qualification_sha256':([sha(a.player_launch_check.read_bytes()),sha(a.player_contact_check.read_bytes())] if player else []),
        'scope':('assisted player-shot model and native diagnostic; launch and hostile-contact leaves independently source-qualified' if player else
                 'assisted source-constructed same-loop first enemy hit; no subsequent burst, natural encounter or gameplay parity')},indent=2)+'\n')


if __name__=='__main__':main()
