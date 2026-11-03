#!/usr/bin/env python3
"""Compare bounded source attack-stat leaves against original 68000."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_combat import lift_combat, ROM_SHA256, SOURCE
CORE_SHA='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(); p.add_argument('--rom',required=True); p.add_argument('--core',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    rom=Path(a.rom).read_bytes(); core=Path(a.core).read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE_SHA: raise ValueError('wrong ROM/core')
    author=SOURCE.read_bytes(); machine=GameMachine(lift_combat(rom),{}); out=_private_directory(a.output); out.mkdir()
    (out/'rom').write_bytes(rom); (out/'core').write_bytes(core)
    totals=[]
    for name,start,end,offset in [('unarmed',0x12dd2,0x12dec,0x85),('alternate',0x12d46,0x12d60,0x87)]:
        cases=[]
        for skill in range(256):
            for baseline in (0,1,127,255,256,32767):
                cases.append({'name':f'{skill}-{baseline}','registers':{'A0':0xff0100,'D6':baseline,'D7':0},'ram':[{'address':0xff0100+offset,'data':f'{skill:02x}'}]})
        contract={'name':name,'entry':start,'code_ranges':[{'start':start,'end':end}],'stop_pcs':[0x12dfe], 'max_instructions':10,'cases':cases}
        contract_path=out/(name+'.json'); contract_path.write_text(json.dumps(contract))
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(contract_path),'--output',str(out/(name+'-native'))],capture_output=True,text=True,timeout=180)
        if proc.returncode: raise RuntimeError(proc.stderr[-4000:])
        receipt=json.loads((out/(name+'-native')/'receipt.json').read_text())
        if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise AssertionError('incomplete native probe')
        for case,native in zip(cases,receipt['cases']):
            skill,baseline=map(int,case['name'].split('-')); machine.set_state({'shadowrun_combat_skill':skill,'shadowrun_combat_baseline':baseline})
            machine.call('shadowrun_combat_skill_stat'); state=machine.snapshot()
            if not state['shadowrun_combat_supported'] or state['shadowrun_combat_attack_stat']!=(native['registers_after']['D6']&65535):raise AssertionError(case['name'])
        totals.append({'source':name,'cases':len(cases),'trace_sha256':receipt['trace_sha256']})
    cases=[]
    for posture in range(5):
        for delta in (0,1,255):
            cases.append({'name':f'{posture}-{delta}','registers':{'D0':delta},'ram':[{'address':0xfffc04,'data':'00ff0100'},{'address':0xff014d,'data':f'{posture:02x}'}]})
    contract={'name':'posture','entry':0x11ae4,'code_ranges':[{'start':0x11ae4,'end':0x11b0e}],'stop_pcs':[0x11b0e],'max_instructions':12,'stack_scratch_bytes':64,'watch':[{'name':'posture','address':0xff014d,'length':1}],'cases':cases}
    cp=out/'posture.json';cp.write_text(json.dumps(contract))
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(cp),'--output',str(out/'posture-native')],capture_output=True,text=True,timeout=180)
    if proc.returncode:raise RuntimeError(proc.stderr[-4000:])
    receipt=json.loads((out/'posture-native'/'receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise AssertionError('incomplete posture probe')
    for case,native in zip(cases,receipt['cases']):
        posture,delta=map(int,case['name'].split('-'))
        machine.set_state({'shadowrun_combat_posture':posture,'shadowrun_combat_posture_delta':delta})
        machine.call('shadowrun_combat_change_posture'); state=machine.snapshot()
        if not state['shadowrun_combat_posture_supported'] or state['shadowrun_combat_posture']!=int(native['ram_after']['posture'],16):raise AssertionError(case['name'])
    totals.append({'source':'posture','cases':len(cases),'trace_sha256':receipt['trace_sha256']})
    if SOURCE.read_bytes()!=author:raise ValueError('authoring source changed during qualification')
    summary={'format':'fdisbull-shadowrun-combat-qualification-1','rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(author),'leaves':totals,'scope':'controlled original 68000 attack-stat leaves, selected nonnegative baselines; prior helpers, targeting, damage and field action execution excluded'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
