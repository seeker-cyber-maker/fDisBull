#!/usr/bin/env python3
"""Compare bounded item-44 dispatch with the original 68000, controlled entry."""
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
    for slot in (0,1,7):
        for armor in (0,1,2,255):
            cells=bytearray(8);cells[slot]=44;phases=bytes([0x55]*8)
            cases.append({'name':f'{slot}-{armor}','ram':[{'address':0xfffc04,'data':'00ff0100'},
                {'address':0xfff09f,'data':'00'},{'address':0xfff0d0,'data':f'{slot%2:02x}{slot//2:02x}'},
                {'address':0xff0166,'data':(cells+phases+bytes([armor])).hex()}]})
    contract={'name':'inventory-item-44-dispatch','entry':0x12168,
        'code_ranges':[{'start':0x12148,'end':0x121c0}], 'stop_pcs':[0x1228c],
        'max_instructions':40,'stack_scratch_bytes':4,'watch':[{'name':'inventory','address':0xff0166,'length':17}], 'cases':cases}
    path=out/'contract.json';path.write_text(json.dumps(contract))
    run=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(a.rom),'--core',str(a.core),'--contract',str(path),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
    if run.returncode:raise ValueError('original probe failed: '+run.stderr[-3000:])
    receipt=json.loads((out/'native/receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise ValueError('incomplete native evidence')
    m=GameMachine(lift_play(rom),{0:rom}); mismatches=[]
    for case,native in zip(cases,receipt['cases']):
        slot,armor=map(int,case['name'].split('-'))
        state={'shadowrun_inventory_row':slot//2,'shadowrun_inventory_column':slot%2,'shadowrun_inventory_equipped_armor':armor,'shadowrun_play_action_gate':0}
        state.update({f'shadowrun_inventory_cell{i}':44 if i==slot else 0 for i in range(8)})
        state.update({f'shadowrun_play_phase{i}':0x55 for i in range(8)})
        m.set_state(state);m.call('shadowrun_inventory_select');m.call('shadowrun_play_equip');s=m.snapshot()
        after=bytes.fromhex(native['ram_after']['inventory'])
        if s['shadowrun_inventory_equipped_armor']!=after[16] or [s[f'shadowrun_play_phase{i}'] for i in range(8)]!=list(after[8:16]) or s['shadowrun_play_refused']:
            mismatches.append(case['name'])
    result={'format':'fdisbull-shadowrun-play-armor-check-1','source_sha256':sha(rom),'core_sha256':sha(core),
        'cases':len(cases),'mismatches':mismatches,'trace_sha256':receipt['trace_sha256'],
        'scope':'controlled original entry $12168 to $1228c, item 44 only; no menu reachability or UI side effects'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
