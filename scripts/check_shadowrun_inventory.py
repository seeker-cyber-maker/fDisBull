#!/usr/bin/env python3
"""Compare inventory leaves with controlled original-core 68000 execution."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_inventory import lift_inventory, ROM_SHA256, SOURCE
CORE_SHA='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(); p.add_argument('--rom',required=True); p.add_argument('--core',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    rom=Path(a.rom).read_bytes(); core=Path(a.core).read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE_SHA: raise ValueError('wrong source/core')
    machine=GameMachine(lift_inventory(rom),{})
    out=_private_directory(a.output); out.mkdir(parents=True)
    (out/'rom').write_bytes(rom); (out/'core').write_bytes(core)
    def run(name,contract):
        path=out/(name+'.json'); path.write_text(json.dumps(contract))
        result=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(out/'rom'),'--core',str(out/'core'),'--contract',str(path),'--output',str(out/(name+'-native'))],capture_output=True,text=True,timeout=180)
        if result.returncode: raise RuntimeError(result.stderr[-4000:])
        r=json.loads((out/(name+'-native')/'receipt.json').read_text())
        if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(contract['cases']): raise AssertionError('incomplete native run')
        return r
    cells=bytes([0,1,17,43,44,49,127,255]); cases=[]
    for row in range(4):
        for col in range(2):
            cases.append({'name':f'{row}-{col}','ram':[{'address':0xfffc04,'data':'00ff0100'},{'address':0xfff0d0,'data':f'{col:02x}{row:02x}'},{'address':0xff0166,'data':cells.hex()}]})
    sel=run('select',{'name':'inventory-select','entry':0x12148,'code_ranges':[{'start':0x12148,'end':0x12166}],'stop_pcs':[0x12166],'max_instructions':10,'cases':cases})
    for case,native in zip(cases,sel['cases']):
        row,col=map(int,case['name'].split('-'))
        state={'shadowrun_inventory_row':row,'shadowrun_inventory_column':col}
        state.update({f'shadowrun_inventory_cell{i}':v for i,v in enumerate(cells)})
        machine.set_state(state); machine.call('shadowrun_inventory_select'); actual=machine.snapshot()
        assert (actual['shadowrun_inventory_item'],actual['shadowrun_inventory_slot'])==(native['registers_after']['D0']&255,native['registers_after']['D7']&255)
    cases=[]
    for item in range(256):
        for equipped in (0,1,255):
            cases.append({'name':f'{item}-{equipped}','registers':{'A0':0xff0100,'D0':item,'D7':3},'ram':[{'address':0xff0176,'data':f'{equipped:02x}'},{'address':0xff0171,'data':'a5'}]})
    arm=run('armor',{'name':'inventory-armor-branch','entry':0x1219c,'code_ranges':[{'start':0x1219c,'end':0x121c0}],'stop_pcs':[0x1228c],'max_instructions':8,'watch':[{'name':'armor','address':0xff0176,'length':1},{'name':'phase','address':0xff0171,'length':1}],'cases':cases})
    for case,native in zip(cases,arm['cases']):
        item,equipped=map(int,case['name'].split('-'))
        machine.set_state({'shadowrun_inventory_item':item,'shadowrun_inventory_equipped_armor':equipped,'shadowrun_inventory_selected_phase':0xa5})
        machine.call('shadowrun_inventory_armor_branch'); actual=machine.snapshot()
        assert (actual['shadowrun_inventory_equipped_armor'],actual['shadowrun_inventory_selected_phase'])==tuple(int(native['ram_after'][k],16) for k in ('armor','phase')),(item,equipped)
    summary={'format':'fdisbull-shadowrun-inventory-qualification-1','rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(SOURCE.read_bytes()),'selection_cases':len(sel['cases']),'selection_trace_sha256':sel['trace_sha256'],'armor_cases':len(arm['cases']),'armor_trace_sha256':arm['trace_sha256'],'scope':'controlled original 68000 entry versus GameIL; valid cursor selection and isolated armor branch only; no dispatch, presentation, or reachability'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
