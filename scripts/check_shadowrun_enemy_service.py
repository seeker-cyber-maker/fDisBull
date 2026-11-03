#!/usr/bin/env python3
"""Compare bounded captured NPC service with controlled original CPU."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_enemy_service import SOURCE, lift_enemy_service
from fdisbull.udl_shadowrun import ROM_SHA256
CORE = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b): return hashlib.sha256(b).hexdigest()
def word(b, n): return int.from_bytes(b[n:n+2], 'big')
def long(b, n): return int.from_bytes(b[n:n+4], 'big')
def main():
    p = argparse.ArgumentParser()
    for k in ('rom','core','run','output'): p.add_argument('--'+k, required=True)
    a = p.parse_args(); rom = Path(a.rom).read_bytes(); core = Path(a.core).read_bytes()
    root = Path(a.run); capraw = (root/'capture.json').read_bytes(); cap=json.loads(capraw)
    receipt=json.loads((root/'native/receipt.json').read_text()); author=SOURCE.read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or receipt['patches'] or receipt['memory_injection_mode']!='no memory patches': raise ValueError('identity or capture patches')
    cases=[]; inputs=[]
    for frame in cap['captures']:
        rel=f'native/scene-{frame:06d}/ram.bin'; raw=(root/rel).read_bytes()
        if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']: raise ValueError('RAM integrity')
        b=bytes(raw[i^1] for i in range(65536))
        for index in range(3):
            original=b[0x400+index*256:0x500+index*256]
            if word(original,14)!=11 or original[0x10]!=37 or not original[0x9e]&32: continue
            for force in (False,True):
                actor=bytearray(original)
                if force: actor[0xb6:0xb8]=b'\0\0'
                cases.append({'name':f'{frame}-{index}-{int(force)}','registers':{'A0':0xff0400}, 'ram':[{'address':0xff0400,'data':actor.hex()},{'address':0xffdd00,'data':b[0xdd00:0xe200].hex()}]})
                inputs.append((frame,index,force,b,bytes(actor)))
    spans=[(0x13904,0x139d8),(0x13e40,0x13e58),(0x13e8c,0x13e9e),(0x13ef4,0x13f76),(0x142ae,0x142ce),(0x144e8,0x144fa),(0x145a2,0x14640),(0x14c2e,0x14c56),(0x15ca4,0x15cc0),(0x15d3c,0x15dcc)]
    contract={'name':'captured-actor-service','entry':0x13904,'code_ranges':[{'start':x,'end':y} for x,y in spans], 'stop_pcs':[0x1390c,0x13918,0x13f76,0x142ce,0x13e9e,0x1461c,0x145ae,0x149c0,0x14c2a,0x1460c,0x13e56,0x13e4c], 'stack_scratch_bytes':128,'max_instructions':1000, 'watch':[{'name':'actor','address':0xff0400,'length':256}], 'cases':cases}
    out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract))
    q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
    if q.returncode: raise RuntimeError(q.stderr[-4000:])
    r=json.loads((out/'native/receipt.json').read_text()); assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
    program=lift_enemy_service(rom); m=GameMachine(program,{0:rom}); passed=0; refused=0; branches={}
    for (frame,index,force,b,actor),native in zip(inputs,r['cases']):
        w=lambda n:word(actor,n)
        m.set_state({'shadowrun_ai_x':w(0),'shadowrun_ai_y':w(4),'shadowrun_ai_kind':w(0xe),'shadowrun_ai_target_heading':w(0x34),'shadowrun_ai_distance':w(0xc8),'shadowrun_ai_collision_state':w(0xb8),'shadowrun_ai_animation':w(0x16),'shadowrun_ai_callback':long(actor,0x3a),'shadowrun_ai_flags':actor[0x10],'shadowrun_ai_equipment_flags':actor[0x9e],'shadowrun_ai_event_flags':actor[0xb0],'shadowrun_ai_combat_global':word(b,0xdf84),'shadowrun_ai_service_timer':w(0xb6),'shadowrun_ai_service_contact':w(0xc),'shadowrun_ai_waypoint_x':w(0x96),'shadowrun_ai_waypoint_y':w(0x98),'shadowrun_ai_service_direction':actor[0xb1], 'shadowrun_ai_service_pause':b[0xe175]})
        m.call('shadowrun_ai_service_tick');s=m.snapshot();pc=native['registers_after']['PC']
        if not s['shadowrun_ai_service_supported']: refused+=1;continue
        if pc not in (0x1390c, 0x1460c, 0x13e56, 0x13e4c, 0x145ae): raise AssertionError(('accepted unmodeled exit',hex(pc)))
        after=bytes.fromhex(native['ram_after']['actor']);w2=lambda n:word(after,n)
        got=tuple(s[k] for k in ('shadowrun_ai_service_timer','shadowrun_ai_target_heading','shadowrun_ai_distance','shadowrun_ai_callback','shadowrun_ai_event_flags','shadowrun_ai_service_direction'))
        expected=(w2(0xb6),w2(0x34),w2(0xc8),long(after,0x3a),after[0xb0],after[0xb1])
        if got!=expected: raise AssertionError((frame,index,force,hex(pc),got,expected))
        passed+=1; key=hex(pc);branches[key]=branches.get(key,0)+1
    if SOURCE.read_bytes()!=author: raise ValueError('authoring changed')
    summary={'status':'passed','source_states':len(cases),'matched':passed,'refused':refused,'matched_terminal_pcs':branches,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(program)),'trace_sha256':r['trace_sha256'],'scope':'captured scheduler countdown and admitted contact-zero service branches, with controlled zero-timer interventions; other branches refused'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
