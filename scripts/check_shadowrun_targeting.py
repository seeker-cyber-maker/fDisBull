#!/usr/bin/env python3
"""Compare bounded prepared NPC targeting with the pinned original 68000 core."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_targeting import lift_targeting

CORE = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser()
    for name in ('rom','core','output'): p.add_argument('--'+name, required=True)
    a = p.parse_args(); rom=Path(a.rom).read_bytes(); core=Path(a.core).read_bytes()
    if sha(core) != CORE: raise ValueError('wrong original core')
    program = lift_targeting(rom)
    out = _private_directory(a.output); out.mkdir(mode=0o700)
    cases=[]; inputs=[]
    for previous, contacts, flags, b0 in [
        (255,[0,273,0],[0x25]*3,[0]*3),
        (255,[101,112,113],[0x25]*3,[0x80,0,0]),
        (1,[101,112,113],[0x25]*3,[0]*3),
        (2,[101,112,113],[0x25]*3,[0]*3),
        (255,[0,0,0],[0x25]*3,[0]*3),
        (255,[101,112,113],[0x35,0x65,0x25],[0]*3),
    ]:
        player=bytearray(256); player[0x57]=2
        if previous!=255: player[0xa2:0xa6]=(0xff0400+previous*256).to_bytes(4,'big')
        actors=[]
        for i in range(7):
            row=bytearray(256); row[0x3e:0x40]=([3,4,5,0,0,0,0][i]).to_bytes(2,'big')
            if i<3: row[0x10]=flags[i];row[0xb0]=b0[i];row[0x0c:0x0e]=contacts[i].to_bytes(2,'big')
            if i==previous:row[0x11]=0x10
            actors.append(row)
        ram=[{'address':0xff0100,'data':player.hex()}]+[
            {'address':0xff0400+256*i,'data':row.hex()} for i,row in enumerate(actors)]
        cases.append({'name':str(len(cases)),'registers':{'A0':0xff0100,'D1':0},'ram':ram})
        inputs.append((previous, contacts+[0]*4, flags+[0]*4, b0+[0]*4))
    contract={'name':'prepared-target-cycle','entry':0x1dc4c,
        'code_ranges':[{'start':0x1dc4c,'end':0x1dd2e}], 'stop_pcs':[0x1dd2c,0x1dd12],
        'stack_scratch_bytes':64,'max_instructions':300,
        'watch':[{'name':'player','address':0xff0100,'length':256},
                 {'name':'actors','address':0xff0400,'length':7*256}], 'cases':cases}
    cp=out/'contract.json';cp.write_text(json.dumps(contract))
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),
        '--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],
        capture_output=True,text=True,timeout=180)
    if proc.returncode:raise RuntimeError(proc.stderr[-4000:])
    native=json.loads((out/'native/receipt.json').read_text())
    if not native['complete'] or not native['inputs_unchanged'] or len(native['cases']) != len(cases):
        raise AssertionError('incomplete original-core run')
    comparisons=[]
    for case_index, ((previous,contacts,flags,b0),case) in enumerate(zip(inputs,native['cases'])):
        m=GameMachine(program); low=[0]*7
        if previous != 255:low[previous]=16
        m.set_state({'shadowrun_target_selected':previous,'shadowrun_target_contact':contacts,
                     'shadowrun_target_flags':flags,'shadowrun_target_flags_b0':b0,
                     'shadowrun_target_flags_low':low,'shadowrun_target_index':[3,4,5,0,0,0,0]})
        m.call('shadowrun_target_cycle'); s=m.snapshot()
        player=bytes.fromhex(case['ram_after']['player']); actors=bytes.fromhex(case['ram_after']['actors'])
        ptr=int.from_bytes(player[0xa2:0xa6],'big'); selected=255 if not ptr else (ptr-0xff0400)//256
        low_after=[actors[256*i+0x11] for i in range(7)]
        markers=[int.from_bytes(actors[256*i+0xa6:256*i+0xa8],'big') for i in range(7)]
        backlinks=[int.from_bytes(actors[256*i+0xac:256*i+0xb0],'big') != 0 for i in range(7)]
        got=(s['shadowrun_target_selected'],s['shadowrun_target_flags_low'],s['shadowrun_target_marker'],s['shadowrun_target_backlink'])
        expected=(selected,low_after,markers,backlinks)
        if s['shadowrun_target_supported'] != 1 or got != expected: raise AssertionError((got,expected))
        comparisons.append({'case':case_index,'selected_slot':selected})
    projection_cases=[]
    geometries=[(12620,8664,17024,11008,0),(21248,13330,17024,11008,0),
                (25216,5590,17024,11008,0),(0,0,256,256,0),
                (256,256,512,512,0),(16127,12031,16000,12000,3),
                (65520,65520,16,16,0)]
    geometries += [((500 + sx - 128)*16, (500 + sy - 128)*16, 8000, 8000, 0)
                   for sx,sy in ((111,200),(112,200),(429,200),(430,200),
                                  (200,98),(200,99),(200,377),(200,378))]
    for i,(x,y,cx,cy,height) in enumerate(geometries):
        row=bytearray(256);row[0:2]=x.to_bytes(2,'big');row[4:6]=y.to_bytes(2,'big')
        row[8:10]=height.to_bytes(2,'big');row[0x10]=1
        camera=cx.to_bytes(2,'big')+cy.to_bytes(2,'big')
        projection_cases.append({'name':str(i),'registers':{'A0':0xff0400},
            'ram':[{'address':0xff0400,'data':row.hex()}, {'address':0xffddc6,'data':camera.hex()}]})
    projection={'name':'prepared-camera-admission','entry':0x5a56,
        'code_ranges':[{'start':0x5a56,'end':0x5ac6}], 'stop_pcs':[0x5abc,0x5ac4],
        'stack_scratch_bytes':64,'max_instructions':100,
        'watch':[{'name':'actor','address':0xff0400,'length':256}], 'cases':projection_cases}
    pp=out/'projection-contract.json';pp.write_text(json.dumps(projection))
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),
        '--rom',a.rom,'--core',a.core,'--contract',str(pp),'--output',str(out/'projection-native')],
        capture_output=True,text=True,timeout=180)
    if proc.returncode:raise RuntimeError(proc.stderr[-4000:])
    pn=json.loads((out/'projection-native/receipt.json').read_text())
    if not pn['complete'] or not pn['inputs_unchanged'] or len(pn['cases']) != len(geometries):
        raise AssertionError('incomplete camera-admission run')
    projection_matches=[]
    for i,((x,y,cx,cy,height),case) in enumerate(zip(geometries,pn['cases'])):
        m=GameMachine(program);m.set_state({'shadowrun_camera_x':cx,'shadowrun_camera_y':cy,
          'shadowrun_target_x':[x,0,0,0,0,0,0],'shadowrun_target_y':[y,0,0,0,0,0,0],
          'shadowrun_target_height':[height,0,0,0,0,0,0], 'shadowrun_target_flags':[1,0,0,0,0,0,0]})
        m.call('shadowrun_target_refresh'); state=m.snapshot()
        actor=bytes.fromhex(case['ram_after']['actor']); expected=int.from_bytes(actor[0xc:0xe],'big')
        got=state['shadowrun_target_contact'][0]
        if got != expected:raise AssertionError(('projection',i,got,expected))
        projection_matches.append({'case':i,'contact':got})
    result={'format':'fdisbull-shadowrun-target-cycle-native-check-1','complete':True,
            'rom_sha256':sha(rom),'core_sha256':sha(core),'program_sha256':sha(canonical(program)),
            'native_receipt_sha256':sha((out/'native/receipt.json').read_bytes()),
            'cases':comparisons,'projection_cases':projection_matches,
            'projection_receipt_sha256':sha((out/'projection-native/receipt.json').read_bytes()), 'scope':'prepared original NPC target routine; no input dispatch or NPC AI'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
