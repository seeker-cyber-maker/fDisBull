#!/usr/bin/env python3
"""Compare a prepared item-1 hit continuation with the pinned original core.

The independent spawn and collision probes remain separate; this is not a
normal input-to-hit run. All native receipts are private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_field_combat import SOURCE, lift_field_combat

CORE = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    for name in ('rom', 'core', 'output'):
        ap.add_argument('--' + name, required=True)
    args = ap.parse_args()
    rom, core, author = Path(args.rom).read_bytes(), Path(args.core).read_bytes(), SOURCE.read_bytes()
    if sha(core) != CORE:
        raise ValueError('wrong core')
    machine = GameMachine(lift_field_combat(rom), {})
    out = _private_directory(args.output)
    out.mkdir(mode=0o700)
    cases = []
    expected_inputs = []
    for attrs in (0, 3, 20, 40):
        for posture in (0, 1, 4):
            for effect in (0, 10, 30):
                for seed in ((1,) if attrs == 40 else (1, 17)):
                    item = 1 + ((attrs + posture + effect + seed) & 1)
                    source = bytearray(0xa0)
                    source[0x57], source[0x9f] = item, effect
                    target = bytearray(0xa0)
                    target[0x3f], target[0x4c] = 3, 50
                    target[0x78] = target[0x7b] = target[0x7c] = attrs
                    target[0x4d] = posture
                    cases.append({'name':f'{attrs}-{posture}-{effect}-{seed}',
                        'registers':{'A0':0xff0100,'A1':0xff0200},
                        'ram':[{'address':0xff0100,'data':source.hex()},
                               {'address':0xff0200,'data':target.hex()},
                               {'address':0xfff9f8,'data':seed.to_bytes(2,'big').hex()}]})
                    expected_inputs.append((attrs, posture, effect, seed, item))
    contract = {'name':'prepared-projectile-hit', 'entry':0x14e6e,
       'code_ranges':[{'start':0x14e6e,'end':0x14e88}, {'start':0x55948,'end':0x55b16},
        {'start':0x55e62,'end':0x55f44}, {'start':0x55786,'end':0x55848},
        {'start':0xd3a,'end':0xdfc}], 'stop_pcs':[0x14e88],
       'stack_scratch_bytes':128, 'max_instructions':2000,
       'watch':[{'name':'source','address':0xff0100,'length':160},
                {'name':'target','address':0xff0200,'length':160},
                {'name':'globals','address':0xfff000,'length':4096}], 'cases':cases}
    cp = out / 'contract.json'
    cp.write_text(json.dumps(contract))
    result = subprocess.run([sys.executable, str(ROOT/'scripts/probe_genesis_function.py'),
        '--rom',args.rom,'--core',args.core,'--contract',str(cp),'--output',str(out/'native')],
        capture_output=True,text=True,timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    native = json.loads((out/'native'/'receipt.json').read_text())
    if not native['complete'] or not native['inputs_unchanged'] or len(native['cases']) != len(cases):
        raise AssertionError('incomplete native run')
    for (attrs, posture, effect, seed, item), case in zip(expected_inputs, native['cases']):
        machine.set_state({'shadowrun_field_actor_index':3,'shadowrun_field_item':item,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':1,'shadowrun_field_ammo':2,'shadowrun_field_slots_busy':0,
         'shadowrun_field_projectile_x':512,'shadowrun_field_projectile_y':512,
         'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,
         'shadowrun_field_target_flags':1,'shadowrun_field_target_hp':50,
         'shadowrun_field_target_a':attrs,'shadowrun_field_target_b':attrs,'shadowrun_field_target_c':attrs,
         'shadowrun_field_target_posture':posture,'shadowrun_field_source_effect':effect,'shadowrun_field_rng':seed})
        machine.call('shadowrun_field_fire')
        state = machine.snapshot()
        target = bytes.fromhex(case['ram_after']['target'])
        glob = bytes.fromhex(case['ram_after']['globals'])
        observed = (target[0x4c], int.from_bytes(glob[0x9f8:0x9fa], 'big'))
        got = (state['shadowrun_field_target_hp'],state['shadowrun_field_rng'])
        if not state['shadowrun_field_supported'] or got != observed:
            raise AssertionError(((attrs,posture,effect,seed,item),got,observed))
    # Independently enter the original spawn gate, including exhausted slots.
    spawn_cases = []
    for ammo in (0, 1, 2):
        for mask in (0, 1, 2, 31, 63):
            actor = bytearray(0x58)
            actor[0x3f], actor[0x4e], actor[0x57] = 3, ammo, 1
            ram = [{'address':0xff0100,'data':actor.hex()}]
            ram += [{'address':0xff0b10 + i*0x100,'data':'01'}
                    for i in range(6) if mask & (1 << i)]
            spawn_cases.append({'name':f'{ammo}-{mask}','registers':{'A0':0xff0100},'ram':ram})
    spawn = {'name':'spawn-gate','entry':0x1517a,
      'code_ranges':[{'start':0x1517a,'end':0x151be},{'start':0x38ac,'end':0x38fa},
                     {'start':0x15a8c,'end':0x15aba}],
      'stop_pcs':[0x152f4,0x151be],'stack_scratch_bytes':64,'max_instructions':150,
      'watch':[{'name':'ammo','address':0xff014e,'length':1}],'cases':spawn_cases}
    (out/'spawn-contract.json').write_text(json.dumps(spawn))
    proc = subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),
      '--rom',args.rom,'--core',args.core,'--contract',str(out/'spawn-contract.json'),
      '--output',str(out/'spawn-native')],capture_output=True,text=True,timeout=180)
    if proc.returncode: raise RuntimeError(proc.stderr[-4000:])
    spawn_receipt = json.loads((out/'spawn-native'/'receipt.json').read_text())
    if not spawn_receipt['complete'] or not spawn_receipt['inputs_unchanged']:
        raise AssertionError('incomplete spawn run')
    for item, original in zip(spawn_cases,spawn_receipt['cases']):
        ammo, mask = map(int,item['name'].split('-'))
        machine.set_state({'shadowrun_field_actor_index':3,'shadowrun_field_item':1,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':1,'shadowrun_field_ammo':ammo,'shadowrun_field_slots_busy':mask,
          'shadowrun_field_projectile_x':656,'shadowrun_field_projectile_y':512,
          'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,
          'shadowrun_field_target_flags':1,'shadowrun_field_target_hp':50,
          'shadowrun_field_target_a':20,'shadowrun_field_target_b':20,'shadowrun_field_target_c':20,
          'shadowrun_field_target_posture':0,'shadowrun_field_source_effect':30,'shadowrun_field_rng':1})
        machine.call('shadowrun_field_fire')
        state=machine.snapshot()
        passed = original['registers_after']['PC'] == 0x151be
        got_passed = state['shadowrun_field_outcome'] == 2
        if not state['shadowrun_field_supported'] or got_passed != passed or state['shadowrun_field_ammo'] != int(original['ram_after']['ammo'],16):
            raise AssertionError(('spawn',item['name']))
        if passed and state['shadowrun_field_slot'] != (original['registers_after']['A1']-0xff0200)//0x100:
            raise AssertionError(('slot',item['name']))
    # Party helper is stopped before its separate HUD presentation call.
    party_cases=[]
    for index in (0,1,2):
      for weapon in (1,2):
        for ammo in (0,1,6,12,13):
            actor=bytearray(0xa0)
            actor[0x10]=1; actor[0x3f]=index; actor[0x4e]=ammo
            actor[0x56]=0; actor[0x57]=weapon; actor[0x66]=weapon
            party_cases.append({'name':f'{index}-{weapon}-{ammo}',
               'registers':{'A0':0xff0100},'ram':[{'address':0xff0100,'data':actor.hex()}]})
    party={'name':'party-ammo-gate','entry':0x38ac,
      'code_ranges':[{'start':0x38ac,'end':0x38fa},{'start':0x36fc,'end':0x37d4}],
      'stop_pcs':[0x37d4,0x38f8],'stack_scratch_bytes':128,'max_instructions':100,
      'watch':[{'name':'actor','address':0xff0100,'length':160}],'cases':party_cases}
    (out/'party-contract.json').write_text(json.dumps(party))
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),
      '--rom',args.rom,'--core',args.core,'--contract',str(out/'party-contract.json'),
      '--output',str(out/'party-native')],capture_output=True,text=True,timeout=180)
    if proc.returncode: raise RuntimeError(proc.stderr[-4000:])
    party_receipt=json.loads((out/'party-native'/'receipt.json').read_text())
    if not party_receipt['complete'] or not party_receipt['inputs_unchanged']:
        raise AssertionError('incomplete party run')
    for item, original in zip(party_cases,party_receipt['cases']):
        index, weapon, ammo=map(int,item['name'].split('-'))
        machine.set_state({'shadowrun_field_actor_index':index,'shadowrun_field_item':weapon,
          'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':1,
          'shadowrun_field_ammo':ammo,'shadowrun_field_slots_busy':63,
          'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,
          'shadowrun_field_target_hp':50,'shadowrun_field_target_a':20,'shadowrun_field_target_b':20,
          'shadowrun_field_target_c':20,'shadowrun_field_target_posture':0,'shadowrun_field_source_effect':30})
        machine.call('shadowrun_field_fire')
        state=machine.snapshot()
        observed=bytes.fromhex(original['ram_after']['actor'])[0x4e]
        if not state['shadowrun_field_supported'] or state['shadowrun_field_ammo'] != observed:
            raise AssertionError(('party ammo',item['name'],state['shadowrun_field_ammo'],observed))
    if SOURCE.read_bytes() != author or Path(args.rom).read_bytes() != rom or Path(args.core).read_bytes() != core:
        raise ValueError('input changed during qualification')
    summary = {'status':'passed','cases':len(cases),'rom_sha256':sha(rom),'core_sha256':sha(core),
       'authoring_sha256':sha(author),'trace_sha256':native['trace_sha256'],
       'spawn_cases':len(spawn_cases),'spawn_trace_sha256':spawn_receipt['trace_sha256'],
       'party_ammo_cases':len(party_cases),'party_trace_sha256':party_receipt['trace_sha256'],
       'scope':'separate original spawn gate and prepared $14E6E continuation and GameIL HP/RNG; dispatcher, spawn-motion connection and target runtime excluded'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__ == '__main__':
    main()
