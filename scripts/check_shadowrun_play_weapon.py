#!/usr/bin/env python3
"""Compare bounded captured item-2 dispatch with the original 68000, controlled entry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_play import lift_play
from fdisbull.shadowrun_inventory import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--rom',required=True,type=Path);p.add_argument('--core',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    rom=a.rom.read_bytes();core=a.core.read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE:raise ValueError('wrong source/core')
    out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
    out.mkdir(mode=0o700,parents=True)
    cases=[]
    for slot,item,values in ((0,2,(0,1,6,11,12)),(127,0,(0,1,50,99,100))):
        for ammo in values:
            actor=bytearray(0x9e);actor[0x10]=1;actor[0x4e]=ammo;actor[0x56]=slot;actor[0x57]=item;actor[0x66]=2;actor[0x9d]=5
            cases.append({'name':f'{slot}-{item}-{ammo}','ram':[{'address':0xfffc04,'data':'00ff0100'},
                {'address':0xfff09f,'data':'00'},{'address':0xfff0d0,'data':'0000'},
                {'address':0xff0100,'data':actor.hex()}]})
    contract={'name':'inventory-item-2-dispatch','entry':0x12168,
        'code_ranges':[{'start':0x12148,'end':0x12288},{'start':0x125fa,'end':0x12634},{'start':0x36fc,'end':0x37d4}],
        'stop_pcs':[0x37d4],'max_instructions':100,'stack_scratch_bytes':64,
        'watch':[{'name':'actor','address':0xff0100,'length':0x9e}], 'cases':cases}
    path=out/'contract.json';path.write_text(json.dumps(contract))
    run=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(a.rom),'--core',str(a.core),'--contract',str(path),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
    if run.returncode:raise ValueError('original probe failed: '+run.stderr[-3000:])
    receipt=json.loads((out/'native/receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise ValueError('incomplete native evidence')
    m=GameMachine(lift_play(rom),{0:rom}); mismatches=[]
    for case,native in zip(cases,receipt['cases']):
        slot,item,ammo=map(int,case['name'].split('-'))
        state={'shadowrun_inventory_row':0,'shadowrun_inventory_column':0,'shadowrun_inventory_cell0':2,
            'shadowrun_play_action_gate':0,'shadowrun_player_flags':1,'shadowrun_play_weapon_slot':slot,
            'shadowrun_play_weapon_item':item,'shadowrun_play_ammo':ammo,'shadowrun_play_weapon_aux':5}
        m.set_state(state);m.call('shadowrun_inventory_select');m.call('shadowrun_play_equip');s=m.snapshot()
        after=bytes.fromhex(native['ram_after']['actor'])
        got=[s['shadowrun_play_weapon_slot'],s['shadowrun_play_weapon_item'],s['shadowrun_play_ammo'],s['shadowrun_play_weapon_aux']]
        if got != [after[0x56],after[0x57],after[0x4e],after[0x9d]] or s['shadowrun_play_refused']:
            mismatches.append({'case':case['name'],'actual':got,'expected':[after[0x56],after[0x57],after[0x4e],after[0x9d]]})
    result={'format':'fdisbull-shadowrun-play-weapon-check-1','source_sha256':sha(rom),'core_sha256':sha(core),
        'cases':len(cases),'mismatches':mismatches,'trace_sha256':receipt['trace_sha256'],
        'scope':'controlled original entry $12168 to $37d4, captured item 2 equip and unequip domains; no menu reachability or HUD effects'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
