#!/usr/bin/env python3
"""Check source field-action attack-stat leaf against pinned original core."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_combat import lift_combat, ROM_SHA256, SOURCE
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rom',required=True);ap.add_argument('--core',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();author=SOURCE.read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE:raise ValueError('wrong input identity')
    machine=GameMachine(lift_combat(rom),{});out=_private_directory(a.output);out.mkdir();(out/'rom').write_bytes(rom);(out/'core').write_bytes(core)
    cases=[{'name':f'{skill}-{base}','registers':{'A0':0xff0100,'D6':base,'D7':0},'ram':[{'address':0xff0185,'data':f'{skill:02x}'}]} for skill in range(256) for base in (0,1,127,255,256,32767)]
    contract={'name':'field-attack-stat','entry':0x55c80,'code_ranges':[{'start':0x55c80,'end':0x55c96}],'stop_pcs':[0x55c96],'max_instructions':8,'cases':cases}
    cp=out/'contract.json';cp.write_text(json.dumps(contract))
    r=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    receipt=json.loads((out/'native'/'receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=len(cases):raise AssertionError('incomplete native probe')
    for case,native in zip(cases,receipt['cases']):
        skill,base=map(int,case['name'].split('-'));machine.set_state({'shadowrun_combat_skill':skill,'shadowrun_combat_baseline':base});machine.call('shadowrun_combat_skill_stat');state=machine.snapshot()
        if not state['shadowrun_combat_supported'] or state['shadowrun_combat_attack_stat']!=(native['registers_after']['D6']&65535):raise AssertionError(case['name'])
    if SOURCE.read_bytes()!=author:raise ValueError('source changed during qualification')
    effect_cases=[{'name':f'{value}-{ref}-{stage}','registers':{'A0':0xff0100,'D5':stage},'ram':[{'address':0xff019f,'data':f'{value:02x}'},{'address':0xfff0dd,'data':f'{ref:02x}'}]} for value in range(128) for ref in (0,63,127) for stage in (1,5,10)]
    effect_contract={'name':'field-effect-adjust','entry':0x559ce,'code_ranges':[{'start':0x559ce,'end':0x559f4}],'stop_pcs':[0x559e4,0x559f4],'max_instructions':12,'cases':effect_cases}
    ep=out/'effect-contract.json';ep.write_text(json.dumps(effect_contract))
    er=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(ep),'--output',str(out/'effect-native')],capture_output=True,text=True,timeout=180)
    if er.returncode:raise RuntimeError(er.stderr[-4000:])
    effect=json.loads((out/'effect-native'/'receipt.json').read_text())
    if not effect['complete'] or not effect['inputs_unchanged'] or len(effect['cases'])!=len(effect_cases):raise AssertionError('incomplete effect probe')
    for case,native in zip(effect_cases,effect['cases']):
        value,ref,stage=map(int,case['name'].split('-'));machine.set_state({'shadowrun_combat_effect_input':value,'shadowrun_combat_effect_reference':ref,'shadowrun_combat_effect_value':stage})
        machine.call('shadowrun_combat_effect_adjust');state=machine.snapshot()
        got=(state['shadowrun_combat_effect_value'],state['shadowrun_combat_effect_proceeds'])
        expected=(native['registers_after']['D5']&255,int(native['registers_after']['PC']==0x559f4))
        if not state['shadowrun_combat_effect_supported'] or got!=expected:raise AssertionError((case['name'],got,expected))
    if SOURCE.read_bytes()!=author:raise ValueError('source changed during qualification')
    summary={'format':'fdisbull-shadowrun-field-combat-qualification-1','rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(author),'cases':len(cases),'trace_sha256':receipt['trace_sha256'],'effect_cases':len(effect_cases),'effect_trace_sha256':effect['trace_sha256'],'scope':'controlled field-action stat leaf at $55C80 and intermediate effect gate $559CE; prior helper and downstream effects excluded'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
