#!/usr/bin/env python3
"""Compare bounded Stoker prompt selection against original 68000 execution."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_interaction import SOURCE, ROM_SHA256, lift_stoker_interaction

CORE_SHA='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rom',required=True);ap.add_argument('--core',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    rom=Path(a.rom).resolve();core=Path(a.core).resolve();probe=ROOT/'scripts/probe_genesis_function.py'
    paths={'rom':rom,'core':core,'probe':probe,'author':SOURCE,'verifier':Path(__file__).resolve(),
           'interaction_module':ROOT/'src/fdisbull/shadowrun_interaction.py',
           'game_il_module':ROOT/'src/fdisbull/game_il.py'}
    captured={k:v.read_bytes() for k,v in paths.items()}
    if sha(captured['rom'])!=ROM_SHA256 or sha(captured['core'])!=CORE_SHA:raise ValueError('wrong ROM/core identity')
    program=lift_stoker_interaction(captured['rom'])
    output=_private_directory(a.output);output.mkdir()
    for name,raw in captured.items():(output/name).write_bytes(raw)
    cases=[]
    for phase in range(256):
        cases.append({'name':f'phase-{phase:02x}','ram':[{'address':0xfffbf8,'data':'0202'},{'address':0xfff0d5,'data':f'{phase:02x}'},{'address':0xfff10d,'data':'a5'}]})
    for scene in range(4):
        for target in range(4):
            if (scene,target)==(2,2):continue
            cases.append({'name':f'unsupported-{scene}-{target}','ram':[{'address':0xfffbf8,'data':f'{scene:02x}{target:02x}'},{'address':0xfff0d5,'data':'00'},{'address':0xfff10d,'data':'a5'}]})
    contract={'name':'stoker-selector','entry':0x1f71e,'code_ranges':[{'start':0x1f71e,'end':0x1f770}],
      'stop_pcs':[0x1f770,0x1f816],'max_instructions':25,
      'registers':{'A0':0x11111111,'A5':0x22222222},
      'watch':[{'name':'dialogue_id','address':0xfff10d,'length':1}],'cases':cases}
    (output/'contract.json').write_text(json.dumps(contract))
    r=subprocess.run([sys.executable,str(output/'probe'),'--core',str(output/'core'),'--rom',str(output/'rom'),
       '--contract',str(output/'contract.json'),'--output',str(output/'native')],capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    receipt=json.loads((output/'native'/'receipt.json').read_text())
    if (not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases'])!=271 or
        receipt['source_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE_SHA):raise AssertionError('native witness incomplete')
    machine=GameMachine(program,{})
    for case,native in zip(cases,receipt['cases']):
        raw=case['ram'];scene,target=bytes.fromhex(raw[0]['data']);phase=int(raw[1]['data'],16)
        machine.set_state({'shadowrun_interaction_context':scene,'shadowrun_interaction_target':target,
           'shadowrun_interaction_phase':phase,'shadowrun_interaction_supported':0,
           'shadowrun_interaction_dialogue_id':0xa5,'shadowrun_interaction_prompt_offset':0x11111111,
           'shadowrun_interaction_portrait_offset':0x22222222})
        machine.call('shadowrun_select_interaction');actual=machine.snapshot();regs=native['registers_after']
        expected=(int(regs['PC']==0x1f816),int(native['ram_after']['dialogue_id'],16),regs['A0'],regs['A5'])
        got=tuple(actual[k] for k in ('shadowrun_interaction_supported','shadowrun_interaction_dialogue_id',
          'shadowrun_interaction_prompt_offset','shadowrun_interaction_portrait_offset'))
        if got!=expected:raise AssertionError(f"UIL/native mismatch for {case['name']}: {got} != {expected}")
    # Qualify the preceding native collision-word copy and low-five-bit
    # projection independently. This does not classify or dispatch an event.
    values=[v if v<128 else 0xff00|v for v in range(256)]+[0x0123,0x7fc2,0xabc2,0x8000,0x8080,0xff20]
    event_cases=[{'name':f'collision-{v:04x}','ram':[{'address':0xffdf64,'data':f'{v:04x}'},
        {'address':0xff01c6,'data':'a55a'}]} for v in values]
    event_contract={'name':'collision-event-index','entry':0xb858,
       'code_ranges':[{'start':0xb858,'end':0xb866}],'stop_pcs':[0xb866],
       'max_instructions':8,'registers':{'A0':0xff0100},
       'watch':[{'name':'actor_collision','address':0xff01c6,'length':2}], 'cases':event_cases}
    (output/'event-contract.json').write_text(json.dumps(event_contract))
    r=subprocess.run([sys.executable,str(output/'probe'),'--core',str(output/'core'),'--rom',str(output/'rom'),
       '--contract',str(output/'event-contract.json'),'--output',str(output/'event-native')],
       capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    event_receipt=json.loads((output/'event-native'/'receipt.json').read_text())
    if not event_receipt['complete'] or not event_receipt['inputs_unchanged'] or len(event_receipt['cases'])!=len(values):
        raise AssertionError('native event witness incomplete')
    for raw,native in zip(values,event_receipt['cases']):
        machine.set_state({'shadowrun_interaction_raw_collision':raw})
        machine.call('shadowrun_decode_collision_event');actual=machine.snapshot()
        expected=(int(native['ram_after']['actor_collision'],16),native['registers_after']['D0']&0xffff)
        got=(actual['shadowrun_interaction_actor_collision'],actual['shadowrun_interaction_event_index'])
        if got!=expected:raise AssertionError(f'collision event projection differs for {raw:04x}')
    # Evaluate the original signed-byte four-corner gate to both exits.
    corner_sets=[[((v*37+i*19)&127)|(128 if v&(1<<i) else 0) for i in range(4)]
                 for v in range(256)] + [[0xc2,0xc2,0,0]]
    gate_cases=[{'name':f'corners-{i:03d}','ram':[{'address':0xffef10,'data':bytes(values).hex()}]}
                for i,values in enumerate(corner_sets)]
    gate_contract={'name':'collision-corner-gate','entry':0xb7fa,
       'code_ranges':[{'start':0xb7fa,'end':0xb834}],'stop_pcs':[0xb834,0xbaae],
       'max_instructions':32,'cases':gate_cases}
    (output/'gate-contract.json').write_text(json.dumps(gate_contract))
    r=subprocess.run([sys.executable,str(output/'probe'),'--core',str(output/'core'),'--rom',str(output/'rom'),
       '--contract',str(output/'gate-contract.json'),'--output',str(output/'gate-native')],
       capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    gate_receipt=json.loads((output/'gate-native'/'receipt.json').read_text())
    if not gate_receipt['complete'] or not gate_receipt['inputs_unchanged'] or len(gate_receipt['cases'])!=len(corner_sets):
        raise AssertionError('native corner witness incomplete')
    for values,native in zip(corner_sets,gate_receipt['cases']):
        machine.set_state({f'shadowrun_interaction_corner{i}':v for i,v in enumerate(values)})
        machine.call('shadowrun_check_event_corners');actual=machine.snapshot()
        expected=(native['registers_after']['D0']&0xffff,int(native['registers_after']['PC']==0xb834))
        got=(actual['shadowrun_interaction_negative_count'],actual['shadowrun_interaction_corner_gate'])
        if got!=expected:raise AssertionError(f'corner gate mismatch {values}: {got} != {expected}')
    # Check the observed generic event-target handoff across its gate branches.
    branch_cases=[]
    for mode in (0,1,2,3):
        for scene in (2,20):
            for event in (0,1,2,31):
                for reaction in (0,1):
                    for visited in (0,1):
                        branch_cases.append({'name':f'branch-{mode}-{scene}-{event}-{reaction}-{visited}',
                          'registers':{'D0':event}, 'ram':[{'address':0xffdf40,'data':f'{mode:04x}'},
                          {'address':0xffddc4,'data':f'{scene:04x}'},{'address':0xffdf84,'data':f'{reaction:04x}'},
                          {'address':0xffe16f,'data':f'{visited:02x}'},{'address':0xfffbf9,'data':'a5'}]})
    branch_contract={'name':'event-branch','entry':0xba3a,
      'code_ranges':[{'start':0xba3a,'end':0xba7c}],'stop_pcs':[0xba7c,0xbaae],
      'max_instructions':25,'watch':[{'name':'target','address':0xfffbf9,'length':1}], 'cases':branch_cases}
    (output/'branch-contract.json').write_text(json.dumps(branch_contract))
    r=subprocess.run([sys.executable,str(output/'probe'),'--core',str(output/'core'),'--rom',str(output/'rom'),
       '--contract',str(output/'branch-contract.json'),'--output',str(output/'branch-native')],
       capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    branch_receipt=json.loads((output/'branch-native'/'receipt.json').read_text())
    if not branch_receipt['complete'] or not branch_receipt['inputs_unchanged'] or len(branch_receipt['cases'])!=len(branch_cases):
        raise AssertionError('native branch witness incomplete')
    for case,native in zip(branch_cases,branch_receipt['cases']):
        event=case['registers']['D0'];mode,scene,reaction=(int(x['data'],16) for x in case['ram'][:3]);visited=int(case['ram'][3]['data'],16)
        machine.set_state({'shadowrun_interaction_event_index':event,'shadowrun_interaction_event_mode':mode,
          'shadowrun_interaction_scene_mode':scene,'shadowrun_interaction_reaction_flag':reaction,
          'shadowrun_interaction_visited_flag':visited})
        machine.call('shadowrun_interaction_source_branch');actual=machine.snapshot()
        expected=(int(native['ram_after']['target'],16),int(native['registers_after']['PC']==0xba7c))
        got=(actual['shadowrun_interaction_source_target'],actual['shadowrun_interaction_source_proceeds'])
        if got!=expected:raise AssertionError(f"branch mismatch {case['name']}: {got} != {expected}")
    transition_cases=[{'name':f'carry-{carry}','ccr':carry,
      'ram':[{'address':0xffdf3a,'data':'12345678'},{'address':0xffdfe8,'data':'9abc'}]} for carry in (0,1)]
    transition_contract={'name':'activity-transition','entry':0xba82,
       'code_ranges':[{'start':0xba82,'end':0xbaa2}],'stop_pcs':[0xbaa2,0xb7cc],
       'max_instructions':10,'watch':[{'name':'transition','address':0xffdf3a,'length':4},
       {'name':'busy','address':0xffdfe8,'length':2}],'cases':transition_cases}
    (output/'transition-contract.json').write_text(json.dumps(transition_contract))
    r=subprocess.run([sys.executable,str(output/'probe'),'--core',str(output/'core'),'--rom',str(output/'rom'),
       '--contract',str(output/'transition-contract.json'),'--output',str(output/'transition-native')],
       capture_output=True,text=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    transition_receipt=json.loads((output/'transition-native'/'receipt.json').read_text())
    if not transition_receipt['complete'] or not transition_receipt['inputs_unchanged'] or len(transition_receipt['cases'])!=2:
        raise AssertionError('native transition witness incomplete')
    for carry,native in enumerate(transition_receipt['cases']):
        machine.set_state({'shadowrun_interaction_dispatch_carry':carry,'shadowrun_interaction_transition_flag':0x1234,
          'shadowrun_interaction_transition_timer':0x5678,'shadowrun_interaction_trigger_busy':0x9abc})
        machine.call('shadowrun_interaction_source_transition');actual=machine.snapshot()
        data=bytes.fromhex(native['ram_after']['transition']);busy=int(native['ram_after']['busy'],16)
        expected=(int.from_bytes(data[:2],'big'),int.from_bytes(data[2:],'big'),busy)
        got=tuple(actual[k] for k in ('shadowrun_interaction_transition_flag','shadowrun_interaction_transition_timer','shadowrun_interaction_trigger_busy'))
        if got!=expected:raise AssertionError(f'transition mismatch carry={carry}')
    if any(path.read_bytes()!=captured[k] for k,path in paths.items()):raise AssertionError('input changed during qualification')
    summary={'format':'fdisbull-shadowrun-interaction-qualification-1','status':'passed','rom_sha256':ROM_SHA256,
      'core_sha256':CORE_SHA,'authoring_sha256':sha(captured['author']),
      'interaction_module_sha256':sha(captured['interaction_module']),
      'game_il_module_sha256':sha(captured['game_il_module']),'native_cases':271,
      'phase_cases':256,'unsupported_pair_controls':15,'native_trace_sha256':receipt['trace_sha256'],
      'collision_projection_cases':len(event_cases),'collision_trace_sha256':event_receipt['trace_sha256'],
      'corner_gate_cases':len(corner_sets),'corner_gate_trace_sha256':gate_receipt['trace_sha256'],
      'source_branch_cases':len(branch_cases),'source_branch_trace_sha256':branch_receipt['trace_sha256'],
      'source_transition_cases':len(transition_cases),'source_transition_trace_sha256':transition_receipt['trace_sha256'],
      'scope':'controlled original-CPU branch slices vs typed UIL; opaque dispatcher side effects and target UI adapter excluded'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(output/'summary.json')

if __name__=='__main__':main()
