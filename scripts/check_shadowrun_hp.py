#!/usr/bin/env python3
"""Compare controlled original field hit-point leaf with GameIL."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_combat import lift_combat, ROM_SHA256, SOURCE
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--rom',required=True);p.add_argument('--core',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();author=SOURCE.read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE:raise ValueError('wrong ROM/core')
    machine=GameMachine(lift_combat(rom),{});out=_private_directory(a.output);out.mkdir();(out/'rom').write_bytes(rom);(out/'core').write_bytes(core)
    cases=[]
    for hp in range(128):
        for damage in (1,5,10):
            for flag in (0,128):
                for selector in (0,1):
                    primary=37 if selector else hp; alternate=hp if selector else 37
                    cases.append({'name':f'{hp}-{damage}-{flag}-{selector}','registers':{'A1':0xff0100,'D1':65536-damage},'ram':[{'address':0xff014c,'data':f'{primary:02x}'},{'address':0xff019a,'data':f'{flag:02x}'},{'address':0xff019c,'data':f'{alternate:02x}'},{'address':0xfff0cc,'data':f'{selector:02x}'}]})
    contract={'name':'field-hp-application','entry':0x55a62,'code_ranges':[{'start':0x55a62,'end':0x55a9e}],'stop_pcs':[0x55a9e,0x55b14],'max_instructions':12,'watch':[{'name':'primary','address':0xff014c,'length':1},{'name':'alternate','address':0xff019c,'length':1},{'name':'selector','address':0xfff0cc,'length':1}],'cases':cases}
    cp=out/'contract.json';cp.write_text(json.dumps(contract))
    result=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError(result.stderr[-4000:])
    receipt=json.loads((out/'native'/'receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise AssertionError('incomplete native run')
    for case,native in zip(cases,receipt['cases']):
        hp,damage,flag,selector=map(int,case['name'].split('-'));primary=37 if selector else hp;alternate=hp if selector else 37
        machine.set_state({'shadowrun_combat_hp_primary':primary,'shadowrun_combat_hp_alternate':alternate,'shadowrun_combat_hp_selector':selector,'shadowrun_combat_hp_target_flags':flag,'shadowrun_combat_hp_damage':damage})
        machine.call('shadowrun_combat_apply_hp');state=machine.snapshot()
        got=tuple(state[k] for k in ('shadowrun_combat_hp_primary','shadowrun_combat_hp_alternate','shadowrun_combat_hp_selector','shadowrun_combat_hp_depleted'))
        expected=tuple(int(native['ram_after'][k],16) for k in ('primary','alternate','selector'))+(int(native['registers_after']['PC']==0x55a9e),)
        if not state['shadowrun_combat_hp_supported'] or got!=expected:raise AssertionError((case['name'],got,expected))
    if SOURCE.read_bytes()!=author:raise ValueError('authoring source changed during qualification')
    summary={'format':'fdisbull-shadowrun-hp-qualification-1','rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(author),'cases':len(cases),'trace_sha256':receipt['trace_sha256'],'scope':'controlled original field hit-point byte application; hit selection, damage calculation and zero-health side effects excluded'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
