#!/usr/bin/env python3
"""Check one assisted camera state with captured records against original leaves."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_replay import _source_capture
from fdisbull.shadowrun_targeting import lift_targeting
from fdisbull.shadowrun_world import SOURCE_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def run(args, contract, path):
 path.parent.joinpath(path.name+'-contract.json').write_text(json.dumps(contract))
 cp=path.parent/(path.name+'-contract.json')
 p=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',args.rom,'--core',args.core,'--contract',str(cp),'--output',str(path)],capture_output=True,text=True,timeout=180)
 if p.returncode:raise RuntimeError(p.stderr[-4000:])
 data=json.loads((path/'receipt.json').read_text())
 if not data['complete'] or not data['inputs_unchanged']:raise ValueError('incomplete original probe')
 return data

def main():
 p=argparse.ArgumentParser()
 for x in ('rom','core','capture','output'):p.add_argument('--'+x,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes()
 if sha(rom)!=SOURCE_SHA256 or sha(core)!=CORE:raise ValueError('wrong source or core')
 identity, arrays, _=_source_capture(a.capture,SOURCE_SHA256)
 if identity['frame']!=5999 or identity['capture_json_sha256']!='b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':raise ValueError('wrong capture')
 raw=arrays['ram'];mem=bytes(raw[i^1] for i in range(len(raw)));player=bytearray(mem[0x100:0x200]);actors=[bytearray(mem[0x400+256*i:0x500+256*i]) for i in range(7)]
 cx,cy=17024,11328;camera=cx.to_bytes(2,'big')+cy.to_bytes(2,'big')
 if int.from_bytes(player[0xa2:0xa6],'big') or int.from_bytes(player[0xac:0xb0],'big'):raise ValueError('capture has existing target')
 out=_private_directory(a.output);out.mkdir(mode=0o700)
 active=[i for i,row in enumerate(actors) if row[0x10]&1]
 projection={'name':'captured-npc-camera','entry':0x5a56,'code_ranges':[{'start':0x5a56,'end':0x5ac6}],
  'stop_pcs':[0x5abc,0x5ac4],'stack_scratch_bytes':64,'max_instructions':100,
  'watch':[{'name':'actor','address':0xff0400,'length':256}],
  'cases':[{'name':str(i),'registers':{'A0':0xff0400},'ram':[{'address':0xff0400,'data':actors[i].hex()},{'address':0xffddc6,'data':camera.hex()}]} for i in active]}
 pr=run(a,projection,out/'projection-native')
 for i,case in zip(active,pr['cases']):actors[i][:]=bytes.fromhex(case['ram_after']['actor'])
 contacts=[int.from_bytes(row[12:14],'big') for row in actors]
 contract={'name':'captured-npc-target','entry':0x1dc4c,'code_ranges':[{'start':0x1dc4c,'end':0x1dd2e}],
  'stop_pcs':[0x1dd2c,0x1dd12],'stack_scratch_bytes':64,'max_instructions':300,
  'watch':[{'name':'player','address':0xff0100,'length':256},{'name':'actors','address':0xff0400,'length':7*256}],
  'cases':[{'name':'captured','registers':{'A0':0xff0100,'D1':0},'ram':[{'address':0xff0100,'data':player.hex()}]+[{'address':0xff0400+i*256,'data':row.hex()} for i,row in enumerate(actors)]}]}
 nr=run(a,contract,out/'target-native');case=nr['cases'][0];actualp=bytes.fromhex(case['ram_after']['player']);actuala=bytes.fromhex(case['ram_after']['actors']);ptr=int.from_bytes(actualp[0xa2:0xa6],'big')
 m=GameMachine(lift_targeting(rom));w=lambda row,n:int.from_bytes(row[n:n+2],'big')
 m.set_state({'shadowrun_camera_x':cx,'shadowrun_camera_y':cy,'shadowrun_target_x':[w(x,0) for x in actors],
 'shadowrun_target_y':[w(x,4) for x in actors],'shadowrun_target_height':[w(x,8) for x in actors],
 'shadowrun_target_index':[w(x,0x3e) for x in actors],'shadowrun_target_flags':[x[0x10] for x in actors],
 'shadowrun_target_flags_low':[x[0x11] for x in actors],'shadowrun_target_flags_b0':[x[0xb0] for x in actors],
 'shadowrun_target_contact':contacts,'shadowrun_target_item':player[0x57],'shadowrun_target_equipped_slot':player[0x56]})
 m.call('shadowrun_target_refresh');s=m.snapshot()
 if s['shadowrun_target_contact']!=contacts:raise AssertionError(('projection',s['shadowrun_target_contact'],contacts))
 m.call('shadowrun_target_cycle');s=m.snapshot();slot=255 if ptr==0 else (ptr-0xff0400)//256
 low=[actuala[i*256+0x11] for i in range(7)];markers=[int.from_bytes(actuala[i*256+0xa6:i*256+0xa8],'big') for i in range(7)]
 back=[int.from_bytes(actuala[i*256+0xac:i*256+0xb0],'big') for i in range(7)]
 expected=(slot,low,markers,[int(x==0xff0100) for x in back]);got=(s['shadowrun_target_selected'],s['shadowrun_target_flags_low'],s['shadowrun_target_marker'],s['shadowrun_target_backlink'])
 if expected!=got or ptr!=0xff0500 or contacts[1]!=253:raise AssertionError((expected,got,ptr,contacts))
 result={'format':'fdisbull-shadowrun-captured-target-camera-check-1','complete':True,'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_receipt_sha256':identity['capture_json_sha256'],'program_sha256':sha(canonical(lift_targeting(rom))),
 'projection_receipt_sha256':sha((out/'projection-native/receipt.json').read_bytes()),'target_receipt_sha256':sha((out/'target-native/receipt.json').read_bytes()),'camera_fixed':[cx,cy], 'contacts':contacts,'selected_address':ptr,'selected_slot':slot,'selected_flags_low':low[slot],'selected_marker':markers[slot],'selected_backlink':back[slot], 'scope':'source-captured actors with assisted camera and prepared original leaf calls; no B-input or NPC AI claim'}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
